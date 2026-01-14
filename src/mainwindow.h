#ifndef MAINWINDOW_H
#define MAINWINDOW_H

// 跨平台网络头文件处理 - 注意：先包含Windows网络头文件，再包含Qt头文件，避免byte类型歧义
#ifdef _WIN32
    #include <winsock2.h>
    #include <ws2tcpip.h>
    // 防止Windows头文件中的byte类型与Qt冲突
    #undef byte
#endif

#include <QMainWindow>
#include <QPushButton>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QWidget>
#include <QLabel>
#include <QLineEdit>
#include <QTextEdit>
#include <QThread>
#include <QMessageBox>
#include "chatserver.h"
#include "loginwindow.h"

class MainWindow : public QMainWindow {
    Q_OBJECT

public:
    MainWindow(QWidget *parent = nullptr);
    ~MainWindow();

private slots:
    void startServer();
    void stopServer();
    void startClient();
    void onServerStarted(bool success);
    void onServerStopped();
    void onClientConnected();
    void handleLoginSuccess(int userId, const QString &userName);

private:
    // UI组件
    QWidget *centralWidget;
    QVBoxLayout *mainLayout;
    QHBoxLayout *buttonLayout;
    QPushButton *startServerButton;
    QPushButton *stopServerButton;
    QPushButton *startClientButton;
    QLineEdit *portEdit;
    QLabel *portLabel;
    QTextEdit *logTextEdit;
    
    // 服务器相关
    ChatServer *server;
    QThread *serverThread;
    bool serverRunning;
    
    // 客户端相关
    LoginWindow *loginWindow;
    
    // 初始化UI
    void initUI();
    
    // 添加日志
    void addLog(const QString &log);
};

#endif // MAINWINDOW_H