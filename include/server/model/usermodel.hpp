#ifndef USERMODEL_H
#define USERMODEL_H
#include"user.hpp"
//User表的数据操作类
class UserModel{
public:
    //User表的增加方法
    bool insert(User &user);

    //根据用户号码查询用户信息 - 使用long long支持大整数用户ID
    User query(long long id);

    //更新用户的状态信息
    bool updateState(User user);
    
    // 更新用户头像
    bool updateAvatar(long long id, const string& avatar);

    //重置用户的状态信息
    void resetState();
};



#endif