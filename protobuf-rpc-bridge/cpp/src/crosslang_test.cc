#include <iostream>
#include <fstream>
#include <string>
#include <cstdint>
#include <zlib.h>
#include "chat.pb.h"

static void writeInt32LE(char* buf, int32_t value) {
    uint8_t* p = reinterpret_cast<uint8_t*>(buf);
    p[0] = value & 0xFF;
    p[1] = (value >> 8) & 0xFF;
    p[2] = (value >> 16) & 0xFF;
    p[3] = (value >> 24) & 0xFF;
}

static int32_t readInt32LE(const char* data) {
    const uint8_t* p = reinterpret_cast<const uint8_t*>(data);
    return static_cast<int32_t>(
        static_cast<uint32_t>(p[0]) |
        (static_cast<uint32_t>(p[1]) << 8) |
        (static_cast<uint32_t>(p[2]) << 16) |
        (static_cast<uint32_t>(p[3]) << 24));
}

int main(int argc, char* argv[]) {
    if (argc < 3) {
        std::cerr << "Usage: " << argv[0] << " <encode|decode> <file>" << std::endl;
        return 1;
    }

    std::string mode = argv[1];
    std::string filename = argv[2];

    if (mode == "encode") {
        bridge::ChatRequest request;
        request.set_user_id(1);
        request.set_bot_id(10000);
        request.set_user_name("cpp_tester");
        request.set_message("hello from C++");
        request.set_session_id("cpp_session_1");
        request.set_timestamp(1000);

        std::string typeName = request.GetTypeName();
        int32_t nameLen = static_cast<int32_t>(typeName.size() + 1);
        std::string serialized;
        request.SerializeToString(&serialized);
        int32_t payloadLen = static_cast<int32_t>(serialized.size());
        int32_t totalLen = 8 + nameLen + payloadLen;

        char* buf = new char[8 + nameLen + payloadLen];
        writeInt32LE(buf, totalLen);
        writeInt32LE(buf + 4, nameLen);
        std::memcpy(buf + 8, typeName.c_str(), nameLen);
        std::memcpy(buf + 8 + nameLen, serialized.data(), payloadLen);

        int32_t checkSum = static_cast<int32_t>(
            ::adler32(1, reinterpret_cast<const Bytef*>(buf), 8 + nameLen + payloadLen));

        std::ofstream out(filename, std::ios::binary);
        out.write(buf, 8 + nameLen + payloadLen);
        char csBuf[4];
        writeInt32LE(csBuf, checkSum);
        out.write(csBuf, 4);
        delete[] buf;
        out.close();

        std::cout << "Encoded ChatRequest to " << filename << std::endl;
        std::cout << "  totalLen=" << totalLen << " nameLen=" << nameLen
                  << " payloadLen=" << payloadLen << " checksum=" << checkSum << std::endl;
    }
    else if (mode == "decode") {
        std::ifstream in(filename, std::ios::binary);
        std::string data((std::istreambuf_iterator<char>(in)),
                         std::istreambuf_iterator<char>());
        in.close();

        int32_t totalLen = readInt32LE(data.data());
        int32_t nameLen = readInt32LE(data.data() + 4);

        std::string typeName(data.data() + 8, nameLen - 1);
        int32_t payloadLen = totalLen - 8 - nameLen;
        std::string payload(data.data() + 8 + nameLen, payloadLen);

        int32_t expectedChecksum = readInt32LE(data.data() + 8 + nameLen + payloadLen);

        int32_t computedChecksum = static_cast<int32_t>(
            ::adler32(1, reinterpret_cast<const Bytef*>(data.data()), 8 + nameLen + payloadLen));

        std::cout << "Decoding from " << filename << std::endl;
        std::cout << "  totalLen=" << totalLen << " nameLen=" << nameLen
                  << " payloadLen=" << payloadLen << std::endl;
        std::cout << "  typeName=" << typeName << std::endl;
        std::cout << "  expectedChecksum=" << expectedChecksum
                  << " computedChecksum=" << computedChecksum << std::endl;

        if (expectedChecksum != computedChecksum) {
            std::cerr << "  CHECKSUM MISMATCH!" << std::endl;
            return 1;
        }

        if (typeName == "bridge.ChatRequest") {
            bridge::ChatRequest request;
            request.ParseFromString(payload);
            std::cout << "  ChatRequest: user_id=" << request.user_id()
                      << " bot_id=" << request.bot_id()
                      << " message=" << request.message() << std::endl;
        } else if (typeName == "bridge.RpcMessage") {
            bridge::RpcMessage rpc;
            rpc.ParseFromString(payload);
            std::cout << "  RpcMessage: id=" << rpc.id()
                      << " service=" << rpc.service_name()
                      << " method=" << rpc.method_name() << std::endl;
        } else {
            std::cout << "  Unknown type: " << typeName << std::endl;
        }

        std::cout << "  CHECKSUM OK!" << std::endl;
    }

    return 0;
}
