#include"chatservice.hpp"
#include"public.hpp"
#include<string>
#include<muduo/base/Logging.h>
#include<iostream>
#include<vector>

using namespace muduo;
using namespace std;
// 获取单例对象的接口函数
// 设计模式：单例模式实现，确保整个应用只有一个ChatService实例
ChatService* ChatService::instance(){
    static ChatService service;
    return &service;
}

// 构造函数 - 服务初始化
// 业务逻辑：注册所有消息处理器，建立消息类型到处理函数的映射关系
ChatService::ChatService(){
    // 输出消息类型的具体值，用于调试
    LOG_INFO << "CREATE_GROUP_MSG: " << CREATE_GROUP_MSG;
    LOG_INFO << "ADD_GROUP_MSG: " << ADD_GROUP_MSG;
    
    // 用户基本业务管理相关事件处理回调注册
    // 命令模式：通过映射表实现消息类型到处理函数的动态路由
    _msgHandlerMap.insert({LOGIN_MSG,std::bind(&ChatService::login,this,_1,_2,_3)});
    _msgHandlerMap.insert({LOGINOUT_MSG,std::bind(&ChatService::loginout,this,_1,_2,_3)});
    _msgHandlerMap.insert({REG_MSG,std::bind(&ChatService::reg,this,_1,_2,_3)});
    _msgHandlerMap.insert({ONE_CHAT_MSG,std::bind(&ChatService::oneChat,this,_1,_2,_3)});
    _msgHandlerMap.insert({ADD_FRIEND_MSG,std::bind(&ChatService::addFriend,this,_1,_2,_3)});
    
    // 群组业务管理相关事件处理回调注册
    _msgHandlerMap.insert({CREATE_GROUP_MSG ,std::bind(&ChatService::createGroup,this,_1,_2,_3)});
    _msgHandlerMap.insert({ADD_GROUP_MSG ,std::bind(&ChatService::addGroup,this,_1,_2,_3)});
    _msgHandlerMap.insert({GROUP_CHAT_MSG,std::bind(&ChatService::groupChat,this,_1,_2,_3)});
    
    // 文件传输相关事件处理回调注册 - 扩展功能支持
    _msgHandlerMap.insert({FILE_TRANSFER_REQ,std::bind(&ChatService::fileTransferRequest,this,_1,_2,_3)});
    _msgHandlerMap.insert({FILE_TRANSFER_ACK,std::bind(&ChatService::fileTransferAck,this,_1,_2,_3)});
    _msgHandlerMap.insert({FILE_TRANSFER_DATA,std::bind(&ChatService::fileTransferData,this,_1,_2,_3)});
    _msgHandlerMap.insert({FILE_TRANSFER_COMPLETE,std::bind(&ChatService::fileTransferComplete,this,_1,_2,_3)});
    
    // 查询好友和群组列表相关事件处理回调注册
    _msgHandlerMap.insert({QUERY_FRIEND_MSG,std::bind(&ChatService::queryFriendList,this,_1,_2,_3)});
    _msgHandlerMap.insert({QUERY_GROUP_MSG,std::bind(&ChatService::queryGroupList,this,_1,_2,_3)});
    
    // 添加对客户端使用的消息类型的支持
    // 客户端使用的消息类型值与服务器端定义的不一致，需要添加映射
    _msgHandlerMap.insert({14,std::bind(&ChatService::queryFriendList,this,_1,_2,_3)}); // 客户端的QUERY_FRIEND_MSG = 14
    _msgHandlerMap.insert({16,std::bind(&ChatService::queryGroupList,this,_1,_2,_3)}); // 客户端的QUERY_GROUP_MSG = 16
    _msgHandlerMap.insert({10,std::bind(&ChatService::groupChat,this,_1,_2,_3)}); // 客户端的GROUP_CHAT_MSG = 10
    _msgHandlerMap.insert({17,std::bind(&ChatService::groupChat,this,_1,_2,_3)}); // 客户端的GROUP_CHAT_MSG = 17
    _msgHandlerMap.insert({7,std::bind(&ChatService::addFriend,this,_1,_2,_3)}); // 客户端的ADD_FRIEND_MSG = 7
    _msgHandlerMap.insert({8,std::bind(&ChatService::createGroup,this,_1,_2,_3)}); // 客户端的CREATE_GROUP_MSG = 8
    _msgHandlerMap.insert({9,std::bind(&ChatService::queryFriendList,this,_1,_2,_3)}); // 客户端的QUERY_FRIEND_MSG = 9
    _msgHandlerMap.insert({11,std::bind(&ChatService::queryGroupList,this,_1,_2,_3)}); // 客户端的QUERY_GROUP_MSG = 11
    _msgHandlerMap.insert({13,std::bind(&ChatService::createGroup,this,_1,_2,_3)}); // 客户端的CREATE_GROUP_MSG = 13
    _msgHandlerMap.insert({15,std::bind(&ChatService::addGroup,this,_1,_2,_3)}); // 客户端的ADD_GROUP_MSG = 15

    // 连接Redis服务器 - 分布式消息支持
    if(_redis.connect()){
        // 设置上报消息的回调 - 跨服务器消息转发机制
        _redis.init_notify_handler(std::bind(&ChatService::handleRedisSubscribeMessage,this,_1,_2));
        LOG_INFO << "Redis connected and notify handler initialized";
    }
    else{
        LOG_ERROR << "Failed to connect to Redis";
    }
}
// 服务器异常后，业务重置方法
// 业务逻辑：确保服务器重启后，所有用户状态的一致性
void ChatService::reset(){
    // 把online状态的用户，设置成offline - 状态恢复机制
    // 保证服务重启后用户在线状态的正确性，防止僵尸会话
    _userModel.resetState();
}



// 获取消息对应的处理器
// 业务逻辑：实现消息分发的核心功能，根据消息类型返回对应的处理函数
MsgHandler ChatService::getHandler(int msgid){
    // 查找对应消息类型的处理器
    // 命令模式的应用：动态路由到具体的处理函数
    auto it=_msgHandlerMap.find(msgid);
    if(it==_msgHandlerMap.end()){//如果没有找到
        // 返回一个空的处理器 - 错误处理机制
        // 优雅降级：对于未知消息类型，记录错误并返回空操作处理器
        return[=](const TcpConnectionPtr& conn,json& js,Timestamp time){
            LOG_ERROR<<"msgid:"<<msgid<<" can not find handler!";
        };
    }
    else{
        // 记录当前的消息类型和处理器
        LOG_INFO << "Mapping msgid:" << msgid << " to handler";
        // 返回一个包装器，捕获所有可能的异常，确保服务器不会崩溃
        return[handler=it->second](const TcpConnectionPtr& conn,json& js,Timestamp time){
            try {
                // 调用实际的消息处理函数
                handler(conn, js, time);
            } catch (const json::exception& e) {
                // 捕获JSON类型转换异常
                LOG_ERROR << "JSON exception in message handling: " << e.what();
            } catch (const std::exception& e) {
                // 捕获其他所有异常
                LOG_ERROR << "Exception in message handling: " << e.what();
            } catch (...) {
                // 捕获未知异常
                LOG_ERROR << "Unknown exception in message handling";
            }
        };
    }
  }
 // 处理登录业务
 // 业务逻辑：实现用户身份认证、会话管理、分布式支持和初始数据同步
 void ChatService::login(const TcpConnectionPtr& conn,json& js,Timestamp time){
        LOG_INFO << "do login service!";
        
        // 安全检查：确保id和password字段存在且类型正确
        if (!js.contains("id") || !js["id"].is_number() || !js.contains("password")) {
            LOG_ERROR << "Login request missing required fields or invalid types";
            json response;
            response["msgid"]=LOGIN_MSG_ACK;
            response["errno"]=1;//失败
            response["errmsg"]="Invalid login request format";
            conn->send(response.dump());
            return;
        }
        
        // 获取客户端提供的用户ID - 身份凭证提取
        long long id = js["id"].get<long long>();
        string pwd=js["password"];
        // 直接使用long long类型查询，避免int类型转换截断
        User user=_userModel.query(id);
        
        // 验证用户登录信息 - 身份认证核心逻辑
        // 安全机制：双重验证（用户存在性和密码匹配）
        if(user.getId()==id&&user.getPwd()==pwd){//登录成功 存在用户且密码正确
            // 检查用户是否已在线 - 防重复登录机制
            if(user.getState()=="online"){//该用户已经登录
                // 拒绝重复登录 - 账户安全保护
                json response;
                response["msgid"]=LOGIN_MSG_ACK;
                response["errno"]=2;//失败 
                response["errmsg"]="this account is using, input another!";
                conn->send(response.dump());
            }
            else{
                // 登录成功，记录用户连接信息 - 会话管理
                // 并发安全：使用互斥锁保护共享资源
                {
                    lock_guard<mutex> lock(_connMutex);
                    _userConnMap.insert({(int)id,conn});
                    LOG_INFO << "User " << id << " added to connection map";
                }

                // 用户登录成功后，向redis订阅channel(id) - 分布式消息支持
                // 微服务架构：通过Redis实现跨服务器消息路由
                if(_redis.subscribe((int)id)){
                    LOG_INFO << "Successfully subscribed to Redis channel for user " << id;
                }
                else{
                    LOG_ERROR << "Failed to subscribe to Redis channel for user " << id;
                }

                // 登录成功，更新用户状态信息 state offline=>online - 状态同步
                user.setState("online");
                _userModel.updateState(user);

                // 构建登录成功响应 - 用户体验优化
                json response;
                response["msgid"]=LOGIN_MSG_ACK;
                response["errno"]=0;
                response["id"]=user.getId();
                response["name"]=user.getName();
                
                // 查询该用户是否有离线消息 - 消息可靠性保障
                // 消息存储策略：确保用户不会丢失离线期间的消息
                vector<string> vec=_offlineMsgModel.query(id);
                if(!vec.empty()){
                    response["offlinemsg"]=vec;
                    // 读取该用户离线消息后，删除该用户的离线消息 - 数据清理
                    _offlineMsgModel.remove(id);
                }
                
                // 查询该用户的好友列表信息并返回 - 社交关系同步
                // 数据预加载：登录时一次性加载用户相关的所有社交数据
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
                
                // 查询用户的群组信息 - 社交关系同步
                vector<Group> groupuserVec = _groupModel.queryGroups(id);
                if (!groupuserVec.empty())
                {
                    // 群组信息序列化 - 数据结构设计
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

                string responseStr = response.dump();
                cout << "[DEBUG] Sending login success response: " << responseStr << endl;
                conn->send(responseStr);
                cout << "[DEBUG] Login response sent successfully" << endl;
            } 
        }
        else{
            //该用户不存在，登录失败或者用户存在但是密码错误
            cout << "[DEBUG] User authentication failed, id: " << id << endl;
            json response;
            response["msgid"]=LOGIN_MSG_ACK;
            response["errno"]=1;//失败
            response["errmsg"]="id or password is invalid!";
            string responseStr = response.dump();
            cout << "[DEBUG] Sending login ACK (failed): " << responseStr << endl;
            conn->send(responseStr);
        }
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
       // 安全检查：确保to或toid字段存在且类型正确
       int toid = -1;
       if (js.contains("toid") && js["toid"].is_number()) {
           toid = js["toid"].get<int>();
       } else if (js.contains("to") && js["to"].is_number()) {
           toid = js["to"].get<int>();
       } else {
           LOG_ERROR << "One chat request missing required field 'toid' or 'to' or invalid type";
           return;
       }
       
       // Get sender ID from connection
       int fromId = -1;
       {
           lock_guard<mutex> lock(_connMutex);
           for (const auto& pair : _userConnMap) {
               if (pair.second == conn) {
                   fromId = pair.first;
                   break;
               }
           }
       }
       // Set sender ID in JSON
       js["from"] = fromId;
       
       // Get sender name and add it to the JSON
       User sender = _userModel.query(fromId);
       js["name"] = sender.getName();
       
       LOG_INFO << "Sending message from user " << fromId << " (" << sender.getName() << ") to " << toid;
        {
        lock_guard<mutex> lock(_connMutex);
        auto it=_userConnMap.find(toid);
        if(it!=_userConnMap.end()){
            //toid在线，转发消息 服务器主动发送消息给toid用户
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
        // 安全检查：确保id和friendid字段存在且类型正确
        if (!js.contains("id") || !js["id"].is_number() || !js.contains("friendid") || !js["friendid"].is_number()) {
            LOG_ERROR << "Add friend request missing required fields or invalid types";
            return;
        }
        
        int userid=js["id"].get<int>();
        int friendid=js["friendid"].get<int>();
        //存储好友信息
        _friendModel.insert(userid,friendid);
        
        // 添加好友后，立即查询好友列表并返回给客户端
        json response;
        response["msgid"]=QUERY_FRIEND_MSG_ACK;
        response["errno"]=0;
        
        // 查询该用户的好友列表信息
        vector<User> userVec=_friendModel.query(userid);
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
        
        string responseStr = response.dump();
        conn->send(responseStr);
  }


  //创建群组业务
  void ChatService::createGroup(const TcpConnectionPtr& conn,json& js,Timestamp time){
       try {
           // 安全检查：确保所有必要字段存在且类型正确
           if (!js.contains("id") || !js["id"].is_number() || 
               !js.contains("groupname") || !js["groupname"].is_string() || 
               !js.contains("groupdesc") || !js["groupdesc"].is_string()) {
               LOG_ERROR << "Create group request missing required fields or invalid types";
               return;
           }
           
           // 获取字段值，使用try-catch处理JSON类型转换异常
           int userid = js["id"].get<int>();
           string name = js["groupname"];
           string desc = js["groupdesc"];
           
           //存储新创建的群组信息
           Group group(-1,name,desc);
           if(_groupModel.createGroup(group)){
               //存储群组创建人信息
               _groupModel.addGroup(userid,group.getId(),"creator");
               
               // 创建群组成功后，立即查询用户的群组列表
               json response;
               response["msgid"]=QUERY_GROUP_MSG_ACK;
               response["errno"]=0;
               
               // 查询该用户的群组列表信息
               vector<Group> groupuserVec = _groupModel.queryGroups(userid);
               if (!groupuserVec.empty()) {
                   vector<string> groupV;
                   for (Group &group : groupuserVec) {
                       json grpjson;
                       grpjson["id"] = group.getId();
                       grpjson["groupname"] = group.getName();
                       grpjson["groupdesc"] = group.getDesc();
                       vector<string> userV;
                       for (GroupUser &user : group.getUsers()) {
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
               
               string responseStr = response.dump();
               conn->send(responseStr);
           } else {
               // 创建群组失败，返回错误信息
               json response;
               response["msgid"]=QUERY_GROUP_MSG_ACK;
               response["errno"]=1;
               response["errmsg"]="Failed to create group, group name may already exist";
               conn->send(response.dump());
           }
       } catch (const json::exception& e) {
           // 捕获JSON类型转换异常
           LOG_ERROR << "JSON exception in create group: " << e.what();
           return;
       }
  }
  //加入群组业务
  void ChatService::addGroup(const TcpConnectionPtr& conn,json& js,Timestamp time){
       try {
           // 安全检查：确保groupid字段存在且类型正确
           if (!js.contains("groupid") || !js["groupid"].is_number()) {
               LOG_ERROR << "Add group request missing required field 'groupid' or invalid type";
               return;
           }
           
           // Get sender ID from connection
           int userid = -1;
           {
               lock_guard<mutex> lock(_connMutex);
               for (const auto& pair : _userConnMap) {
                   if (pair.second == conn) {
                       userid = pair.first;
                       break;
                   }
               }
           }
           
           if (userid == -1) {
               LOG_ERROR << "Failed to get sender ID from connection";
               return;
           }
           
           // 尝试获取字段值，使用try-catch处理JSON类型转换异常
           int groupid = js["groupid"].get<int>();
           
           //存储用户的群组信息
           _groupModel.addGroup(userid,groupid,"normal");
           
           // 加入群组后，立即查询群组列表并返回给客户端
           json response;
           response["msgid"]=QUERY_GROUP_MSG_ACK;
           response["errno"]=0;
           
           // 查询该用户的群组列表信息
           vector<Group> groupuserVec = _groupModel.queryGroups(userid);
           if (!groupuserVec.empty()) {
               vector<string> groupV;
               for (Group &group : groupuserVec) {
                   json grpjson;
                   grpjson["id"] = group.getId();
                   grpjson["groupname"] = group.getName();
                   grpjson["groupdesc"] = group.getDesc();
                   vector<string> userV;
                   for (GroupUser &user : group.getUsers()) {
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
           
           string responseStr = response.dump();
           conn->send(responseStr);
       } catch (const json::exception& e) {
           // 捕获JSON类型转换异常
           LOG_ERROR << "JSON exception in add group: " << e.what();
           return;
       }
  }
    //群聊天业务
    void ChatService::groupChat(const TcpConnectionPtr& conn,json& js,Timestamp time){
         // 安全检查：确保groupid字段存在且类型正确
         if (!js.contains("groupid") || !js["groupid"].is_number()) {
             LOG_ERROR << "Group chat request missing required field 'groupid' or invalid type";
             return;
         }
         
         // Get sender ID from connection
         int userid = -1;
         {
             lock_guard<mutex> lock(_connMutex);
             for (const auto& pair : _userConnMap) {
                 if (pair.second == conn) {
                     userid = pair.first;
                     break;
                 }
             }
         }
         
         if (userid == -1) {
             LOG_ERROR << "Failed to get sender ID from connection";
             return;
         }
         
         int groupid=js["groupid"].get<int>();
         // Set sender ID in JSON
         js["from"] = userid;
         
         // Get sender name and add to JSON
         User sender = _userModel.query(userid);
         js["fromName"] = sender.getName();
         
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
                }
                else{
                    //存储离线消息
                 _offlineMsgModel.insert(id,js.dump());
                 } 
             }
         }
}
//当数据很多时，如一百万，会涉及数据库表的优化和拆分，还有分库分表的工具
// 文件传输请求处理
void ChatService::fileTransferRequest(const TcpConnectionPtr& conn, json& js, Timestamp time) {
    LOG_INFO << "File transfer request received";
    
    // 安全检查：确保所有必要字段存在且类型正确
    if (!js.contains("from") || !js["from"].is_number() || 
        !js.contains("to") || !js["to"].is_number() || 
        !js.contains("filename") || !js.contains("filesize") || !js["filesize"].is_number() || 
        !js.contains("fileid")) {
        LOG_ERROR << "File transfer request missing required fields or invalid types";
        return;
    }
    
    int fromId = js["from"].get<int>();
    int toId = js["to"].get<int>();
    std::string filename = js["filename"].get<std::string>();
    long long filesize = js["filesize"].get<long long>();
    std::string fileId = js["fileid"].get<std::string>();
    
    LOG_INFO << "File request from: " << fromId << " to: " << toId << ", file: " << filename << ", size: " << filesize;
    
    // 检查接收方是否在线
    {   
        lock_guard<mutex> lock(_connMutex);
        auto it = _userConnMap.find(toId);
        if (it != _userConnMap.end()) {
            // 接收方在线，转发文件传输请求
            json response;
            response["msgid"] = FILE_TRANSFER_REQ;
            response["from"] = fromId;
            response["to"] = toId;
            response["filename"] = filename;
            response["filesize"] = filesize;
            response["fileid"] = fileId;
            
            std::string responseStr = response.dump();
            it->second->send(responseStr);
            LOG_INFO << "File transfer request forwarded to user " << toId;
            return;
        }
    }
    
    // 接收方不在线，存储离线消息
    json offlineMsg;
    offlineMsg["msgid"] = FILE_TRANSFER_REQ;
    offlineMsg["from"] = fromId;
    offlineMsg["filename"] = filename;
    offlineMsg["filesize"] = filesize;
    offlineMsg["fileid"] = fileId;
    
    _offlineMsgModel.insert(toId, offlineMsg.dump());
    LOG_INFO << "File transfer request stored as offline message for user " << toId;
    
    // 回复发送方，接收方不在线
    json reply;
    reply["msgid"] = FILE_TRANSFER_ERROR;
    reply["errno"] = 1;
    reply["errmsg"] = "Recipient is offline";
    conn->send(reply.dump());
}

// 文件数据传输处理
void ChatService::fileTransferData(const TcpConnectionPtr& conn, json& js, Timestamp time) {
    LOG_INFO << "File transfer data received";
    
    // 安全检查：确保所有必要字段存在且类型正确
    if (!js.contains("from") || !js["from"].is_number() || 
        !js.contains("to") || !js["to"].is_number() || 
        !js.contains("fileid") || !js.contains("chunkindex") || !js["chunkindex"].is_number() || 
        !js.contains("data")) {
        LOG_ERROR << "File transfer data missing required fields or invalid types";
        return;
    }
    
    int fromId = js["from"].get<int>();
    int toId = js["to"].get<int>();
    std::string fileId = js["fileid"].get<std::string>();
    int chunkIndex = js["chunkindex"].get<int>();
    std::string data = js["data"].get<std::string>();
    
    // 检查接收方是否在线
    {   
        lock_guard<mutex> lock(_connMutex);
        auto it = _userConnMap.find(toId);
        if (it != _userConnMap.end()) {
            // 接收方在线，转发文件数据
            json response;
            response["msgid"] = FILE_TRANSFER_DATA;
            response["from"] = fromId;
            response["fileid"] = fileId;
            response["chunkindex"] = chunkIndex;
            response["data"] = data;
            
            std::string responseStr = response.dump();
            it->second->send(responseStr);
            return;
        }
    }
    
    // 接收方不在线，回复发送方错误
    json reply;
    reply["msgid"] = FILE_TRANSFER_ERROR;
    reply["errno"] = 2;
    reply["errmsg"] = "Recipient went offline during file transfer";
    conn->send(reply.dump());
}

// 文件传输确认处理
void ChatService::fileTransferAck(const TcpConnectionPtr& conn, json& js, Timestamp time) {
    LOG_INFO << "File transfer acknowledgment received";
    
    // 安全检查：确保所有必要字段存在且类型正确
    if (!js.contains("from") || !js["from"].is_number() || 
        !js.contains("to") || !js["to"].is_number() || 
        !js.contains("fileid") || !js.contains("accepted")) {
        LOG_ERROR << "File transfer acknowledgment missing required fields or invalid types";
        return;
    }
    
    int fromId = js["from"].get<int>();
    int toId = js["to"].get<int>();
    std::string fileId = js["fileid"].get<std::string>();
    bool accepted = js["accepted"].get<bool>();
    
    // 检查接收方是否在线
    {   
        lock_guard<mutex> lock(_connMutex);
        auto it = _userConnMap.find(toId);
        if (it != _userConnMap.end()) {
            // 接收方在线，转发确认消息
            json response;
            response["msgid"] = FILE_TRANSFER_ACK;
            response["from"] = fromId;
            response["to"] = toId;
            response["fileid"] = fileId;
            response["accepted"] = accepted;
            
            std::string responseStr = response.dump();
            it->second->send(responseStr);
            LOG_INFO << "File transfer acknowledgment forwarded to user " << toId;
            return;
        }
    }
    
    // 接收方不在线，回复发送方错误
    json reply;
    reply["msgid"] = FILE_TRANSFER_ERROR;
    reply["errno"] = 3;
    reply["errmsg"] = "Recipient went offline";
    conn->send(reply.dump());
    LOG_INFO << "Recipient offline, sent error to file transfer acknowledgment sender";
}

// 文件传输完成处理
void ChatService::fileTransferComplete(const TcpConnectionPtr& conn, json& js, Timestamp time) {
    LOG_INFO << "File transfer complete notification received";
    
    // 安全检查：确保所有必要字段存在且类型正确
    if (!js.contains("from") || !js["from"].is_number() || 
        !js.contains("to") || !js["to"].is_number() || 
        !js.contains("fileid") || !js.contains("success")) {
        LOG_ERROR << "File transfer complete notification missing required fields or invalid types";
        return;
    }
    
    int fromId = js["from"].get<int>();
    int toId = js["to"].get<int>();
    std::string fileId = js["fileid"].get<std::string>();
    bool success = js["success"].get<bool>();
    
    // 检查接收方是否在线
    {   
        lock_guard<mutex> lock(_connMutex);
        auto it = _userConnMap.find(toId);
        if (it != _userConnMap.end()) {
            // 接收方在线，转发完成通知
            json response;
            response["msgid"] = FILE_TRANSFER_COMPLETE;
            response["from"] = fromId;
            response["fileid"] = fileId;
            response["success"] = success;
            
            std::string responseStr = response.dump();
            it->second->send(responseStr);
            return;
        }
    }
    
    // 接收方不在线，存储离线通知
    json offlineMsg;
    offlineMsg["msgid"] = FILE_TRANSFER_COMPLETE;
    offlineMsg["from"] = fromId;
    offlineMsg["fileid"] = fileId;
    offlineMsg["success"] = success;
    
    _offlineMsgModel.insert(toId, offlineMsg.dump());
}

// 从redis消息队列中获取订阅的消息
void ChatService::handleRedisSubscribeMessage(long long userid, string msg)
{
    LOG_INFO << "Received message from Redis for user " << userid;
    LOG_INFO << "Message content: " << msg;
    
    try {
        // 尝试解析JSON消息，检查是否包含msgid字段
        json js = json::parse(msg);
        // 检查msgid是否存在且为数字类型
        if (!js.contains("msgid") || !js["msgid"].is_number()) {
            LOG_ERROR << "Message from Redis missing valid msgid field, userid: " << userid;
            return;
        }
    } catch (const json::exception& e) {
        LOG_ERROR << "Failed to parse message from Redis, error: " << e.what() << ", userid: " << userid;
        return;
    }
    
    lock_guard<mutex> lock(_connMutex);
    // 将long long转换为int进行查找，因为_userConnMap存储的是int类型的键
    auto it = _userConnMap.find(static_cast<int>(userid));
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

// 查询好友列表业务
void ChatService::queryFriendList(const TcpConnectionPtr& conn, json& js, Timestamp time) {
    LOG_INFO << "do query friend list service!";
    
    // 安全检查：确保id字段存在且类型正确
    if (!js.contains("id") || !js["id"].is_number()) {
        LOG_ERROR << "Query friend list request missing required field 'id' or invalid type";
        json response;
        response["msgid"] = QUERY_FRIEND_MSG_ACK;
        response["errno"] = 1;
        response["errmsg"] = "Invalid request format";
        conn->send(response.dump());
        return;
    }
    
    long long userId = js["id"].get<long long>();
    cout << "[DEBUG] Querying friend list for user: " << userId << endl;
    
    // 查询该用户的好友列表
    vector<User> friendList = _friendModel.query(userId);
    cout << "[DEBUG] Found " << friendList.size() << " friends" << endl;
    
    json response;
    response["msgid"] = QUERY_FRIEND_MSG_ACK;
    response["errno"] = 0;
    
    if (!friendList.empty()) {
        vector<string> vec;
        for (User& user : friendList) {
            json js;
            js["id"] = user.getId();
            js["name"] = user.getName();
            js["state"] = user.getState();
            vec.push_back(js.dump());
        }
        response["friends"] = vec;
    }
    
    string responseStr = response.dump();
    cout << "[DEBUG] Sending friend list response: " << responseStr << endl;
    conn->send(responseStr);
}

// 查询群组列表业务
void ChatService::queryGroupList(const TcpConnectionPtr& conn, json& js, Timestamp time) {
    LOG_INFO << "do query group list service!";
    
    // 安全检查：确保id字段存在且类型正确
    if (!js.contains("id") || !js["id"].is_number()) {
        LOG_ERROR << "Query group list request missing required field 'id' or invalid type";
        json response;
        response["msgid"] = QUERY_GROUP_MSG_ACK;
        response["errno"] = 1;
        response["errmsg"] = "Invalid request format";
        conn->send(response.dump());
        return;
    }
    
    long long userId = js["id"].get<long long>();
    cout << "[DEBUG] Querying group list for user: " << userId << endl;
    
    // 查询该用户的群组列表
    vector<Group> groupList = _groupModel.queryGroups(userId);
    cout << "[DEBUG] Found " << groupList.size() << " groups" << endl;
    
    json response;
    response["msgid"] = QUERY_GROUP_MSG_ACK;
    response["errno"] = 0;
    
    if (!groupList.empty()) {
        vector<string> groupV;
        for (Group& group : groupList) {
            json grpjson;
            grpjson["id"] = group.getId();
            grpjson["groupname"] = group.getName();
            grpjson["groupdesc"] = group.getDesc();
            vector<string> userV;
            for (GroupUser& user : group.getUsers()) {
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
    
    string responseStr = response.dump();
    cout << "[DEBUG] Sending group list response: " << responseStr << endl;
    conn->send(responseStr);
}