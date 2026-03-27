#!/usr/bin/env python3

import socket
import struct
import sys
import time

sys.path.append('/home/xmy/code/protobuf-rpc-bridge/proto')

import chat_pb2

def send_message(sock, message):
    serialized = message.SerializeToString()
    type_name = message.DESCRIPTOR.full_name.encode()
    
    name_len = len(type_name) + 1
    payload_len = len(serialized)
    total_len = 2 * 4 + name_len + payload_len
    
    header = struct.pack('<II', total_len, name_len)
    name_bytes = type_name + b'\x00'
    
    import zlib
    checksum_data = header + name_bytes + serialized
    checksum = zlib.adler32(checksum_data) & 0xffffffff
    
    packet = header + name_bytes + serialized + struct.pack('<I', checksum)
    
    sock.sendall(packet)
    print(f"Sent message: {message.DESCRIPTOR.name}")

def receive_message(sock):
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
        response = chat_pb2.ChatResponse()
        response.ParseFromString(payload)
        return response
    elif type_name == "bridge.ChatRequest":
        request = chat_pb2.ChatRequest()
        request.ParseFromString(payload)
        return request
    
    return None

def test_chat_server():
    print("Testing Protobuf RPC Bridge System")
    print("=" * 50)
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(('127.0.0.1', 8888))
        print("Connected to C++ muduo server on port 8888")
        
        test_messages = [
            "Hello, AI assistant!",
            "How are you today?",
            "Can you help me with something?",
            "What's the weather like?",
            "Goodbye!"
        ]
        
        for i, msg in enumerate(test_messages, 1):
            print(f"\n--- Test {i} ---")
            
            request = chat_pb2.ChatRequest(
                session_id=f"session_{i}",
                user_id="test_user_001",
                message=msg,
                timestamp=int(time.time() * 1000)
            )
            request.metadata["source"] = "python_test_client"
            request.metadata["version"] = "1.0"
            
            send_message(sock, request)
            
            response = receive_message(sock)
            
            if response:
                print(f"Session ID: {response.session_id}")
                print(f"Status: {response.status}")
                print(f"Reply: {response.reply}")
                print(f"Timestamp: {response.timestamp}")
                if response.metadata:
                    print(f"Metadata: {dict(response.metadata)}")
            else:
                print("Failed to receive response")
                break
            
            time.sleep(0.5)
        
        sock.close()
        print("\n" + "=" * 50)
        print("Test completed successfully!")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_chat_server()
