// 跨平台网络头文件处理 - 注意：先包含Windows网络头文件，再包含Qt头文件，避免byte类型歧义
#ifdef _WIN32
    // 首先包含Windows头文件
    #include <winsock2.h>
    #include <ws2tcpip.h>
    // 防止Windows头文件中的byte类型与Qt冲突
    #undef byte
#endif

// 包含Qt应用程序的核心头文件
#include <QApplication>
#include <QCoreApplication>
#include <QFontDatabase>
// 文本编码相关的头文件 - Qt 5.14+ 已弃用 QTextCodec::setCodecForLocale
// #include <QTextCodec>
// 包含定时器相关的头文件
#include <QTimer>
// 包含登录窗口的头文件
#include "loginwindow.h"
// 包含聊天窗口的头文件
#include "chatwindow.h"

// 注意：不要包含数据库头文件，客户端不需要直接连接数据库
// #include "db/db.h"

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
    
    // 【新增】这一行非常关键！解决Windows/虚拟机下界面空白、文字不显示的问题
    // 强制 Qt 使用 CPU 进行界面绘制，绕过可能有问题的显卡驱动
    QCoreApplication::setAttribute(Qt::AA_UseSoftwareOpenGL);

    // 设置Qt属性，必须在QApplication创建之前调用
    QCoreApplication::setAttribute(Qt::AA_EnableHighDpiScaling);
    QCoreApplication::setAttribute(Qt::AA_UseHighDpiPixmaps);
    
    // 创建Qt应用程序实例
    // QApplication是Qt GUI应用程序的核心类，管理应用程序的资源、设置和事件循环
    QApplication a(argc, argv);
    
    // 全局字体设置 - 为所有平台设置明确的字体
    QFont globalFont;
    #ifdef _WIN32
    // 设置全局字体，确保Windows平台上文本显示
    // 尝试多种字体，确保至少有一种可用
    QStringList fontFamilies = {"Microsoft YaHei", "SimHei", "Arial", "SansSerif"};
    QString selectedFont;
    
    for (const QString &fontFamily : fontFamilies) {
        if (QFontDatabase::hasFamily(fontFamily)) {
            globalFont = QFont(fontFamily, 10);
            selectedFont = fontFamily;
            break;
        }
    }
    
    // 如果没有找到指定字体，使用默认字体
    if (selectedFont.isEmpty()) {
        globalFont = QFont();
        globalFont.setPointSize(10);
        selectedFont = "Default";
    }
    
    globalFont.setStyleStrategy(QFont::PreferAntialias); // 开启抗锯齿
    a.setFont(globalFont);
    qDebug() << "已设置Windows平台全局字体: " << selectedFont << ", 10pt";
    #else
    // Linux平台使用Arial字体
    globalFont = QFont("Arial", 14);
    qDebug() << "非Windows平台: 使用Arial字体, 14px";
    a.setFont(globalFont);
    #endif
    qDebug() << "已设置全局字体: " << globalFont.family() << ", " << globalFont.pointSize() << "pt";
    
    // 确保应用程序字体在所有平台上正确设置
    QApplication::setFont(globalFont);
    
    // 加载样式表
    QFile file(":/styles.qss");
    if(file.open(QFile::ReadOnly)) {
        QString styleSheet = file.readAll();
        a.setStyleSheet(styleSheet);
        file.close();
        qDebug() << "样式表加载成功";
    } else {
        qDebug() << "样式表加载失败:" << file.errorString();
    }
    
    // 设置中文显示
    // Qt 5.14+ 推荐使用 QCoreApplication::setAttribute(Qt::AA_EnableHighDpiScaling) 等属性
    // 现代Qt默认使用UTF-8编码，无需手动设置
    
    // 客户端不需要直接连接数据库，数据库操作由服务器处理
    // 移除数据库连接和表创建代码，避免编译错误
    qDebug() << "客户端启动，数据库操作由服务器处理";
    
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
                qDebug() << "[CRITICAL] Logout signal received in main.cpp";
                if (chatWindow) {
                    qDebug() << "[CRITICAL] Processing logout for chatWindow:" << chatWindow;
                    // 先保存chatWindow指针
                    ChatWindow *windowToDelete = chatWindow;
                    // 立即将chatWindow置为nullptr，防止其他地方访问
                    chatWindow = nullptr;
                    
                    // 先断开所有信号连接
                    windowToDelete->disconnect();
                    
                    // 关闭窗口
                    windowToDelete->close();
                    
                    // 重新显示登录窗口
                    loginWindow.resetChatClient();
                    loginWindow.show();
                    qDebug() << "[CRITICAL] Login window shown after logout";
                    
                    // 使用QTimer延迟删除，确保所有事件都已处理
                    QTimer::singleShot(100, [windowToDelete]() {
                        qDebug() << "[CRITICAL] Deleting chatWindow:" << windowToDelete;
                        delete windowToDelete;
                    });
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