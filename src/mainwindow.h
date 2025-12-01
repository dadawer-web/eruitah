#ifndef MAINWINDOW_H
#define MAINWINDOW_H

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