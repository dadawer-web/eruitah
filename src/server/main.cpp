#include"chatserver.hpp"
#include"chatservice.hpp"
#include<iostream>
#include<signal.h>
using namespace std;

//处理服务器Ctrl+C退出后，重置用户user的在线状态
void resetHandler(int){
    ChatService::instance()->reset();
    exit(0);
}
int main(int argc, char **argv){
if (argc < 3)
    {
        cerr << "command invalid! example: ./ChatServer 127.0.0.1 6000" << endl;
        exit(-1);
    }

    // 解析通过命令行参数传递的ip和port
    char *ip = argv[1];
    uint16_t port = atoi(argv[2]);

    signal(SIGINT, resetHandler);

    EventLoop loop;
    InetAddress addr(ip, port);
    ChatServer server(&loop, addr, "ChatServer");

    server.start();
    loop.loop();

    return 0;
}
//nginx.conf
//#nginx tcp loadbalance config
/*stream{
        upstream MyServer{//定义名为 MyServer 的后端服务器组（负载均衡池）
                server 127.0.0.1:6000 weight=1 max_fails=3 fail_timeout=30s;//一台服务器地址127.0.0.1 权重1，最大失败次数为 3 次,失败超时时间 30 秒（超过 3 次失败后，30 秒内不再向该服务器转发请求）
                server 127.0.0.1:6002 weight=1  max_fails=3 fail_timeout=30s;
        }

        server{
                proxy_connect_timeout 1s;与后端服务器建立连接的超时时间为 1 秒
                #proxy_timeout 3s;被注释的配置，如果取消注释表示：客户端与 Nginx 之间，或 Nginx 与后端服务器之间的连接超时时间为 3 秒3 秒内没有数据传输则关闭连接
                listen 8000;//监听8000端口
                proxy_pass MyServer;//进入MyServer
                tcp_nodelay on;
        }
}*/
//引入nginx之后./ChatServer 127.0.0.1 6000  ./ChatServer 127.0.0.1 6002 连接的时候变为./ChatClient 127.0.0.1 8000