#include "chat_server.h"
#include <muduo/base/Logging.h>
#include <signal.h>

using namespace muduo;
using namespace muduo::net;

EventLoop* g_loop = nullptr;

void signalHandler(int sig) {
    if (g_loop) {
        g_loop->quit();
    }
}

int main(int argc, char* argv[]) {
    LOG_INFO << "Starting ChatServer (C++ muduo -> Java backend bridge)";
    
    signal(SIGINT, signalHandler);
    signal(SIGTERM, signalHandler);
    
    EventLoop loop;
    g_loop = &loop;
    
    InetAddress listenAddr(8888);
    InetAddress javaBackendAddr(9999, "127.0.0.1");
    
    ChatServer server(&loop, listenAddr, javaBackendAddr);
    server.setThreadNum(4);
    server.start();
    
    LOG_INFO << "ChatServer listening on port 8888";
    LOG_INFO << "Connecting to Java backend at 127.0.0.1:9999";
    
    loop.loop();
    
    LOG_INFO << "ChatServer stopped";
    return 0;
}
