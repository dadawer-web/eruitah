// 头文件保护宏，防止头文件被重复包含
// 当第一次包含这个头文件时，CHATSERVER_H宏未定义，会定义它并包含下面的内容
// 当再次尝试包含这个头文件时，由于CHATSERVER_H已定义，会跳过包含内容
#ifndef CHATSERVER_H
#define CHATSERVER_H

// 包含必要的标准库头文件
#include <map>
#include <string>
#include <cstring> // 用于memcpy
#include <cstdint> // 用于uint32_t
#include <arpa/inet.h> // 用于ntohl

// 包含Muduo网络库的Logging头文件，用于日志功能
#include <muduo/base/Logging.h>

// 包含Muduo网络库的TcpServer头文件，用于实现TCP服务器功能
#include <muduo/net/TcpServer.h>
// 包含Muduo网络库的EventLoop头文件，用于事件循环管理
#include <muduo/net/EventLoop.h>

// 使用命名空间别名，简化代码中的命名空间引用
// 这样可以直接使用TcpServer而不是muduo::net::TcpServer
using namespace muduo;
using namespace muduo::net;

// 聊天服务器主类
// 该类封装了基于Muduo网络库的聊天服务器功能
class ChatServer
{
public:
    // 构造函数，初始化聊天服务器对象
    // 参数loop: 事件循环对象指针，负责监听和分发IO事件
    // 参数listenAddr: 服务器监听的网络地址，包含IP和端口
    // 参数nameArg: 服务器名称，用于日志和调试
    ChatServer(EventLoop *loop, const InetAddress& listenAddr, const string& nameArg);
    
    // 启动服务器
    void start();
private:
    // 连接回调函数，当有新的客户端连接建立或断开时被调用
    // 参数conn: 连接对象的智能指针，封装了连接信息和操作方法
    // TcpConnectionPtr是一个智能指针类型，指向TcpConnection对象
    void onConnection(const TcpConnectionPtr &conn);
    
    // 消息回调函数，当客户端发送数据到服务器时被调用
    // 参数conn: 连接对象的智能指针
    // 参数buffer: 数据缓冲区指针，包含接收到的数据
    // 参数time: 接收到数据的时间戳
    void onMessage(const TcpConnectionPtr &conn, Buffer *buffer, Timestamp time);
    
    // 处理单个JSON消息的辅助方法
    // 参数conn: 连接对象的智能指针
    // 参数message: 消息字符串内容
    // 参数time: 消息接收时间戳
    void processSingleMessage(const TcpConnectionPtr &conn, const string& message, Timestamp time);
    
    EventLoop *_loop;  // 指向事件循环对象的指针
                      // EventLoop是Muduo库的核心类，负责管理和调度所有IO事件
    
    TcpServer _server; // 组合的Muduo库TcpServer对象
                      // TcpServer封装了TCP服务器的功能，包括监听端口、接受连接等
    
    // 为每个连接维护消息缓冲区，用于处理粘包问题
    // 键：连接对象的智能指针
    // 值：该连接对应的消息缓冲区
    std::map<TcpConnectionPtr, std::string> _messageBuffers;
};

#endif // CHATSERVER_H  // 头文件保护宏结束标记