#include "ai_service_client.hpp"
#include <curl/curl.h>
#include <curl/multi.h>
#include <muduo/base/Logging.h>
#include <sstream>
#include <regex>

namespace {
    size_t WriteCallback(void* contents, size_t size, size_t nmemb, void* userp) {
        ((std::string*)userp)->append((char*)contents, size * nmemb);
        return size * nmemb;
    }

    struct StreamContext {
        std::string buffer;
        std::function<void(const std::string&, const std::string&)> callback;
        std::string sessionId;
        bool done;
        
        StreamContext() : done(false) {}
    };

    size_t StreamWriteCallback(void* contents, size_t size, size_t nmemb, void* userp) {
        size_t realsize = size * nmemb;
        StreamContext* ctx = (StreamContext*)userp;
        ctx->buffer.append((char*)contents, realsize);

        LOG_DEBUG << "StreamWriteCallback received " << realsize << " bytes, buffer size: " << ctx->buffer.size();

        size_t pos;
        while ((pos = ctx->buffer.find("\n\n")) != std::string::npos) {
            std::string line = ctx->buffer.substr(0, pos);
            ctx->buffer.erase(0, pos + 2);

            while (!line.empty() && (line.back() == '\r' || line.back() == '\n')) {
                line.pop_back();
            }

            if (line.empty()) {
                continue;
            }

            LOG_DEBUG << "Processing line: " << line;

            if (line.find("[SESSION:") == 0) {
                size_t start = 9;
                size_t end = line.find("]");
                if (end != std::string::npos) {
                    ctx->sessionId = line.substr(start, end - start);
                    LOG_INFO << "Received sessionId: " << ctx->sessionId;
                }
                continue;
            }

            if (line == "[DONE]" || line == "[STREAM_END]") {
                ctx->done = true;
                LOG_INFO << "Stream end marker received";
                continue;
            }

            if (!line.empty()) {
                ctx->callback(ctx->sessionId, line);
            }
        }

        return realsize;
    }
}

AiServiceClient& AiServiceClient::instance() {
    static AiServiceClient client;
    return client;
}

AiServiceClient::AiServiceClient()
    : _serviceUrl("http://localhost:8081/api/ai/chat"), _available(false) {
    LOG_INFO << "AiServiceClient initialized with URL: " << _serviceUrl;
}

std::string AiServiceClient::sendRequest(const std::string& requestBody) {
    CURL* curl = curl_easy_init();
    if (!curl) {
        LOG_ERROR << "Failed to initialize CURL";
        _available = false;
        return "";
    }

    std::string readBuffer;
    struct curl_slist* headers = NULL;

    headers = curl_slist_append(headers, "Content-Type: application/json");

    curl_easy_setopt(curl, CURLOPT_URL, _serviceUrl.c_str());
    curl_easy_setopt(curl, CURLOPT_POST, 1L);
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, requestBody.c_str());
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteCallback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &readBuffer);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 30L);
    curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 5L);

    CURLcode res = curl_easy_perform(curl);

    if (res != CURLE_OK) {
        LOG_ERROR << "curl_easy_perform() failed: " << curl_easy_strerror(res);
        _available = false;
        curl_slist_free_all(headers);
        curl_easy_cleanup(curl);
        return "";
    }

    long response_code;
    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &response_code);

    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);

    _available = (response_code == 200);

    if (!_available) {
        LOG_ERROR << "AI service returned status code: " << response_code;
        return "";
    }

    return readBuffer;
}

std::string AiServiceClient::getSessionId(int userId) {
    std::lock_guard<std::mutex> lock(_sessionMutex);
    auto it = _userSessions.find(userId);
    if (it != _userSessions.end()) {
        return it->second.sessionId;
    }
    return "";
}

void AiServiceClient::clearSession(int userId) {
    std::lock_guard<std::mutex> lock(_sessionMutex);
    _userSessions.erase(userId);
    LOG_INFO << "Cleared session for userId: " << userId;
}

std::string AiServiceClient::chat(const std::string& message, int userId, const std::string& userName) {
    json requestJson;
    requestJson["message"] = message;
    requestJson["userId"] = userId;
    requestJson["userName"] = userName;
    
    std::string sessionId = getSessionId(userId);
    if (!sessionId.empty()) {
        requestJson["sessionId"] = sessionId;
    }

    std::string requestBody = requestJson.dump();
    LOG_INFO << "Sending request to AI service: " << requestBody;

    std::string response = sendRequest(requestBody);

    if (response.empty()) {
        LOG_ERROR << "Empty response from AI service";
        return "Sorry, AI service is temporarily unavailable. Please try again later.";
    }

    try {
        json responseJson = json::parse(response);

        if (responseJson.contains("success") && responseJson["success"].get<bool>()) {
            if (responseJson.contains("sessionId")) {
                std::lock_guard<std::mutex> lock(_sessionMutex);
                _userSessions[userId].sessionId = responseJson["sessionId"].get<std::string>();
                LOG_INFO << "Updated sessionId for userId " << userId << ": " << _userSessions[userId].sessionId;
            }
            
            if (responseJson.contains("message")) {
                return responseJson["message"].get<std::string>();
            }
        } else {
            std::string error = responseJson.value("error", "Unknown error");
            LOG_ERROR << "AI service error: " << error;
            return "Sorry, AI service returned an error: " + error;
        }
    } catch (const json::exception& e) {
        LOG_ERROR << "Failed to parse AI service response: " << e.what();
        return "Sorry, AI service returned data format error.";
    }

    return "Sorry, AI service returned unexpected response.";
}

void AiServiceClient::chatAsync(const std::string& message, int userId, const std::string& userName,
                                 std::function<void(const std::string&)> callback) {
    std::thread([this, message, userId, userName, callback]() {
        std::string response = chat(message, userId, userName);
        callback(response);
    }).detach();
}

void AiServiceClient::streamChat(const std::string& message, int userId, const std::string& userName,
                                  std::function<void(const std::string&)> callback) {
    std::string sessionId = getSessionId(userId);
    
    streamChatWithSession(message, userId, userName, sessionId, 
        [this, userId, callback](const std::string& sid, const std::string& content) {
            if (!sid.empty()) {
                std::lock_guard<std::mutex> lock(_sessionMutex);
                _userSessions[userId].sessionId = sid;
            }
            callback(content);
        });
}

void AiServiceClient::streamChatWithSession(const std::string& message, int userId, const std::string& userName,
                                             const std::string& sessionId,
                                             std::function<void(const std::string&, const std::string&)> callback) {
    std::thread([this, message, userId, userName, sessionId, callback]() {
        CURLM* multi = curl_multi_init();
        if (!multi) {
            LOG_ERROR << "Failed to initialize CURLM";
            callback("", "Failed to initialize CURLM");
            return;
        }

        CURL* curl = curl_easy_init();
        if (!curl) {
            LOG_ERROR << "Failed to initialize CURL";
            curl_multi_cleanup(multi);
            callback("", "Failed to initialize CURL");
            return;
        }

        char* encodedMessage = curl_easy_escape(curl, message.c_str(), message.length());
        if (!encodedMessage) {
            LOG_ERROR << "Failed to URL encode message";
            curl_easy_cleanup(curl);
            curl_multi_cleanup(multi);
            callback("", "Failed to URL encode message");
            return;
        }

        std::string encodedMessageStr(encodedMessage);
        curl_free(encodedMessage);

        std::string streamUrl = "http://localhost:8081/api/ai/stream-chat?message=" + encodedMessageStr;
        if (!sessionId.empty()) {
            char* encodedSessionId = curl_easy_escape(curl, sessionId.c_str(), sessionId.length());
            if (encodedSessionId) {
                streamUrl += "&sessionId=" + std::string(encodedSessionId);
                curl_free(encodedSessionId);
            }
        }
        LOG_INFO << "Stream URL: " << streamUrl;

        StreamContext ctx;
        ctx.callback = callback;

        struct curl_slist* headers = NULL;
        headers = curl_slist_append(headers, "Accept: text/plain");

        curl_easy_setopt(curl, CURLOPT_URL, streamUrl.c_str());
        curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
        curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, StreamWriteCallback);
        curl_easy_setopt(curl, CURLOPT_WRITEDATA, &ctx);
        curl_easy_setopt(curl, CURLOPT_TIMEOUT, 120L);
        curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 5L);

        curl_multi_add_handle(multi, curl);

        int still_running = 1;
        CURLMcode mc = curl_multi_perform(multi, &still_running);

        if (mc != CURLM_OK) {
            LOG_ERROR << "curl_multi_perform failed: " << mc;
        }

        while (still_running && !ctx.done) {
            int numfds = 0;
            mc = curl_multi_wait(multi, NULL, 0, 100, &numfds);
            if (mc != CURLM_OK) {
                LOG_ERROR << "curl_multi_wait failed: " << mc;
                break;
            }
            mc = curl_multi_perform(multi, &still_running);
            if (mc != CURLM_OK) {
                LOG_ERROR << "curl_multi_perform failed in loop: " << mc;
                break;
            }
        }

        if (!ctx.sessionId.empty()) {
            std::lock_guard<std::mutex> lock(_sessionMutex);
            _userSessions[userId].sessionId = ctx.sessionId;
            LOG_INFO << "Saved sessionId for userId " << userId << ": " << ctx.sessionId;
        }

        curl_multi_remove_handle(multi, curl);
        curl_easy_cleanup(curl);
        curl_slist_free_all(headers);
        curl_multi_cleanup(multi);

        callback(ctx.sessionId, "[STREAM_END]");
        LOG_INFO << "Stream completed for userId " << userId;
    }).detach();
}

void AiServiceClient::setServiceUrl(const std::string& url) {
    _serviceUrl = url;
}

bool AiServiceClient::isAvailable() const {
    return _available;
}
