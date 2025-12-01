// 头文件保护宏，防止头文件被重复包含
#ifndef PUBLIC_H
#define PUBLIC_H

// 消息类型枚举定义
// enum是C++中的枚举类型，用于定义一组命名的整数值
// 每个枚举值都有一个整数值，默认从0开始递增，但这里明确指定了起始值为1
enum MsgType {
    // 登录相关消息类型
    LOGIN_MSG = 1,          // 登录请求消息，客户端发送给服务器
    LOGIN_MSG_ACK = 2,      // 登录响应消息，服务器返回给客户端
    LOGINOUT_MSG = 3,       // 注销消息，用户退出登录时发送
    REG_MSG = 4,            // 注册请求消息，新用户注册时发送
    REG_MSG_ACK = 5,        // 注册响应消息，服务器返回注册结果
    
    // 聊天相关消息类型
    ONE_CHAT_MSG = 6,       // 一对一聊天消息，用户发送给单个好友
    GROUP_CHAT_MSG = 7,     // 群聊消息，用户发送给群组所有成员
    
    // 好友相关消息类型
    ADD_FRIEND_MSG = 8,     // 添加好友请求消息
    ADD_FRIEND_MSG_ACK = 9, // 添加好友响应消息，返回添加结果
    
    // 群组相关消息类型
    CREATE_GROUP_MSG = 10,  // 创建群组请求消息
    ADD_GROUP_MSG = 11,     // 加入群组请求消息
    ADD_GROUP_MSG_ACK = 12, // 加入群组响应消息
    CREATE_GROUP_MSG_ACK = 13, // 创建群组响应消息
    GROUP_CHAT_MSG_ACK = 14, // 群聊响应消息
    
    // 查询相关消息类型
    QUERY_FRIEND_MSG = 15,  // 查询好友列表请求消息
    QUERY_FRIEND_MSG_ACK = 16, // 查询好友列表响应消息
    QUERY_GROUP_MSG = 17,   // 查询群组列表请求消息
    QUERY_GROUP_MSG_ACK = 18 // 查询群组列表响应消息
};

// 数据库表名常量定义
// static const char* 定义了不可修改的字符串常量，用于数据库操作中指定表名
static const char* TABLE_USER = "user";              // 用户表，存储用户基本信息
static const char* TABLE_FRIEND = "friend";          // 好友表，存储好友关系
static const char* TABLE_ALLGROUP = "allgroup";      // 群组表，存储群组基本信息
static const char* TABLE_GROUPUSER = "groupuser";    // 群成员表，存储群组成员关系
static const char* TABLE_OFFLINEMESSAGE = "offlinemessage"; // 离线消息表，存储用户离线时的消息

// 服务器默认端口定义
// 静态常量，定义服务器程序默认监听的端口号
static const int DEFAULT_SERVER_PORT = 8000;

#endif // PUBLIC_H  // 头文件保护宏结束