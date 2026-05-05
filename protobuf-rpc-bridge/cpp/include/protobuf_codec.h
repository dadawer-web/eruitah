#ifndef PROTOBUF_CODEC_H
#define PROTOBUF_CODEC_H

#include <muduo/net/Buffer.h>
#include <muduo/net/TcpConnection.h>
#include <google/protobuf/message.h>
#include <functional>
#include <memory>
#include <string>
#include <cstdint>

using namespace muduo;
using namespace muduo::net;

inline void appendInt32LE(muduo::net::Buffer& buf, int32_t value) {
    uint8_t bytes[4];
    bytes[0] = value & 0xFF;
    bytes[1] = (value >> 8) & 0xFF;
    bytes[2] = (value >> 16) & 0xFF;
    bytes[3] = (value >> 24) & 0xFF;
    buf.append(bytes, 4);
}

inline int32_t readInt32LE(const char* data) {
    const uint8_t* p = reinterpret_cast<const uint8_t*>(data);
    return static_cast<int32_t>(
        static_cast<uint32_t>(p[0]) |
        (static_cast<uint32_t>(p[1]) << 8) |
        (static_cast<uint32_t>(p[2]) << 16) |
        (static_cast<uint32_t>(p[3]) << 24));
}

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
