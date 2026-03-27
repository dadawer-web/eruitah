#ifndef AI_SERVICE_CLIENT_HPP
#define AI_SERVICE_CLIENT_HPP

#include <string>
#include <functional>
#include <memory>
#include <thread>
#include <mutex>
#include <unordered_map>
#include <json.hpp>

using json = nlohmann::json;

struct AiChatSession {
    std::string sessionId;
    std::string lastResponse;
};

class AiServiceClient {
public:
    static AiServiceClient& instance();
    
    std::string chat(const std::string& message, int userId, const std::string& userName);
    
    void chatAsync(const std::string& message, int userId, const std::string& userName,
                   std::function<void(const std::string&)> callback);
    
    void streamChat(const std::string& message, int userId, const std::string& userName,
                   std::function<void(const std::string&)> callback);
    
    void streamChatWithSession(const std::string& message, int userId, const std::string& userName,
                               const std::string& sessionId,
                               std::function<void(const std::string&, const std::string&)> callback);
    
    void setServiceUrl(const std::string& url);
    
    bool isAvailable() const;
    
    std::string getSessionId(int userId);
    void clearSession(int userId);
    
private:
    AiServiceClient();
    ~AiServiceClient() = default;
    
    AiServiceClient(const AiServiceClient&) = delete;
    AiServiceClient& operator=(const AiServiceClient&) = delete;
    
    std::string sendRequest(const std::string& requestBody);
    
    std::string _serviceUrl;
    bool _available;
    std::mutex _sessionMutex;
    std::unordered_map<int, AiChatSession> _userSessions;
    static constexpr int AI_BOT_ID = 100;
};

#endif
