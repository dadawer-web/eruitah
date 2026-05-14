#include "rpc_channel.h"
#include "protobuf_codec.h"
#include "proto/chat.pb.h"
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
        LOG_ERROR << "Not connected to backend, dropping: " << serviceName << "." << methodName;
        if (done) done(nullptr);
        return;
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
        if (done) done(nullptr);
        return;
    }
    rpcMessage.set_payload(serialized);

    {
        std::lock_guard<std::mutex> lock(mutex_);
        OutstandingCall call;
        call.response = response;
        call.done = done;
        outstandingCalls_[rpcId] = call;
    }

    ProtobufCodec codec([](const TcpConnectionPtr&,
                           const std::shared_ptr<google::protobuf::Message>&) {});
    codec.send(conn_, rpcMessage);

    LOG_INFO << "Sent RPC: " << serviceName << "." << methodName << " id=" << rpcId;
}

void RpcChannel::callStreamMethod(const std::string& serviceName,
                                   const std::string& methodName,
                                   const google::protobuf::Message& request,
                                   std::shared_ptr<google::protobuf::Message> streamChunk,
                                   StreamChunkCallback onChunk,
                                   StreamEndCallback onEnd,
                                   ResponseCallback onError) {
    if (!connected()) {
        LOG_ERROR << "Not connected to backend, dropping stream: " << serviceName << "." << methodName;
        if (onError) onError(nullptr);
        return;
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
        LOG_ERROR << "Failed to serialize stream request for " << serviceName << "." << methodName;
        if (onError) onError(nullptr);
        return;
    }
    rpcMessage.set_payload(serialized);

    {
        std::lock_guard<std::mutex> lock(mutex_);
        OutstandingStream stream;
        stream.streamChunk = streamChunk;
        stream.onChunk = onChunk;
        stream.onEnd = onEnd;
        stream.onError = onError;
        outstandingStreams_[rpcId] = stream;
    }

    ProtobufCodec codec([](const TcpConnectionPtr&,
                           const std::shared_ptr<google::protobuf::Message>&) {});
    codec.send(conn_, rpcMessage);

    LOG_INFO << "Sent stream RPC: " << serviceName << "." << methodName << " id=" << rpcId;
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
        LOG_INFO << "RpcChannel connected to backend: " << conn->peerAddress().toIpPort();
    } else {
        conn_.reset();
        LOG_WARN << "RpcChannel disconnected from backend";

        for (auto& pair : outstandingCalls_) {
            if (pair.second.done) pair.second.done(nullptr);
        }
        outstandingCalls_.clear();

        for (auto& pair : outstandingStreams_) {
            if (pair.second.onError) pair.second.onError(nullptr);
        }
        outstandingStreams_.clear();
    }
}

void RpcChannel::onMessage(const TcpConnectionPtr& conn, Buffer* buf, Timestamp time) {
    ProtobufCodec codec([this](const TcpConnectionPtr&,
                                const std::shared_ptr<google::protobuf::Message>& msg) {
        auto rpcMessage = std::dynamic_pointer_cast<bridge::RpcMessage>(msg);
        if (!rpcMessage) {
            LOG_ERROR << "Invalid RPC message type in RpcChannel";
            return;
        }

        if (rpcMessage->type() == bridge::RpcMessage::RESPONSE) {
            OutstandingCall call;
            {
                std::lock_guard<std::mutex> lock(mutex_);
                auto it = outstandingCalls_.find(rpcMessage->id());
                if (it != outstandingCalls_.end()) {
                    call = it->second;
                    outstandingCalls_.erase(it);
                } else {
                    LOG_WARN << "Unknown RPC response id=" << rpcMessage->id();
                    return;
                }
            }

            if (call.response) {
                if (!call.response->ParseFromString(rpcMessage->payload())) {
                    LOG_ERROR << "Failed to parse response for id=" << rpcMessage->id();
                }
            }
            if (call.done) {
                call.done(call.response);
            }

        } else if (rpcMessage->type() == bridge::RpcMessage::STREAM) {
            OutstandingStream stream;
            {
                std::lock_guard<std::mutex> lock(mutex_);
                auto it = outstandingStreams_.find(rpcMessage->id());
                if (it != outstandingStreams_.end()) {
                    stream = it->second;
                } else {
                    LOG_WARN << "Unknown stream chunk id=" << rpcMessage->id();
                    return;
                }
            }

            if (stream.streamChunk) {
                auto chunk = stream.streamChunk->New();
                if (chunk->ParseFromString(rpcMessage->payload())) {
                    stream.onChunk(std::shared_ptr<google::protobuf::Message>(chunk));
                } else {
                    LOG_ERROR << "Failed to parse stream chunk for id=" << rpcMessage->id();
                    delete chunk;
                }
            }

        } else if (rpcMessage->type() == bridge::RpcMessage::STREAM_END) {
            OutstandingStream stream;
            {
                std::lock_guard<std::mutex> lock(mutex_);
                auto it = outstandingStreams_.find(rpcMessage->id());
                if (it != outstandingStreams_.end()) {
                    stream = it->second;
                    outstandingStreams_.erase(it);
                } else {
                    LOG_WARN << "Unknown stream end id=" << rpcMessage->id();
                    return;
                }
            }

            if (stream.onEnd) {
                stream.onEnd();
            }

        } else if (rpcMessage->type() == bridge::RpcMessage::ERROR) {
            int64_t id = rpcMessage->id();
            LOG_ERROR << "RPC error: code=" << rpcMessage->error_code()
                      << " desc=" << rpcMessage->error_desc();

            OutstandingCall call;
            bool isCall = false;
            {
                std::lock_guard<std::mutex> lock(mutex_);
                auto it = outstandingCalls_.find(id);
                if (it != outstandingCalls_.end()) {
                    call = it->second;
                    outstandingCalls_.erase(it);
                    isCall = true;
                }
            }

            if (isCall) {
                if (call.done) call.done(nullptr);
            } else {
                OutstandingStream stream;
                {
                    std::lock_guard<std::mutex> lock(mutex_);
                    auto it = outstandingStreams_.find(id);
                    if (it != outstandingStreams_.end()) {
                        stream = it->second;
                        outstandingStreams_.erase(it);
                    }
                }
                if (stream.onError) stream.onError(nullptr);
            }
        }
    });

    codec.onMessage(conn, buf, time);
}
