// 包含Qt应用程序的核心头文件
#include <QApplication>
#include <QCoreApplication>
// 包含文本编码相关的头文件
#include <QTextCodec>
// 包含定时器相关的头文件
#include <QTimer>
// 包含登录窗口的头文件
#include "loginwindow.h"
// 包含聊天窗口的头文件
#include "chatwindow.h"
// 包含数据库操作的头文件
#include "db/db.h"

// 跨平台网络头文件处理
#ifdef _WIN32
    #include <winsock2.h>
    #include <ws2tcpip.h>
#endif

// 程序入口函数
// argc: 命令行参数数量
// argv: 命令行参数数组
int main(int argc, char *argv[]) {
    // 初始化Winsock（Windows平台）
    #ifdef _WIN32
    WSADATA wsaData;
    if (WSAStartup(MAKEWORD(2, 2), &wsaData) != 0) {
        qDebug() << "Winsock初始化失败";
        return -1;
    }
    #endif
    
    // 创建Qt应用程序实例
    // QApplication是Qt GUI应用程序的核心类，管理应用程序的资源、设置和事件循环
    QApplication a(argc, argv);
    
    // 设置中文显示
    // QTextCodec用于处理不同字符编码
    // setCodecForLocale设置程序的默认文本编码为UTF-8，确保中文等非ASCII字符能正确显示
    QTextCodec::setCodecForLocale(QTextCodec::codecForName("UTF-8"));
    
    // 初始化数据库连接
    // 创建MySQL对象并尝试连接数据库
    MySQL mysql;
    if (mysql.connect()) {
        qDebug() << "数据库连接成功";
        
        // 创建必要的数据表
        // 使用CREATE TABLE IF NOT EXISTS确保表只在不存在时创建
        
        // 用户表：存储用户基本信息
        QString createUserTable = "CREATE TABLE IF NOT EXISTS user (" 
                                 "id INT PRIMARY KEY AUTO_INCREMENT, "  // 主键，自增
                                 "name VARCHAR(50) UNIQUE NOT NULL, "  // 用户名，唯一
                                 "password VARCHAR(50) NOT NULL, "     // 密码
                                 "state VARCHAR(20) DEFAULT 'offline')";// 在线状态，默认离线
        
        // 好友表：存储好友关系
        QString createFriendTable = "CREATE TABLE IF NOT EXISTS friend (" 
                                   "userid INT NOT NULL, "            // 用户ID
                                   "friendid INT NOT NULL, "          // 好友ID
                                   "PRIMARY KEY (userid, friendid), "  // 复合主键，确保好友关系唯一性
                                   "FOREIGN KEY (userid) REFERENCES user(id), "  // 外键引用user表
                                   "FOREIGN KEY (friendid) REFERENCES user(id))";// 外键引用user表
        
        // 群组表：存储群组基本信息
        QString createAllGroupTable = "CREATE TABLE IF NOT EXISTS allgroup (" 
                                      "id INT PRIMARY KEY AUTO_INCREMENT, "  // 主键，自增
                                      "groupname VARCHAR(50) NOT NULL, "     // 群组名称
                                      "groupdesc VARCHAR(200) NOT NULL)" ;   // 群组描述
        
        // 群成员表：存储群组成员关系
        QString createGroupUserTable = "CREATE TABLE IF NOT EXISTS groupuser (" 
                                       "groupid INT NOT NULL, "             // 群组ID
                                       "userid INT NOT NULL, "              // 用户ID
                                       "grouprole VARCHAR(20) NOT NULL, "    // 用户在群组中的角色
                                       "PRIMARY KEY (groupid, userid), "     // 复合主键，确保成员关系唯一性
                                       "FOREIGN KEY (groupid) REFERENCES allgroup(id), "  // 外键引用allgroup表
                                       "FOREIGN KEY (userid) REFERENCES user(id))" ;      // 外键引用user表
        
        // 离线消息表：存储用户离线时的消息
        QString createOfflineMsgTable = "CREATE TABLE IF NOT EXISTS offlineMessage (" 
                                        "id INT PRIMARY KEY AUTO_INCREMENT, "  // 主键，自增
                                        "userid INT NOT NULL, "               // 接收者ID
                                        "message TEXT NOT NULL, "             // 消息内容
                                        "FOREIGN KEY (userid) REFERENCES user(id))" ;   // 外键引用user表
        
        // 执行SQL语句创建表
        mysql.update(createUserTable.toStdString());
        mysql.update(createFriendTable.toStdString());
        mysql.update(createAllGroupTable.toStdString());
        mysql.update(createGroupUserTable.toStdString());
        mysql.update(createOfflineMsgTable.toStdString());
    } else {
        qDebug() << "数据库连接失败";
    }
    
    // 创建并显示登录窗口
    LoginWindow loginWindow;
    // 聊天窗口指针，初始为nullptr（空指针）
    ChatWindow *chatWindow = nullptr;
    
    // 连接登录成功信号到处理函数
    // Qt的信号槽机制：当loginWindow发出loginSuccess信号时，执行后面的lambda函数
    // connectResult保存信号槽连接是否成功
    bool connectResult = QObject::connect(&loginWindow, &LoginWindow::loginSuccess, 
    // 这是一个lambda表达式，作为信号的槽函数
    // [&loginWindow, &chatWindow]是捕获列表，捕获外部变量的引用
    // (int userId, const QString &userName)是参数列表，接收信号发送的数据
    [&loginWindow, &chatWindow](int userId, const QString &userName) {
        qDebug() << "[CRITICAL] ==== 登录成功信号开始处理 ====";
        
        // 首先记录登录成功事件到日志文件
            // 跨平台路径处理，使用应用程序所在目录
            QString logFilePath = QCoreApplication::applicationDirPath() + "/login_debug.log";
            QFile logFile(logFilePath);
            // 打开文件用于追加文本
            if (logFile.open(QIODevice::Append | QIODevice::Text)) {
            QTextStream out(&logFile);
            // 写入带时间戳的日志信息
            out << "[" << QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss.zzz") << "] " 
                << "main.cpp: 登录成功信号触发，准备处理跳转，userId:" << userId << " userName:" << userName << Qt::endl;
            logFile.close();
        }
        qDebug() << "[CRITICAL] main.cpp: 登录成功信号触发，准备处理跳转，userId:" << userId << " userName:" << userName;
        
        // 重要：防止重复创建ChatWindow实例
        if (chatWindow != nullptr) {
            qDebug() << "[CRITICAL] ChatWindow already exists, showing existing window";
            // 显示已有的聊天窗口
            chatWindow->showNormal(); // 使用showNormal确保窗口正常显示
            chatWindow->raise();      // 将窗口提升到最上层
            chatWindow->activateWindow(); // 激活窗口
            return; // 结束函数执行
        }
        
        // 关闭登录窗口，而不是隐藏，确保事件循环能继续运行
        loginWindow.close();
        qDebug() << "[CRITICAL] main.cpp: 登录窗口已关闭";
        
        // 直接获取ChatClient实例
        ChatClient *client = loginWindow.getChatClient();
        qDebug() << "[CRITICAL] main.cpp: 获取ChatClient实例:" << client;
        
        // 如果ChatClient为空，创建一个新实例
        if (!client) {
            qDebug() << "[CRITICAL] main.cpp: 从LoginWindow获取的ChatClient为空，创建新实例";
            client = new ChatClient();
            // 确保新创建的client连接到服务器
            client->connectToServer("127.0.0.1", 6000); // 连接到本地服务器，端口6000
        }
        
        // 直接创建ChatWindow，不使用QTimer延迟
        try {
            qDebug() << "[CRITICAL] 准备创建ChatWindow实例";
            // 创建聊天窗口实例，传入用户ID、用户名和客户端连接
            chatWindow = new ChatWindow(userId, userName, client);
            qDebug() << "[CRITICAL] main.cpp: ChatWindow实例创建成功，地址:" << chatWindow;
            
            // 当ChatWindow发出logout信号时，关闭聊天窗口并重新显示登录窗口
            QObject::connect(chatWindow, &ChatWindow::logout, [&loginWindow, &chatWindow]() {
                if (chatWindow) {
                    chatWindow->close();
                    delete chatWindow;
                    chatWindow = nullptr;
                    // 重新创建ChatClient实例，确保LoginWindow有一个有效的ChatClient指针
                    loginWindow.resetChatClient();
                    loginWindow.show();
                }
            });
            
            // 设置窗口属性，确保能够正确显示
            // Qt::WA_ShowWithoutActivating: 显示窗口时不激活它
            chatWindow->setAttribute(Qt::WA_ShowWithoutActivating, false);
            // 确保窗口不是最小化状态
            chatWindow->setWindowState(chatWindow->windowState() & ~Qt::WindowMinimized);
            // 临时设置窗口置顶，确保可见
            chatWindow->setWindowFlags(chatWindow->windowFlags() | Qt::WindowStaysOnTopHint);
            
            // 立即显示ChatWindow
            chatWindow->show(); // 显示窗口
            qDebug() << "[CRITICAL] 执行show()";
            chatWindow->raise(); // 将窗口提升到最上层
            qDebug() << "[CRITICAL] 执行raise()";
            chatWindow->activateWindow(); // 激活窗口
            qDebug() << "[CRITICAL] 执行activateWindow()";
            
            // 设置窗口位置和大小，确保可见
            chatWindow->resize(800, 600);
            chatWindow->move(100, 100);
            qDebug() << "[CRITICAL] 执行resize(800, 600)和move(100, 100)";
            
            // 强制应用窗口更新
            chatWindow->repaint(); // 立即重绘窗口
            qDebug() << "[CRITICAL] 执行repaint()";
            
            // 添加事件循环处理，确保窗口事件被处理
            QCoreApplication::processEvents(); // 处理所有待处理的事件
            qDebug() << "[CRITICAL] 执行processEvents()";
            
            // 验证是否显示成功
            if (chatWindow->isVisible()) {
                qDebug() << "[CRITICAL] main.cpp: ChatWindow显示成功 - SUCCESS";
                qDebug() << "[CRITICAL] ChatWindow大小: " << chatWindow->size();
                qDebug() << "[CRITICAL] ChatWindow位置: " << chatWindow->pos();
                qDebug() << "[CRITICAL] ChatWindow可见性: " << chatWindow->isVisible();
                qDebug() << "[CRITICAL] ChatWindow窗口状态: " << chatWindow->windowState();
                // 移除置顶属性，恢复正常窗口行为
                chatWindow->setWindowFlags(chatWindow->windowFlags() & ~Qt::WindowStaysOnTopHint);
                chatWindow->show(); // 重新显示，因为修改windowFlags后需要重新show
                
                // 记录日志
                if (logFile.open(QIODevice::Append | QIODevice::Text)) {
                    QTextStream out(&logFile);
                    QSize size = chatWindow->size();
                    QPoint pos = chatWindow->pos();
                    out << "[" << QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss.zzz") << "] " 
                        << "main.cpp: ChatWindow显示成功，跳转完成" << Qt::endl;
                    out << "[" << QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss.zzz") << "] " 
                        << "main.cpp: ChatWindow大小: " << QString("(%1, %2)").arg(size.width()).arg(size.height()) << Qt::endl;
                    out << "[" << QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss.zzz") << "] " 
                        << "main.cpp: ChatWindow位置: " << QString("(%1, %2)").arg(pos.x()).arg(pos.y()) << Qt::endl;
                    logFile.close();
                }
            } else {
                qDebug() << "[CRITICAL] main.cpp: ChatWindow创建但未显示，立即重试";
                qDebug() << "[CRITICAL] ChatWindow大小: " << chatWindow->size();
                qDebug() << "[CRITICAL] ChatWindow位置: " << chatWindow->pos();
                qDebug() << "[CRITICAL] ChatWindow可见性: " << chatWindow->isVisible();
                qDebug() << "[CRITICAL] ChatWindow窗口状态: " << chatWindow->windowState();
                
                // 立即重试显示窗口
                chatWindow->showNormal(); // 以正常状态显示
                chatWindow->resize(800, 600);
                chatWindow->move(100, 100);
                chatWindow->raise();
                chatWindow->activateWindow();
                chatWindow->repaint();
                QCoreApplication::processEvents();
                
                // 再次检查是否显示成功
                if (chatWindow->isVisible()) {
                    qDebug() << "[CRITICAL] main.cpp: 立即重试显示ChatWindow成功";
                    qDebug() << "[CRITICAL] ChatWindow大小: " << chatWindow->size();
                    qDebug() << "[CRITICAL] ChatWindow位置: " << chatWindow->pos();
                    // 移除置顶属性
                    chatWindow->setWindowFlags(chatWindow->windowFlags() & ~Qt::WindowStaysOnTopHint);
                    chatWindow->show(); // 重新显示，因为修改windowFlags后需要重新show
                    
                    // 记录日志
                if (logFile.open(QIODevice::Append | QIODevice::Text)) {
                    QTextStream out(&logFile);
                    QSize size = chatWindow->size();
                    QPoint pos = chatWindow->pos();
                    out << "[" << QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss.zzz") << "] " 
                        << "main.cpp: 立即重试显示ChatWindow成功" << Qt::endl;
                    out << "[" << QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss.zzz") << "] " 
                        << "main.cpp: ChatWindow大小: " << QString("(%1, %2)").arg(size.width()).arg(size.height()) << Qt::endl;
                    out << "[" << QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss.zzz") << "] " 
                        << "main.cpp: ChatWindow位置: " << QString("(%1, %2)").arg(pos.x()).arg(pos.y()) << Qt::endl;
                    logFile.close();
                }
                } else {
                    qDebug() << "[CRITICAL] main.cpp: 立即重试显示ChatWindow失败，使用定时器再次尝试";
                    qDebug() << "[CRITICAL] ChatWindow大小: " << chatWindow->size();
                    qDebug() << "[CRITICAL] ChatWindow位置: " << chatWindow->pos();
                    
                    // 设置定时器延时100毫秒后再次尝试
                    // QTimer::singleShot是一次性定时器，只触发一次
                    QTimer::singleShot(100, chatWindow, 
                    // lambda表达式捕获chatWindow和logFile的引用
                    [chatWindow, &logFile]() {
                        qDebug() << "[CRITICAL] main.cpp: 定时器重试显示ChatWindow...";
                        // 再次尝试显示窗口
                        chatWindow->showNormal();
                        chatWindow->resize(800, 600);
                        chatWindow->move(100, 100);
                        chatWindow->raise();
                        chatWindow->activateWindow();
                        chatWindow->repaint();
                        QCoreApplication::processEvents();
                        
                        // 检查是否显示成功
                        if (chatWindow->isVisible()) {
                            qDebug() << "[CRITICAL] main.cpp: 定时器重试显示ChatWindow成功";
                            qDebug() << "[CRITICAL] ChatWindow大小: " << chatWindow->size();
                            qDebug() << "[CRITICAL] ChatWindow位置: " << chatWindow->pos();
                            // 移除置顶属性
                            chatWindow->setWindowFlags(chatWindow->windowFlags() & ~Qt::WindowStaysOnTopHint);
                            chatWindow->show(); // 重新显示，因为修改windowFlags后需要重新show
                            
                            // 记录日志
                    if (logFile.open(QIODevice::Append | QIODevice::Text)) {
                        QTextStream out(&logFile);
                        QSize size = chatWindow->size();
                        QPoint pos = chatWindow->pos();
                        out << "[" << QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss.zzz") << "] " 
                            << "main.cpp: 定时器重试显示ChatWindow成功" << Qt::endl;
                        out << "[" << QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss.zzz") << "] " 
                            << "main.cpp: ChatWindow大小: " << QString("(%1, %2)").arg(size.width()).arg(size.height()) << Qt::endl;
                        out << "[" << QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss.zzz") << "] " 
                            << "main.cpp: ChatWindow位置: " << QString("(%1, %2)").arg(pos.x()).arg(pos.y()) << Qt::endl;
                        logFile.close();
                    }
                        } else {
                            qDebug() << "[CRITICAL] main.cpp: 定时器重试显示ChatWindow失败";
                            qDebug() << "[CRITICAL] ChatWindow大小: " << chatWindow->size();
                            qDebug() << "[CRITICAL] ChatWindow位置: " << chatWindow->pos();
                            // 即使失败，也移除置顶属性
                            chatWindow->setWindowFlags(chatWindow->windowFlags() & ~Qt::WindowStaysOnTopHint);
                            chatWindow->show(); // 重新显示，因为修改windowFlags后需要重新show
                        }
                    });
                }
            }
        } catch (const std::exception &e) {
            // 捕获标准异常
            qDebug() << "[CRITICAL] main.cpp: 创建ChatWindow异常:" << e.what();
            // 记录异常日志
            QString logFilePath = QCoreApplication::applicationDirPath() + "/login_debug.log";
            QFile logFile(logFilePath);
            if (logFile.open(QIODevice::Append | QIODevice::Text)) {
                QTextStream out(&logFile);
                out << "[" << QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss.zzz") << "] " 
                    << "main.cpp: 创建ChatWindow异常:" << e.what() << Qt::endl;
                logFile.close();
            }
        } catch (...) {
            // 捕获所有其他类型的异常
            qDebug() << "[CRITICAL] main.cpp: 创建ChatWindow未知异常";
            // 记录未知异常日志
            QString logFilePath = QCoreApplication::applicationDirPath() + "/login_debug.log";
            QFile logFile(logFilePath);
            if (logFile.open(QIODevice::Append | QIODevice::Text)) {
                QTextStream out(&logFile);
                out << "[" << QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss.zzz") << "] " 
                    << "main.cpp: 创建ChatWindow未知异常" << Qt::endl;
                logFile.close();
            }
        }
        qDebug() << "[CRITICAL] ==== 登录成功信号处理完成 ====";
    });
    
    // 记录信号槽连接结果到日志文件
    // 跨平台路径处理，使用应用程序所在目录
    QString logFilePath = QCoreApplication::applicationDirPath() + "/login_debug.log";
    QFile logFile(logFilePath);
    if (logFile.open(QIODevice::Append | QIODevice::Text)) {
        QTextStream out(&logFile);
        out << "[" << QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss.zzz") << "] " 
            << "main.cpp: 信号槽连接结果:" << (connectResult ? "SUCCESS" : "FAILED") << Qt::endl;
        logFile.close();
    }
    qDebug() << "main.cpp: 信号槽连接结果:" << (connectResult ? "SUCCESS" : "FAILED");
    
    // 显示登录窗口
    loginWindow.show();
    
    // 启动Qt应用程序的事件循环
    // a.exec()会一直运行，直到应用程序退出
    int result = a.exec();
    
    // 清理资源
    // 在程序退出前释放动态分配的内存
    if (chatWindow) {
        delete chatWindow; // 释放ChatWindow对象
    }
    
    // 清理Winsock（Windows平台）
    #ifdef _WIN32
    WSACleanup();
    #endif
    
    // 返回应用程序的退出代码
    return result;
}