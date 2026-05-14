#include "internal_rpc_server.hpp"
#include "protobuf_codec.h"
#include "proto/chat.pb.h"
#include <muduo/base/Logging.h>

InternalRpcServer::InternalRpcServer(EventLoop* loop, const InetAddress& listenAddr)
    : server_(loop, listenAddr, "InternalRpcServer") {
    server_.setConnectionCallback(
        std::bind(&InternalRpcServer::onConnection, this, std::placeholders::_1));
    server_.setMessageCallback(
        std::bind(&InternalRpcServer::onMessage, this, std::placeholders::_1,
                  std::placeholders::_2, std::placeholders::_3));
}

void InternalRpcServer::start() {
    server_.start();
    LOG_INFO << "InternalRpcServer started on " << server_.ipPort();
}

void InternalRpcServer::setPushCallback(PushCallback cb) {
    std::lock_guard<std::mutex> lock(mutex_);
    pushCallback_ = cb;
}

void InternalRpcServer::onConnection(const TcpConnectionPtr& conn) {
    if (conn->connected()) {
        LOG_INFO << "Java RPC client connected: " << conn->peerAddress().toIpPort();
    } else {
        LOG_INFO << "Java RPC client disconnected: " << conn->peerAddress().toIpPort();
    }
}

void InternalRpcServer::onMessage(const TcpConnectionPtr& conn, Buffer* buf, Timestamp time) {
    ProtobufCodec codec([this, conn](const TcpConnectionPtr&,
                                      const std::shared_ptr<google::protobuf::Message>& msg) {
        auto rpcMessage = std::dynamic_pointer_cast<bridge::RpcMessage>(msg);
        if (!rpcMessage) {
            LOG_ERROR << "Invalid RPC message in InternalRpcServer";
            return;
        }

        if (rpcMessage->type() != bridge::RpcMessage::REQUEST) {
            LOG_WARN << "Ignoring non-REQUEST message type=" << rpcMessage->type();
            return;
        }

        handlePushRequest(conn, rpcMessage->service_name(),
                          rpcMessage->method_name(),
                          rpcMessage->id(),
                          rpcMessage->payload());
    });

    codec.onMessage(conn, buf, time);
}

void InternalRpcServer::handlePushRequest(const TcpConnectionPtr& conn,
                                           const std::string& serviceName,
                                           const std::string& methodName,
                                           int64_t rpcId,
                                           const std::string& payload) {
    LOG_INFO << "Received RPC: " << serviceName << "." << methodName << " id=" << rpcId;

    if (serviceName == "InternalRouterService" && methodName == "PushToClient") {
        bridge::InternalPushRequest pushReq;
        if (!pushReq.ParseFromString(payload)) {
            LOG_ERROR << "Failed to parse InternalPushRequest";

            bridge::RpcMessage errorMsg;
            errorMsg.set_type(bridge::RpcMessage::ERROR);
            errorMsg.set_id(rpcId);
            errorMsg.set_error_code(400);
            errorMsg.set_error_desc("Failed to parse InternalPushRequest");

            ProtobufCodec sendCodec([](const TcpConnectionPtr&,
                                        const std::shared_ptr<google::protobuf::Message>&) {});
            sendCodec.send(conn, errorMsg);
            return;
        }

        LOG_INFO << "PushToClient: receiverId=" << pushReq.receiver_id()
                 << " groupId=" << pushReq.group_id()
                 << " msgType=" << pushReq.msg_type()
                 << " broadcast=" << pushReq.broadcast()
                 << " payloadSize=" << pushReq.payload_json().size();

        {
            std::lock_guard<std::mutex> lock(mutex_);
            if (pushCallback_) {
                pushCallback_(pushReq.receiver_id(), pushReq.group_id(),
                              pushReq.msg_type(), pushReq.payload_json(),
                              pushReq.broadcast());
            }
        }

        bridge::InternalPushResponse pushResp;
        pushResp.set_success(true);
        pushResp.set_trace_id(pushReq.trace_id());
        pushResp.set_delivered_count(1);

        bridge::RpcMessage responseMsg;
        responseMsg.set_type(bridge::RpcMessage::RESPONSE);
        responseMsg.set_id(rpcId);
        std::string respPayload;
        pushResp.SerializeToString(&respPayload);
        responseMsg.set_payload(respPayload);

        ProtobufCodec sendCodec([](const TcpConnectionPtr&,
                                    const std::shared_ptr<google::protobuf::Message>&) {});
        sendCodec.send(conn, responseMsg);

        LOG_INFO << "PushToClient response sent: id=" << rpcId;

    } else {
        LOG_WARN << "Unknown RPC method: " << serviceName << "." << methodName;

        bridge::RpcMessage errorMsg;
        errorMsg.set_type(bridge::RpcMessage::ERROR);
        errorMsg.set_id(rpcId);
        errorMsg.set_error_code(404);
        errorMsg.set_error_desc("Unknown method: " + serviceName + "." + methodName);

        ProtobufCodec sendCodec([](const TcpConnectionPtr&,
                                    const std::shared_ptr<google::protobuf::Message>&) {});
        sendCodec.send(conn, errorMsg);
    }
}
