#include"UserModel.hpp"
#include"db.h"
#include<iostream>

using namespace std;
//User表的增加方法
bool UserModel::insert(User &user)
{
    //1.组装sql语句
    char sql[1024]={0};
    sprintf(sql,"insert into user(name,password,state) values('%s','%s','%s')",//sprintf字符串拼接方法
            user.getName().c_str(),user.getPwd().c_str(),user.getState().c_str());
    //2.创建数据库连接
    MySQL mysql;
    if(mysql.connect())
    {
        //3.执行sql语句
        if(mysql.update(sql))
        {
            //4.获取插入成功的用户数据生成的主键id
            user.setId(mysql_insert_id(mysql.getConnection()));
            return true;
        }
    }
    return false;
}
//根据用户号码查询用户信息
User UserModel::query(int id)
{
    //1.组装sql语句
    char sql[1024]={0};
    sprintf(sql,"select * from user where id=%d",id);
    //2.创建数据库连接
    MySQL mysql;
    if(mysql.connect())
    {
        MYSQL_RES *res=mysql.query(sql);
        if(res!=nullptr)//如果查询成功
        {
            MYSQL_ROW row=mysql_fetch_row(res);//fetch_row从结果集中获取一行数据
            if(row!=nullptr)
            {
                User user;
                user.setId(atoi(row[0]));//atoi字符串转整数
                user.setName(row[1]);
                user.setPwd(row[2]);
                user.setState(row[3]);
                mysql_free_result(res);//释放资源
                return user;
            }
        }
    }
    return User();
}
    //更新用户的状态信息
bool UserModel::updateState(User user){
    //1.组装sql语句
    char sql[1024]={0};
    sprintf(sql,"update user set state='%s' where id=%d",user.getState().c_str(),user.getId());
    //2.创建数据库连接
    MySQL mysql;
    if(mysql.connect())
    {
        //3.执行sql语句
        if(mysql.update(sql))
        {
            return true;
        }
    }
    return false;
}
//重置用户的状态信息
void UserModel::resetState(){
    //组装sql语句
    char sql[1024]="update user set state='offline' where state='online'";
    //创建数据库连接
    MySQL mysql;
    if(mysql.connect())
    {
        mysql.update(sql);
    }
}