#include "redis.hpp"
#include <iostream>
#include<muduo/base/Logging.h>
using namespace std;

// 构造函数 - Redis客户端初始化
// 业务逻辑：初始化Redis发布和订阅上下文指针，为分布式消息通信做准备
Redis::Redis()
    : _publish_context(nullptr), _subcribe_context(nullptr)
{
}

// 析构函数 - 资源清理
// 业务逻辑：安全释放Redis连接资源，避免内存泄漏和连接资源浪费
Redis::~Redis()
{
    // 释放发布上下文资源
    if (_publish_context != nullptr)
    {
        redisFree(_publish_context);
    }

    // 释放订阅上下文资源
    if (_subcribe_context != nullptr)
    {
        redisFree(_subcribe_context);
    }
}

// 连接Redis服务器 - 分布式通信基础
// 业务逻辑：建立与Redis服务器的双连接（发布和订阅），支持分布式消息转发
bool Redis::connect()
{
    // 建立发布消息上下文连接
    // 关键业务：独立的发布连接确保消息发送不受订阅阻塞影响
    _publish_context = redisConnect("127.0.0.1", 6379);
    if (nullptr == _publish_context)
    {
        cerr << "connect redis failed!" << endl;
        return false;
    }

    // 发布连接密码认证
    redisReply *reply = (redisReply *)redisCommand(_publish_context, "AUTH %s", "123456");
    if (nullptr == reply || reply->type == REDIS_REPLY_ERROR)
    {
        cerr << "redis auth failed!" << endl;
        if (reply) {
            freeReplyObject(reply);
        }
        // 连接失败时资源清理
        redisFree(_publish_context);
        _publish_context = nullptr;
        return false;
    }
    freeReplyObject(reply);

    // 建立订阅消息上下文连接
    // 关键业务：独立的订阅连接支持异步消息接收
    _subcribe_context = redisConnect("127.0.0.1", 6379);
    if (nullptr == _subcribe_context)
    {
        cerr << "connect redis failed!" << endl;
        // 错误处理：释放已成功连接的发布上下文
        redisFree(_publish_context);
        _publish_context = nullptr;
        return false;
    }

    // 订阅连接密码认证
    reply = (redisReply *)redisCommand(_subcribe_context, "AUTH %s", "123456");
    if (nullptr == reply || reply->type == REDIS_REPLY_ERROR)
    {
        cerr << "redis auth failed!" << endl;
        if (reply) {
            freeReplyObject(reply);
        }
        // 错误处理：释放所有已分配资源
        redisFree(_publish_context);
        redisFree(_subcribe_context);
        _publish_context = nullptr;
        _subcribe_context = nullptr;
        return false;
    }
    freeReplyObject(reply);

    // 启动异步消息监听线程
    // 关键业务：在独立线程中处理订阅消息，避免阻塞主业务流程
    thread t([&]() {
        observer_channel_message();
    });
    t.detach();  // 线程分离，由系统自动回收

    cout << "connect redis-server success!" << endl;

    return true;
}

// 发布消息 - 分布式消息广播
// 业务逻辑：向指定Redis通道发布消息，支持跨服务器节点的消息传递
bool Redis::publish(int channel, string message)
{
    // 参数有效性检查
    if (nullptr == _publish_context)
    {
        cerr << "publish context is null!" << endl;
        return false;
    }
    
    // 执行Redis发布命令
    // 关键业务：将消息广播到所有订阅该通道的服务节点
    redisReply *reply = (redisReply *)redisCommand(_publish_context, "PUBLISH %lld %s", (long long)channel, message.c_str());
    if (nullptr == reply)
    {
        cerr << "publish command failed!" << endl;
        return false;
    }
    
    // 资源清理
    freeReplyObject(reply);
    return true;
}

// 订阅消息 - 分布式消息接收
// 业务逻辑：订阅指定Redis通道，准备接收来自其他服务器节点的消息
bool Redis::subscribe(int channel)
{
    // 使用redisAppendCommand而非redisCommand避免阻塞
    // 关键设计：非阻塞式订阅，消息接收在独立线程中进行
    if (REDIS_ERR == redisAppendCommand(this->_subcribe_context, "SUBSCRIBE %lld", (long long)channel))
    {
        cerr << "subscribe command failed!" << endl;
        return false;
    }
    
    // 循环发送缓冲区数据
    int done = 0;
    while (!done)
    {
        if (REDIS_ERR == redisBufferWrite(this->_subcribe_context, &done))
        {
            cerr << "subscribe command failed!" << endl;
            return false;
        }
    }
    
    return true;
}

// 取消订阅 - 资源管理
// 业务逻辑：取消对指定Redis通道的订阅，避免接收不必要的消息
bool Redis::unsubscribe(int channel)
{
    // 非阻塞式取消订阅
    if (REDIS_ERR == redisAppendCommand(this->_subcribe_context, "UNSUBSCRIBE %lld", (long long)channel))
    {
        cerr << "unsubscribe command failed!" << endl;
        return false;
    }
    
    // 循环发送缓冲区数据
    int done = 0;
    while (!done)
    {
        if (REDIS_ERR == redisBufferWrite(this->_subcribe_context, &done))
        {
            cerr << "unsubscribe command failed!" << endl;
            return false;
        }
    }
    return true;
}

// 异步消息监听 - 分布式消息处理核心
// 业务逻辑：在独立线程中持续监听订阅通道的消息，并通过回调函数转发给业务层
void Redis::observer_channel_message()
{
    // 持续监听消息的无限循环
    while(true)
    {
        redisReply *reply = nullptr;
        // 阻塞式获取回复
        if(redisGetReply(this->_subcribe_context, (void **)&reply) != REDIS_OK)
        {
            LOG_ERROR << "Get reply error!";
            // 错误处理：避免访问无效的reply对象
            continue;
        }

        // 处理接收到的消息
        if(reply != nullptr)
        {
            // 验证消息格式是否为有效的Redis消息数组
            if(reply->type == REDIS_REPLY_ARRAY && reply->elements >= 3)
            {
                // 确认消息类型并提取通道和消息内容
                if(strcmp(reply->element[0]->str, "message") == 0)
                {
                    int channel = atoi(reply->element[1]->str);
                    string msg = reply->element[2]->str;
                    // 通过回调函数将消息传递给业务层处理
                    _notify_message_handler(channel, msg);
                }
            }
            // 释放回复对象资源
            freeReplyObject(reply);
        }
    }
}

// 初始化消息通知回调 - 业务层集成
// 业务逻辑：设置消息处理回调函数，实现Redis消息与业务层的解耦
void Redis::init_notify_handler(function<void(int,string)> fn)
{
    // 设置回调函数，用于处理接收到的Redis消息
    this->_notify_message_handler = fn;
}