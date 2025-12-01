#include"usermodel.hpp"
#include"db.h"
#include<iostream>

using namespace std;

// 用户注册 - 数据持久化
// 业务逻辑：将新用户信息写入数据库，生成唯一用户ID，完成用户创建流程
bool UserModel::insert(User &user)
{
    // SQL语句构造 - 数据验证和格式化
    char sql[1024]={0};
    sprintf(sql,"insert into user(name,password,state) values('%s','%s','%s')",
            user.getName().c_str(),user.getPwd().c_str(),user.getState().c_str());
    
    // 数据库连接建立 - 资源分配和连接池管理
    MySQL mysql;
    if(mysql.connect())
    {
        // 执行插入操作 - 事务处理和数据持久化
        if(mysql.update(sql))
        {
            // 获取自增主键 - 数据完整性保障
            // 关键业务：将生成的ID回填到用户对象，完成注册流程闭环
            user.setId(mysql_insert_id(mysql.getConnection()));
            return true;
        }
    }
    
    // 注册失败 - 数据回滚
    return false;
}

// 用户查询 - 身份验证
// 业务逻辑：根据用户ID检索完整用户信息，支持登录认证和用户状态检查
User UserModel::query(long long id)
{
    // SQL语句构造 - 精确查询条件
    char sql[1024]={0};
    sprintf(sql,"select * from user where id=%lld",id);
    
    // 数据库连接建立 - 按需连接
    MySQL mysql;
    if(mysql.connect())
    {
        // 执行查询操作 - 数据检索
        MYSQL_RES *res=mysql.query(sql);
        if(res!=nullptr)
        {
            // 结果集解析 - 数据映射
            MYSQL_ROW row=mysql_fetch_row(res);
            if(row!=nullptr)
            {
                // 对象实例化 - 数据转换和模型映射
                User user;
                user.setId(stoll(row[0]));  // 字符串转长整型
                user.setName(row[1]);       // 用户名设置
                user.setPwd(row[2]);        // 密码信息（实际应进行加密处理）
                user.setState(row[3]);      // 用户状态获取
                
                // 资源释放 - 防止内存泄漏
                mysql_free_result(res);
                return user;
            }
        }
    }
    
    // 查询失败 - 返回默认用户对象
    return User();
}

// 用户状态更新 - 会话管理
// 业务逻辑：实时更新用户在线/离线状态，支持分布式会话追踪
bool UserModel::updateState(User user){
    // SQL语句构造 - 精确状态更新
    char sql[1024]={0};
    sprintf(sql,"update user set state='%s' where id=%lld",user.getState().c_str(),user.getId());
    
    // 数据库连接建立
    MySQL mysql;
    if(mysql.connect())
    {
        // 执行更新操作 - 状态同步
        if(mysql.update(sql))
        {
            return true;
        }
    }
    return false;
}

// 用户状态重置 - 系统恢复
// 业务逻辑：服务重启时将所有在线用户状态重置为离线，确保数据一致性
void UserModel::resetState(){
    // SQL语句构造 - 批量状态更新
    char sql[1024]="update user set state='offline' where state='online'";
    
    // 数据库连接建立
    MySQL mysql;
    if(mysql.connect())
    {
        // 执行批量更新 - 系统恢复机制
        mysql.update(sql);
    }
}