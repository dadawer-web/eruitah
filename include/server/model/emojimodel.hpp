#ifndef EMOJIMODEL_H
#define EMOJIMODEL_H

#include <vector>
#include "emoji.hpp"

// 表情包数据操作类，用于处理表情包的数据库操作
class EmojiModel {
public:
    // 插入表情包
    bool insert(Emoji &emoji);
    
    // 根据用户ID查询表情包列表
    vector<Emoji> queryByUserId(long long userId);
    
    // 根据表情ID查询表情包
    Emoji queryById(long long id);
    
    // 根据用户ID和表情ID删除表情包
    bool removeById(long long userId, long long id);
    
    // 初始化表情包表（如果不存在则创建）
    bool initTable();
};

#endif