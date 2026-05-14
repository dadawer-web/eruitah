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
#include"server/rpc/internal_rpc_client.hpp"
#include"server/rpc/internal_rpc_server.hpp"
using namespace muduo;
using namespace std;
using namespace muduo::net;
using json=nlohmann::json;
using  MsgHandler=std::function<void(const TcpConnectionPtr& conn,json& js,Timestamp time)>;

static const int GROUP_DISPATCH_CHANNEL = 9997;

class ChatService
{
public:
   static ChatService* instance();
  void login(const TcpConnectionPtr& conn,json& js,Timestamp time);
  void reg(const TcpConnectionPtr& conn,json& js,Timestamp time);
  void oneChat(const TcpConnectionPtr& conn,json& js,Timestamp time);
  void addFriend(const TcpConnectionPtr& conn,json& js,Timestamp time);
  void createGroup(const TcpConnectionPtr& conn,json& js,Timestamp time);
  void addGroup(const TcpConnectionPtr& conn,json& js,Timestamp time);
  void groupChat(const TcpConnectionPtr& conn,json& js,Timestamp time);
  void inviteToGroup(const TcpConnectionPtr& conn,json& js,Timestamp time);
  void createInterviewGroup(const TcpConnectionPtr& conn,json& js,Timestamp time);
  void loginout(const TcpConnectionPtr& conn,json& js,Timestamp time);
  
  void pushStateUpdate(int userId, const string& state);
  
  void fileTransferRequest(const TcpConnectionPtr& conn,json& js,Timestamp time);
  void fileTransferAck(const TcpConnectionPtr& conn,json& js,Timestamp time);
  void fileTransferData(const TcpConnectionPtr& conn,json& js,Timestamp time);
  void fileTransferComplete(const TcpConnectionPtr& conn,json& js,Timestamp time);
  
  void queryFriendList(const TcpConnectionPtr& conn,json& js,Timestamp time);
  void queryGroupList(const TcpConnectionPtr& conn,json& js,Timestamp time);
  
  void uploadEmoji(const TcpConnectionPtr& conn,json& js,Timestamp time);
  void queryEmojiList(const TcpConnectionPtr& conn,json& js,Timestamp time);
  
  void uploadAvatar(const TcpConnectionPtr& conn,json& js,Timestamp time);
  void updateAvatar(const TcpConnectionPtr& conn,json& js,Timestamp time);

  void farmPlant(const TcpConnectionPtr& conn, json& js, Timestamp time);
  void farmAnswer(const TcpConnectionPtr& conn, json& js, Timestamp time);
  void farmQuery(const TcpConnectionPtr& conn, json& js, Timestamp time);
  void farmHarvest(const TcpConnectionPtr& conn, json& js, Timestamp time);
  
  void clientCloseException(const TcpConnectionPtr& conn);
  
  void reset();

  MsgHandler getHandler(int msgid);
  void handleRedisSubscribeMessage(long long,string);
  void handleGroupDispatchMessage(const string& msg);

  void handleRpcPushMessage(int receiverId, int64_t groupId,
                            int msgType, const string& payloadJson,
                            bool broadcast);

  void initRpc(EventLoop* loop,
               const InetAddress& javaRpcAddr,
               const InetAddress& rpcListenAddr);

private:
    ChatService();
    unordered_map<int,MsgHandler> _msgHandlerMap;
    
    unordered_map<int,TcpConnectionPtr> _userConnMap;
    mutex _connMutex;

    UserModel _userModel;
    OfflineMsgModel _offlineMsgModel;
    FriendModel _friendModel;
    GroupModel _groupModel;
    EmojiModel _emojiModel;
    FarmModel _farmModel;

    Redis _redis;
    
    AiServiceClient& _aiServiceClient;

    InternalRpcClientPtr _rpcClient;
    InternalRpcServerPtr _rpcServer;
};

#endif
