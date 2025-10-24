#ifndef GROUPMODEL_H
#define GROUPMODEL_H

#include"group.hpp"
#include<vector>
#include<string>
using namespace std;
//维护群组信息的操作接口方法  
class GroupModel
{
public:
    //创建群组 群名是唯一的，群号自动生成
    bool createGroup(Group &group);
    //加入群组
    void addGroup(int userid,int groupid,string role);
    //查询用户所在的群组信息
    vector<Group> queryGroups(int userid);
    //根据指定的groupid查询群组用户id列表，除userid自己之外，主要用于群聊业务给群组其他成员群发消息,在线直接接收到信息，离线存储离线消息
    vector<int> queryGroupUsers(int userid,int groupid);
};

#endif