#ifndef FRIENDMODEL_H
#define FRIENDMODEL_H

#include"user.hpp"
#include<vector>
using namespace std;

//维护好友信息的操作接口方法  
class FriendModel
{
public:
    //添加好友 后期可以去做删除好友功能
    void insert(int userid,int friendid);
    
    //返回用户的好友列表 friendid  name state     两表联合查询
    vector<User> query(int userid);

};

#endif