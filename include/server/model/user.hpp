#ifndef USER_H
#define USER_H
#include<string>
using namespace std;
//匹配User表的ORM类
class User{
  public:
    User(long long id=-1,string name="",string pwd="",string state="offline")
    {
        this->_id=id;
        this->name=name;
        this->password=pwd;
        this->state=state;
    }
    void setId(long long id){this->_id=id;}
    void setName(string name){this->name=name;}
    void setPwd(string pwd){this->password=pwd;}
    void setState(string state){this->state=state;}
    long long getId(){return this->_id;}
    string getName(){return this->name;}
    string getPwd(){return this->password;}
    string getState(){return this->state;}
protected:
    long long _id; // 使用long long支持大整数用户ID
    string name;
    string password;
    string state;
};

#endif