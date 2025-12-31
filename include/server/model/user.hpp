#ifndef USER_H
#define USER_H
#include<string>
using namespace std;
//匹配User表的ORM类
class User{
  public:
    User(long long id=-1,string name="",string pwd="",string state="offline",string avatar="")
    {
        this->_id=id;
        this->name=name;
        this->password=pwd;
        this->state=state;
        this->avatar=avatar;
    }
    void setId(long long id){this->_id=id;}
    void setName(string name){this->name=name;}
    void setPwd(string pwd){this->password=pwd;}
    void setState(string state){this->state=state;}
    void setAvatar(string avatar){this->avatar=avatar;}
    long long getId() const {return this->_id;}
    string getName() const {return this->name;}
    string getPwd() const {return this->password;}
    string getState() const {return this->state;}
    string getAvatar() const {return this->avatar;}
protected:
    long long _id; // 使用long long支持大整数用户ID
    string name;
    string password;
    string state;
    string avatar; // 头像路径
};

#endif