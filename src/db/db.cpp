// 包含自己的头文件
#include "db.h"
// 包含标准输入输出流库
#include <iostream>
// 使用标准命名空间
using namespace std;

// 构造函数：初始化数据库连接
// mysql_init函数初始化一个MYSQL对象，参数为nullptr表示创建新的对象
MySQL::MySQL() {
    _conn = mysql_init(nullptr);
}

// 析构函数：释放数据库连接资源
// 在对象销毁前，如果连接存在，则关闭连接
MySQL::~MySQL() {
    // 条件判断：只有当_conn不为空时才执行关闭操作
    if (_conn != nullptr) {
        // mysql_close函数关闭数据库连接并释放相关资源
        mysql_close(_conn);
    }
}

// 连接数据库
// 返回值：成功返回true，失败返回false
bool MySQL::connect() {
    // mysql_real_connect函数建立与MySQL服务器的连接
    // 参数说明：
    // _conn: 之前初始化的MYSQL对象
    // server.c_str(): 服务器地址(需要将string转为C风格字符串)
    // user.c_str(): 用户名
    // password.c_str(): 密码
    // dbname.c_str(): 数据库名
    // 3306: MySQL默认端口号
    // nullptr: UNIX套接字(Windows下不使用)
    // 0: 连接标志(使用默认值)
    MYSQL *p = mysql_real_connect(_conn, server.c_str(), user.c_str(), 
                                 password.c_str(), dbname.c_str(), 3306, nullptr, 0);
    
    if (p != nullptr) {
        // 设置字符集，解决中文乱码问题
        // "set names gbk"是SQL语句，设置客户端与服务器之间的通信字符集为GBK
        mysql_query(_conn, "set names gbk");
        cout << "数据库连接成功" << endl;
    } else {
        // 如果连接失败，输出错误信息
        // mysql_error函数返回最近一次MySQL操作的错误信息
        cout << "数据库连接失败: " << mysql_error(_conn) << endl;
    }
    
    // 返回连接是否成功的结果
    return p != nullptr;
}

// 更新操作(插入、删除、修改)
// 参数：sql - 要执行的SQL语句
// 返回值：成功返回true，失败返回false
bool MySQL::update(string sql) {
    // mysql_query函数执行SQL语句
    // 如果执行失败，返回非零值
    if (mysql_query(_conn, sql.c_str())) {
        cout << "更新失败: " << sql << endl;
        cout << "错误信息: " << mysql_error(_conn) << endl;
        return false;
    }
    return true;
}

// 查询操作
// 参数：sql - 要执行的查询SQL语句
// 返回值：成功返回结果集指针，失败返回nullptr
MYSQL_RES* MySQL::query(string sql) {
    // 执行SQL查询
    if (mysql_query(_conn, sql.c_str())) {
        cout << "查询失败: " << sql << endl;
        cout << "错误信息: " << mysql_error(_conn) << endl;
        return nullptr;
    }
    
    // mysql_use_result函数获取查询结果
    // 注意：使用完结果集后需要调用mysql_free_result释放资源
    return mysql_use_result(_conn);
}

// 获取数据库连接对象
// 返回值：MYSQL连接指针
MYSQL* MySQL::getConnection() {
    // 直接返回内部存储的连接指针
    return _conn;
}