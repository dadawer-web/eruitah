#include "loginwindow.h"
#include <QDebug>
#include <QTimer>

LoginWindow::LoginWindow(QWidget *parent) : QMainWindow(parent) {
    // 设置窗口标题和大小
    setWindowTitle("Qt Chat - 登录");
    setFixedSize(400, 300);

    // 登录窗口初始化

    // 创建聊天客户端实例
    chatClient = new ChatClient(this);
    connect(chatClient, &ChatClient::loginResponse, this, &LoginWindow::handleLoginResponse);
    connect(chatClient, &ChatClient::registerResponse, this, &LoginWindow::handleRegisterResponse);

    // 初始化登录界面
    loginWidget = new QWidget;
    loginTitleLabel = new QLabel("用户登录");
    QFont font = loginTitleLabel->font();
    font.setPointSize(18);
    font.setBold(true);
    loginTitleLabel->setFont(font);
    loginTitleLabel->setAlignment(Qt::AlignCenter);

    idLabel = new QLabel("用户ID:");
    idLineEdit = new QLineEdit;
    passwordLabel = new QLabel("密码:");
    passwordLineEdit = new QLineEdit;
    passwordLineEdit->setEchoMode(QLineEdit::Password);

    loginButton = new QPushButton("登录");
    registerButton = new QPushButton("注册");

    QVBoxLayout *loginLayout = new QVBoxLayout;
    loginLayout->addWidget(loginTitleLabel);
    loginLayout->addSpacing(20);

    QHBoxLayout *idLayout = new QHBoxLayout;
    idLayout->addWidget(idLabel);
    idLayout->addWidget(idLineEdit);
    loginLayout->addLayout(idLayout);

    QHBoxLayout *passwordLayout = new QHBoxLayout;
    passwordLayout->addWidget(passwordLabel);
    passwordLayout->addWidget(passwordLineEdit);
    loginLayout->addLayout(passwordLayout);
    loginLayout->addSpacing(20);

    QHBoxLayout *buttonLayout = new QHBoxLayout;
    buttonLayout->addWidget(loginButton);
    buttonLayout->addWidget(registerButton);
    loginLayout->addLayout(buttonLayout);

    loginWidget->setLayout(loginLayout);

    // 初始化注册界面
    registerWidget = new QWidget;
    registerTitleLabel = new QLabel("用户注册");
    registerTitleLabel->setFont(font);
    registerTitleLabel->setAlignment(Qt::AlignCenter);

    registerNameLabel = new QLabel("用户名:");
    registerNameLineEdit = new QLineEdit;
    registerPasswordLabel = new QLabel("密码:");
    registerPasswordLineEdit = new QLineEdit;
    registerPasswordLineEdit->setEchoMode(QLineEdit::Password);

    registerSubmitButton = new QPushButton("注册");
    backToLoginButton = new QPushButton("返回登录");

    QVBoxLayout *registerLayout = new QVBoxLayout;
    registerLayout->addWidget(registerTitleLabel);
    registerLayout->addSpacing(20);

    QHBoxLayout *nameLayout = new QHBoxLayout;
    nameLayout->addWidget(registerNameLabel);
    nameLayout->addWidget(registerNameLineEdit);
    registerLayout->addLayout(nameLayout);

    QHBoxLayout *regPasswordLayout = new QHBoxLayout;
    regPasswordLayout->addWidget(registerPasswordLabel);
    regPasswordLayout->addWidget(registerPasswordLineEdit);
    registerLayout->addLayout(regPasswordLayout);
    registerLayout->addSpacing(20);

    QHBoxLayout *regButtonLayout = new QHBoxLayout;
    regButtonLayout->addWidget(registerSubmitButton);
    regButtonLayout->addWidget(backToLoginButton);
    registerLayout->addLayout(regButtonLayout);

    registerWidget->setLayout(registerLayout);

    // 创建堆栈窗口
    stackedWidget = new QStackedWidget;
    stackedWidget->addWidget(loginWidget);
    stackedWidget->addWidget(registerWidget);

    setCentralWidget(stackedWidget);

    // 连接信号和槽
    connect(loginButton, &QPushButton::clicked, this, &LoginWindow::handleLogin);
    connect(registerButton, &QPushButton::clicked, this, &LoginWindow::switchToRegister);
    connect(registerSubmitButton, &QPushButton::clicked, this, &LoginWindow::handleRegister);
    connect(backToLoginButton, &QPushButton::clicked, this, &LoginWindow::switchToLogin);
    
    // 登录窗口初始化完成，等待用户手动登录
}

LoginWindow::~LoginWindow() {
}

void LoginWindow::handleLogin() {
    // 重置登录处理标志，允许新的登录请求
    loginHandled = false;
    qDebug() << "[CRITICAL] Login button clicked, resetting loginHandled flag to false";
    
    QString idStr = idLineEdit->text();
    QString password = passwordLineEdit->text();
    
    if (idStr.isEmpty() || password.isEmpty()) {
        QMessageBox::warning(this, "警告", "请输入用户ID和密码");
        return;
    }

    bool ok;
    int id = idStr.toInt(&ok);
    if (!ok) {
        QMessageBox::warning(this, "警告", "用户ID必须是数字");
        return;
    }

    // 先连接服务器，再登录
    if (!chatClient->connectToServer("127.0.0.1", 6000)) {
        QMessageBox::warning(this, "连接失败", "无法连接到服务器，请检查服务器是否运行");
        return;
    }

    // 调用客户端登录方法
    chatClient->login(id, password);

    
}

void LoginWindow::handleRegister() {
    QString name = registerNameLineEdit->text();
    QString password = registerPasswordLineEdit->text();

    if (name.isEmpty() || password.isEmpty()) {
        QMessageBox::warning(this, "警告", "请输入用户名和密码");
        return;
    }

    // 先连接服务器，再注册
    if (!chatClient->connectToServer("127.0.0.1", 6000)) {
        QMessageBox::warning(this, "连接失败", "无法连接到服务器，请检查服务器是否运行");
        return;
    }

    // 调用客户端注册方法
    chatClient->registerUser(name, password);
}

void LoginWindow::switchToRegister() {
    stackedWidget->setCurrentWidget(registerWidget);
}

void LoginWindow::switchToLogin() {
    stackedWidget->setCurrentWidget(loginWidget);
}

void LoginWindow::showEvent(QShowEvent *event) {
    QMainWindow::showEvent(event);
    // 重置登录处理标志，确保每次显示登录窗口时都能处理新的登录请求
    loginHandled = false;
    qDebug() << "[CRITICAL] Login window shown, resetting loginHandled flag to false";
}

void LoginWindow::handleLoginResponse(bool success, const QString &message) {
    // 首先检查是否已处理，防止重复处理
    if (loginHandled) {
        qDebug() << "[CRITICAL] Login response already handled, ignoring repeated signal";
        return;
    }
    
    qDebug() << "[CRITICAL] Login response received, success:" << success;
    qDebug() << "[CRITICAL] Response message:" << message;
    
    // 标记已处理，防止重复处理
    loginHandled = true;
    
    if (success) {
        // 发送登录成功信号，传递用户ID和名称
        int userId = idLineEdit->text().toInt();
        
        // 尝试从消息中解析JSON以获取用户名
        QString userName = "未知用户";
        
        // 移除可能的特殊字符前缀
        QString cleanMessage = message;
        if (cleanMessage.startsWith("&")) {
            cleanMessage = cleanMessage.mid(1);
        }
        
        // 尝试解析JSON
        QJsonDocument doc = QJsonDocument::fromJson(cleanMessage.toUtf8());
        if (doc.isObject()) {
            QJsonObject obj = doc.object();
            if (obj.contains("name")) {
                userName = obj["name"].toString();
                qDebug() << "[CRITICAL] Successfully parsed username:" << userName;
            } else {
                qDebug() << "[CRITICAL] JSON does not contain 'name' field";
            }
        } else {
            qDebug() << "[CRITICAL] Failed to parse JSON from message";
        }
        
        // 如果JSON解析失败，使用一个默认值或者从用户输入中获取
        if (userName == "未知用户") {
            // 可以尝试使用ID作为用户名或者其他合理的默认值
            userName = QString("用户%1").arg(userId);
            qDebug() << "[CRITICAL] Using default username:" << userName;
        }
        
        // 发出登录成功信号
        qDebug() << "[CRITICAL] About to emit loginSuccess signal with userId:" << userId << "userName:" << userName;
        
        // 写入日志文件，记录信号发出
        QFile logFile("/home/xmy/code/login_debug.log");
        if (logFile.open(QIODevice::Append | QIODevice::Text)) {
            QTextStream out(&logFile);
            out << "[" << QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss.zzz") << "] " 
                << "LoginWindow: emitting loginSuccess signal with userId:" << userId << " userName:" << userName << Qt::endl;
            logFile.close();
        }
        
        // 直接发出登录成功信号，不等待消息框
        emit loginSuccess(userId, userName);
        
        // 注意：移除登录成功消息框，避免干扰窗口跳转
        qDebug() << "[CRITICAL] Login success signal emitted, window switching should proceed";

        // 在 ChatWindow 创建并连接信号槽后再请求好友和群组列表，避免丢失初始的列表更新信号
        // 使用短延迟确保 ChatWindow 构造完成并连接完信号
        QTimer::singleShot(100, this, [=]() {
            qDebug() << "[CRITICAL] Requesting friend list after loginSuccess for userId:" << userId;
            chatClient->requestFriendList(userId);
        });

        // 请求群组列表稍后执行，避免网络消息合并
        QTimer::singleShot(300, this, [=]() {
            qDebug() << "[CRITICAL] Requesting group list after loginSuccess for userId:" << userId;
            chatClient->requestGroupList(userId);
        });

        QMessageBox::information(this, "成功", message);
    } else {
        QMessageBox::warning(this, "失败", message);
        qDebug() << "[CRITICAL] Login failed, showing error message";
        // 登录失败时重置loginHandled标志，允许用户再次尝试登录
        loginHandled = false;
        qDebug() << "[CRITICAL] Login failed, resetting loginHandled flag to false";
    }
}

void LoginWindow::handleRegisterResponse(bool success, int userId, const QString &message) {
    if (success) {
        QMessageBox::information(this, "成功", message + QString("，您的用户ID是: %1").arg(userId));
        switchToLogin();
    } else {
        QMessageBox::warning(this, "失败", message);
    }
}
