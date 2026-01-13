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
#include <QTimer>
#include "chatclient.h"

class LoginWindow : public QMainWindow {
    Q_OBJECT

public:
    LoginWindow(QWidget *parent = nullptr);
    ~LoginWindow();
    
    // 获取ChatClient实例
    ChatClient *getChatClient() { return chatClient; }
    
    // 重置ChatClient实例（用于登出后重新创建）
    void resetChatClient() {
        // 创建新的ChatClient实例，然后替换旧的
        ChatClient *newClient = new ChatClient(this);
        connect(newClient, &ChatClient::loginResponse, this, &LoginWindow::handleLoginResponse);
        connect(newClient, &ChatClient::registerResponse, this, &LoginWindow::handleRegisterResponse);
        
        // 先保存旧的指针
        ChatClient *oldClient = chatClient;
        // 立即替换为新的实例
        chatClient = newClient;
        
        // 延迟删除旧的实例，确保所有事件都已处理
        QTimer::singleShot(100, [oldClient]() {
            delete oldClient;
        });
    }

private:
    // 防止重复处理登录响应（避免消息框/窗口重复弹出）
    bool loginHandled = false;

private:
    // 登录界面组件
    QWidget *loginWidget;
    QLabel *loginTitleLabel;
    QLabel *serverLabel;
    QLineEdit *serverLineEdit;
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
    QLabel *registerAvatarLabel;
    QPushButton *registerAvatarButton;
    QLabel *avatarPreviewLabel;
    QPushButton *registerSubmitButton;
    QPushButton *backToLoginButton;
    QString avatarPath;

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