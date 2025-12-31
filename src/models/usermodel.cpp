#include "usermodel.h"
#include "../db/db.h"
#include <iostream>
#include <fstream>
#include <vector>
#include <openssl/bio.h>
#include <openssl/buffer.h>
#include <openssl/evp.h>
using namespace std;

// Base64编码辅助函数
string base64Encode(const string &data) {
    BIO *bio, *b64;
    BUF_MEM *bufferPtr;

    b64 = BIO_new(BIO_f_base64());
    bio = BIO_new(BIO_s_mem());
    bio = BIO_push(b64, bio);

    BIO_set_flags(bio, BIO_FLAGS_BASE64_NO_NL);
    BIO_write(bio, data.c_str(), data.size());
    BIO_flush(bio);
    BIO_get_mem_ptr(bio, &bufferPtr);

    // 先复制数据，因为bufferPtr会被BIO_free_all释放
    string encoded(bufferPtr->data, bufferPtr->length);

    BIO_free_all(bio);
    // 不需要手动释放bufferPtr，它已经被BIO_free_all释放了

    return encoded;
}

// 读取文件内容并转换为Base64编码
string fileToBase64(const string &filePath) {
    if (filePath.empty()) {
        return "";
    }

    ifstream file(filePath, ios::in | ios::binary);
    if (!file.is_open()) {
        cout << "[DEBUG] Failed to open avatar file: " << filePath << endl;
        return "";
    }

    file.seekg(0, ios::end);
    size_t fileSize = file.tellg();
    file.seekg(0, ios::beg);

    vector<char> buffer(fileSize);
    file.read(buffer.data(), fileSize);
    file.close();

    return base64Encode(string(buffer.begin(), buffer.end()));
}

// User表的增加方法
bool UserModel::insert(User &user) {
    cout << "[DEBUG] UserModel::insert called for user: " << user.getName() << endl;
    cout << "[DEBUG] Avatar data length: " << user.getAvatar().size() << endl;
    
    // 创建数据库连接
    MySQL mysql;
    if (mysql.connect()) {
        cout << "[DEBUG] MySQL connected successfully" << endl;
        
        // 获取数据库连接
        MYSQL *conn = mysql.getConnection();
        if (conn == nullptr) {
            cout << "[ERROR] Failed to get MySQL connection" << endl;
            return false;
        }
        
        cout << "[DEBUG] Got MySQL connection: " << conn << endl;
        
        // 使用预处理语句处理大二进制数据
        MYSQL_STMT *stmt = mysql_stmt_init(conn);
        if (stmt == nullptr) {
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
        bind[0].is_null = 0;
        bind[0].length = nullptr;
        
        // 绑定密码
        bind[1].buffer_type = MYSQL_TYPE_STRING;
        bind[1].buffer = (void *)user.getPwd().c_str();
        bind[1].buffer_length = user.getPwd().size();
        bind[1].is_null = 0;
        bind[1].length = nullptr;
        
        // 绑定状态
        bind[2].buffer_type = MYSQL_TYPE_STRING;
        bind[2].buffer = (void *)user.getState().c_str();
        bind[2].buffer_length = user.getState().size();
        bind[2].is_null = 0;
        bind[2].length = nullptr;
        
        // 绑定头像数据
        bind[3].buffer_type = MYSQL_TYPE_BLOB;
        bind[3].buffer = (void *)user.getAvatar().data();
        bind[3].buffer_length = user.getAvatar().size();
        bind[3].is_null = 0;
        bind[3].length = nullptr;
        
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
        
        // 获取插入的主键id
        user.setId(mysql_stmt_insert_id(stmt));
        
        // 关闭预处理语句
        mysql_stmt_close(stmt);
        
        return true;
    }
    cout << "[DEBUG] MySQL connection failed" << endl;
    return false;
}

// 根据用户号码查询用户信息，支持大整数ID
User UserModel::query(long long id) {
    cout << "[DEBUG] UserModel::query called for user id: " << id << endl;
    // 组装sql语句
    char sql[1024] = {0};
    sprintf(sql, "select * from user where id=%lld", id);
    cout << "[DEBUG] Executing SQL: " << sql << endl;

    // 创建数据库连接
    MySQL mysql;
    if (mysql.connect()) {
        cout << "[DEBUG] MySQL connected successfully" << endl;
        MYSQL_RES *res = mysql.query(sql);
        if (res != nullptr) {
            cout << "[DEBUG] Query executed, got result set" << endl;
            MYSQL_ROW row = mysql_fetch_row(res);
            if (row != nullptr) {
                cout << "[DEBUG] Found user in database, id: " << row[0] 
                     << ", name: " << row[1] << endl;
                User user;
                user.setId(stoll(row[0]));
                user.setName(row[1]);
                user.setPwd(row[2]);
                user.setState(row[3]);
                
                // 获取BLOB字段的长度和内容
                unsigned long *lengths = mysql_fetch_lengths(res);
                if (row[4] != nullptr && lengths[4] > 0) {
                    // 直接获取二进制头像数据
                    string avatarData(row[4], lengths[4]);
                    cout << "[DEBUG] Avatar data length from database: " << avatarData.size() << endl;
                    user.setAvatar(avatarData);
                }
                mysql_free_result(res);
                cout << "[DEBUG] Returning user object with id: " << user.getId() << endl;
                return user;
            }
            cout << "[DEBUG] No user found with id: " << id << endl;
            mysql_free_result(res);
        } else {
            cout << "[DEBUG] Query failed or returned null result" << endl;
        }
    } else {
        cout << "[DEBUG] Failed to connect to MySQL" << endl;
    }
    cout << "[DEBUG] Returning default User object" << endl;
    return User(); // 返回默认用户对象
}

// 更新用户的头像信息
bool UserModel::updateAvatar(long long id, const string& avatar) {
    cout << "[DEBUG] UserModel::updateAvatar called for user id: " << id << endl;
    cout << "[DEBUG] Avatar data length: " << avatar.size() << endl;
    
    // 创建数据库连接
    MySQL mysql;
    if (mysql.connect()) {
        cout << "[DEBUG] MySQL connected successfully" << endl;
        
        // 获取数据库连接
        MYSQL *conn = mysql.getConnection();
        if (conn == nullptr) {
            cout << "[ERROR] Failed to get MySQL connection" << endl;
            return false;
        }
        
        cout << "[DEBUG] Got MySQL connection: " << conn << endl;
        
        // 使用预处理语句处理大二进制数据，避免转义问题
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

// 更新用户的状态信息
bool UserModel::updateState(User user) {
    // 组装sql语句
    char sql[1024] = {0};
    sprintf(sql, "update user set state='%s' where id=%lld", 
            user.getState().c_str(), user.getId());

    // 创建数据库连接
    MySQL mysql;
    if (mysql.connect()) {
        // 执行sql语句
        if (mysql.update(sql)) {
            return true;
        }
    }
    return false;
}

// 重置用户的状态信息
void UserModel::resetState() {
    // 组装sql语句
    char sql[1024] = "update user set state='offline' where state='online'";

    // 创建数据库连接
    MySQL mysql;
    if (mysql.connect()) {
        mysql.update(sql);
    }
}