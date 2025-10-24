#设置 muduo 路径
set(MUDUO_ROOT_DIR "/home/xmy/muduo")
#配置头文件搜索路径
include_directories(${MUDUO_ROOT_DIR}/include)
#配置库文件搜索路径
link_directories(${MUDUO_ROOT_DIR}/build/lib)
#定义了应该SRC_LIST变量,包含了该目录下所有的源文件
aux_source_directory(. SRC_LIST)
aux_source_directory(./db DB_LIST)
aux_source_directory(./model MODEL_LIST)
aux_source_directory(./redis REDIS_LIST)
#指定生成可执行文件
add_executable(ChatServer ${SRC_LIST} ${DB_LIST} ${MODEL_LIST} ${REDIS_LIST} )
#指定可执行文件所依赖的库
target_link_libraries(ChatServer muduo_net muduo_base pthread mysqlclient hiredis)