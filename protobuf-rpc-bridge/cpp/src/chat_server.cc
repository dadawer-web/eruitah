#include "chat_server.h"
#include "protobuf_codec.h"
#include <muduo/base/Logging.h>

using namespace muduo;
using namespace muduo::net;

ChatServer::ChatServer(EventLoop* loop,
                       const InetAddress& listenAddr,
                       const InetAddress& javaBackendAddr)
    : server_(loop, listenAddr, "ChatServer"),
      rpcChannel_(std::make_shared<RpcChannel>(loop, javaBackendAddr)) {
    
    server_.setConnectionCallback(
        std::bind(&ChatServer::onClientConnection, this, _1));
    server_.setMessageCallback(
        std::bind(&ChatServer::onClientMessage, this, _1, _2, _3));
    
    threadPool_.setMaxQueueSize(100);
}

void ChatServer::start() {
    threadPool_.start(4);
    rpcChannel_->connect();
    server_.start();
    LOG_INFO << "ChatServer started on " << server_.ipPort();
}

void ChatServer::setThreadNum(int numThreads) {
    server_.setThreadNum(numThreads);
}

void ChatServer::onClientConnection(const TcpConnectionPtr& conn) {
    if (conn->connected()) {
        LOG_INFO << "Client connected: " << conn->peerAddress().toIpPort();
    } else {
        LOG_INFO << "Client disconnected: " << conn->peerAddress().toIpPort();
        
        std::lock_guard<std::mutex> lock(mutex_);
        for (auto it = clientConnections_.begin(); it != clientConnections_.end(); ) {
            if (it->second == conn) {
                it = clientConnections_.erase(it);
            } else {
                ++it;
            }
        }
    }
}

void ChatServer::onClientMessage(const TcpConnectionPtr& conn, 
                                  Buffer* buf, 
                                  Timestamp time) {
    static ProtobufCodec codec([](const TcpConnectionPtr&, 
                                   const std::shared_ptr<google::protobuf::Message>&) {});
    
    codec.onMessage(conn, buf, time, 
        [this, conn](const TcpConnectionPtr&, 
                     const std::shared_ptr<google::protobuf::Message>& msg) {
            auto request = std::dynamic_pointer_cast<bridge::ChatRequest>(msg);
            if (!request) {
                LOG_ERROR << "Invalid message type";
                return;
            }
            
            {
                std::lock_guard<std::mutex> lock(mutex_);
                clientConnections_[request->session_id()] = conn;
            }
            
            threadPool_.run([this, request, conn]() {
                bridge::ChatResponse response;
                bridge::ChatController controller;
                
                this->Chat(&controller, request.get(), &response, nullptr);
                
                if (!controller.Failed()) {
                    ProtobufCodec codec([](const TcpConnectionPtr&, 
                                           const std::shared_ptr<google::protobuf::Message>&) {});
                    codec.send(conn, response);
                }
            });
        });
}

void ChatServer::Chat(google::protobuf::RpcController* controller,
                      const bridge::ChatRequest* request,
                      bridge::ChatResponse* response,
                      google::protobuf::Closure* done) {
    if (!rpcChannel_->connected()) {
        controller->SetFailed("Java backend not connected");
        LOG_ERROR << "Java backend not connected";
        if (done) done->Run();
        return;
    }
    
    LOG_INFO << "Forwarding chat request from user: " << request->user_id()
             << " session: " << request->session_id();
    
    bridge::ChatRequest forwardRequest;
    forwardRequest.CopyFrom(*request);
    forwardRequest.set_timestamp(Timestamp::now().microSecondsSinceEpoch());
    
    rpcChannel_->CallMethod(
        bridge::ChatService::descriptor()->FindMethodByName("Chat"),
        controller,
        &forwardRequest,
        response,
        done);
}
