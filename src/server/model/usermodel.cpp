#include"usermodel.hpp"
#include"db.h"
#include<iostream>
#include<cstring>

using namespace std;

// 用户注册 - 数据持久化
// 业务逻辑：将新用户信息写入数据库，生成唯一用户ID，完成用户创建流程
bool UserModel::insert(User &user)
{
    cout << "[DEBUG] Server UserModel::insert called for user: " << user.getName() << endl;
    cout << "[DEBUG] Avatar data length: " << user.getAvatar().size() << endl;
    
    // 创建数据库连接
    MySQL mysql;
    if (mysql.connect())
    {
        cout << "[DEBUG] MySQL connected successfully" << endl;
        
        // 获取数据库连接
        MYSQL *conn = mysql.getConnection();
        if (!conn) {
            cout << "[ERROR] Failed to get MySQL connection" << endl;
            return false;
        }
        
        cout << "[DEBUG] Got MySQL connection: " << conn << endl;
        
        // 使用预处理语句处理大二进制数据
        MYSQL_STMT *stmt = mysql_stmt_init(conn);
        if (!stmt) {
            cout << "[ERROR] Failed to initialize MySQL statement: " << mysql_error(conn) << endl;
            return false;
        }
        
        // 预处理SQL语句
        const char *sql = "INSERT INTO user(name, password, state, avatar) VALUES(?, ?, ?, ?)";
        if (mysql_stmt_prepare(stmt, sql, strlen(sql)) != 0) {
            cout << "[ERROR] Failed to prepare MySQL statement: " << mysql_stmt_error(stmt) << endl;
            mysql_stmt_close(stmt);
            return false;
        }
        
        cout << "[DEBUG] MySQL statement prepared successfully" << endl;
        
        // 绑定参数
        MYSQL_BIND bind[4];
        memset(bind, 0, sizeof(bind));
        
        // 绑定用户名
        bind[0].buffer_type = MYSQL_TYPE_STRING;
        bind[0].buffer = (void *)user.getName().c_str();
        bind[0].buffer_length = user.getName().size();
        
        // 绑定密码
        bind[1].buffer_type = MYSQL_TYPE_STRING;
        bind[1].buffer = (void *)user.getPwd().c_str();
        bind[1].buffer_length = user.getPwd().size();
        
        // 绑定状态
        bind[2].buffer_type = MYSQL_TYPE_STRING;
        bind[2].buffer = (void *)user.getState().c_str();
        bind[2].buffer_length = user.getState().size();
        
        // 绑定头像数据
        bind[3].buffer_type = MYSQL_TYPE_BLOB;
        bind[3].buffer = (void *)user.getAvatar().c_str();
        bind[3].buffer_length = user.getAvatar().size();
        
        if (mysql_stmt_bind_param(stmt, bind) != 0) {
            cout << "[ERROR] Failed to bind parameters: " << mysql_stmt_error(stmt) << endl;
            mysql_stmt_close(stmt);
            return false;
        }
        
        cout << "[DEBUG] Parameters bound successfully" << endl;
        
        // 执行预处理语句
        if (mysql_stmt_execute(stmt) != 0) {
            cout << "[ERROR] Failed to execute statement: " << mysql_stmt_error(stmt) << endl;
            mysql_stmt_close(stmt);
            return false;
        }
        
        cout << "[DEBUG] Statement executed successfully" << endl;
        
        // 获取自增主键
        user.setId(mysql_stmt_insert_id(stmt));
        
        // 关闭预处理语句
        mysql_stmt_close(stmt);
        
        return true;
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
                // 获取各字段的长度，特别是BLOB字段
                unsigned long *lengths = mysql_fetch_lengths(res);
                
                // 对象实例化 - 数据转换和模型映射
                User user;
                user.setId(stoll(row[0]));  // 字符串转长整型
                user.setName(row[1]);       // 用户名设置
                user.setPwd(row[2]);        // 密码信息（实际应进行加密处理）
                user.setState(row[3]);      // 用户状态获取
                
                // 正确处理BLOB类型的头像数据
                if (row[4] != nullptr && lengths[4] > 0) {
                    // 使用实际长度创建string，而不是依赖null终止符
                    string avatarData(row[4], lengths[4]);
                    user.setAvatar(avatarData);  // 用户头像数据
                    cout << "[DEBUG] Avatar data retrieved from database, length: " << avatarData.size() << endl;
                } else {
                    cout << "[DEBUG] No avatar data or empty avatar for user: " << id << endl;
                }
                
                // 资源释放 - 防止内存泄漏
                mysql_free_result(res);
                return user;
            }
        }
    }
    
    // 查询失败 - 返回默认用户对象
    return User();
}

// 更新用户头像 - 业务逻辑：更新用户头像信息，支持动态头像变更
// 参数：id - 用户ID，avatar - 头像路径
// 返回值：更新是否成功
bool UserModel::updateAvatar(long long id, const string& avatar)
{
    cout << "[DEBUG] Server UserModel::updateAvatar called for user id: " << id << endl;
    cout << "[DEBUG] Avatar data length: " << avatar.size() << endl;
    
    // 创建数据库连接
    MySQL mysql;
    if (mysql.connect())
    {
        cout << "[DEBUG] MySQL connected successfully" << endl;
        
        // 获取数据库连接
        MYSQL *conn = mysql.getConnection();
        if (conn == nullptr) {
            cout << "[ERROR] Failed to get MySQL connection" << endl;
            return false;
        }
        
        cout << "[DEBUG] Got MySQL connection: " << conn << endl;
        
        // 使用预处理语句处理大二进制数据，避免缓冲区溢出
        MYSQL_STMT *stmt = mysql_stmt_init(conn);
        if (stmt == nullptr) {
            cout << "[ERROR] Failed to initialize MySQL statement: " << mysql_error(conn) << endl;
            return false;
        }
        
        // 预处理SQL语句
        const char *sql = "UPDATE user SET avatar = ? WHERE id = ?";
        if (mysql_stmt_prepare(stmt, sql, strlen(sql)) != 0) {
            cout << "[ERROR] Failed to prepare MySQL statement: " << mysql_stmt_error(stmt) << endl;
            mysql_stmt_close(stmt);
            return false;
        }
        
        cout << "[DEBUG] MySQL statement prepared successfully" << endl;
        
        // 绑定参数
        MYSQL_BIND bind[2];
        memset(bind, 0, sizeof(bind));
        
        // 绑定头像数据
        bind[0].buffer_type = MYSQL_TYPE_BLOB;
        bind[0].buffer = (void *)avatar.data();
        bind[0].buffer_length = avatar.size();
        bind[0].is_null = 0;
        // 对于BLOB类型，必须正确设置length字段
        unsigned long avatarLength = avatar.size();
        bind[0].length = &avatarLength;
        
        // 绑定用户ID
        bind[1].buffer_type = MYSQL_TYPE_LONGLONG;
        bind[1].buffer = (void *)&id;
        bind[1].buffer_length = sizeof(id);
        bind[1].is_null = 0;
        // 对于数值类型，可以设置length为nullptr
        bind[1].length = nullptr;
        
        if (mysql_stmt_bind_param(stmt, bind) != 0) {
            cout << "[ERROR] Failed to bind MySQL statement parameters: " << mysql_stmt_error(stmt) << endl;
            mysql_stmt_close(stmt);
            return false;
        }
        
        cout << "[DEBUG] MySQL statement parameters bound successfully" << endl;
        
        // 执行预处理语句
        if (mysql_stmt_execute(stmt) != 0) {
            cout << "[ERROR] Failed to execute MySQL statement: " << mysql_stmt_error(stmt) << endl;
            mysql_stmt_close(stmt);
            return false;
        }
        
        cout << "[DEBUG] MySQL statement executed successfully" << endl;
        
        // 获取影响的行数
        my_ulonglong affectedRows = mysql_stmt_affected_rows(stmt);
        cout << "[DEBUG] Affected rows: " << affectedRows << endl;
        
        // 关闭预处理语句
        mysql_stmt_close(stmt);
        
        // 如果影响行数为0，可能是因为新数据与旧数据相同，这是正常情况
        // 只有当mysql_stmt_execute返回错误时才返回false
        return true;
    }
    cout << "[DEBUG] MySQL connection failed" << endl;
    return false;
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