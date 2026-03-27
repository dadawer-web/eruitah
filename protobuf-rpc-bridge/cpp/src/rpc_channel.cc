#include "rpc_channel.h"
#include "protobuf_codec.h"
#include "chat.pb.h"
#include <muduo/base/Logging.h>

using namespace muduo;
using namespace muduo::net;

RpcChannel::RpcChannel(EventLoop* loop, const InetAddress& serverAddr)
    : client_(loop, serverAddr, "RpcChannel"),
      id_(0) {
    client_.setConnectionCallback(
        std::bind(&RpcChannel::onConnection, this, _1));
    client_.setMessageCallback(
        std::bind(&RpcChannel::onMessage, this, _1, _2, _3));
}

RpcChannel::~RpcChannel() {
    disconnect();
}

void RpcChannel::CallMethod(const google::protobuf::MethodDescriptor* method,
                             google::protobuf::RpcController* controller,
                             const google::protobuf::Message* request,
                             google::protobuf::Message* response,
                             google::protobuf::Closure* done) {
    if (!connected()) {
        LOG_ERROR << "Not connected to Java backend";
        if (done) {
            done->Run();
        }
        return;
    }

    bridge::RpcMessage rpcMessage;
    rpcMessage.set_type(bridge::RpcMessage::REQUEST);
    
    {
        std::lock_guard<std::mutex> lock(mutex_);
        rpcMessage.set_id(++id_);
    }
    
    rpcMessage.set_service_name(method->service()->name());
    rpcMessage.set_method_name(method->name());
    
    std::string serialized;
    if (!request->SerializeToString(&serialized)) {
        LOG_ERROR << "Failed to serialize request";
        if (done) {
            done->Run();
        }
        return;
    }
    rpcMessage.set_payload(serialized);

    {
        std::lock_guard<std::mutex> lock(mutex_);
        OutstandingCall call;
        call.response = response;
        call.done = done;
        outstandingCalls_[rpcMessage.id()] = call;
    }

    ProtobufCodec codec([](const TcpConnectionPtr&, 
                           const std::shared_ptr<google::protobuf::Message>&) {});
    codec.send(conn_, rpcMessage);
    
    LOG_INFO << "Sent RPC request: " << method->service()->name() 
             << "." << method->name() << " id=" << rpcMessage.id();
}

void RpcChannel::connect() {
    client_.connect();
}

void RpcChannel::disconnect() {
    client_.disconnect();
}

void RpcChannel::onConnection(const TcpConnectionPtr& conn) {
    std::lock_guard<std::mutex> lock(mutex_);
    
    if (conn->connected()) {
        conn_ = conn;
        LOG_INFO << "Connected to Java backend: " << conn->peerAddress().toIpPort();
    } else {
        conn_.reset();
        LOG_INFO << "Disconnected from Java backend";
        outstandingCalls_.clear();
    }
}

void RpcChannel::onMessage(const TcpConnectionPtr& conn, Buffer* buf, Timestamp time) {
    static ProtobufCodec codec([](const TcpConnectionPtr&, 
                                   const std::shared_ptr<google::protobuf::Message>&) {});
    
    codec.onMessage(conn, buf, time, [this](const TcpConnectionPtr&,
                                            const std::shared_ptr<google::protobuf::Message>& msg) {
        auto rpcMessage = std::dynamic_pointer_cast<bridge::RpcMessage>(msg);
        if (!rpcMessage) {
            LOG_ERROR << "Invalid RPC message type";
            return;
        }

        OutstandingCall call;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            auto it = outstandingCalls_.find(rpcMessage->id());
            if (it != outstandingCalls_.end()) {
                call = it->second;
                outstandingCalls_.erase(it);
            } else {
                LOG_ERROR << "Unknown RPC id: " << rpcMessage->id();
                return;
            }
        }

        if (rpcMessage->type() == bridge::RpcMessage::RESPONSE) {
            if (!call.response->ParseFromString(rpcMessage->payload())) {
                LOG_ERROR << "Failed to parse response";
            }
            LOG_INFO << "Received RPC response for id=" << rpcMessage->id();
        } else if (rpcMessage->type() == bridge::RpcMessage::ERROR) {
            LOG_ERROR << "RPC error: " << rpcMessage->error_desc();
        }

        if (call.done) {
            call.done->Run();
        }
    });
}
