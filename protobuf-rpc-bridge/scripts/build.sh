#!/bin/bash

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="$PROJECT_ROOT/build"

echo "========================================="
echo "Building Protobuf RPC Bridge System"
echo "========================================="

echo ""
echo "1. Generating Protobuf code..."
"$PROJECT_ROOT/scripts/generate_proto.sh"

echo ""
echo "2. Building C++ muduo server..."
mkdir -p "$PROJECT_ROOT/cpp/build"
cd "$PROJECT_ROOT/cpp/build"
cmake ..
make -j$(nproc)

echo ""
echo "3. Building Java backend..."
cd "$PROJECT_ROOT/java"
mvn clean package -DskipTests

echo ""
echo "========================================="
echo "Build completed successfully!"
echo "========================================="
echo ""
echo "Executables:"
echo "  C++ server: $PROJECT_ROOT/cpp/build/bin/chat_server"
echo "  Java server: $PROJECT_ROOT/java/target/protobuf-rpc-bridge-1.0.0.jar"
echo ""
