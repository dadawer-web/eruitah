#include "emojimodel.hpp"
#include "db.h"
#include <iostream>
#include <cstring>

using namespace std;

// 初始化表情包表（如果不存在则创建）
bool EmojiModel::initTable() {
    // SQL语句：创建emoji表
    const char* sql = "CREATE TABLE IF NOT EXISTS emoji ("
                     "id BIGINT PRIMARY KEY AUTO_INCREMENT,"
                     "user_id BIGINT NOT NULL,"
                     "name VARCHAR(100) NOT NULL,"
                     "image_data LONGBLOB NOT NULL,"
                     "create_time DATETIME DEFAULT CURRENT_TIMESTAMP,"
                     "FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE"
                     ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;";
    
    // 数据库连接建立
    MySQL mysql;
    if (mysql.connect()) {
        // 执行创建表操作
        if (mysql.update(sql)) {
            return true;
        }
    }
    
    return false;
}

// 插入表情包
bool EmojiModel::insert(Emoji &emoji) {
    // SQL语句构造 - 使用string避免栈溢出
    string sql = "INSERT INTO emoji(user_id, name, image_data) VALUES(";
    sql += to_string(emoji.getUserId()) + ", '" + emoji.getName() + "', '" + emoji.getImageData() + "')";
    
    // 数据库连接建立
    MySQL mysql;
    if (mysql.connect()) {
        // 执行插入操作
        if (mysql.update(sql)) {
            // 获取自增主键
            emoji.setId(mysql_insert_id(mysql.getConnection()));
            return true;
        }
    }
    
    return false;
}

// 根据用户ID查询表情包列表 - 返回所有表情包，让所有用户都能看到
vector<Emoji> EmojiModel::queryByUserId(long long userId) {
    vector<Emoji> emojis;
    
    // SQL语句构造 - 查询所有表情包，不再限制user_id
    char sql[1024] = {0};
    sprintf(sql, "SELECT id, user_id, name, image_data, create_time FROM emoji ORDER BY id DESC");
    
    // 数据库连接建立
    MySQL mysql;
    if (mysql.connect()) {
        // 执行查询操作
        MYSQL_RES *res = mysql.query(sql);
        if (res != nullptr) {
            // 结果集解析
            MYSQL_ROW row;
            while ((row = mysql_fetch_row(res)) != nullptr) {
                Emoji emoji;
                emoji.setId(stoll(row[0]));
                emoji.setUserId(stoll(row[1]));
                emoji.setName(row[2]);
                emoji.setImageData(row[3]);
                emoji.setCreateTime(row[4]);
                
                emojis.push_back(emoji);
            }
            
            // 资源释放
            mysql_free_result(res);
        }
    }
    
    return emojis;
}

// 根据表情ID查询表情包
Emoji EmojiModel::queryById(long long id) {
    // SQL语句构造
    char sql[1024] = {0};
    sprintf(sql, "SELECT id, user_id, name, image_data, create_time FROM emoji WHERE id = %lld", id);
    
    // 数据库连接建立
    MySQL mysql;
    if (mysql.connect()) {
        // 执行查询操作
        MYSQL_RES *res = mysql.query(sql);
        if (res != nullptr) {
            // 结果集解析
            MYSQL_ROW row = mysql_fetch_row(res);
            if (row != nullptr) {
                Emoji emoji;
                emoji.setId(stoll(row[0]));
                emoji.setUserId(stoll(row[1]));
                emoji.setName(row[2]);
                emoji.setImageData(row[3]);
                emoji.setCreateTime(row[4]);
                
                // 资源释放
                mysql_free_result(res);
                return emoji;
            }
        }
    }
    
    // 查询失败 - 返回默认表情包对象
    return Emoji();
}

// 根据用户ID和表情ID删除表情包
bool EmojiModel::removeById(long long userId, long long id) {
    // SQL语句构造
    char sql[1024] = {0};
    sprintf(sql, "DELETE FROM emoji WHERE id = %lld AND user_id = %lld", id, userId);
    
    // 数据库连接建立
    MySQL mysql;
    if (mysql.connect()) {
        // 执行删除操作
        if (mysql.update(sql)) {
            return true;
        }
    }
    
    return false;
}