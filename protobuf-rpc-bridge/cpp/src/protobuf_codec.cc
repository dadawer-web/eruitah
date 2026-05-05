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
        int32_t len = readInt32LE(buf->peek());

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

    const std::string& typeName = message.GetTypeName();
    int32_t nameLen = static_cast<int32_t>(typeName.size() + 1);
    std::string serialized;
    message.SerializeToString(&serialized);
    int32_t payloadLen = static_cast<int32_t>(serialized.size());
    int32_t totalLen = 2 * kHeaderLen + nameLen + payloadLen;

    buf.ensureWritableBytes(totalLen + kHeaderLen);

    appendInt32LE(buf, totalLen);
    appendInt32LE(buf, nameLen);
    buf.append(typeName.c_str(), nameLen);
    buf.append(serialized.data(), payloadLen);

    int32_t checkSum = static_cast<int32_t>(
        ::adler32(1,
                  reinterpret_cast<const Bytef*>(buf.peek()),
                  static_cast<int>(buf.readableBytes())));
    appendInt32LE(buf, checkSum);

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
    int32_t totalLen = readInt32LE(ptr);
    ptr += kHeaderLen;

    if (totalLen + kHeaderLen > totalBufLen) {
        *error = kInvalidLength;
        return nullptr;
    }

    int32_t nameLen = readInt32LE(ptr);
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

    int32_t expectedCheckSum = readInt32LE(ptr);

    int32_t checkSum = static_cast<int32_t>(
        ::adler32(1,
                  reinterpret_cast<const Bytef*>(data),
                  totalLen));
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
    } else if (typeName == "bridge.CompanionReadRequest") {
        message = new bridge::CompanionReadRequest();
    } else if (typeName == "bridge.CompanionReadResponse") {
        message = new bridge::CompanionReadResponse();
    } else if (typeName == "bridge.DashboardRequest") {
        message = new bridge::DashboardRequest();
    } else if (typeName == "bridge.DashboardResponse") {
        message = new bridge::DashboardResponse();
    } else if (typeName == "bridge.DashboardSummaryRequest") {
        message = new bridge::DashboardSummaryRequest();
    } else if (typeName == "bridge.DashboardSummaryResponse") {
        message = new bridge::DashboardSummaryResponse();
    } else if (typeName == "bridge.WeeklyReportRequest") {
        message = new bridge::WeeklyReportRequest();
    } else if (typeName == "bridge.WeeklyReportResponse") {
        message = new bridge::WeeklyReportResponse();
    } else if (typeName == "bridge.PdfParseRequest") {
        message = new bridge::PdfParseRequest();
    } else if (typeName == "bridge.PdfParseResponse") {
        message = new bridge::PdfParseResponse();
    } else if (typeName == "bridge.SandboxExecuteRequest") {
        message = new bridge::SandboxExecuteRequest();
    } else if (typeName == "bridge.SandboxExecuteResponse") {
        message = new bridge::SandboxExecuteResponse();
    } else if (typeName == "bridge.SandboxTaskRequest") {
        message = new bridge::SandboxTaskRequest();
    } else if (typeName == "bridge.SandboxTaskResponse") {
        message = new bridge::SandboxTaskResponse();
    } else if (typeName == "bridge.SandboxToolEvent") {
        message = new bridge::SandboxToolEvent();
    } else if (typeName == "bridge.SwarmMessage") {
        message = new bridge::SwarmMessage();
    } else if (typeName == "bridge.SwarmRegisterRequest") {
        message = new bridge::SwarmRegisterRequest();
    } else if (typeName == "bridge.SwarmRegisterResponse") {
        message = new bridge::SwarmRegisterResponse();
    } else if (typeName == "bridge.SwarmHelpRequest") {
        message = new bridge::SwarmHelpRequest();
    } else if (typeName == "bridge.SwarmHelpResponse") {
        message = new bridge::SwarmHelpResponse();
    } else if (typeName == "bridge.SwarmNodeListResponse") {
        message = new bridge::SwarmNodeListResponse();
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
