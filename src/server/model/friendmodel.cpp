#include"friendmodel.hpp"
#include"db.h"

// 添加好友关系 - 社交关系管理
// 业务逻辑：建立用户之间的好友关系，支持双向好友系统的数据基础
void FriendModel::insert(int userid,int friendid){
    // SQL语句构造 - 关系数据持久化
    char sql[1024]={0};
    sprintf(sql,"insert into friend values(%d,%d)",userid,friendid);
    
    // 数据库连接和操作 - 事务一致性保障
    MySQL mysql;
    if(mysql.connect()){
        // 执行插入操作 - 社交关系建立
        mysql.update(sql);
    }
}

// 查询好友列表 - 用户社交圈获取
// 业务逻辑：获取指定用户的完整好友信息，包括在线状态，支持实时社交功能
vector<User> FriendModel::query(int userid){
    // SQL语句构造 - 多表关联查询
    // 关键业务：通过INNER JOIN关联user和friend表，一次性获取好友详细信息
    char sql[1024]={0};
    sprintf(sql,"select a.id,a.name,a.state from user a inner join friend b on b.friendid=a.id where b.userid=%d",userid);
    
    // 结果集容器初始化
    vector<User> vec;
    
    // 数据库操作执行
    MySQL mysql;
    if(mysql.connect()){
        // 执行查询 - 数据检索
        MYSQL_RES *res=mysql.query(sql);
        if(res!=nullptr){
            MYSQL_ROW row;
            
            // 批量数据处理 - 结果集迭代和对象映射
            while((row=mysql_fetch_row(res))!=nullptr){
                // 对象实例化 - 好友信息封装
                User user;
                user.setId(atoi(row[0]));      // 用户ID转换和设置
                user.setName(row[1]);          // 好友昵称
                user.setState(row[2]);         // 在线状态获取（用于实时显示）
                vec.push_back(user);           // 添加到结果集
            }
            
            // 资源管理 - 防止内存泄漏
            mysql_free_result(res);
            return vec;
        }
    }
    
    // 查询失败 - 返回空结果集
    return vec;
}                      