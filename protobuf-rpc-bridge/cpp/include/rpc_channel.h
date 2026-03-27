#ifndef RPC_CHANNEL_H
#define RPC_CHANNEL_H

#include <muduo/net/TcpClient.h>
#include <muduo/net/TcpConnection.h>
#include <muduo/net/EventLoop.h>
#include <google/protobuf/service.h>
#include <google/protobuf/descriptor.h>
#include <map>
#include <mutex>
#include <memory>

using namespace muduo;
using namespace muduo::net;

class RpcChannel : public google::protobuf::RpcChannel {
public:
    RpcChannel(EventLoop* loop, const InetAddress& serverAddr);
    ~RpcChannel() override;

    void CallMethod(const google::protobuf::MethodDescriptor* method,
                    google::protobuf::RpcController* controller,
                    const google::protobuf::Message* request,
                    google::protobuf::Message* response,
                    google::protobuf::Closure* done) override;

    void connect();
    void disconnect();

    bool connected() const { return conn_ && conn_->connected(); }

private:
    void onConnection(const TcpConnectionPtr& conn);
    void onMessage(const TcpConnectionPtr& conn, Buffer* buf, Timestamp time);

    struct OutstandingCall {
        google::protobuf::Message* response;
        google::protobuf::Closure* done;
    };

    TcpClient client_;
    TcpConnectionPtr conn_;
    std::mutex mutex_;
    std::map<int64_t, OutstandingCall> outstandingCalls_;
    int64_t id_;
};

typedef std::shared_ptr<RpcChannel> RpcChannelPtr;

#endif
