cmake_minimum_required(VERSION 3.0)
project(main)

#配置编译选项
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -g ")

#设置可执行文件最终存储路径,server
set(EXECUTABLE_OUTPUT_PATH ${PROJECT_SOURCE_DIR}/bin)
# 设置 muduo 路径
set(MUDUO_ROOT_DIR "/home/xmy/muduo")
#配置头文件搜索路径
include_directories(${MUDUO_ROOT_DIR}/include)
#配置库文件搜索路径
link_directories(${MUDUO_ROOT_DIR}/build/lib)

#设置需要编译的源文件列表
set(SRC_LIST ./muduo_server.cpp)

#如果有很多文件，把.指定路径下所有源文件的名字放入变量名SRC_LIST中
#aux_source_directory(. SRC_LIST)

#表示生成可执行文件server，由SRC_LIST变量指定的源文件编译而成
add_executable(server ${SRC_LIST})
#表示server这个目标程序需要链接muduo_net muduo-base pthread几个库文件
target_link_libraries(server muduo_net muduo_base pthread)

#最后在终端中进入目录，执行cmake . 生成Makefile
#然后执行make命令进行编译，生成可执行文件server
#执行./server 运行可执行文件
## 清理之前的构建文件
#rm -rf CMakeCache.txt CMakeFiles cmake_install.cmake Makefile
