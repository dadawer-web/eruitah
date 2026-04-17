#ifndef PROTOBUF_CODEC_H
#define PROTOBUF_CODEC_H

#include <muduo/net/Buffer.h>
#include <muduo/net/TcpConnection.h>
#include <google/protobuf/message.h>
#include <functional>
#include <memory>
#include <string>

using namespace muduo;
using namespace muduo::net;

class ProtobufCodec {
public:
    typedef std::function<void(const TcpConnectionPtr&,
                               const std::shared_ptr<google::protobuf::Message>&)> ProtobufMessageCallback;

    enum ErrorCode {
        kNoError = 0,
        kInvalidLength,
        kCheckSumError,
        kInvalidNameLen,
        kUnknownMessageType,
        kParseError,
    };

    explicit ProtobufCodec(const ProtobufMessageCallback& messageCb)
        : messageCallback_(messageCb) {}

    void onMessage(const TcpConnectionPtr& conn,
                   Buffer* buf,
                   Timestamp receiveTime);

    void send(const TcpConnectionPtr& conn,
              const google::protobuf::Message& message);

    static const std::string errorCodeToString(ErrorCode errorCode);

    static const int kHeaderLen = sizeof(int32_t);
    static const int kMinMessageLen = 2 * kHeaderLen + 2;
    static const int kMaxMessageLen = 64 * 1024 * 1024;

private:
    std::shared_ptr<google::protobuf::Message> parse(const char* buf, int len, ErrorCode* error);

    ProtobufMessageCallback messageCallback_;
};

#endif
