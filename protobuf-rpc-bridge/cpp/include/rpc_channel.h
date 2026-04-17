#ifndef RPC_CHANNEL_H
#define RPC_CHANNEL_H

#include <muduo/net/TcpClient.h>
#include <muduo/net/TcpConnection.h>
#include <muduo/net/EventLoop.h>
#include <google/protobuf/message.h>
#include <map>
#include <mutex>
#include <memory>
#include <functional>

using namespace muduo;
using namespace muduo::net;

class RpcChannel {
public:
    typedef std::function<void(std::shared_ptr<google::protobuf::Message>)> ResponseCallback;

    RpcChannel(EventLoop* loop, const InetAddress& serverAddr);
    ~RpcChannel();

    void callMethod(const std::string& serviceName,
                    const std::string& methodName,
                    const google::protobuf::Message& request,
                    std::shared_ptr<google::protobuf::Message> response,
                    ResponseCallback done);

    void connect();
    void disconnect();

    bool connected() const { return conn_ && conn_->connected(); }

private:
    void onConnection(const TcpConnectionPtr& conn);
    void onMessage(const TcpConnectionPtr& conn, Buffer* buf, Timestamp time);

    struct OutstandingCall {
        std::shared_ptr<google::protobuf::Message> response;
        ResponseCallback done;
    };

    TcpClient client_;
    TcpConnectionPtr conn_;
    std::mutex mutex_;
    std::map<int64_t, OutstandingCall> outstandingCalls_;
    int64_t id_;
};

typedef std::shared_ptr<RpcChannel> RpcChannelPtr;

#endif
