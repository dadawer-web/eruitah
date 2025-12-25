// 头文件保护宏，防止头文件被重复包含
#ifndef PUBLIC_H
#define PUBLIC_H

// 消息类型枚举定义
// 统一使用与服务器端相同的消息类型定义，确保客户端和服务器端消息类型一致
enum MsgType {
    LOGIN_MSG=1,            // Login request message
    LOGIN_MSG_ACK,          // Login response message
    LOGINOUT_MSG,           // Logout message
    REG_MSG,                // Registration request message
    REG_MSG_ACK,            // Registration response message
    ONE_CHAT_MSG,           // One-to-one chat message
    ADD_FRIEND_MSG,         // Add friend request message
    ADD_FRIEND_MSG_ACK,     // Add friend response message
    QUERY_FRIEND_MSG,       // Query friend list request message
    QUERY_FRIEND_MSG_ACK,   // Query friend list response message
    QUERY_GROUP_MSG,        // Query group list request message
    QUERY_GROUP_MSG_ACK,    // Query group list response message

    CREATE_GROUP_MSG,       // Create group request message
    CREATE_GROUP_MSG_ACK,   // Create group response message
    ADD_GROUP_MSG,          // Join group request message
    ADD_GROUP_MSG_ACK,      // Join group response message
    GROUP_CHAT_MSG,         // Group chat message
    
    // File transfer related message types
    FILE_TRANSFER_REQ=20,   // File transfer request
    FILE_TRANSFER_ACK,      // File transfer response
    FILE_TRANSFER_DATA,     // File data transfer
    FILE_TRANSFER_COMPLETE, // File transfer complete notification
    FILE_TRANSFER_ERROR,    // File transfer error notification
    
    // Emoji related message types
    UPLOAD_EMOJI_MSG,       // Upload emoji request message
    UPLOAD_EMOJI_MSG_ACK,   // Upload emoji response message
    QUERY_EMOJI_LIST_MSG,   // Query emoji list request message
    QUERY_EMOJI_LIST_MSG_ACK // Query emoji list response message
};

// 数据库表名常量定义
// 使用constexpr关键字，因为它们是非整数类型的静态数据成员
constexpr const char* TABLE_USER = "user";              // 用户表，存储用户基本信息
constexpr const char* TABLE_FRIEND = "friend";          // 好友表，存储好友关系
constexpr const char* TABLE_ALLGROUP = "allgroup";      // 群组表，存储群组基本信息
constexpr const char* TABLE_GROUPUSER = "groupuser";    // 群成员表，存储群组成员关系
constexpr const char* TABLE_OFFLINEMESSAGE = "offlinemessage"; // 离线消息表，存储用户离线时的消息

// 服务器默认端口定义
// 静态常量，定义服务器程序默认监听的端口号
static const int DEFAULT_SERVER_PORT = 8000;

#endif // PUBLIC_H  // 头文件保护宏结束