cmake_minimum_required(VERSION 3.10)
project(protobuf_rpc_bridge CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Protobuf REQUIRED)
find_package(muduo REQUIRED)

include_directories(
    ${CMAKE_SOURCE_DIR}/include
    ${Protobuf_INCLUDE_DIRS}
)

set(PROTO_SRCS
    ${CMAKE_SOURCE_DIR}/include/chat.pb.cc
)

set(SERVER_SRCS
    src/main.cc
    src/chat_server.cc
    src/protobuf_codec.cc
    src/rpc_channel.cc
    ${PROTO_SRCS}
)

add_executable(chat_server ${SERVER_SRCS})

target_link_libraries(chat_server
    ${Protobuf_LIBRARIES}
    muduo_net
    muduo_base
    pthread
    z
)

set_target_properties(chat_server PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin
)
