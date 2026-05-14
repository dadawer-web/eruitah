#ifndef AI_SERVICE_CLIENT_HPP
#define AI_SERVICE_CLIENT_HPP

#include <string>
#include <functional>
#include <memory>
#include <mutex>
#include <unordered_map>
#include "proto/chat.pb.h"

struct AiChatSession {
    std::string sessionId;
    std::string lastResponse;
};

class InternalRpcClient;

class AiServiceClient {
public:
    static AiServiceClient& instance();

    void setRpcClient(std::shared_ptr<InternalRpcClient> rpcClient);

    void chat(int userId, int botId, const std::string& userName,
              const std::string& message,
              std::function<void(bool, const std::string&, const std::string&)> callback);

    void streamChat(int userId, int botId, const std::string& userName,
                    const std::string& message,
                    std::function<void(const std::string&)> onChunk,
                    std::function<void()> onEnd,
                    std::function<void(const std::string&)> onError);

    void voiceChat(int userId, int botId, const std::string& userName,
                   const std::string& voiceUrl, int voiceDuration,
                   std::function<void(bool, const std::string&, const std::string&)> callback);

    std::string getSessionId(int userId);
    void clearSession(int userId);
    bool isAvailable() const;

private:
    AiServiceClient() = default;
    ~AiServiceClient() = default;

    AiServiceClient(const AiServiceClient&) = delete;
    AiServiceClient& operator=(const AiServiceClient&) = delete;

    std::shared_ptr<InternalRpcClient> rpcClient_;
    std::mutex sessionMutex_;
    std::unordered_map<int, AiChatSession> userSessions_;
};

#endif
