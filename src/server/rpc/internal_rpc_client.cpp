#include "internal_rpc_client.hpp"
#include "protobuf_codec.h"
#include "proto/chat.pb.h"
#include <muduo/base/Logging.h>

InternalRpcClient::InternalRpcClient(EventLoop* loop, const InetAddress& javaAddr)
    : client_(loop, javaAddr, "InternalRpcClient"),
      id_(0) {
    client_.setConnectionCallback(
        std::bind(&InternalRpcClient::onConnection, this, std::placeholders::_1));
    client_.setMessageCallback(
        std::bind(&InternalRpcClient::onMessage, this, std::placeholders::_1,
                  std::placeholders::_2, std::placeholders::_3));
}

InternalRpcClient::~InternalRpcClient() {
    disconnect();
}

void InternalRpcClient::connect() {
    client_.connect();
}

void InternalRpcClient::disconnect() {
    client_.disconnect();
}

bool InternalRpcClient::connected() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return conn_ && conn_->connected();
}

void InternalRpcClient::forwardToJava(int senderId, int receiverId, int64_t groupId,
                                       int msgType, const std::string& payloadJson,
                                       const std::string& traceId,
                                       RpcCallback callback) {
    bridge::InternalForwardRequest request;
    request.set_sender_id(senderId);
    request.set_receiver_id(receiverId);
    request.set_group_id(groupId);
    request.set_msg_type(static_cast<bridge::InternalMsgType>(msgType));
    request.set_payload_json(payloadJson);
    request.set_trace_id(traceId);
    request.set_timestamp(Timestamp::now().microSecondsSinceEpoch() / 1000);

    auto response = std::make_shared<bridge::InternalForwardResponse>();

    sendRpcMessage("InternalRouterService", "ForwardToJava",
                   request, response,
                   [callback](const std::string& svc, const std::string& method,
                              bool success, const std::string& error) {
                       if (callback) callback(svc, method, success, error);
                   });
}

void InternalRpcClient::sendRpcMessage(const std::string& serviceName,
                                        const std::string& methodName,
                                        const google::protobuf::Message& request,
                                        std::shared_ptr<google::protobuf::Message> response,
                                        RpcCallback callback) {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (!conn_ || !conn_->connected()) {
            LOG_ERROR << "Not connected to Java RPC, dropping: "
                      << serviceName << "." << methodName;
            if (callback) callback(serviceName, methodName, false, "Not connected");
            return;
        }
    }

    bridge::RpcMessage rpcMessage;
    rpcMessage.set_type(bridge::RpcMessage::REQUEST);

    int64_t rpcId;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        rpcId = ++id_;
    }
    rpcMessage.set_id(rpcId);
    rpcMessage.set_service_name(serviceName);
    rpcMessage.set_method_name(methodName);

    std::string serialized;
    if (!request.SerializeToString(&serialized)) {
        LOG_ERROR << "Failed to serialize request for " << serviceName << "." << methodName;
        if (callback) callback(serviceName, methodName, false, "Serialize failed");
        return;
    }
    rpcMessage.set_payload(serialized);

    {
        std::lock_guard<std::mutex> lock(mutex_);
        PendingCall call;
        call.response = response;
        call.callback = callback;
        call.serviceName = serviceName;
        call.methodName = methodName;
        pendingCalls_[rpcId] = call;
    }

    ProtobufCodec codec([](const TcpConnectionPtr&,
                           const std::shared_ptr<google::protobuf::Message>&) {});
    {
        std::lock_guard<std::mutex> lock(mutex_);
        codec.send(conn_, rpcMessage);
    }

    LOG_INFO << "Sent RPC: " << serviceName << "." << methodName << " id=" << rpcId;
}

void InternalRpcClient::onConnection(const TcpConnectionPtr& conn) {
    std::lock_guard<std::mutex> lock(mutex_);

    if (conn->connected()) {
        conn_ = conn;
        LOG_INFO << "InternalRpcClient connected to Java: " << conn->peerAddress().toIpPort();
    } else {
        conn_.reset();
        LOG_WARN << "InternalRpcClient disconnected from Java";
        pendingCalls_.clear();
    }
}

void InternalRpcClient::onMessage(const TcpConnectionPtr& conn, Buffer* buf, Timestamp time) {
    ProtobufCodec codec([this](const TcpConnectionPtr&,
                                const std::shared_ptr<google::protobuf::Message>& msg) {
        auto rpcMessage = std::dynamic_pointer_cast<bridge::RpcMessage>(msg);
        if (!rpcMessage) {
            LOG_ERROR << "Invalid RPC message type in InternalRpcClient";
            return;
        }

        PendingCall call;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            auto it = pendingCalls_.find(rpcMessage->id());
            if (it != pendingCalls_.end()) {
                call = it->second;
                pendingCalls_.erase(it);
            } else {
                LOG_WARN << "Unknown RPC response id=" << rpcMessage->id();
                return;
            }
        }

        bool success = false;
        std::string error;

        if (rpcMessage->type() == bridge::RpcMessage::RESPONSE) {
            if (call.response) {
                if (!call.response->ParseFromString(rpcMessage->payload())) {
                    LOG_ERROR << "Failed to parse response for id=" << rpcMessage->id();
                    error = "Parse response failed";
                } else {
                    success = true;
                }
            }
        } else if (rpcMessage->type() == bridge::RpcMessage::ERROR) {
            error = rpcMessage->error_desc();
            LOG_ERROR << "RPC error for " << call.serviceName << "." << call.methodName
                      << ": " << error;
        }

        if (call.callback) {
            call.callback(call.serviceName, call.methodName, success, error);
        }
    });

    codec.onMessage(conn, buf, time);
}
