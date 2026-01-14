#include"chatserver.hpp"
#include"json.hpp"
#include<functional>
#include<string>
#include"chatservice.hpp"
using namespace std;
using namespace placeholders;
using json=nlohmann::json;
//初始化服务器对象
ChatServer::ChatServer(EventLoop* loop,
                         const InetAddress& listenAddr,
                         const string& nameArg)
  : _server(loop, listenAddr, nameArg),_loop(loop)
  {
    //注册链接回调
    _server.setConnectionCallback(
        std::bind(&ChatServer::onConnection, this, _1));
    //注册信息回调
    _server.setMessageCallback(
        std::bind(&ChatServer::onMessage, this, _1, _2, _3));
    //设置合适的线程数量
    _server.setThreadNum(4);
  }
   
 //启动服务
    void ChatServer::start(){
       _server.start();
    }
//上报连接相关信息的回调函数
    void ChatServer:: onConnection(const TcpConnectionPtr &conn){
        //客户端断开连接 
        if(!conn->connected()){
            ChatService::instance()->clientCloseException(conn);
            conn->shutdown();
        }

    }
    //上报读写事件相关信息的回调函数
    void ChatServer::onMessage(const TcpConnectionPtr &conn, Buffer *buffer, Timestamp time){
        string buf=buffer->retrieveAllAsString();
        
        // 将新数据追加到连接的消息缓冲区
        _messageBuffers[conn] += buf;
        
        // 循环处理缓冲区中的数据
        while (true) {
            string &messageBuffer = _messageBuffers[conn];
            
            // 检查缓冲区大小是否足够读取长度前缀
            if (messageBuffer.size() < 4) {
                break; // 数据不足，等待更多数据
            }
            
            // 读取长度前缀（大端字节序）
            uint32_t length = 0;
            memcpy(&length, messageBuffer.data(), sizeof(uint32_t));
            // 转换为大端字节序
            length = ntohl(length);
            
            // 检查缓冲区是否包含完整的消息
            if (messageBuffer.size() < sizeof(uint32_t) + length) {
                break; // 数据不足，等待更多数据
            }
            
            // 提取完整的JSON数据
            string jsonStr(messageBuffer.data() + sizeof(uint32_t), length);
            
            // 从缓冲区中移除已处理的数据
            messageBuffer.erase(0, sizeof(uint32_t) + length);
            
            try {
                // 数据的反序列化
                json js=json::parse(jsonStr);
                //达到的目的：完全解耦网络模块的代码和业务模块的代码
                //通过js["msgid"]获取=>业务handler=>conn js time
                int msgid = -1;
                if (js.contains("msgid") && js["msgid"].is_number()) {
                    msgid = js["msgid"].get<int>();
                } else if (js.contains("type") && js["type"].is_number()) {
                    msgid = js["type"].get<int>();
                } else {
                    continue;
                }
                auto msgHandler=ChatService::instance()->getHandler(msgid);
                //回调消息绑定好的事件处理器，来执行相应的业务处理
                msgHandler(conn,js,time);
            } catch (const json::exception& e) {
                // 捕获JSON解析异常
                LOG_ERROR << "JSON parse error: " << e.what();
                LOG_ERROR << "Invalid JSON string: " << jsonStr;
                // 发送错误响应给客户端
                json response;
                response["msgid"] = 999; // 自定义错误消息类型
                response["errno"] = 5;
                response["errmsg"] = "JSON parse error: " + string(e.what());
                conn->send(response.dump() + "\n");
            } catch (const exception& e) {
                // 捕获其他异常
                LOG_ERROR << "Exception in message handling: " << e.what();
                // 发送错误响应给客户端
                json response;
                response["msgid"] = 999; // 自定义错误消息类型
                response["errno"] = 6;
                response["errmsg"] = "Internal server error: " + string(e.what());
                conn->send(response.dump() + "\n");
            }
        }
    }
    //外网是0.0.0.0 6000