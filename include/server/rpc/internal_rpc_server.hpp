#ifndef INTERNAL_RPC_SERVER_H
#define INTERNAL_RPC_SERVER_H

#include <muduo/net/TcpServer.h>
#include <muduo/net/EventLoop.h>
#include <functional>
#include <string>
#include <mutex>

using namespace muduo;
using namespace muduo::net;

class InternalRpcServer {
public:
    typedef std::function<void(int receiverId, int64_t groupId,
                                int msgType, const std::string& payloadJson,
                                bool broadcast)> PushCallback;

    InternalRpcServer(EventLoop* loop, const InetAddress& listenAddr);

    void start();
    void setPushCallback(PushCallback cb);

private:
    void onConnection(const TcpConnectionPtr& conn);
    void onMessage(const TcpConnectionPtr& conn, Buffer* buf, Timestamp time);

    void handlePushRequest(const TcpConnectionPtr& conn,
                           const std::string& serviceName,
                           const std::string& methodName,
                           int64_t rpcId,
                           const std::string& payload);

    TcpServer server_;
    PushCallback pushCallback_;
    std::mutex mutex_;
};

typedef std::shared_ptr<InternalRpcServer> InternalRpcServerPtr;

#endif
