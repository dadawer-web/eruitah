#!/usr/bin/env python3

import socket
import struct
import sys
import time
import zlib

from google.protobuf.descriptor import FieldDescriptor

def make_chat_request_pb2():
    sys.path.insert(0, '/home/xmy/code/protobuf-rpc-bridge/proto')
    import chat_pb2
    return chat_pb2

def send_message(sock, message):
    serialized = message.SerializeToString()
    type_name = message.DESCRIPTOR.full_name.encode()

    name_len = len(type_name) + 1
    payload_len = len(serialized)
    total_len = 2 * 4 + name_len + payload_len

    header = struct.pack('<II', total_len, name_len)
    name_bytes = type_name + b'\x00'

    checksum_data = header + name_bytes + serialized
    checksum = zlib.adler32(checksum_data) & 0xffffffff

    packet = header + name_bytes + serialized + struct.pack('<I', checksum)

    sock.sendall(packet)
    print(f"Sent message: {message.DESCRIPTOR.name}")

def receive_message(sock, pb2):
    header = sock.recv(8)
    if len(header) < 8:
        return None

    total_len, name_len = struct.unpack('<II', header)

    remaining = total_len - 8 + 4
    data = b''
    while len(data) < remaining:
        chunk = sock.recv(remaining - len(data))
        if not chunk:
            return None
        data += chunk

    name_bytes = data[:name_len]
    type_name = name_bytes[:-1].decode()

    payload_len = total_len - 8 - name_len
    payload = data[name_len:name_len + payload_len]

    if type_name == "bridge.ChatResponse":
        response = pb2.ChatResponse()
        response.ParseFromString(payload)
        return response
    elif type_name == "bridge.GroupChatResponse":
        response = pb2.GroupChatResponse()
        response.ParseFromString(payload)
        return response
    elif type_name == "bridge.RpcMessage":
        response = pb2.RpcMessage()
        response.ParseFromString(payload)
        return response

    return None

def test_chat_server():
    pb2 = make_chat_request_pb2()

    print("Testing Protobuf RPC Bridge System")
    print("=" * 60)

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(('127.0.0.1', 8888))
        print("Connected to C++ muduo server on port 8888")

        test_cases = [
            {"user_id": 1, "bot_id": 10000, "message": "你好，旗舰大师！"},
            {"user_id": 1, "bot_id": 10001, "message": "数据结构怎么学？"},
            {"user_id": 1, "bot_id": 10002, "message": "操作系统好难啊"},
            {"user_id": 1, "bot_id": 10003, "message": "帮我看看这段代码"},
            {"user_id": 1, "bot_id": 10000, "message": "计算机网络的三次握手"},
        ]

        for i, tc in enumerate(test_cases, 1):
            print(f"\n--- Test {i}: bot={tc['bot_id']} ---")

            request = pb2.ChatRequest(
                user_id=tc["user_id"],
                bot_id=tc["bot_id"],
                user_name="test_user",
                message=tc["message"],
                session_id=f"session_{i}",
                timestamp=int(time.time() * 1000),
            )

            send_message(sock, request)

            response = receive_message(sock, pb2)

            if response:
                print(f"  Bot: {response.bot_name}")
                print(f"  Reply: {response.message}")
                print(f"  Success: {response.success}")
                print(f"  Type: {response.msg_type}")
                if response.metadata:
                    print(f"  Metadata: {dict(response.metadata)}")
            else:
                print("  Failed to receive response")
                break

            time.sleep(0.3)

        sock.close()
        print("\n" + "=" * 60)
        print("Test completed!")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_chat_server()
