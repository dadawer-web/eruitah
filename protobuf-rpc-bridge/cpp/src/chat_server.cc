#include "chat_server.h"
#include "protobuf_codec.h"
#include <muduo/base/Logging.h>

ChatServer::ChatServer(EventLoop* loop,
                       const InetAddress& listenAddr,
                       const InetAddress& javaBackendAddr)
    : server_(loop, listenAddr, "ChatServer"),
      rpcChannel_(std::make_shared<RpcChannel>(loop, javaBackendAddr)) {
    server_.setConnectionCallback(
        std::bind(&ChatServer::onClientConnection, this, std::placeholders::_1));
    server_.setMessageCallback(
        std::bind(&ChatServer::onClientMessage, this, std::placeholders::_1,
                  std::placeholders::_2, std::placeholders::_3));

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
    ProtobufCodec codec([this, conn](const TcpConnectionPtr&,
                                      const std::shared_ptr<google::protobuf::Message>& msg) {
        if (auto chatReq = std::dynamic_pointer_cast<bridge::ChatRequest>(msg)) {
            handleChatRequest(conn, chatReq);
        } else if (auto groupReq = std::dynamic_pointer_cast<bridge::GroupChatRequest>(msg)) {
            handleGroupChatRequest(conn, groupReq);
        } else {
            LOG_WARN << "Unknown message type: " << msg->GetTypeName();
        }
    });

    codec.onMessage(conn, buf, time);
}

void ChatServer::handleChatRequest(const TcpConnectionPtr& conn,
                                    const std::shared_ptr<bridge::ChatRequest>& request) {
    LOG_INFO << "Chat request from user=" << request->user_id()
             << " bot=" << request->bot_id()
             << " msg=" << request->message().substr(0, 50);

    {
        std::lock_guard<std::mutex> lock(mutex_);
        clientConnections_[request->session_id()] = conn;
    }

    auto response = std::make_shared<bridge::ChatResponse>();

    rpcChannel_->callMethod(
        "ChatService", "Chat",
        *request, response,
        [this, conn, request, response](std::shared_ptr<google::protobuf::Message> resp) {
            if (resp) {
                auto chatResp = std::dynamic_pointer_cast<bridge::ChatResponse>(resp);
                if (chatResp) {
                    ProtobufCodec sendCodec(
                        [](const TcpConnectionPtr&,
                           const std::shared_ptr<google::protobuf::Message>&) {});
                    sendCodec.send(conn, *chatResp);
                    LOG_INFO << "Sent chat response to user=" << chatResp->user_id();
                }
            } else {
                bridge::ChatResponse errorResp;
                errorResp.set_user_id(request->user_id());
                errorResp.set_bot_id(request->bot_id());
                errorResp.set_success(false);
                errorResp.set_error("Java backend unavailable");
                errorResp.set_timestamp(Timestamp::now().microSecondsSinceEpoch());

                ProtobufCodec sendCodec(
                    [](const TcpConnectionPtr&,
                       const std::shared_ptr<google::protobuf::Message>&) {});
                sendCodec.send(conn, errorResp);
                LOG_ERROR << "Java backend unavailable for user=" << request->user_id();
            }
        });
}

void ChatServer::handleGroupChatRequest(const TcpConnectionPtr& conn,
                                         const std::shared_ptr<bridge::GroupChatRequest>& request) {
    LOG_INFO << "Group chat request from group=" << request->group_id()
             << " sender=" << request->sender_id();

    auto response = std::make_shared<bridge::GroupChatResponse>();

    rpcChannel_->callMethod(
        "ChatService", "GroupChat",
        *request, response,
        [this, conn, response](std::shared_ptr<google::protobuf::Message> resp) {
            if (resp) {
                auto groupResp = std::dynamic_pointer_cast<bridge::GroupChatResponse>(resp);
                if (groupResp) {
                    ProtobufCodec sendCodec(
                        [](const TcpConnectionPtr&,
                           const std::shared_ptr<google::protobuf::Message>&) {});
                    sendCodec.send(conn, *groupResp);
                }
            }
        });
}
