#ifndef CHATSERVICE_H
#define CHATSERVICE_H
#include"json.hpp"
#include<muduo/net/TcpServer.h>
#include<muduo/net/EventLoop.h>
#include<unordered_map>
#include<functional>
#include"server/model/usermodel.hpp"
#include<mutex>
#include"redis.hpp"
#include"server/model/offlinemessagemodel.hpp"
#include"server/model/friendmodel.hpp"
#include"server/model/groupmodel.hpp"
#include"server/model/emojimodel.hpp"
#include"server/model/farmmodel.hpp"
#include"server/ai_service_client.hpp"
using namespace muduo;
using namespace std;
using namespace muduo::net;
using json=nlohmann::json;
using  MsgHandler=std::function<void(const TcpConnectionPtr& conn,json& js,Timestamp time)>;

// 群组消息分发频道（用于AI群聊回复）
static const int GROUP_DISPATCH_CHANNEL = 9997;

//聊天服务器业务类
class ChatService
{
public:
   //获取单例对象的接口函数
   static ChatService* instance();
  //处理登录业务
  void login(const TcpConnectionPtr& conn,json& js,Timestamp time);
  //处理注册业务
  void reg(const TcpConnectionPtr& conn,json& js,Timestamp time);
  //一对一聊天业务
  void oneChat(const TcpConnectionPtr& conn,json& js,Timestamp time);
  //添加好友业务
  void addFriend(const TcpConnectionPtr& conn,json& js,Timestamp time);
  //创建群组业务
  void createGroup(const TcpConnectionPtr& conn,json& js,Timestamp time);
  //加入群组业务
  void addGroup(const TcpConnectionPtr& conn,json& js,Timestamp time);
  //群聊天业务
  void groupChat(const TcpConnectionPtr& conn,json& js,Timestamp time);
  //拉人进群业务
  void inviteToGroup(const TcpConnectionPtr& conn,json& js,Timestamp time);
  //创建面试群组业务
  void createInterviewGroup(const TcpConnectionPtr& conn,json& js,Timestamp time);
  //处理注销业务
  void loginout(const TcpConnectionPtr& conn,json& js,Timestamp time);
  
  // 向用户的所有好友推送状态更新
  void pushStateUpdate(int userId, const string& state);
  
  // 文件传输相关业务
  void fileTransferRequest(const TcpConnectionPtr& conn,json& js,Timestamp time);
  void fileTransferAck(const TcpConnectionPtr& conn,json& js,Timestamp time);
  void fileTransferData(const TcpConnectionPtr& conn,json& js,Timestamp time);
  void fileTransferComplete(const TcpConnectionPtr& conn,json& js,Timestamp time);
  
  // 查询好友和群组列表业务
  void queryFriendList(const TcpConnectionPtr& conn,json& js,Timestamp time);
  void queryGroupList(const TcpConnectionPtr& conn,json& js,Timestamp time);
  
  // 表情包相关业务
  void uploadEmoji(const TcpConnectionPtr& conn,json& js,Timestamp time);
  void queryEmojiList(const TcpConnectionPtr& conn,json& js,Timestamp time);
  
  // 头像相关业务
  void uploadAvatar(const TcpConnectionPtr& conn,json& js,Timestamp time);
  void updateAvatar(const TcpConnectionPtr& conn,json& js,Timestamp time);

  void farmPlant(const TcpConnectionPtr& conn, json& js, Timestamp time);
  void farmAnswer(const TcpConnectionPtr& conn, json& js, Timestamp time);
  void farmQuery(const TcpConnectionPtr& conn, json& js, Timestamp time);
  void farmHarvest(const TcpConnectionPtr& conn, json& js, Timestamp time);
  
  //处理客户端异常退出
  void clientCloseException(const TcpConnectionPtr& conn);
  
  //服务器异常后，业务重置方法
  void reset();

    //获取消息对应的处理器
  MsgHandler getHandler(int msgid);
  //从redis消息队列中获取订阅的信息
  void handleRedisSubscribeMessage(long long,string);
  //处理群组消息分发（AI群聊回复）
  void handleGroupDispatchMessage(const string& msg);
private:
    ChatService();
     //存储消息id和其对应的业务处理方法
    unordered_map<int,MsgHandler> _msgHandlerMap;
    
    //存储在线用户的通信连接
    unordered_map<int,TcpConnectionPtr> _userConnMap;

    //定义互斥锁，保证_userConnMap的线程安全
    mutex _connMutex;

    //数据操作类对象
    UserModel _userModel;
    OfflineMsgModel _offlineMsgModel;
    FriendModel _friendModel;
    GroupModel _groupModel;
    EmojiModel _emojiModel;
    FarmModel _farmModel;

    //redis操作对象
    Redis _redis;
    
    // AI 服务客户端
    AiServiceClient& _aiServiceClient;
};

#endif