#!/bin/bash

PROTO_DIR="$(cd "$(dirname "$0")/.." && pwd)/proto"
CPP_OUT="$(cd "$(dirname "$0")/.." && pwd)/cpp/include"
JAVA_OUT="$(cd "$(dirname "$0")/.." && pwd)/java/src/main/proto"
PYTHON_OUT="$(cd "$(dirname "$0")/.." && pwd)/python/bridge"

echo "Generating C++ protobuf code..."
protoc -I=$PROTO_DIR --cpp_out=$CPP_OUT $PROTO_DIR/chat.proto

echo "Generating Java protobuf code..."
protoc -I=$PROTO_DIR --java_out=$JAVA_OUT $PROTO_DIR/chat.proto

echo "Generating Python protobuf code..."
protoc -I=$PROTO_DIR --python_out=$PYTHON_OUT $PROTO_DIR/chat.proto

echo "Protobuf code generation completed!"
echo "C++ headers: $CPP_OUT"
echo "Java sources: $JAVA_OUT"
echo "Python sources: $PYTHON_OUT"
