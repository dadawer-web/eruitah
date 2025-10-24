#ifndef GROUPUSER_H
#define GROUPUSER_H
#include"user.hpp"
//群组角色，多了一个role角色信息，从User类继承而来，复用User的其他信息
class GroupUser : public User//// 单冒号表示继承  // 类外定义成员函数时使用 ::void GroupUser::someFunction() {  // 双冒号表示作用域
{
public:
    void setRole(string role){this->role=role;}
    string getRole(){return this->role;}
private:
    string role;//在群组中的角色信息
};


#endif