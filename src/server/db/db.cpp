   #include"db.h"
   #include<muduo/base/Logging.h>
   
   // 构造函数 - 数据库连接初始化
   // 业务逻辑：创建MySQL连接对象，为后续数据库操作做准备
   MySQL::MySQL()
   {
      // 初始化MySQL连接句柄 - 资源分配
      _conn = mysql_init(nullptr);
   }
   
   // 析构函数 - 资源清理
   // 业务逻辑：确保数据库连接资源正确释放，避免内存泄漏
   MySQL::~MySQL()
   {
      // 安全释放连接资源 - 异常安全保障
      if (_conn != nullptr)
         mysql_close(_conn);
   }
   
   // 连接数据库
   // 业务逻辑：建立与MySQL服务器的连接，配置编码以支持中文
   bool MySQL::connect()
   {
      // 实际建立数据库连接 - 网络通信和认证
      MYSQL *p = mysql_real_connect(_conn, server.c_str(), user.c_str(),
      password.c_str(), dbname.c_str(), 3306, nullptr, 0);
      
      if (p != nullptr)
      {
         // 设置字符编码为GBK - 国际化支持
         // 数据一致性：确保中文字符在存储和检索过程中不会出现乱码
         mysql_query(_conn, "set names gbk"); 
         LOG_INFO<<"connect mysql success!";
      }
      else
      { 
         LOG_INFO << "connect mysql failed!";
      }
      
      // 返回连接状态 - 提供连接结果反馈
      return p;
   }
   
   // 更新操作
   // 业务逻辑：执行数据库写操作（INSERT、UPDATE、DELETE），处理事务提交
   bool MySQL::update(string sql)
   {
      // 执行SQL语句 - 数据修改操作
      if (mysql_query(_conn, sql.c_str()))
      {
         // 错误日志记录 - 便于问题排查和数据一致性监控
         LOG_INFO << __FILE__ << ":" << __LINE__ << ":"
         << sql << "更新失败!";
         return false;
      }
      
      // 操作成功 - 数据持久化完成
      return true;
   }
   
   // 查询操作
   // 业务逻辑：执行数据库读操作（SELECT），返回查询结果集
   MYSQL_RES* MySQL::query(string sql)
   {
      // 执行SQL查询 - 数据检索操作
      if (mysql_query(_conn, sql.c_str()))
      {
         // 错误日志记录 - 便于问题排查和性能监控
         LOG_INFO << __FILE__ << ":" << __LINE__ << ":"
         << sql << "查询失败!";
         return nullptr;
      }
      
      // 返回结果集 - 延迟加载机制，提高查询效率
      return mysql_use_result(_conn);
   }
   
   // 获取连接    
   // 业务逻辑：提供原始连接句柄，支持复杂的自定义SQL操作
   MYSQL* MySQL::getConnection()
   {
      // 直接返回连接指针 - 扩展性支持
      return _conn;
   }