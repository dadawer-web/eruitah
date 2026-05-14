#include"chatserver.hpp"
#include"chatservice.hpp"
#include<iostream>
#include<signal.h>
#include<cstdlib>
#include<string>

using namespace std;

EventLoop* g_loop = nullptr;

void signalHandler(int){
    LOG_INFO << "Received shutdown signal, gracefully stopping...";
    ChatService::instance()->reset();
    if (g_loop) {
        g_loop->queueInLoop([](){
            g_loop->quit();
        });
    }
}

int main(int argc, char **argv){
    if (argc < 3)
    {
        cerr << "command invalid! example: ./ChatServer 127.0.0.1 6000" << endl;
        exit(-1);
    }

    char *ip = argv[1];
    uint16_t port = atoi(argv[2]);

    EventLoop loop;
    g_loop = &loop;

    signal(SIGINT, signalHandler);
    signal(SIGTERM, signalHandler);

    InetAddress addr(ip, port);

    ChatServer server(&loop, addr, "ChatServer");

    ChatService::instance();

    string javaHost = getenv("JAVA_RPC_HOST") ? getenv("JAVA_RPC_HOST") : "127.0.0.1";
    int javaPort = getenv("JAVA_RPC_PORT") ? atoi(getenv("JAVA_RPC_PORT")) : 9999;
    int rpcListenPort = getenv("RPC_LISTEN_PORT") ? atoi(getenv("RPC_LISTEN_PORT")) : 8888;

    InetAddress javaRpcAddr(javaHost.c_str(), javaPort);
    InetAddress rpcListenAddr("0.0.0.0", rpcListenPort);
    ChatService::instance()->initRpc(&loop, javaRpcAddr, rpcListenAddr);

    server.start();

    loop.loop();

    LOG_INFO << "ChatServer exited cleanly";
    g_loop = nullptr;

    return 0;
}
