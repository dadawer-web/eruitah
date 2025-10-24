/*
muduo网络库给用户提供两个主要的类
TcpServer：用于编写服务器程序
TcpClient：用于编写客户端程序

epoll+线程池
好处；能够把网络I/O和用户逻辑处理分开
                用户的连接和断开  用户的可读写事件

*/
#include <muduo/net/TcpServer.h>
#include <muduo/net/EventLoop.h>
#include<iostream>
#include<functional>
#include<string>
using namespace std;
using namespace muduo;
using namespace muduo::net;
using namespace placeholders;//占位符
/*基于网络库开发服务器程序
    1.组合TcpServer对象
    2.创建EventLoop事件循环对象的指针
    3.明确TcpServer构造函数需要传递的参数TcpServer(EventLoop* loop,
            const InetAddress& listenAddr,
            const string& nameArg,
            Option option = kNoReusePort);,输出ChatServer的构造函数
    4.在当前服务器类的构造函数，注册处理连接的回调函数和处理读写事件的回调函数
    5.设置合适的线程数量，muduo库会自己分配I/O线程和worker线程
*/
class ChatServer
{
public:
    ChatServer(EventLoop *loop,//事件循环
               const InetAddress &listenAddr,//IP+Port
               const string &nameArg)//服务器的名字
               :_server(loop,listenAddr,nameArg),_loop(loop)//3.明确TcpServer构造函数需要传递的参数
    {
        //给服务器注册用户连接的创建和断开回调
        _server.setConnectionCallback(
            std::bind(&ChatServer::onConnection,this,_1));
        //给服务器注册用户读写事件回调
        _server.setMessageCallback(
            std::bind(&ChatServer::onMessage,this,_1,_2,_3));
        //设置服务器端的线程数量 
        _server.setThreadNum(4);//1个I/O线程 3个worker线程
    }
    //开启事件循环
    void start()
    {
        _server.start();//epoll_wait
    }
private:
    //主要精力在处理onConnection和onMessage
    //专门处理用户连接创建和断开 epoll listenfd accept
    void onConnection(const TcpConnectionPtr &conn)
    {         
        if(conn->connected())//连接
        {
            cout<<conn->peerAddress().toIpPort()
                <<"-->"<<conn->localAddress().toIpPort()
                <<" state:online"<<endl;
        }
        else//断开
        {
            cout<<conn->peerAddress().toIpPort()
                <<"-->"<<conn->localAddress().toIpPort()
                <<" state:offline"<<endl;
            conn->shutdown();//close(fd)
           //loop->quit();//让底层的epoll退出
        }
    }
    //专门处理用户的读写事件
    void onMessage(const TcpConnectionPtr &conn,//连接
                   Buffer *buffer,//缓冲区
                   Timestamp time)//接收数据的时间信息
    {
        string buf=buffer->retrieveAllAsString();//把接收的数据从缓冲区取出，放到字符串中
        cout<<"recv data:"<<buf<<" time:"<<time.toString()<<endl;
        conn->send(buf);//回显给客户端
    }
    TcpServer _server;//1.组合TcpServer对象
    EventLoop *_loop;//2.创建EventLoop事件循环对象的指针\\epoll
};
 int main()
 {
        EventLoop loop;//Reactor事件循环 epoll
        InetAddress addr("127.0.0.1",6000);//IP+Port
        ChatServer server(&loop,addr,"ChatServer");//3.明确TcpServer构造函数需要传递的参数
        server.start();//开启事件循环,listenfd epoll_ctl->epoll
        loop.loop();//epoll_wait以阻塞方式等待新用户连接，已连接用户的读写事件等
        return 0;
 }
 //cd testmuduo
 // g++ -o muduo_server muduo_server.cpp \
    /home/xmy/muduo/build/lib/libmuduo_net.a \
    /home/xmy/muduo/build/lib/libmuduo_base.a \
    -lpthread -std=c++11
 //./muduo_server
 //另一个终端
 //telnet 127.0.0.1 6000
//输入数据，回显
 //先按下 Ctrl + ]然后你会看到 telnet> 提示符
// quit 或 exit 然后回车
//第一个终端ctrl+c退出



//ctrl+shift+b
//选择C/C++: g++ 生成活动文件
//终端运行 ./muduo_server
//telnet