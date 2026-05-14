set(MUDUO_ROOT_DIR "/home/xmy/muduo")

set(RPC_BRIDGE_DIR "${PROJECT_SOURCE_DIR}/protobuf-rpc-bridge/cpp")

include_directories(${MUDUO_ROOT_DIR}/include)
include_directories(${PROJECT_SOURCE_DIR}/src)
include_directories(${PROJECT_SOURCE_DIR}/include)
include_directories(${PROJECT_SOURCE_DIR}/include/server)
include_directories(${PROJECT_SOURCE_DIR}/include/server/rpc)
include_directories(${RPC_BRIDGE_DIR}/include)
include_directories(${RPC_BRIDGE_DIR}/include/proto)

link_directories(${MUDUO_ROOT_DIR}/build/lib)

find_package(Qt5 COMPONENTS Core Network REQUIRED)
find_package(Protobuf REQUIRED)

aux_source_directory(. SRC_LIST)
aux_source_directory(./db DB_LIST)
aux_source_directory(./model MODEL_LIST)
aux_source_directory(./redis REDIS_LIST)
aux_source_directory(./rpc RPC_LIST)

add_executable(ChatServer 
    ${SRC_LIST} 
    ${DB_LIST} 
    ${MODEL_LIST} 
    ${REDIS_LIST} 
    ${RPC_LIST}
    ../chatserver.cpp 
    ../public.h 
    ${RPC_BRIDGE_DIR}/src/protobuf_codec.cc
    ${RPC_BRIDGE_DIR}/src/rpc_channel.cc
    ${RPC_BRIDGE_DIR}/include/proto/chat.pb.cc
)

target_include_directories(ChatServer PRIVATE ${Protobuf_INCLUDE_DIRS})

target_link_libraries(ChatServer 
    Qt5::Core Qt5::Network 
    muduo_net muduo_base 
    pthread mysqlclient hiredis crypto
    protobuf z
)

set_target_properties(ChatServer PROPERTIES
    AUTOMOC ON
)
