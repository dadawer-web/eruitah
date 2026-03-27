#设置 muduo 路径
set(MUDUO_ROOT_DIR "/home/xmy/muduo")
#配置头文件搜索路径
include_directories(${MUDUO_ROOT_DIR}/include)
include_directories(${PROJECT_SOURCE_DIR}/src)
include_directories(${PROJECT_SOURCE_DIR}/include)
include_directories(${PROJECT_SOURCE_DIR}/include/server)
#配置库文件搜索路径
link_directories(${MUDUO_ROOT_DIR}/build/lib)

#查找Qt包（因为chatserver.h依赖QObject）
find_package(Qt5 COMPONENTS Core Network REQUIRED)

#定义源文件列表
aux_source_directory(. SRC_LIST)
aux_source_directory(./db DB_LIST)
aux_source_directory(./model MODEL_LIST)
aux_source_directory(./redis REDIS_LIST)

#指定生成可执行文件，包含服务器相关的共享源文件
add_executable(ChatServer 
    ${SRC_LIST} 
    ${DB_LIST} 
    ${MODEL_LIST} 
    ${REDIS_LIST} 
    ../chatserver.cpp 
    ../public.h 
)

#指定可执行文件所依赖的库
target_link_libraries(ChatServer Qt5::Core Qt5::Network muduo_net muduo_base pthread mysqlclient hiredis crypto curl)

#启用Qt的MOC处理
set_target_properties(ChatServer PROPERTIES
    AUTOMOC ON
)