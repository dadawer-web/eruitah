#ifndef EMOJI_H
#define EMOJI_H

#include <string>

using namespace std;

// 表情包类，用于存储表情包信息
class Emoji {
private:
    long long _id;          // 表情ID
    long long _userId;      // 所属用户ID
    string _name;           // 表情名称
    string _imageData;      // 表情图片数据（Base64编码）
    string _createTime;     // 创建时间

public:
    Emoji() : _id(0), _userId(0) {}
    Emoji(long long userId, string name, string imageData) 
        : _id(0), _userId(userId), _name(name), _imageData(imageData) {}
    
    // 设置和获取表情ID
    void setId(long long id) { _id = id; }
    long long getId() const { return _id; }
    
    // 设置和获取所属用户ID
    void setUserId(long long userId) { _userId = userId; }
    long long getUserId() const { return _userId; }
    
    // 设置和获取表情名称
    void setName(string name) { _name = name; }
    string getName() const { return _name; }
    
    // 设置和获取表情图片数据
    void setImageData(string imageData) { _imageData = imageData; }
    string getImageData() const { return _imageData; }
    
    // 设置和获取创建时间
    void setCreateTime(string createTime) { _createTime = createTime; }
    string getCreateTime() const { return _createTime; }
};

#endif