#ifndef LOGINWINDOW_H
#define LOGINWINDOW_H

#include <QMainWindow>
#include <QWidget>
#include <QLabel>
#include <QLineEdit>
#include <QPushButton>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QMessageBox>
#include <QStackedWidget>
#include <QShowEvent>
#include "chatclient.h"

class LoginWindow : public QMainWindow {
    Q_OBJECT

public:
    LoginWindow(QWidget *parent = nullptr);
    ~LoginWindow();
    
    // 获取ChatClient实例
    ChatClient *getChatClient() { return chatClient; }

private:
    // 防止重复处理登录响应（避免消息框/窗口重复弹出）
    bool loginHandled = false;

private:
    // 登录界面组件
    QWidget *loginWidget;
    QLabel *loginTitleLabel;
    QLabel *idLabel;
    QLineEdit *idLineEdit;
    QLabel *passwordLabel;
    QLineEdit *passwordLineEdit;
    QPushButton *loginButton;
    QPushButton *registerButton;
    QMessageBox *messageBox;

    // 注册界面组件
    QWidget *registerWidget;
    QLabel *registerTitleLabel;
    QLabel *registerNameLabel;
    QLineEdit *registerNameLineEdit;
    QLabel *registerPasswordLabel;
    QLineEdit *registerPasswordLineEdit;
    QPushButton *registerSubmitButton;
    QPushButton *backToLoginButton;

    QStackedWidget *stackedWidget;
    ChatClient *chatClient;

protected:
    // 重写showEvent事件处理函数
    void showEvent(QShowEvent *event) override;

private slots:
    void handleLogin();
    void handleRegister();
    void switchToRegister();
    void switchToLogin();
    void handleLoginResponse(bool success, const QString &message);
    void handleRegisterResponse(bool success, int userId, const QString &message);

signals:
    void loginSuccess(int userId, const QString &userName);
};

#endif // LOGINWINDOW_H