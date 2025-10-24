#ifndef GROUP_H
#define GROUP_H

#include"groupuser.hpp"
#include<vector>
#include<string>
using namespace std;

//User表的ORM类
class Group
{
public:
    Group(int id=-1,string name="",string desc=""){
        this->_id=id;
        this->_name=name;
        this->_desc=desc;
    }
    void setId(int id){this->_id=id;}
    void setName(string name){this->_name=name;}
    void setDesc(string desc){this->_desc=desc;}
    int getId(){return this->_id;}
    string getName(){return this->_name;}
    string getDesc(){return this->_desc;}
    vector<GroupUser>& getUsers(){return this->users;}

private:
    int _id;//群组id
    string _name;//群组名称
    string _desc;//群组描述
    vector<GroupUser> users;//群组用户列表 由于包含一个grouprole字段,所以并没有使用user，而是groupuser
};
#endif