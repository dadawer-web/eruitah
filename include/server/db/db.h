#ifndef DB_H
#define DB_H

#include<mysql/mysql.h>
#include<cstdlib>

#include<string>
using namespace std;
static string server = getenv("MYSQL_HOST") ? getenv("MYSQL_HOST") : "127.0.0.1";
static string user = getenv("MYSQL_USER") ? getenv("MYSQL_USER") : "root";
static string password = getenv("MYSQL_PASSWORD") ? getenv("MYSQL_PASSWORD") : "xieming562";
static string dbname = getenv("MYSQL_DBNAME") ? getenv("MYSQL_DBNAME") : "chat";
// 数据库操作类
class MySQL
{
  public:
 // 初始化数据库连接
    MySQL();
    ~MySQL();
 // 连接数据库
    bool connect();
 // 更新操作
    bool update(string sql);
 // 查询操作
      MYSQL_RES* query(string sql);
   // 获取连接
    MYSQL* getConnection();
private:
 MYSQL *_conn;
};

#endif
