#ifndef INTERNAL_RPC_CLIENT_H
#define INTERNAL_RPC_CLIENT_H

#include <muduo/net/EventLoop.h>
#include <muduo/net/TcpClient.h>
#include <muduo/net/TcpConnection.h>
#include <google/protobuf/message.h>
#include <functional>
#include <map>
#include <mutex>
#include <memory>
#include <string>

using namespace muduo;
using namespace muduo::net;

class InternalRpcClient {
public:
    typedef std::function<void(const std::string& serviceName,
                                const std::string& methodName,
                                bool success,
                                const std::string& error)> RpcCallback;

    InternalRpcClient(EventLoop* loop, const InetAddress& javaAddr);
    ~InternalRpcClient();

    void connect();
    void disconnect();
    bool connected() const;

    void forwardToJava(int senderId, int receiverId, int64_t groupId,
                       int msgType, const std::string& payloadJson,
                       const std::string& traceId,
                       RpcCallback callback = nullptr);

private:
    void onConnection(const TcpConnectionPtr& conn);
    void onMessage(const TcpConnectionPtr& conn, Buffer* buf, Timestamp time);

    void sendRpcMessage(const std::string& serviceName,
                        const std::string& methodName,
                        const google::protobuf::Message& request,
                        std::shared_ptr<google::protobuf::Message> response,
                        RpcCallback callback);

    struct PendingCall {
        std::shared_ptr<google::protobuf::Message> response;
        RpcCallback callback;
        std::string serviceName;
        std::string methodName;
    };

    TcpClient client_;
    TcpConnectionPtr conn_;
    mutable std::mutex mutex_;
    std::map<int64_t, PendingCall> pendingCalls_;
    int64_t id_;
};

typedef std::shared_ptr<InternalRpcClient> InternalRpcClientPtr;

#endif
