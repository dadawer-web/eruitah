#include"groupmodel.hpp"
#include"db.h"

// 创建群组 - 群组管理核心功能
// 业务逻辑：创建新的聊天群组，生成唯一群组ID，初始化群组基本信息
bool GroupModel::createGroup(Group &group){
    // SQL语句构造 - 群组数据初始化
    char sql[1024]={0};
    sprintf(sql,"insert into allgroup(groupname,groupdesc) values('%s','%s')",group.getName().c_str(),group.getDesc().c_str());
    
    // 数据库操作执行
    MySQL mysql;
    if(mysql.connect()){
        // 执行插入操作 - 群组创建
        if(mysql.update(sql)){
            // 获取自增主键 - 群组ID分配
            // 关键业务：将生成的群组ID回填到群组对象，完成创建流程
            group.setId(mysql_insert_id(mysql.getConnection()));
            return true;
        }
    }
    
    // 创建失败 - 可能是群名重复或数据库错误
    return false;
}

// 加入群组 - 成员管理功能
// 业务逻辑：将用户添加到指定群组，设置用户在群组中的角色权限
void GroupModel::addGroup(int userid,int groupid,string role){
    // SQL语句构造 - 成员关系建立
    char sql[1024]={0};
    sprintf(sql,"insert into groupuser values(%d,%d,'%s')",groupid,userid,role.c_str());
    
    // 数据库操作执行
    MySQL mysql;
    if(mysql.connect()){
        // 执行插入操作 - 成员关系持久化
        mysql.update(sql);
    }
}

// 查询用户群组列表 - 群组信息聚合
// 业务逻辑：获取用户加入的所有群组信息，包括群组基本信息和群内所有成员详情
vector<Group> GroupModel::queryGroups(int userid){
    // 第一步：查询用户所属的所有群组基本信息
    char sql[1024]={0};
    sprintf(sql,"select a.id,a.groupname,a.groupdesc from allgroup a inner join groupuser b on a.id=b.groupid where b.userid=%d",userid);
    
    vector<Group> groupVec;
    MySQL mysql;
    
    if(mysql.connect()){
        // 执行查询 - 群组列表获取
        MYSQL_RES *res=mysql.query(sql);
        if(res!=nullptr){
            MYSQL_ROW row;
            
            // 批量处理 - 群组基本信息映射
            while((row=mysql_fetch_row(res))!=nullptr){
                Group group;
                group.setId(atoi(row[0]));
                group.setName(row[1]);
                group.setDesc(row[2]);
                groupVec.push_back(group);
            }
            mysql_free_result(res);
        }
    }
    
    // 第二步：为每个群组查询其成员详细信息
    for(Group &group : groupVec){
        // SQL语句构造 - 群组成员查询
        sprintf(sql,"select a.id,a.name,a.state,b.grouprole from user a inner join groupuser b on b.userid=a.id where b.groupid=%d",group.getId());
        
        MYSQL_RES *res=mysql.query(sql);
        if(res!=nullptr){
            MYSQL_ROW row;
            
            // 批量处理 - 群组成员信息映射
            while((row=mysql_fetch_row(res))!=nullptr){
                GroupUser user;
                user.setId(atoi(row[0]));       // 用户ID
                user.setName(row[1]);           // 用户名
                user.setState(row[2]);          // 在线状态
                user.setRole(row[3]);           // 群组角色（如群主、管理员、普通成员）
                group.getUsers().push_back(user);
            }
            mysql_free_result(res);
        }
    }
    
    // 返回完整的群组信息列表
    return groupVec;
}

// 查询群组成员ID列表 - 群消息分发支持
// 业务逻辑：获取除发送者外的所有群组成员ID，用于群消息广播和离线存储
vector<int> GroupModel::queryGroupUsers(int userid, int groupid){
    // SQL语句构造 - 排除发送者的成员查询
    char sql[1024]={0};
    sprintf(sql,"select userid from groupuser where groupid=%d and userid!=%d",groupid,userid);
    
    vector<int> idVec;
    MySQL mysql;
    
    if(mysql.connect()){
        // 执行查询 - 成员ID获取
        MYSQL_RES *res=mysql.query(sql);
        if(res!=nullptr){
            MYSQL_ROW row;
            
            // 批量处理 - 成员ID列表构建
            while((row=mysql_fetch_row(res))!=nullptr){
                idVec.push_back(atoi(row[0]));
            }
            mysql_free_result(res);
        }
    }
    
    // 返回群组成员ID列表，用于消息分发
    return idVec;
}