#include "usermodel.h"
#include "../db/db.h"
#include <iostream>
using namespace std;

// User表的增加方法
bool UserModel::insert(User &user) {
    // 组装sql语句
    char sql[1024] = {0};
    sprintf(sql, "insert into user(name, password, state) values('%s', '%s', '%s')",
            user.getName().c_str(), user.getPwd().c_str(), user.getState().c_str());

    // 创建数据库连接
    MySQL mysql;
    if (mysql.connect()) {
        // 执行sql语句
        if (mysql.update(sql)) {
            // 获取插入成功的用户数据生成的主键id
            user.setId(mysql_insert_id(mysql.getConnection()));
            return true;
        }
    }
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