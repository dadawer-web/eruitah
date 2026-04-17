#ifndef CHAT_SERVER_H
#define CHAT_SERVER_H

#include <muduo/net/TcpServer.h>
#include <muduo/net/EventLoop.h>
#include <muduo/base/ThreadPool.h>
#include "rpc_channel.h"
#include "chat.pb.h"
#include <memory>
#include <unordered_map>
#include <mutex>

using namespace muduo;
using namespace muduo::net;

class ChatServer {
public:
    ChatServer(EventLoop* loop,
               const InetAddress& listenAddr,
               const InetAddress& javaBackendAddr);

    void start();
    void setThreadNum(int numThreads);

private:
    void onClientConnection(const TcpConnectionPtr& conn);
    void onClientMessage(const TcpConnectionPtr& conn, Buffer* buf, Timestamp time);

    void handleChatRequest(const TcpConnectionPtr& conn,
                           const std::shared_ptr<bridge::ChatRequest>& request);
    void handleGroupChatRequest(const TcpConnectionPtr& conn,
                                const std::shared_ptr<bridge::GroupChatRequest>& request);

    TcpServer server_;
    RpcChannelPtr rpcChannel_;
    ThreadPool threadPool_;

    std::mutex mutex_;
    std::unordered_map<std::string, TcpConnectionPtr> clientConnections_;
};

#endif
