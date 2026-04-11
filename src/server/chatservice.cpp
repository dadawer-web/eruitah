#include"chatservice.hpp"
#include"public.hpp"
#include<string>
#include<map>
#include<muduo/base/Logging.h>
#include<iostream>
#include<vector>
#include<fstream>
#include <openssl/bio.h>
#include <openssl/buffer.h>
#include <openssl/evp.h>
#include"server/ai_service_client.hpp"

using namespace muduo;
using namespace std;

// Base64编码辅助函数
string base64Encode(const string &data) {
    BIO *bio, *b64;
    BUF_MEM *bufferPtr;

    b64 = BIO_new(BIO_f_base64());
    bio = BIO_new(BIO_s_mem());
    bio = BIO_push(b64, bio);

    BIO_set_flags(bio, BIO_FLAGS_BASE64_NO_NL);
    BIO_write(bio, data.c_str(), data.size());
    BIO_flush(bio);
    BIO_get_mem_ptr(bio, &bufferPtr);

    string encoded(bufferPtr->data, bufferPtr->length);

    BIO_free_all(bio);

    return encoded;
}

// Base64解码函数
string base64Decode(const string &encoded) {
    BIO *bio, *b64;
    char buffer[1024];
    int len;
    string decoded;

    b64 = BIO_new(BIO_f_base64());
    bio = BIO_new_mem_buf(encoded.c_str(), -1);
    bio = BIO_push(b64, bio);

    BIO_set_flags(bio, BIO_FLAGS_BASE64_NO_NL);
    while ((len = BIO_read(bio, buffer, sizeof(buffer))) > 0) {
        decoded.append(buffer, len);
    }

    BIO_free_all(bio);

    return decoded;
}

// 读取文件内容并转换为Base64编码
string fileToBase64(const string &filePath) {
    if (filePath.empty()) {
        return "";
    }

    ifstream file(filePath, ios::in | ios::binary);
    if (!file.is_open()) {
        LOG_ERROR << "Failed to open avatar file: " << filePath;
        return "";
    }

    file.seekg(0, ios::end);
    size_t fileSize = file.tellg();
    file.seekg(0, ios::beg);

    vector<char> buffer(fileSize);
    file.read(buffer.data(), fileSize);
    file.close();

    return base64Encode(string(buffer.begin(), buffer.end()));
}

// 获取单例对象的接口函数
ChatService* ChatService::instance(){
    static ChatService service;
    return &service;
}

// 构造函数 - 服务初始化
ChatService::ChatService()
    : _aiServiceClient(AiServiceClient::instance()) {
    LOG_INFO << "CREATE_GROUP_MSG: " << CREATE_GROUP_MSG;
    LOG_INFO << "ADD_GROUP_MSG: " << ADD_GROUP_MSG;

    _msgHandlerMap.insert({LOGIN_MSG,std::bind(&ChatService::login,this,_1,_2,_3)});
    _msgHandlerMap.insert({LOGINOUT_MSG,std::bind(&ChatService::loginout,this,_1,_2,_3)});
    _msgHandlerMap.insert({REG_MSG,std::bind(&ChatService::reg,this,_1,_2,_3)});
    _msgHandlerMap.insert({ONE_CHAT_MSG,std::bind(&ChatService::oneChat,this,_1,_2,_3)});
    _msgHandlerMap.insert({ADD_FRIEND_MSG,std::bind(&ChatService::addFriend,this,_1,_2,_3)});

    _msgHandlerMap.insert({CREATE_GROUP_MSG ,std::bind(&ChatService::createGroup,this,_1,_2,_3)});
    _msgHandlerMap.insert({ADD_GROUP_MSG ,std::bind(&ChatService::addGroup,this,_1,_2,_3)});
    _msgHandlerMap.insert({GROUP_CHAT_MSG,std::bind(&ChatService::groupChat,this,_1,_2,_3)});
    _msgHandlerMap.insert({INVITE_GROUP_MSG,std::bind(&ChatService::inviteToGroup,this,_1,_2,_3)});

    _msgHandlerMap.insert({FILE_TRANSFER_REQ,std::bind(&ChatService::fileTransferRequest,this,_1,_2,_3)});
    _msgHandlerMap.insert({FILE_TRANSFER_ACK,std::bind(&ChatService::fileTransferAck,this,_1,_2,_3)});
    _msgHandlerMap.insert({FILE_TRANSFER_DATA,std::bind(&ChatService::fileTransferData,this,_1,_2,_3)});
    _msgHandlerMap.insert({FILE_TRANSFER_COMPLETE,std::bind(&ChatService::fileTransferComplete,this,_1,_2,_3)});

    _msgHandlerMap.insert({QUERY_FRIEND_MSG,std::bind(&ChatService::queryFriendList,this,_1,_2,_3)});
    _msgHandlerMap.insert({QUERY_GROUP_MSG,std::bind(&ChatService::queryGroupList,this,_1,_2,_3)});

    _msgHandlerMap.insert({UPLOAD_EMOJI_MSG,std::bind(&ChatService::uploadEmoji,this,_1,_2,_3)});
    _msgHandlerMap.insert({QUERY_EMOJI_LIST_MSG,std::bind(&ChatService::queryEmojiList,this,_1,_2,_3)});

    _msgHandlerMap.insert(std::make_pair(UPLOAD_AVATAR_MSG,std::bind(&ChatService::uploadAvatar,this,_1,_2,_3)));
    _msgHandlerMap.insert(std::make_pair(UPDATE_AVATAR_MSG,std::bind(&ChatService::updateAvatar,this,_1,_2,_3)));

    if(_redis.connect()){
        LOG_INFO << "Redis connected successfully!";
        _redis.init_notify_handler(std::bind(&ChatService::handleRedisSubscribeMessage,this,_1,_2));
        LOG_INFO << "Redis notify handler initialized";
        
        if(_redis.subscribe(GROUP_DISPATCH_CHANNEL)){
            LOG_INFO << "Subscribed to group dispatch channel: " << GROUP_DISPATCH_CHANNEL;
        } else {
            LOG_ERROR << "Failed to subscribe to group dispatch channel: " << GROUP_DISPATCH_CHANNEL;
        }
    }
    else{
        LOG_ERROR << "Failed to connect to Redis!";
    }
}

void ChatService::reset(){
    _userModel.resetState();
}

MsgHandler ChatService::getHandler(int msgid){
    LOG_INFO << "getHandler called with msgid: " << msgid;
    auto it=_msgHandlerMap.find(msgid);
    if(it==_msgHandlerMap.end()){
        LOG_ERROR<<"msgid:"<<msgid<<" can not find handler!";
        return[=](const TcpConnectionPtr& conn,json& js,Timestamp time){
            LOG_ERROR<<"msgid:"<<msgid<<" can not find handler!";
        };
    }
    else{
        LOG_INFO << "Mapping msgid:" << msgid << " to handler";
        return[handler=it->second](const TcpConnectionPtr& conn,json& js,Timestamp time){
            try {
                handler(conn, js, time);
            } catch (const json::exception& e) {
                LOG_ERROR << "JSON exception in message handling: " << e.what();
                json response;
                response["msgid"] = 999;
                response["errno"] = 5;
                response["errmsg"] = "JSON parse error: " + std::string(e.what());
                conn->send(response.dump() + "\n");
            } catch (const std::exception& e) {
                LOG_ERROR << "Exception in message handling: " << e.what();
                json response;
                response["msgid"] = 999;
                response["errno"] = 6;
                response["errmsg"] = "Internal server error: " + std::string(e.what());
                conn->send(response.dump() + "\n");
            } catch (...) {
                LOG_ERROR << "Unknown exception in message handling";
                json response;
                response["msgid"] = 999;
                response["errno"] = 7;
                response["errmsg"] = "Unknown server error";
                conn->send(response.dump() + "\n");
            }
        };
    }
}

void ChatService::login(const TcpConnectionPtr& conn,json& js,Timestamp time){
    LOG_INFO << "do login service!";

    if (!js.contains("id") || !js["id"].is_number() || !js.contains("password")) {
        LOG_ERROR << "Login request missing required fields or invalid types";
        json response;
        response["msgid"]=LOGIN_MSG_ACK;
        response["errno"]=1;
        response["errmsg"]="Invalid login request format";
        conn->send(response.dump());
        return;
    }

    long long id = js["id"].get<long long>();
    string pwd=js["password"];
    User user=_userModel.query(id);

    if(user.getId()==id&&user.getPwd()==pwd){
        if(user.getState()=="online"){
            json response;
            response["msgid"]=LOGIN_MSG_ACK;
            response["errno"]=2;
            response["errmsg"]="this account is using, input another!";
            conn->send(response.dump());
        }
        else{
            {
                lock_guard<mutex> lock(_connMutex);
                _userConnMap.insert({(int)id,conn});
                LOG_INFO << "User " << id << " added to connection map";
            }

            if(_redis.subscribe((int)id)){
                LOG_INFO << "Successfully subscribed to Redis channel for user " << id;
            }
            else{
                LOG_ERROR << "Failed to subscribe to Redis channel for user " << id;
            }

            user.setState("online");
            _userModel.updateState(user);

            LOG_INFO << "Calling pushStateUpdate for user" << user.getId() << "with state online";
            pushStateUpdate(user.getId(), "online");
            LOG_INFO << "pushStateUpdate completed for user" << user.getId();

            json response;
            response["msgid"]=LOGIN_MSG_ACK;
            response["errno"]=0;
            response["id"]=user.getId();
            response["name"]=user.getName();

            string avatarData = user.getAvatar();
            cout << "[DEBUG] Original avatar data length: " << avatarData.size() << endl;

            if (avatarData.size() >= 50) {
                cout << "[DEBUG] Avatar data header (50 bytes): ";
                for (int i = 0; i < 50; i++) {
                    printf("%02x ", (unsigned char)avatarData[i]);
                }
                cout << endl;

                cout << "[DEBUG] Avatar data header (ASCII): ";
                for (int i = 0; i < 50; i++) {
                    cout << avatarData[i];
                }
                cout << endl;
            }

            if (!avatarData.empty()) {
                string encodedAvatar = base64Encode(avatarData);
                response["avatar"] = encodedAvatar;
                cout << "[DEBUG] Base64 encoded avatar length: " << encodedAvatar.size() << endl;

                cout << "[DEBUG] Base64 encoded avatar preview: " << encodedAvatar.substr(0, 100) << (encodedAvatar.size() > 100 ? "..." : "") << endl;

                string smallEncoded = encodedAvatar.substr(0, 100);
                string smallDecoded = base64Decode(smallEncoded);
                cout << "[DEBUG] Decoded first 100 chars of Base64: ";
                for (char c : smallDecoded) {
                    printf("%02x ", (unsigned char)c);
                }
                cout << endl;
            } else {
                response["avatar"] = "";
            }

            vector<string> vec=_offlineMsgModel.query(id);
            if(!vec.empty()){
                response["offlinemsg"]=vec;
                _offlineMsgModel.remove(id);
            }

            vector<User> userVec=_friendModel.query(id);
            vector<string> vec2;
            for(User &user:userVec){
                json js;
                js["id"]=user.getId();
                js["name"]=user.getName();
                js["state"]=user.getState();
                string friendAvatarData = user.getAvatar();
                if (!friendAvatarData.empty()) {
                    js["avatar"] = base64Encode(friendAvatarData);
                } else {
                    js["avatar"] = "";
                }
                vec2.push_back(js.dump());
            }
            response["friends"]=vec2;
            cout << "[DEBUG] Added " << vec2.size() << " friends to login response" << endl;

            vector<Group> groupuserVec = _groupModel.queryGroups(id);
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
            cout << "[DEBUG] Added " << groupV.size() << " groups to login response" << endl;

            string responseStr = response.dump();
            cout << "[DEBUG] Sending login success response: " << responseStr << endl;
            conn->send(responseStr);
            cout << "[DEBUG] Login response sent successfully" << endl;
        }
    }
    else{
        cout << "[DEBUG] User authentication failed, id: " << id << endl;
        json response;
        response["msgid"]=LOGIN_MSG_ACK;
        response["errno"]=1;
        response["errmsg"]="id or password is invalid!";
        string responseStr = response.dump();
        cout << "[DEBUG] Sending login ACK (failed): " << responseStr << endl;
        conn->send(responseStr);
    }
}

void ChatService::reg(const TcpConnectionPtr& conn,json& js,Timestamp time){
    string name=js["name"];
    string pwd=js["password"];
    User user;
    user.setName(name);
    user.setPwd(pwd);
    user.setState("offline");

    bool state=_userModel.insert(user);
    if(state){
        if (js.contains("avatarData")) {
            string base64EncodedAvatar = js["avatarData"];

            string decodedAvatar = base64Decode(base64EncodedAvatar);
            LOG_INFO << "Base64 decoded avatar data length: " << decodedAvatar.size();

            _userModel.updateAvatar(user.getId(), decodedAvatar);
        }

        json response;
        response["msgid"]=REG_MSG_ACK;
        response["errno"]=0;
        response["id"]=user.getId();

        if (js.contains("avatarData")) {
            response["avatar"] = js["avatarData"];
            LOG_INFO << "Returning avatar data in registration response";
        } else {
            response["avatar"] = "";
        }

        conn->send(response.dump());
    }
    else{
        json response;
        response["msgid"]=REG_MSG_ACK;
        response["errno"]=1;
        conn->send(response.dump());
    }
}

void ChatService::loginout(const TcpConnectionPtr& conn,json& js,Timestamp time){
    int userid=js["id"].get<int>();
    {
        lock_guard<mutex> lock(_connMutex);
        auto it =_userConnMap.find(userid);
        if(it!=_userConnMap.end()){
            _userConnMap.erase(it);
        }
    }

    _redis.unsubscribe(userid);

    User user(userid,"","","offline");
    _userModel.updateState(user);

    pushStateUpdate(userid, "offline");
}

void ChatService::pushStateUpdate(int userId, const string& state) {
    LOG_INFO << "pushStateUpdate called for user" << userId << "with state" << state;

    vector<User> friends = _friendModel.query(userId);
    LOG_INFO << "Found" << friends.size() << "friends for user" << userId;

    for (const User& friendUser : friends) {
        LOG_INFO << "Friend" << friendUser.getId() << "name" << friendUser.getName() << "state" << friendUser.getState();
    }

    json stateMsg;
    stateMsg["msgid"] = STATE_UPDATE_MSG;
    stateMsg["userid"] = userId;
    stateMsg["state"] = state;

    string msgStr = stateMsg.dump();
    LOG_INFO << "State update message:" << msgStr;

    for (const User& friendUser : friends) {
        int friendId = friendUser.getId();
        LOG_INFO << "Checking if friend" << friendId << "is online";
        {
            lock_guard<mutex> lock(_connMutex);
            auto it = _userConnMap.find(friendId);
            if (it != _userConnMap.end()) {
                LOG_INFO << "Friend" << friendId << "is online, sending state update";
                it->second->send(msgStr);
                LOG_INFO << "State update sent to friend" << friendId;
            } else {
                LOG_INFO << "Friend" << friendId << "is offline, skipping state update";
            }
        }
    }
}

void ChatService::clientCloseException(const TcpConnectionPtr& conn){
    User user;
    {
        lock_guard<mutex> lock(_connMutex);
        for(auto it=_userConnMap.begin();it!=_userConnMap.end();++it){
            if(it->second==conn){
                user.setId(it->first);
                _userConnMap.erase(it);
                break;
            }
        }
    }

    _redis.unsubscribe(user.getId());

    if(user.getId()!=-1){
        user.setState("offline");
        _userModel.updateState(user);

        pushStateUpdate(user.getId(), "offline");
    }
}

void ChatService::oneChat(const TcpConnectionPtr& conn,json& js,Timestamp time){
    int toid = -1;
    if (js.contains("toid") && js["toid"].is_number()) {
        toid = js["toid"].get<int>();
    } else if (js.contains("to") && js["to"].is_number()) {
        toid = js["to"].get<int>();
    } else {
        LOG_ERROR << "One chat request missing required field 'toid' or 'to' or invalid type";
        return;
    }

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

    const int AI_BOT_ID_MIN = 10000;
    const int AI_BOT_ID_MAX = 10099;

    // ==================== AI私聊拦截逻辑 ====================
    // 如果目标用户ID在 10000~10099 范围内，说明是发给AI机器人的私聊
    // 需要将消息投递到Redis的AI专属任务队列，由Java AI服务处理并返回结果
    // 注意：AI用户不需要存储离线消息，因为AI服务会通过Redis订阅处理并返回回复
    if (toid >= AI_BOT_ID_MIN && toid <= AI_BOT_ID_MAX) {
        LOG_INFO << "Message sent to AI Bot (id=" << toid << ") from user " << fromId;

        User sender = _userModel.query(fromId);
        string senderName = sender.getName();

        string userMessage = js.value("msg", "");
        if (userMessage.empty()) {
            userMessage = js.value("message", "");
        }

        if (userMessage.empty()) {
            LOG_ERROR << "Empty message sent to AI Bot";
            return;
        }

        // 构造AI任务请求，投递到Redis桥交给Java AI服务处理
        // 包含：发送者ID、AI角色ID(botId)、消息内容
        json aiRequest;
        aiRequest["userId"] = fromId;
        aiRequest["botId"] = toid;
        aiRequest["message"] = userMessage;
        aiRequest["userName"] = senderName;

        // 将AI请求发布到Redis的AI任务频道
        // Java端的AiChatService会订阅该频道并处理
        string aiRequestStr = aiRequest.dump();
        if (_redis.publish(9999, aiRequestStr)) {
            LOG_INFO << "AI chat request published to Redis: userId=" << fromId << ", botId=" << toid;
        } else {
            LOG_ERROR << "Failed to publish AI chat request to Redis";
        }

        // AI用户不需要存储离线消息，AI服务会通过Redis返回回复
        // 离线消息表仅用于普通用户离线时保存消息
        return;
    }

    js["from"] = fromId;

    User sender = _userModel.query(fromId);
    js["name"] = sender.getName();

    js["timestamp"] = time.toFormattedString(true);

    const size_t MAX_MESSAGE_SIZE = 1024 * 1024;
    string msgStr = js.dump();
    if (msgStr.size() > MAX_MESSAGE_SIZE) {
        LOG_ERROR << "Message too large from user " << fromId << ", size: " << msgStr.size() << " bytes, max allowed: " << MAX_MESSAGE_SIZE;
        json response;
        response["msgid"] = 999;
        response["errno"] = 4;
        response["errmsg"] = "Message too large, max size is 1MB";
        conn->send(response.dump());
        return;
    }

    LOG_INFO << "Sending message from user " << fromId << " (" << sender.getName() << ") to " << toid;

     {
     lock_guard<mutex> lock(_connMutex);
     auto it=_userConnMap.find(toid);
     if(it!=_userConnMap.end()){
         it->second->send(msgStr);
         LOG_INFO << "Message sent directly to online user " << toid;
         return;
         }
     }

    User user=_userModel.query(toid);
    LOG_INFO << "User " << toid << " state: " << user.getState();
    if(user.getState()=="online"){
        LOG_INFO << "Publishing message to Redis for user " << toid;
          if(_redis.publish(toid,msgStr)){
           LOG_INFO << "Message published to Redis successfully";
       }else{
           LOG_ERROR << "Failed to publish message to Redis";
       }
       return;
     }

      LOG_INFO << "Storing offline message for user " << toid;
      _offlineMsgModel.insert(toid, msgStr);
      LOG_INFO << "User " << toid << " is offline, message stored";
}

void ChatService::addFriend(const TcpConnectionPtr& conn,json& js,Timestamp time){
    if (!js.contains("id") || !js["id"].is_number() || !js.contains("friendid") || !js["friendid"].is_number()) {
        LOG_ERROR << "Add friend request missing required fields or invalid types";
        return;
    }

    int userid=js["id"].get<int>();
    int friendid=js["friendid"].get<int>();
    _friendModel.insert(userid,friendid);

    json response;
    response["msgid"]=QUERY_FRIEND_MSG_ACK;
    response["errno"]=0;

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

void ChatService::createGroup(const TcpConnectionPtr& conn,json& js,Timestamp time){
    try {
        if (!js.contains("id") || !js["id"].is_number() ||
            !js.contains("groupname") || !js["groupname"].is_string() ||
            !js.contains("groupdesc") || !js["groupdesc"].is_string()) {
            LOG_ERROR << "Create group request missing required fields or invalid types";
            return;
        }

        int userid = js["id"].get<int>();
        string name = js["groupname"];
        string desc = js["groupdesc"];

        Group group(-1,name,desc);
        if(_groupModel.createGroup(group)){
            _groupModel.addGroup(userid,group.getId(),"creator");

            json response;
            response["msgid"]=QUERY_GROUP_MSG_ACK;
            response["errno"]=0;

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
            json response;
            response["msgid"]=QUERY_GROUP_MSG_ACK;
            response["errno"]=1;
            response["errmsg"]="Failed to create group, group name may already exist";
            conn->send(response.dump());
        }
    } catch (const json::exception& e) {
        LOG_ERROR << "JSON exception in create group: " << e.what();
        return;
    }
}

void ChatService::addGroup(const TcpConnectionPtr& conn,json& js,Timestamp time){
    try {
        if (!js.contains("groupid") || !js["groupid"].is_number()) {
            LOG_ERROR << "Add group request missing required field 'groupid' or invalid type";
            return;
        }

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

        int groupid = js["groupid"].get<int>();

        _groupModel.addGroup(userid,groupid,"normal");

        json response;
        response["msgid"]=QUERY_GROUP_MSG_ACK;
        response["errno"]=0;

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
        LOG_ERROR << "JSON exception in add group: " << e.what();
        return;
    }
}

void ChatService::groupChat(const TcpConnectionPtr& conn,json& js,Timestamp time){
    if (!js.contains("groupid") || !js["groupid"].is_number()) {
        LOG_ERROR << "Group chat request missing required field 'groupid' or invalid type";
        return;
    }

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
    js["from"] = userid;

    User sender = _userModel.query(userid);
    js["fromName"] = sender.getName();

    string senderAvatar = sender.getAvatar();
    if (!senderAvatar.empty()) {
        js["avatar"] = base64Encode(senderAvatar);
    } else {
        js["avatar"] = "";
    }

    js["timestamp"] = time.toFormattedString(true);

     vector<int> useridVec=_groupModel.queryGroupUsers(userid,groupid);

     // ==================== AI群聊拦截逻辑（@AI触发） ====================
     // 只有消息中@了AI，才触发对应AI回复
     // AI名称与ID映射：旗舰大师(10000)、严厉导师(10001)、温柔学长(10002)、代码审查员(10003)
     const int AI_BOT_ID_MIN = 10000;
     const int AI_BOT_ID_MAX = 10099;
     
     string messageContent = js.value("msg", js.value("message", ""));
     vector<int> mentionedAiBotIds;
     
     map<string, int> aiNameToId = {
         {"旗舰大师", 10000},
         {"严厉导师", 10001},
         {"温柔学长", 10002},
         {"代码审查员", 10003}
     };
     
     for (const auto& pair : aiNameToId) {
         string mentionPattern = "@" + pair.first;
         if (messageContent.find(mentionPattern) != string::npos) {
             for (int id : useridVec) {
                 if (id == pair.second) {
                     mentionedAiBotIds.push_back(id);
                     LOG_INFO << "Message mentions AI: " << pair.first << " (id=" << id << ")";
                     break;
                 }
             }
         }
     }

     // 只有被@的AI才需要回复
     if (!mentionedAiBotIds.empty()) {
         LOG_INFO << "Group " << groupid << " message mentions " << mentionedAiBotIds.size() << " AI bots, forwarding to Java AI service";

         json aiGroupRequest;
         aiGroupRequest["groupId"] = groupid;
         aiGroupRequest["senderId"] = userid;
         aiGroupRequest["senderName"] = sender.getName();
         aiGroupRequest["content"] = messageContent;
         aiGroupRequest["aiBotIds"] = mentionedAiBotIds;

         string aiGroupRequestStr = aiGroupRequest.dump();
         if (_redis.publish(9998, aiGroupRequestStr)) {
             LOG_INFO << "AI group chat request published to Redis: groupId=" << groupid
                      << ", mentionedAiBotIds count=" << mentionedAiBotIds.size();
         } else {
             LOG_ERROR << "Failed to publish AI group chat request to Redis";
         }
     }

     // ==================== 正常群聊消息分发 ====================
     // 照常给群里的真实人类用户（id < 10000）转发消息
     // AI成员不需要通过C++转发，它们由Java端直接通过Redis Pub/Sub回复
     lock_guard<mutex> lock(_connMutex);
     for(int id:useridVec){
         // 跳过AI机器人，它们由Java端处理
         if (id >= AI_BOT_ID_MIN && id <= AI_BOT_ID_MAX) {
             continue;
         }

         auto it=_userConnMap.find(id);
         if(it!=_userConnMap.end()){
             it->second->send(js.dump());
         }
         else{
              User user=_userModel.query(id);
              if(user.getState()=="online"){
                 _redis.publish(id,js.dump());
              }
              else{
                  string offlineMsg = js.dump();
                  LOG_INFO << "Storing group offline message: " << offlineMsg;
                  _offlineMsgModel.insert(id, offlineMsg);
               }
          }
      }
}

void ChatService::inviteToGroup(const TcpConnectionPtr& conn,json& js,Timestamp time){
    LOG_INFO << "do invite to group service!";

    if (!js.contains("id") || !js["id"].is_number() ||
        !js.contains("groupid") || !js["groupid"].is_number() ||
        !js.contains("targetid") || !js["targetid"].is_number()) {
        LOG_ERROR << "Invite to group request missing required fields or invalid types";
        json response;
        response["msgid"] = INVITE_GROUP_MSG_ACK;
        response["errno"] = 1;
        response["errmsg"] = "Invalid invite request format";
        conn->send(response.dump());
        return;
    }

    int inviterId = js["id"].get<int>();
    int groupid = js["groupid"].get<int>();
    int targetid = js["targetid"].get<int>();

    LOG_INFO << "User " << inviterId << " inviting user " << targetid << " to group " << groupid;

    const int AI_BOT_ID_MIN = 10000;
    const int AI_BOT_ID_MAX = 10099;

    bool dbResult = _groupModel.addGroup(targetid, groupid, "normal");
    if (!dbResult) {
        LOG_ERROR << "DB insert failed: user " << targetid << " could not be added to group " << groupid;
        json response;
        response["msgid"] = INVITE_GROUP_MSG_ACK;
        response["errno"] = 2;
        response["errmsg"] = "Database error: failed to add user to group";
        conn->send(response.dump());
        return;
    }
    LOG_INFO << "DB insert success: user " << targetid << " added to group " << groupid;

    json response;
    response["msgid"] = INVITE_GROUP_MSG_ACK;
    response["errno"] = 0;
    response["inviterid"] = inviterId;
    response["groupid"] = groupid;
    response["targetid"] = targetid;

    vector<Group> groupuserVec = _groupModel.queryGroups(inviterId);
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

    conn->send(response.dump());

    if (targetid < AI_BOT_ID_MIN || targetid > AI_BOT_ID_MAX) {
        User targetUser = _userModel.query(targetid);
        json notify;
        notify["msgid"] = INVITE_GROUP_MSG_ACK;
        notify["errno"] = 0;
        notify["inviterid"] = inviterId;
        notify["groupid"] = groupid;
        notify["targetid"] = targetid;
        notify["notify"] = true;

        string notifyStr = notify.dump();

        {
            lock_guard<mutex> lock(_connMutex);
            auto it = _userConnMap.find(targetid);
            if (it != _userConnMap.end()) {
                it->second->send(notifyStr);
                LOG_INFO << "Invite notification sent directly to online user " << targetid;
            }
        }

        if (targetUser.getState() == "online") {
            if (_redis.publish(targetid, notifyStr)) {
                LOG_INFO << "Invite notification published to Redis for user " << targetid;
            }
        }
    } else {
        LOG_INFO << "Target user " << targetid << " is AI bot, skipping notification";
    }
}

void ChatService::fileTransferRequest(const TcpConnectionPtr& conn, json& js, Timestamp time) {
    LOG_INFO << "File transfer request received";

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

    {
        lock_guard<mutex> lock(_connMutex);
        auto it = _userConnMap.find(toId);
        if (it != _userConnMap.end()) {
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

    json offlineMsg;
    offlineMsg["msgid"] = FILE_TRANSFER_REQ;
    offlineMsg["from"] = fromId;
    offlineMsg["filename"] = filename;
    offlineMsg["filesize"] = filesize;
    offlineMsg["fileid"] = fileId;

    _offlineMsgModel.insert(toId, offlineMsg.dump());
    LOG_INFO << "File transfer request stored as offline message for user " << toId;

    json reply;
    reply["msgid"] = FILE_TRANSFER_ERROR;
    reply["errno"] = 1;
    reply["errmsg"] = "Recipient is offline";
    conn->send(reply.dump());
}

void ChatService::fileTransferData(const TcpConnectionPtr& conn, json& js, Timestamp time) {
    LOG_INFO << "File transfer data received";

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

    {
        lock_guard<mutex> lock(_connMutex);
        auto it = _userConnMap.find(toId);
        if (it != _userConnMap.end()) {
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

    json reply;
    reply["msgid"] = FILE_TRANSFER_ERROR;
    reply["errno"] = 2;
    reply["errmsg"] = "Recipient went offline during file transfer";
    conn->send(reply.dump());
}

void ChatService::fileTransferAck(const TcpConnectionPtr& conn, json& js, Timestamp time) {
    LOG_INFO << "File transfer acknowledgment received";

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

    {
        lock_guard<mutex> lock(_connMutex);
        auto it = _userConnMap.find(toId);
        if (it != _userConnMap.end()) {
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

    json reply;
    reply["msgid"] = FILE_TRANSFER_ERROR;
    reply["errno"] = 3;
    reply["errmsg"] = "Recipient went offline";
    conn->send(reply.dump());
    LOG_INFO << "Recipient offline, sent error to file transfer acknowledgment sender";
}

void ChatService::fileTransferComplete(const TcpConnectionPtr& conn, json& js, Timestamp time) {
    LOG_INFO << "File transfer complete notification received";

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

    {
        lock_guard<mutex> lock(_connMutex);
        auto it = _userConnMap.find(toId);
        if (it != _userConnMap.end()) {
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

    json offlineMsg;
    offlineMsg["msgid"] = FILE_TRANSFER_COMPLETE;
    offlineMsg["from"] = fromId;
    offlineMsg["fileid"] = fileId;
    offlineMsg["success"] = success;

    _offlineMsgModel.insert(toId, offlineMsg.dump());
}

void ChatService::handleRedisSubscribeMessage(long long channel, string msg)
{
    LOG_INFO << "Received message from Redis on channel " << channel;
    LOG_INFO << "Message content: " << msg;

    try {
        json js = json::parse(msg);
        if (!js.contains("msgid") || !js["msgid"].is_number()) {
            LOG_ERROR << "Message from Redis missing valid msgid field, channel: " << channel;
            return;
        }
    } catch (const json::exception& e) {
        LOG_ERROR << "Failed to parse message from Redis, error: " << e.what() << ", channel: " << channel;
        return;
    }

    if (channel == GROUP_DISPATCH_CHANNEL) {
        handleGroupDispatchMessage(msg);
        return;
    }

    lock_guard<mutex> lock(_connMutex);
    auto it = _userConnMap.find(static_cast<int>(channel));
    if (it != _userConnMap.end())
    {
        LOG_INFO << "Found user " << channel << " in connection map";
        it->second->send(msg);
        LOG_INFO << "Message forwarded to user " << channel;
        return;
    }
    else{
        LOG_INFO << "User " << channel << " not found in connection map, storing as offline message";
        _offlineMsgModel.insert(channel, msg);
    }
}

void ChatService::handleGroupDispatchMessage(const string& msg)
{
    LOG_INFO << "Handling group dispatch message: " << msg;
    
    try {
        json js = json::parse(msg);
        
        if (!js.contains("groupid") || !js["groupid"].is_number()) {
            LOG_ERROR << "Group dispatch message missing groupid";
            return;
        }
        
        int groupid = js["groupid"].get<int>();
        int fromId = js.contains("from") ? js["from"].get<int>() : -1;
        
        LOG_INFO << "Dispatching group message to group: " << groupid << ", from: " << fromId;
        
        vector<int> useridVec = _groupModel.queryGroupUsers(fromId > 0 ? fromId : 1, groupid);
        
        const int AI_BOT_ID_MIN = 10000;
        const int AI_BOT_ID_MAX = 10099;
        
        lock_guard<mutex> lock(_connMutex);
        for (int userid : useridVec) {
            if (userid == fromId) {
                continue;
            }
            
            if (userid >= AI_BOT_ID_MIN && userid <= AI_BOT_ID_MAX) {
                LOG_INFO << "Skipping AI bot: " << userid << ", no offline message storage";
                continue;
            }
            
            auto it = _userConnMap.find(userid);
            if (it != _userConnMap.end()) {
                LOG_INFO << "Forwarding group message to online user: " << userid;
                it->second->send(msg);
            } else {
                User user = _userModel.query(userid);
                if (user.getState() == "online") {
                    _redis.publish(userid, msg);
                } else {
                    LOG_INFO << "Storing group offline message for user: " << userid;
                    _offlineMsgModel.insert(userid, msg);
                }
            }
        }
        
        LOG_INFO << "Group dispatch completed for group: " << groupid;
        
    } catch (const json::exception& e) {
        LOG_ERROR << "Failed to parse group dispatch message: " << e.what();
    }
}

void ChatService::queryFriendList(const TcpConnectionPtr& conn, json& js, Timestamp time) {
    LOG_INFO << "do query friend list service!";

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
            string friendAvatarData = user.getAvatar();
            if (!friendAvatarData.empty()) {
                js["avatar"] = base64Encode(friendAvatarData);
            } else {
                js["avatar"] = "";
            }
            vec.push_back(js.dump());
        }
        response["friends"] = vec;
    }

    string responseStr = response.dump();
    cout << "[DEBUG] Sending friend list response: " << responseStr << endl;
    conn->send(responseStr);
}

void ChatService::queryGroupList(const TcpConnectionPtr& conn, json& js, Timestamp time) {
    LOG_INFO << "do query group list service!";

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

void ChatService::uploadEmoji(const TcpConnectionPtr& conn, json& js, Timestamp time) {
    LOG_INFO << "do upload emoji service!";

    if (!js.contains("id") || !js["id"].is_number() ||
        !js.contains("name") || !js["name"].is_string() ||
        !js.contains("imageData") || !js["imageData"].is_string()) {
        LOG_ERROR << "Upload emoji request missing required fields or invalid types";
        json response;
        response["msgid"] = UPLOAD_EMOJI_MSG_ACK;
        response["errno"] = 1;
        response["errmsg"] = "Invalid upload emoji request format";
        conn->send(response.dump());
        return;
    }

    long long userId = js["id"].get<long long>();
    string name = js["name"];
    string imageData = js["imageData"];

    const size_t MAX_EMOJI_SIZE = 1024 * 1024;
    if (imageData.size() > MAX_EMOJI_SIZE) {
        LOG_ERROR << "Emoji too large from user " << userId << ", size: " << imageData.size() << " bytes, max allowed: " << MAX_EMOJI_SIZE;
        json response;
        response["msgid"] = UPLOAD_EMOJI_MSG_ACK;
        response["errno"] = 2;
        response["errmsg"] = "Emoji too large, max size is 1MB";
        conn->send(response.dump());
        return;
    }

    Emoji emoji(userId, name, imageData);
    if (_emojiModel.insert(emoji)) {
        json response;
        response["msgid"] = UPLOAD_EMOJI_MSG_ACK;
        response["errno"] = 0;
        response["emojiId"] = emoji.getId();
        response["name"] = name;
        response["errmsg"] = "Upload emoji success";
        conn->send(response.dump());
        LOG_INFO << "Upload emoji success for user " << userId;
    } else {
        json response;
        response["msgid"] = UPLOAD_EMOJI_MSG_ACK;
        response["errno"] = 3;
        response["errmsg"] = "Upload emoji failed";
        conn->send(response.dump());
        LOG_ERROR << "Upload emoji failed for user " << userId;
    }
}

void ChatService::queryEmojiList(const TcpConnectionPtr& conn, json& js, Timestamp time) {
    LOG_INFO << "do query emoji list service!";

    if (!js.contains("id") || !js["id"].is_number()) {
        LOG_ERROR << "Query emoji list request missing required field 'id' or invalid type";
        json response;
        response["msgid"] = QUERY_EMOJI_LIST_MSG_ACK;
        response["errno"] = 1;
        response["errmsg"] = "Invalid request format";
        conn->send(response.dump());
        return;
    }

    long long userId = js["id"].get<long long>();
    LOG_INFO << "Querying emoji list for user: " << userId;

    vector<Emoji> emojiList = _emojiModel.queryByUserId(userId);
    LOG_INFO << "Found " << emojiList.size() << " emojis for user: " << userId;

    json response;
    response["msgid"] = QUERY_EMOJI_LIST_MSG_ACK;
    response["errno"] = 0;

    if (!emojiList.empty()) {
        vector<string> vec;
        for (Emoji& emoji : emojiList) {
            json emojiJson;
            emojiJson["id"] = emoji.getId();
            emojiJson["userId"] = emoji.getUserId();
            emojiJson["name"] = emoji.getName();
            emojiJson["imageData"] = emoji.getImageData();
            emojiJson["createTime"] = emoji.getCreateTime();
            vec.push_back(emojiJson.dump());
        }
        response["emojis"] = vec;
    }

    string responseStr = response.dump();
    LOG_INFO << "Sending emoji list response for user " << userId;
    conn->send(responseStr);
}

void ChatService::uploadAvatar(const TcpConnectionPtr& conn, json& js, Timestamp time) {
    LOG_INFO << "do upload avatar service!";

    if (!js.contains("id") || !js["id"].is_number() || !js.contains("avatarData")) {
        LOG_ERROR << "Upload avatar request missing required fields or invalid types";
        json response;
        response["msgid"] = UPLOAD_AVATAR_MSG_ACK;
        response["errno"] = 1;
        response["errmsg"] = "Invalid request format";
        conn->send(response.dump());
        return;
    }

    long long userId = js["id"].get<long long>();
    string base64EncodedAvatar = js["avatarData"];

    string decodedAvatar = base64Decode(base64EncodedAvatar);
    LOG_INFO << "Base64 decoded avatar data length: " << decodedAvatar.size();

    if (_userModel.updateAvatar(userId, decodedAvatar)) {
        LOG_INFO << "Upload avatar success for user: " << userId;
        json response;
        response["msgid"] = UPLOAD_AVATAR_MSG_ACK;
        response["errno"] = 0;
        response["avatar"] = base64EncodedAvatar;
        conn->send(response.dump());
    } else {
        LOG_ERROR << "Failed to update avatar in database for user: " << userId;
        json response;
        response["msgid"] = UPLOAD_AVATAR_MSG_ACK;
        response["errno"] = 3;
        response["errmsg"] = "Failed to update avatar in database";
        conn->send(response.dump());
    }
}

void ChatService::updateAvatar(const TcpConnectionPtr& conn, json& js, Timestamp time) {
    LOG_INFO << "do update avatar service!";

    try {
        LOG_INFO << "Checking required fields...";
        if (!js.contains("id") || !js["id"].is_number()) {
            LOG_ERROR << "Update avatar request missing required field 'id' or invalid type";
            json response;
            response["msgid"] = UPDATE_AVATAR_MSG_ACK;
            response["errno"] = 1;
            response["errmsg"] = "Invalid request format: missing 'id'";
            conn->send(response.dump());
            return;
        }

        if (!js.contains("avatarData")) {
            LOG_ERROR << "Update avatar request missing required field 'avatarData'";
            json response;
            response["msgid"] = UPDATE_AVATAR_MSG_ACK;
            response["errno"] = 1;
            response["errmsg"] = "Invalid request format: missing 'avatarData'";
            conn->send(response.dump());
            return;
        }

        LOG_INFO << "avatarData type: " << js["avatarData"].type_name() << ", contains: " << js.contains("avatarData");

        long long userId = js["id"].get<long long>();
        LOG_INFO << "User ID: " << userId;

        string base64EncodedAvatar;
        if (js["avatarData"].is_string()) {
            base64EncodedAvatar = js["avatarData"].get<string>();
            LOG_INFO << "Avatar data length: " << base64EncodedAvatar.size();
        } else {
            LOG_ERROR << "Invalid avatarData type: " << js["avatarData"].type_name();
            json response;
            response["msgid"] = UPDATE_AVATAR_MSG_ACK;
            response["errno"] = 1;
            response["errmsg"] = "Invalid avatarData type";
            conn->send(response.dump());
            return;
        }

        string decodedAvatar = base64Decode(base64EncodedAvatar);
        LOG_INFO << "Base64 decoded avatar data length: " << decodedAvatar.size();

        LOG_INFO << "Calling _userModel.updateAvatar...";
        if (_userModel.updateAvatar(userId, decodedAvatar)) {
            LOG_INFO << "Update avatar success for user: " << userId;
            json response;
            response["msgid"] = UPDATE_AVATAR_MSG_ACK;
            response["errno"] = 0;
            response["avatar"] = base64EncodedAvatar;
            conn->send(response.dump());
        } else {
            LOG_ERROR << "Failed to update avatar in database for user: " << userId;
            json response;
            response["msgid"] = UPDATE_AVATAR_MSG_ACK;
            response["errno"] = 3;
            response["errmsg"] = "Failed to update avatar in database";
            conn->send(response.dump());
        }
    } catch (const exception& e) {
        LOG_ERROR << "Exception in updateAvatar: " << e.what();
        json response;
        response["msgid"] = UPDATE_AVATAR_MSG_ACK;
        response["errno"] = 999;
        response["errmsg"] = "Internal server error: " + string(e.what());
        conn->send(response.dump());
    }
    LOG_INFO << "updateAvatar method completed";
}
