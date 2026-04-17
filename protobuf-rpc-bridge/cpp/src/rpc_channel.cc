#include "rpc_channel.h"
#include "protobuf_codec.h"
#include "chat.pb.h"
#include <muduo/base/Logging.h>

RpcChannel::RpcChannel(EventLoop* loop, const InetAddress& serverAddr)
    : client_(loop, serverAddr, "RpcChannel"),
      id_(0) {
    client_.setConnectionCallback(
        std::bind(&RpcChannel::onConnection, this, std::placeholders::_1));
    client_.setMessageCallback(
        std::bind(&RpcChannel::onMessage, this, std::placeholders::_1,
                  std::placeholders::_2, std::placeholders::_3));
}

RpcChannel::~RpcChannel() {
    disconnect();
}

void RpcChannel::callMethod(const std::string& serviceName,
                             const std::string& methodName,
                             const google::protobuf::Message& request,
                             std::shared_ptr<google::protobuf::Message> response,
                             ResponseCallback done) {
    if (!connected()) {
        LOG_ERROR << "Not connected to Java backend";
        if (done) done(nullptr);
        return;
    }

    bridge::RpcMessage rpcMessage;
    rpcMessage.set_type(bridge::RpcMessage::REQUEST);

    {
        std::lock_guard<std::mutex> lock(mutex_);
        rpcMessage.set_id(++id_);
    }

    rpcMessage.set_service_name(serviceName);
    rpcMessage.set_method_name(methodName);

    std::string serialized;
    if (!request.SerializeToString(&serialized)) {
        LOG_ERROR << "Failed to serialize request";
        if (done) done(nullptr);
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

    LOG_INFO << "Sent RPC request: " << serviceName
             << "." << methodName << " id=" << rpcMessage.id();
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
    ProtobufCodec codec([this](const TcpConnectionPtr&,
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
            if (call.response && !call.response->ParseFromString(rpcMessage->payload())) {
                LOG_ERROR << "Failed to parse response for id=" << rpcMessage->id();
            }
            LOG_INFO << "Received RPC response for id=" << rpcMessage->id();
        } else if (rpcMessage->type() == bridge::RpcMessage::ERROR) {
            LOG_ERROR << "RPC error: " << rpcMessage->error_desc();
        }

        if (call.done) {
            call.done(call.response);
        }
    });

    codec.onMessage(conn, buf, time);
}
