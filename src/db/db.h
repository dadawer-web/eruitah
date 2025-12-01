// 头文件保护宏，防止头文件被重复包含
// 如果DB_H未定义，则定义它并包含下面的代码
#ifndef DB_H
#define DB_H

// 包含MySQL C API头文件，提供MySQL数据库操作的基本函数
#include <mysql/mysql.h>
// 包含C++标准字符串库
#include <string>

// 使用标准命名空间，这样可以直接使用string而不是std::string
using namespace std;

// 数据库配置信息
// static关键字表示这些变量只在当前文件中可见
static string server = "127.0.0.1";    // 数据库服务器地址：本地服务器(127.0.0.1是localhost的IP地址)
static string user = "root";           // 数据库用户名
static string password = "xieming562";  // 数据库密码
static string dbname = "chat";         // 数据库名称

// 数据库操作类
// 这个类封装了所有的数据库操作，方便其他代码调用
class MySQL {
public:
    // 构造函数：初始化数据库连接对象
    // 构造函数在创建MySQL对象时自动调用
    MySQL();
    
    // 析构函数：释放数据库连接资源
    // 析构函数在MySQL对象被销毁时自动调用
    ~MySQL();
    
    // 连接数据库
    // 返回值：bool类型，true表示连接成功，false表示连接失败
    bool connect();
    
    // 更新操作（插入、删除、修改）
    // 参数：sql - SQL语句字符串
    // 返回值：bool类型，true表示操作成功，false表示操作失败
    bool update(string sql);
    
    // 查询操作
    // 参数：sql - SQL语句字符串
    // 返回值：MYSQL_RES*类型，是指向查询结果集的指针
    MYSQL_RES* query(string sql);
    
    // 获取数据库连接对象
    // 返回值：MYSQL*类型，是指向MySQL连接的指针
    // 这个函数允许外部代码直接访问底层的MySQL连接
    MYSQL* getConnection();

private:
    // 私有成员变量，存储MySQL数据库连接
    // _conn是一个指向MYSQL结构体的指针
    MYSQL *_conn; // 数据库连接
};

// 头文件保护宏的结束部分
#endif // DB_H