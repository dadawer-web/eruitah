#include "ai_service_client.hpp"
#include "internal_rpc_client.hpp"
#include "json.hpp"
#include <muduo/base/Logging.h>

using json = nlohmann::json;

AiServiceClient& AiServiceClient::instance() {
    static AiServiceClient client;
    return client;
}

void AiServiceClient::setRpcClient(std::shared_ptr<InternalRpcClient> rpcClient) {
    rpcClient_ = rpcClient;
    LOG_INFO << "[AiRpc] AiServiceClient bound to InternalRpcClient";
}

void AiServiceClient::chat(int userId, int botId, const std::string& userName,
                            const std::string& message,
                            std::function<void(bool, const std::string&, const std::string&)> callback) {
    if (!rpcClient_ || !rpcClient_->connected()) {
        LOG_ERROR << "[AiRpc] Not connected to Java backend";
        if (callback) callback(false, "", "RPC not connected");
        return;
    }

    json payload;
    payload["userId"] = userId;
    payload["botId"] = botId;
    payload["userName"] = userName;
    payload["message"] = message;

    rpcClient_->forwardToJava(userId, userId, 0,
        static_cast<int>(bridge::InternalMsgType::CHAT_PRIVATE),
        payload.dump(),
        "chat_" + std::to_string(userId),
        [callback](const std::string& svc, const std::string& method,
                   bool success, const std::string& error) {
            if (callback) callback(success, success ? "ok" : "", error);
        });
}

void AiServiceClient::streamChat(int userId, int botId, const std::string& userName,
                                  const std::string& message,
                                  std::function<void(const std::string&)> onChunk,
                                  std::function<void()> onEnd,
                                  std::function<void(const std::string&)> onError) {
    if (!rpcClient_ || !rpcClient_->connected()) {
        LOG_ERROR << "[AiRpc] Not connected to Java backend for stream";
        if (onError) onError("RPC not connected");
        return;
    }

    json payload;
    payload["userId"] = userId;
    payload["botId"] = botId;
    payload["userName"] = userName;
    payload["message"] = message;

    {
        std::lock_guard<std::mutex> lock(sessionMutex_);
        auto it = userSessions_.find(userId);
        if (it != userSessions_.end() && !it->second.sessionId.empty()) {
            payload["sessionId"] = it->second.sessionId;
        }
    }

    rpcClient_->forwardToJava(userId, userId, 0,
        static_cast<int>(bridge::InternalMsgType::CHAT_PRIVATE),
        payload.dump(),
        "stream_" + std::to_string(userId),
        [onChunk, onEnd, onError](const std::string& svc, const std::string& method,
                                   bool success, const std::string& error) {
            if (success) {
                if (onChunk) onChunk("ok");
                if (onEnd) onEnd();
            } else {
                if (onError) onError(error);
            }
        });
}

void AiServiceClient::voiceChat(int userId, int botId, const std::string& userName,
                                 const std::string& voiceUrl, int voiceDuration,
                                 std::function<void(bool, const std::string&, const std::string&)> callback) {
    if (!rpcClient_ || !rpcClient_->connected()) {
        LOG_ERROR << "[AiRpc] Not connected to Java backend for voice";
        if (callback) callback(false, "", "RPC not connected");
        return;
    }

    json payload;
    payload["userId"] = userId;
    payload["botId"] = botId;
    payload["userName"] = userName;
    payload["voiceUrl"] = voiceUrl;
    payload["duration"] = voiceDuration;

    rpcClient_->forwardToJava(userId, userId, 0,
        static_cast<int>(bridge::InternalMsgType::VOICE_CHAT),
        payload.dump(),
        "voice_" + std::to_string(userId),
        [callback](const std::string& svc, const std::string& method,
                   bool success, const std::string& error) {
            if (callback) callback(success, success ? "ok" : "", error);
        });
}

void AiServiceClient::groupChat(int64_t groupId, int senderId, const std::string& senderName,
                                 const std::string& content,
                                 const std::vector<int32_t>& aiBotIds,
                                 std::function<void(bool, const std::string&)> callback) {
    if (!rpcClient_ || !rpcClient_->connected()) {
        LOG_ERROR << "[AiRpc] Not connected to Java backend for group chat";
        if (callback) callback(false, "RPC not connected");
        return;
    }

    json payload;
    payload["groupId"] = groupId;
    payload["senderId"] = senderId;
    payload["senderName"] = senderName;
    payload["content"] = content;
    payload["aiBotIds"] = aiBotIds;

    rpcClient_->forwardToJava(senderId, 0, groupId,
        static_cast<int>(bridge::InternalMsgType::CHAT_GROUP),
        payload.dump(),
        "grp_" + std::to_string(groupId),
        [callback](const std::string& svc, const std::string& method,
                   bool success, const std::string& error) {
            if (callback) callback(success, error);
        });
}

void AiServiceClient::farmAnswer(int userId, int plotId, int ownerId,
                                  const std::string& question, const std::string& answer,
                                  std::function<void(bool, const std::string&)> callback) {
    if (!rpcClient_ || !rpcClient_->connected()) {
        LOG_ERROR << "[AiRpc] Not connected to Java backend for farm answer";
        if (callback) callback(false, "RPC not connected");
        return;
    }

    json payload;
    payload["action"] = "answer";
    payload["userid"] = userId;
    payload["plotid"] = plotId;
    payload["ownerid"] = ownerId;
    payload["question"] = question;
    payload["answer"] = answer;

    rpcClient_->forwardToJava(userId, 0, 0,
        static_cast<int>(bridge::InternalMsgType::AI_GRADE_RESULT),
        payload.dump(),
        "farm_" + std::to_string(plotId),
        [callback](const std::string& svc, const std::string& method,
                   bool success, const std::string& error) {
            if (callback) callback(success, error);
        });
}

std::string AiServiceClient::getSessionId(int userId) {
    std::lock_guard<std::mutex> lock(sessionMutex_);
    auto it = userSessions_.find(userId);
    if (it != userSessions_.end()) {
        return it->second.sessionId;
    }
    return "";
}

void AiServiceClient::clearSession(int userId) {
    std::lock_guard<std::mutex> lock(sessionMutex_);
    userSessions_.erase(userId);
    LOG_INFO << "[AiRpc] Cleared session for userId=" << userId;
}

bool AiServiceClient::isAvailable() const {
    return rpcClient_ && rpcClient_->connected();
}
