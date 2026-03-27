#include"friendmodel.hpp"
#include"db.h"
#include <cstring>
#include <iostream>

// 添加好友关系 - 社交关系管理
// 业务逻辑：建立用户之间的好友关系，支持双向好友系统的数据基础
void FriendModel::insert(int userid,int friendid){
    // SQL语句构造 - 关系数据持久化
    char sql[1024]={0};
    
    // 检查是否已经是好友 - 防止重复添加
    char checkSql[1024]={0};
    sprintf(checkSql,"select count(*) from friend where userid=%d and friendid=%d",userid,friendid);
    
    MySQL mysql;
    if(mysql.connect()){
        // 执行检查查询
        MYSQL_RES *res=mysql.query(checkSql);
        if(res!=nullptr){
            MYSQL_ROW row=mysql_fetch_row(res);
            if(row!=nullptr && atoi(row[0])>0){
                // 已经是好友，直接返回
                mysql_free_result(res);
                return;
            }
            mysql_free_result(res);
        }
        
        // 双向好友关系：A添加B为好友，B也添加A为好友
        // 第一次插入：userid -> friendid
        sprintf(sql,"INSERT IGNORE INTO friend values(%d,%d)",userid,friendid);
        
        // 数据库连接和操作 - 事务一致性保障
        // 执行第一次插入操作 - 社交关系建立
        mysql.update(sql);
        
        // 第二次插入：friendid -> userid
        memset(sql, 0, sizeof(sql));
        sprintf(sql,"INSERT IGNORE INTO friend values(%d,%d)",friendid,userid);
        mysql.update(sql);
    }
}

// 查询好友列表 - 用户社交圈获取
// 业务逻辑：获取指定用户的完整好友信息，包括在线状态，支持实时社交功能
vector<User> FriendModel::query(int userid){
    // SQL语句构造 - 多表关联查询
    // 关键业务：通过INNER JOIN关联user和friend表，一次性获取好友详细信息
    char sql[1024]={0};
    sprintf(sql,"select a.id,a.name,a.state,a.avatar from user a inner join friend b on b.friendid=a.id where b.userid=%d",userid);
    
    // 结果集容器初始化
    vector<User> vec;
    
    // 数据库操作执行
    MySQL mysql;
    if(mysql.connect()){
        // 执行查询 - 数据检索
        MYSQL_RES *res=mysql.query(sql);
        if(res!=nullptr){
            MYSQL_ROW row;
            
            // 获取字段数量
            unsigned int fieldCount = mysql_num_fields(res);
            
            // 批量数据处理 - 结果集迭代和对象映射
            while((row=mysql_fetch_row(res))!=nullptr){
                // 对象实例化 - 好友信息封装
                User user;
                user.setId(atoi(row[0]));      // 用户ID转换和设置
                user.setName(row[1]);          // 好友昵称
                user.setState(row[2]);         // 在线状态获取（用于实时显示）
                
                // 处理BLOB类型的头像数据
                if (fieldCount > 3 && row[3] != nullptr) {
                    // 获取头像字段的长度 - 必须在mysql_fetch_row之后立即调用
                    unsigned long *lengths = mysql_fetch_lengths(res);
                    if (lengths && lengths[3] > 0) {
                        // 使用实际长度创建string，而不是依赖null终止符
                        string avatarData(row[3], lengths[3]);
                        user.setAvatar(avatarData);  // 好友头像数据
                        cout << "[DEBUG] Friend avatar data retrieved, length: " << avatarData.size() << endl;
                    }
                }
                
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