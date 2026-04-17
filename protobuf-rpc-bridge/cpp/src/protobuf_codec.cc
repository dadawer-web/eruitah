#include "protobuf_codec.h"
#include "chat.pb.h"
#include <muduo/base/Logging.h>
#include <google/protobuf/descriptor.h>
#include <zlib.h>
#include <cstring>

void ProtobufCodec::onMessage(const TcpConnectionPtr& conn,
                               Buffer* buf,
                               Timestamp receiveTime) {
    while (buf->readableBytes() >= static_cast<size_t>(kMinMessageLen + kHeaderLen)) {
        int32_t len = buf->peekInt32();

        if (len > kMaxMessageLen || len < kMinMessageLen) {
            LOG_ERROR << "Invalid length " << len;
            conn->shutdown();
            break;
        }

        if (buf->readableBytes() >= implicit_cast<size_t>(len + kHeaderLen + kHeaderLen)) {
            ErrorCode errorCode = kNoError;
            std::shared_ptr<google::protobuf::Message> message =
                parse(buf->peek(), len + kHeaderLen + kHeaderLen, &errorCode);

            if (errorCode == kNoError && message) {
                messageCallback_(conn, message);
                buf->retrieve(len + kHeaderLen + kHeaderLen);
            } else {
                LOG_ERROR << "Parse error: " << errorCodeToString(errorCode);
                conn->shutdown();
                break;
            }
        } else {
            break;
        }
    }
}

void ProtobufCodec::send(const TcpConnectionPtr& conn,
                         const google::protobuf::Message& message) {
    Buffer buf;

    const std::string& typeName = message.GetTypeName();
    int32_t nameLen = static_cast<int32_t>(typeName.size() + 1);
    std::string serialized;
    message.SerializeToString(&serialized);
    int32_t payloadLen = static_cast<int32_t>(serialized.size());
    int32_t totalLen = 2 * kHeaderLen + nameLen + payloadLen;

    buf.ensureWritableBytes(totalLen + kHeaderLen);

    buf.appendInt32(totalLen);
    buf.appendInt32(nameLen);
    buf.append(typeName.c_str(), nameLen);
    buf.append(serialized.data(), payloadLen);

    int32_t checkSum = static_cast<int32_t>(
        ::adler32(1,
                  reinterpret_cast<const Bytef*>(buf.peek()),
                  static_cast<int>(buf.readableBytes())));
    buf.appendInt32(checkSum);

    conn->send(&buf);
}

const std::string ProtobufCodec::errorCodeToString(ErrorCode errorCode) {
    switch (errorCode) {
        case kNoError: return "NoError";
        case kInvalidLength: return "InvalidLength";
        case kCheckSumError: return "CheckSumError";
        case kInvalidNameLen: return "InvalidNameLen";
        case kUnknownMessageType: return "UnknownMessageType";
        case kParseError: return "ParseError";
        default: return "UnknownError";
    }
}

std::shared_ptr<google::protobuf::Message> ProtobufCodec::parse(
    const char* data, int totalBufLen, ErrorCode* error) {

    const char* ptr = data;
    int32_t totalLen;
    std::memcpy(&totalLen, ptr, kHeaderLen);
    ptr += kHeaderLen;

    if (totalLen + kHeaderLen > totalBufLen) {
        *error = kInvalidLength;
        return nullptr;
    }

    int32_t nameLen;
    std::memcpy(&nameLen, ptr, kHeaderLen);
    ptr += kHeaderLen;

    if (nameLen < 2 || nameLen > totalLen - 2 * kHeaderLen) {
        *error = kInvalidNameLen;
        return nullptr;
    }

    std::string typeName(ptr, nameLen - 1);
    ptr += nameLen;

    int32_t payloadLen = totalLen - 2 * kHeaderLen - nameLen;
    const char* payload = ptr;
    ptr += payloadLen;

    int32_t expectedCheckSum;
    std::memcpy(&expectedCheckSum, ptr, kHeaderLen);

    int32_t checkSum = static_cast<int32_t>(
        ::adler32(1,
                  reinterpret_cast<const Bytef*>(data),
                  totalLen + kHeaderLen));
    if (checkSum != expectedCheckSum) {
        *error = kCheckSumError;
        return nullptr;
    }

    google::protobuf::Message* message = nullptr;

    if (typeName == "bridge.ChatRequest") {
        message = new bridge::ChatRequest();
    } else if (typeName == "bridge.ChatResponse") {
        message = new bridge::ChatResponse();
    } else if (typeName == "bridge.GroupChatRequest") {
        message = new bridge::GroupChatRequest();
    } else if (typeName == "bridge.GroupChatResponse") {
        message = new bridge::GroupChatResponse();
    } else if (typeName == "bridge.RpcMessage") {
        message = new bridge::RpcMessage();
    } else {
        *error = kUnknownMessageType;
        return nullptr;
    }

    if (!message->ParseFromArray(payload, payloadLen)) {
        delete message;
        *error = kParseError;
        return nullptr;
    }

    *error = kNoError;
    return std::shared_ptr<google::protobuf::Message>(message);
}
