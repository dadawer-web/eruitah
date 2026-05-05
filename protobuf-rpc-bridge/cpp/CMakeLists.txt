cmake_minimum_required(VERSION 3.10)
project(protobuf_rpc_bridge CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Protobuf REQUIRED)

set(MUDUO_INCLUDE_DIR "/usr/local/include")
set(MUDUO_LIB_DIR "/usr/local/lib")

include_directories(
    ${CMAKE_SOURCE_DIR}/include
    ${Protobuf_INCLUDE_DIRS}
    ${MUDUO_INCLUDE_DIR}
)

link_directories(${MUDUO_LIB_DIR})

set(PROTO_SRCS
    ${CMAKE_SOURCE_DIR}/include/chat.pb.cc
)

add_executable(chat_server
    src/main.cc
    src/chat_server.cc
    src/protobuf_codec.cc
    src/rpc_channel.cc
    ${PROTO_SRCS}
)

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

add_executable(crosslang_test
    src/crosslang_test.cc
    ${PROTO_SRCS}
)

target_link_libraries(crosslang_test
    ${Protobuf_LIBRARIES}
    z
)

set_target_properties(crosslang_test PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin
)
