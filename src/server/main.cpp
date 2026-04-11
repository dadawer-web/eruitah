#include"chatserver.hpp"
#include"chatservice.hpp"
#include<iostream>
#include<signal.h>
using namespace std;

// 信号处理函数 - 服务器资源清理
// 业务逻辑：确保服务器异常终止时的数据一致性和资源正确释放
void resetHandler(int){    
    // 调用聊天服务单例执行重置操作
    // 关键业务：将所有在线用户状态重置为离线，防止用户被错误标记为在线
    ChatService::instance()->reset();
    // 终止进程
    exit(0);
}

// 主函数 - 服务器程序入口
// 业务逻辑：初始化和启动聊天服务器，包括网络配置、信号处理和事件循环
int main(int argc, char **argv){
    // 参数校验 - 确保提供了必要的网络参数
    if (argc < 3)
    {
        cerr << "command invalid! example: ./ChatServer 127.0.0.1 6000" << endl;
        exit(-1);
    }

    // 解析命令行参数 - 实现服务器配置的动态化
    // 设计亮点：支持通过命令行动态指定监听地址和端口，提高部署灵活性
    char *ip = argv[1];
    uint16_t port = atoi(argv[2]);

    // 注册信号处理函数 - 实现优雅退出机制
    // 关键设计：捕获SIGINT信号(Ctrl+C)，在服务器意外终止前执行资源清理
    signal(SIGINT, resetHandler);

    // 创建事件循环对象 - 事件驱动架构的核心组件
    // 业务说明：EventLoop是muduo网络库的核心，负责事件监听和分发
    EventLoop loop;
    
    // 创建网络地址对象 - 配置服务器监听地址
    InetAddress addr(ip, port);
    
    // 创建聊天服务器对象 - 初始化服务器实例
    // 设计模式：组合模式，将事件循环注入到服务器对象中
    ChatServer server(&loop, addr, "ChatServer");

    // 初始化ChatService单例 - 确保Redis连接和订阅在服务器启动前完成
    // 关键业务：提前初始化单例，建立Redis连接，订阅GROUP_DISPATCH_CHANNEL
    ChatService::instance();

    // 启动服务器 - 开始接受客户端连接请求
    // 内部逻辑：创建监听套接字，注册读事件，准备接受新连接
    server.start();
    
    // 启动事件循环 - 服务器主循环
    // 关键业务：阻塞等待并处理各类事件（新连接、消息收发等）
    loop.loop();

    return 0;
}

// 以下是Nginx TCP负载均衡配置的说明（非代码部分）
/*
# Nginx TCP负载均衡配置示例
stream{
    upstream MyServer{// 定义后端服务器组（负载均衡池）
        server 127.0.0.1:6000 weight=1 max_fails=3 fail_timeout=30s;
        // 服务器节点1：权重1，最大失败次数3次，失败超时30秒
        server 127.0.0.1:6002 weight=1 max_fails=3 fail_timeout=30s;
        // 服务器节点2：权重1，与节点1相同配置
    }

    server{
        proxy_connect_timeout 1s; // 与后端服务器建立连接的超时时间
        #proxy_timeout 3s; // 连接超时时间（当前被注释）
        listen 8000; // 监听8000端口
        proxy_pass MyServer; // 请求转发到后端服务器组
        tcp_nodelay on; // 禁用Nagle算法，提高实时性
    }
}

// 部署说明：
// 引入Nginx负载均衡后，启动多台服务器实例：
// ./ChatServer 127.0.0.1 6000 （服务器实例1）
// ./ChatServer 127.0.0.1 6002 （服务器实例2）
// 客户端连接时连接到Nginx：
// ./ChatClient 127.0.0.1 8000
*/