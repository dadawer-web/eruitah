#include"offlinemessagemodel.hpp"
#include"db.h"

// 存储离线消息 - 消息可靠性保障
// 业务逻辑：当用户离线时，将发送给该用户的消息持久化存储，确保消息不丢失
void OfflineMsgModel::insert(int userid, string msg)
{
    // SQL语句构造 - 消息数据持久化
    char sql[1024]={0};
    sprintf(sql,"insert into offlinemessage values(%d,'%s')",userid,msg.c_str());
    
    // 数据库操作执行
    MySQL mysql;
    if(mysql.connect()){
        // 执行插入操作 - 离线消息存储
        mysql.update(sql);
    }
}

// 清除离线消息 - 资源管理和状态同步
// 业务逻辑：当用户上线并成功接收离线消息后，删除已投递的离线消息，避免重复投递
void OfflineMsgModel::remove(int userid){
    // SQL语句构造 - 批量消息删除
    char sql[1024]={0};
    sprintf(sql,"delete from offlinemessage where userid=%d",userid);
    
    // 数据库操作执行
    MySQL mysql;
    if(mysql.connect()){
        // 执行删除操作 - 离线消息清理
        mysql.update(sql);
    }
}

// 查询离线消息 - 消息投递
// 业务逻辑：用户上线时，获取并返回所有待接收的离线消息，支持消息历史恢复
vector<string> OfflineMsgModel::query(int userid){
    // SQL语句构造 - 批量消息查询
    char sql[1024]={0};
    sprintf(sql,"select message from offlinemessage where userid=%d",userid);
    
    // 结果集容器初始化
    vector<string> vec;
    
    // 数据库操作执行
    MySQL mysql;
    if(mysql.connect()){
        // 执行查询 - 离线消息检索
        MYSQL_RES* res=mysql.query(sql);
        if(res!=nullptr){
            MYSQL_ROW row;
            
            // 批量数据处理 - 消息列表构建
            while((row=mysql_fetch_row(res))!=nullptr){
                vec.push_back(row[0]);  // 消息内容添加到结果集
            }
            
            // 资源管理 - 防止内存泄漏
            mysql_free_result(res);
            return vec;
        }
    }
    
    // 查询失败 - 返回空结果集
    return vec;
}