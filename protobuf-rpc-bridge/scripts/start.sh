#!/bin/bash

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "Starting Protobuf RPC Bridge System..."

echo "Starting Java backend server on port 9999..."
java -jar "$PROJECT_ROOT/java/target/protobuf-rpc-bridge-1.0.0.jar" &
JAVA_PID=$!
echo "Java backend PID: $JAVA_PID"

sleep 2

echo "Starting C++ muduo server on port 8888..."
"$PROJECT_ROOT/cpp/build/bin/chat_server" &
CPP_PID=$!
echo "C++ server PID: $CPP_PID"

echo ""
echo "========================================="
echo "System started successfully!"
echo "========================================="
echo "Java backend: http://localhost:9999"
echo "C++ bridge:   http://localhost:8888"
echo ""
echo "To stop the system, run: kill $JAVA_PID $CPP_PID"
echo ""

wait
