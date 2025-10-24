#include"chatservice.hpp"
#include"public.hpp"
#include<string>
#include<muduo/base/Logging.h>
#include<vector>

using namespace muduo;
using namespace std;
//获取单例对象的接口函数
ChatService* ChatService::instance(){
    static ChatService service;
    return &service;
}
//构造函数注册消息以及对应的handler操作
ChatService::ChatService()
{
    // 用户基本业务管理相关事件处理回调注册
    _msgHandlerMap.insert({LOGIN_MSG,std::bind(&ChatService::login,this,_1,_2,_3)});
    _msgHandlerMap.insert({LOGINOUT_MSG,std::bind(&ChatService::loginout,this,_1,_2,_3)});
    _msgHandlerMap.insert({REG_MSG,std::bind(&ChatService::reg,this,_1,_2,_3)});
    _msgHandlerMap.insert({ONE_CHAT_MSG,std::bind(&ChatService::oneChat,this,_1,_2,_3)});
    _msgHandlerMap.insert({ADD_FRIEND_MSG,std::bind(&ChatService::addFriend,this,_1,_2,_3)});
     // 群组业务管理相关事件处理回调注册
    _msgHandlerMap.insert({CREATE_GROUP_MSG ,std::bind(&ChatService::createGroup,this,_1,_2,_3)});
    _msgHandlerMap.insert({ADD_GROUP_MSG ,std::bind(&ChatService::addGroup,this,_1,_2,_3)});
    _msgHandlerMap.insert({GROUP_CHAT_MSG,std::bind(&ChatService::groupChat,this,_1,_2,_3)});

    //连接redis服务器
    if(_redis.connect()){
        //设置上报消息的回调
        _redis.init_notify_handler(std::bind(&ChatService::handleRedisSubscribeMessage,this,_1,_2));
         LOG_INFO << "Redis connected and notify handler initialized";
    }
    else{
    LOG_ERROR << "Failed to connect to Redis";
  }
}
//如果服务器宕机，用户的在线状态需要更新，以免出现服务器断开后，用户一直显示在线的情况(自己更新数据库offline我遇到的)
//服务器异常后，业务重置方法
void ChatService::reset(){
    //把online状态的用户，设置成offline
    _userModel.resetState();
}





//获取消息对应的处理器
MsgHandler ChatService::getHandler(int msgid){
    //记录错误日志，msgid没有对应的处理事件回调
    auto it=_msgHandlerMap.find(msgid);
    if(it==_msgHandlerMap.end()){//如果没有找到
        //返回一个空的处理器。空操作
        return[=](const TcpConnectionPtr& conn,json& js,Timestamp time){
            LOG_ERROR<<"msgid:"<<msgid<<" can not find handler!";
        };
    }
    else{
           return _msgHandlerMap[msgid];
    }
  
}
 //处理登录业务 ORM 业务层操作的都是对象 DAO  数据层操作的都是关系型数据库 id pwd pwd
  void ChatService::login(const TcpConnectionPtr& conn,json& js,Timestamp time){
        int id=js["id"].get<int>();//字符串转换成整型
        string pwd=js["password"];
        User user=_userModel.query(id);
        if(user.getId()==id&&user.getPwd()==pwd){//登录成功 存在用户且密码正确
            if(user.getState()=="online"){//该用户已经登录
                //该用户已经登录，不能重复登录
                json response;
                response["msgid"]=LOGIN_MSG_ACK;
                response["errno"]=2;//失败 
                response["errmsg"]="this account is using, input another!";
                conn->send(response.dump());
            }
            else{
                //登录成功，记录用户连接信息 因为是多线程，考虑线程安全,数据库的操作是线程安全的，mysql自动保证,而代码中json都是局部变量不用加锁
                {
                lock_guard<mutex> lock(_connMutex);
                _userConnMap.insert({id,conn});
                 LOG_INFO << "User " << id << " added to connection map";
                }

                //id用户登录成功后，向redis订阅channel(id)
                if(_redis.subscribe(id)){
                     LOG_INFO << "Successfully subscribed to Redis channel for user " << id;
                }
                else{
                    LOG_ERROR << "Failed to subscribe to Redis channel for user " << id;
                }

                //登录成功，更新用户状态信息 state offline=>online
                user.setState("online");
                _userModel.updateState(user);

                json response;
                response["msgid"]=LOGIN_MSG_ACK;
                response["errno"]=0;
                response["id"]=user.getId();
                response["name"]=user.getName();
                //查询该用户是否有离线消息，如果有的话，查询，json返回给用户
                vector<string> vec=_offlineMsgModel.query(id);
                if(!vec.empty()){
                    response["offlinemsg"]=vec;
                    //读取该用户离线消息后，删除该用户的离线消息
                    _offlineMsgModel.remove(id);
                }
                //查询该用户的好友列表信息并返回
                vector<User> userVec=_friendModel.query(id);
                if(!userVec.empty()){
                    vector<string> vec2;
                    for(User &user:userVec){
                        json js;
                        js["id"]=user.getId();
                        js["name"]=user.getName();
                        js["state"]=user.getState();
                        vec2.push_back(js.dump());
                    }
                    response["friends"]=vec2;
                }
                // 查询用户的群组信息
                vector<Group> groupuserVec = _groupModel.queryGroups(id);
                 if (!groupuserVec.empty())
                {
                // group:[{groupid:[xxx, xxx, xxx, xxx]}]
                vector<string> groupV;
                for (Group &group : groupuserVec)
                {
                    json grpjson;
                    grpjson["id"] = group.getId();
                    grpjson["groupname"] = group.getName();
                    grpjson["groupdesc"] = group.getDesc();
                    vector<string> userV;
                    for (GroupUser &user : group.getUsers())
                    {
                        json js;
                        js["id"] = user.getId();
                        js["name"] = user.getName();
                        js["state"] = user.getState();
                        js["role"] = user.getRole();
                        userV.push_back(js.dump());
                    }
                    grpjson["users"] = userV;
                    groupV.push_back(grpjson.dump());
                }

                response["groups"] = groupV;
            }

            conn->send(response.dump());
            } 
        }
        else{
            //该用户不存在，登录失败或者用户存在但是密码错误
            json response;
            response["msgid"]=LOGIN_MSG_ACK;
            response["errno"]=1;//失败
            response["errmsg"]="id or password is invalid!";
            conn->send(response.dump());
        }
        //测试{"msgid":1,"id":12,"password":"123456"}注意json数字不加引号(id)      //{"msgid":1,"id":22,"password":"123456"}正确的 再新开一个终端登录
        //{"msgid":1,"id":23,"password":"666666"}
         //学会调试gdb
  }
  //处理注册业务 name password
  void ChatService::reg(const TcpConnectionPtr& conn,json& js,Timestamp time){
        string name=js["name"];
        string pwd=js["password"];
        User user;
        user.setName(name);
        user.setPwd(pwd);
        bool state=_userModel.insert(user);
        if(state){//注册成功
            //注册成功，返回用户的id和状态信息
            json response;
            response["msgid"]=REG_MSG_ACK;
            response["errno"]=0;
            response["id"]=user.getId();
            conn->send(response.dump());
        }
        else{//注册失败
            json response;
            response["msgid"]=REG_MSG_ACK;
            response["errno"]=1;//失败
            conn->send(response.dump());
        }
        //测试{"msgid":4,"name":"zhangsan","password":"123456"}id是22
         //{"msgid":4,"name":"li si","password":"666666"}id是23
        
  }
  //处理注销业务
  void ChatService::loginout(const TcpConnectionPtr& conn,json& js,Timestamp time){
    int userid=js["id"].get<int>();
    {
        lock_guard<mutex> lock(_connMutex);
        auto it =_userConnMap.find(userid);
        if(it!=_userConnMap.end()){
            _userConnMap.erase(it);
        }
    }

    //用户注销，相当于是下线，在redis中取消订阅通道
    _redis.unsubscribe(userid);


    //更新用户的状态信息
         User user(userid,"","","offline");
         _userModel.updateState(user);    
  }
  //处理客户端异常退出 由于输出错误的json格式
  void ChatService::clientCloseException(const TcpConnectionPtr& conn){
        User user;
       {
        lock_guard<mutex> lock(_connMutex);
        for(auto it=_userConnMap.begin();it!=_userConnMap.end();++it){
            if(it->second==conn){
                //从map表删除用户的连接信息
                user.setId(it->first);
                _userConnMap.erase(it);
                break;
             }
          }
       }

        //用户注销，相当于是下线，在redis中取消订阅通道
        _redis.unsubscribe(user.getId());

         //更新用户的状态信息
         if(user.getId()!=-1){//用户存在
         user.setState("offline");
         _userModel.updateState(user);    
         }
  }
  //一对一聊天业务 在线消息不需要数据库，离线消息有OfflineMessage表保存//offlineMessage表设计userid不能为主键，因为可能收到来自同一用户很多信息，应该NOT NULL
  void ChatService::oneChat(const TcpConnectionPtr& conn,json& js,Timestamp time){
       //获取对方的id
       int toid=js["toid"].get<int>(); 
       LOG_INFO << "Sending message from user " << toid;
        {
        lock_guard<mutex> lock(_connMutex);
        auto it=_userConnMap.find(toid);
        if(it!=_userConnMap.end()){
            //toid在线，转发消息 服务器主动发送消息给toid用户   测试{"msgid":6,"id":22,"from":"zhangsan","toid":23,"msg":"yuanshen2"}
            //{"msgid":6,"id":23,"from":"li si","toid":22,"msg":"确实挺不错的"}会报错，json解析问题,不可避免
            it->second->send(js.dump());
            LOG_INFO << "Message sent directly to online user " << toid;
            return;
            }
        }

       //查询toid是否在线
       User user=_userModel.query(toid);
     LOG_INFO << "User " << toid << " state: " << user.getState();
       if(user.getState()=="online"){
          LOG_INFO << "Publishing message to Redis for user " << toid;
            if(_redis.publish(toid,js.dump())){
             LOG_INFO << "Message published to Redis successfully";
         }else{
             LOG_ERROR << "Failed to publish message to Redis";
         }
         return;
       }

      //toid用户不在线，存储离线消息
        _offlineMsgModel.insert(toid,js.dump());
        LOG_INFO << "User " << toid << " is offline, message stored";
}
  //添加好友业务 msgid id friendid 此业务加好友不需要对方去同意，后面可以去扩展！！id和friendid是联合主键，不会重复添加
  //提示，就跟服务器给用户发信息那一套，如果用户同意了，添加到数据库，没有同意就不添加
  void  ChatService::addFriend(const TcpConnectionPtr& conn,json& js,Timestamp time){
        int userid=js["id"].get<int>();
        int friendid=js["friendid"].get<int>();
        //存储好友信息
        _friendModel.insert(userid,friendid);
        //测试{"msgid":7,"id":22,"friendid":23}//添加好友只有一方，是单向的{"msgid":7,"id":23,"friendid":22}要双方都显示要这样
  }


  //创建群组业务
  void ChatService::createGroup(const TcpConnectionPtr& conn,json& js,Timestamp time){
       int userid=js["id"].get<int>();
       string name=js["groupname"];
       string desc=js["groupdesc"];
       //存储新创建的群组信息
       Group group(-1,name,desc);
       if(_groupModel.createGroup(group)){
           //存储群组创建人信息
           _groupModel.addGroup(userid,group.getId(),"creator");
       }
  }//可以给一个响应，如群组创建成功，这个业务未写(可参考之前所写的登录成功或者失败的响应)
  //加入群组业务
  void ChatService::addGroup(const TcpConnectionPtr& conn,json& js,Timestamp time){
       int userid=js["id"].get<int>();
       int groupid=js["groupid"].get<int>();
       //存储用户的群组信息
       _groupModel.addGroup(userid,groupid,"normal");
  }
    //群聊天业务
    void ChatService::groupChat(const TcpConnectionPtr& conn,json& js,Timestamp time){
         int userid=js["id"].get<int>();
         int groupid=js["groupid"].get<int>();
         //查询群组用户id列表，除userid自己之外，主要用于群聊业务给群组其他成员群发消息,在线直接接收到信息，离线存储离线消息
         vector<int> useridVec=_groupModel.queryGroupUsers(userid,groupid);

         lock_guard<mutex> lock(_connMutex);
         for(int id:useridVec){
             auto it=_userConnMap.find(id);
             if(it!=_userConnMap.end()){
                 //转发消息
                 it->second->send(js.dump());
             }
             else{
                  //查询id是否在线
                User user=_userModel.query(id);
                if(user.getState()=="online"){
                   _redis.publish(id,js.dump());
                    return;
                 }
                 else{
                    //存储离线消息
                 _offlineMsgModel.insert(id,js.dump());
                 } 
             }
         }
}
//当数据很多时，如一百万，会涉及数据库表的优化和拆分，还有分库分表的工具
// 从redis消息队列中获取订阅的消息
void ChatService::handleRedisSubscribeMessage(int userid, string msg)
{
    LOG_INFO << "Received message from Redis for user " << userid;
    LOG_INFO << "Message content: " << msg;
    lock_guard<mutex> lock(_connMutex);
    auto it = _userConnMap.find(userid);
    if (it != _userConnMap.end())
    {
        LOG_INFO << "Found user " << userid << " in connection map";
        it->second->send(msg);
        LOG_INFO << "Message forwarded to user " << userid;
        return;
    }
    else{
    // 存储该用户的离线消息
    LOG_INFO << "User " << userid << " not found in connection map, storing as offline message";
    _offlineMsgModel.insert(userid, msg);
    }
    
}