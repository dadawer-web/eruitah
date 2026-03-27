#include "protobuf_codec.h"
#include "chat.pb.h"
#include <muduo/base/Logging.h>
#include <google/protobuf/descriptor.h>
#include <zlib.h>

using namespace muduo;
using namespace muduo::net;

void ProtobufCodec::onMessage(const TcpConnectionPtr& conn,
                               Buffer* buf,
                               Timestamp receiveTime) {
    while (buf->readableBytes() >= kMinMessageLen) {
        int32_t len = buf->peekInt32();
        
        if (len > kMaxMessageLen || len < kMinMessageLen) {
            LOG_ERROR << "Invalid length " << len;
            conn->shutdown();
            break;
        }
        
        if (buf->readableBytes() >= implicit_cast<size_t>(len + kHeaderLen)) {
            ErrorCode errorCode = kNoError;
            std::shared_ptr<google::protobuf::Message> message = 
                parse(buf->peek(), len + kHeaderLen, &errorCode);
            
            if (errorCode == kNoError && message) {
                messageCallback_(conn, message);
                buf->retrieve(len + kHeaderLen);
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
    
    int byte_size = message.ByteSizeLong();
    buf.ensureWritableBytes(byte_size + 2 * kHeaderLen);
    
    buf.writeInt32(byte_size + 2 * kHeaderLen);
    
    const std::string& typeName = message.GetTypeName();
    int32_t nameLen = static_cast<int32_t>(typeName.size() + 1);
    buf.writeInt32(nameLen);
    buf.append(typeName.c_str(), nameLen);
    
    uint8_t* start = reinterpret_cast<uint8_t*>(buf.beginWrite());
    uint8_t* end = message.SerializeWithCachedSizesToArray(start);
    if (end - start != byte_size) {
        LOG_ERROR << "Serialize error";
    }
    buf.hasWritten(byte_size);
    
    int32_t checkSum = static_cast<int32_t>(
        ::adler32(1, 
                  reinterpret_cast<const Bytef*>(buf.peek()),
                  static_cast<int>(buf.readableBytes())));
    buf.writeInt32(checkSum);
    
    conn->send(&buf);
}

const std::string& ProtobufCodec::errorCodeToString(ErrorCode errorCode) {
    static const std::string kNoErrorStr = "NoError";
    static const std::string kInvalidLengthStr = "InvalidLength";
    static const std::string kCheckSumErrorStr = "CheckSumError";
    static const std::string kInvalidNameLenStr = "InvalidNameLen";
    static const std::string kUnknownMessageTypeStr = "UnknownMessageType";
    static const std::string kParseErrorStr = "ParseError";
    
    switch (errorCode) {
        case kNoError:
            return kNoErrorStr;
        case kInvalidLength:
            return kInvalidLengthStr;
        case kCheckSumError:
            return kCheckSumErrorStr;
        case kInvalidNameLen:
            return kInvalidNameLenStr;
        case kUnknownMessageType:
            return kUnknownMessageTypeStr;
        case kParseError:
            return kParseErrorStr;
        default:
            return kNoErrorStr;
    }
}

std::shared_ptr<google::protobuf::Message> ProtobufCodec::parse(
    const void* buf, int len, ErrorCode* error) {
    
    const char* data = static_cast<const char*>(buf);
    int32_t totalLen = *reinterpret_cast<const int32_t*>(data);
    
    if (totalLen != len) {
        *error = kInvalidLength;
        return nullptr;
    }
    
    int32_t expectedCheckSum = *reinterpret_cast<const int32_t*>(data + len - kHeaderLen);
    int32_t checkSum = static_cast<int32_t>(
        ::adler32(1, reinterpret_cast<const Bytef*>(data), len - kHeaderLen));
    
    if (checkSum != expectedCheckSum) {
        *error = kCheckSumError;
        return nullptr;
    }
    
    int32_t nameLen = *reinterpret_cast<const int32_t*>(data + kHeaderLen);
    if (nameLen < 2 || nameLen > len - 2 * kHeaderLen) {
        *error = kInvalidNameLen;
        return nullptr;
    }
    
    const char* typeName = data + 2 * kHeaderLen;
    std::string typeStr(typeName, nameLen - 1);
    
    google::protobuf::Message* message = nullptr;
    
    if (typeStr == "bridge.ChatRequest") {
        message = new bridge::ChatRequest();
    } else if (typeStr == "bridge.ChatResponse") {
        message = new bridge::ChatResponse();
    } else if (typeStr == "bridge.RpcMessage") {
        message = new bridge::RpcMessage();
    } else {
        *error = kUnknownMessageType;
        return nullptr;
    }
    
    const char* payload = data + 2 * kHeaderLen + nameLen;
    int payloadLen = len - 3 * kHeaderLen - nameLen;
    
    if (!message->ParseFromArray(payload, payloadLen)) {
        delete message;
        *error = kParseError;
        return nullptr;
    }
    
    *error = kNoError;
    return std::shared_ptr<google::protobuf::Message>(message);
}
