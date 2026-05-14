#include "ai_service_client.hpp"
#include "internal_rpc_client.hpp"
#include <muduo/base/Logging.h>

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

    bridge::ChatRequest request;
    request.set_user_id(userId);
    request.set_bot_id(botId);
    request.set_user_name(userName);
    request.set_message(message);
    request.set_timestamp(muduo::Timestamp::now().microSecondsSinceEpoch() / 1000);

    {
        std::lock_guard<std::mutex> lock(sessionMutex_);
        auto it = userSessions_.find(userId);
        if (it != userSessions_.end() && !it->second.sessionId.empty()) {
            request.set_session_id(it->second.sessionId);
        }
    }

    rpcClient_->forwardToJava(userId, userId, 0,
        static_cast<int>(bridge::InternalMsgType::CHAT_PRIVATE),
        request.SerializeAsString(),
        "chat_" + std::to_string(userId),
        [this, userId, callback](const std::string& svc, const std::string& method,
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

    bridge::ChatRequest request;
    request.set_user_id(userId);
    request.set_bot_id(botId);
    request.set_user_name(userName);
    request.set_message(message);
    request.set_timestamp(muduo::Timestamp::now().microSecondsSinceEpoch() / 1000);

    {
        std::lock_guard<std::mutex> lock(sessionMutex_);
        auto it = userSessions_.find(userId);
        if (it != userSessions_.end() && !it->second.sessionId.empty()) {
            request.set_session_id(it->second.sessionId);
        }
    }

    rpcClient_->forwardToJava(userId, userId, 0,
        static_cast<int>(bridge::InternalMsgType::CHAT_PRIVATE),
        request.SerializeAsString(),
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

    bridge::ChatRequest request;
    request.set_user_id(userId);
    request.set_bot_id(botId);
    request.set_user_name(userName);
    request.set_voice_url(voiceUrl);
    request.set_voice_duration(voiceDuration);
    request.set_timestamp(muduo::Timestamp::now().microSecondsSinceEpoch() / 1000);

    rpcClient_->forwardToJava(userId, userId, 0,
        static_cast<int>(bridge::InternalMsgType::VOICE_CHAT),
        request.SerializeAsString(),
        "voice_" + std::to_string(userId),
        [this, userId, callback](const std::string& svc, const std::string& method,
                                  bool success, const std::string& error) {
            if (callback) callback(success, success ? "ok" : "", error);
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
