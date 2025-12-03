#include "loginwindow.h"
#include <QDebug>
#include <QTimer>

LoginWindow::LoginWindow(QWidget *parent) : QMainWindow(parent) {
    // 设置窗口标题和大小
    setWindowTitle("Qt Chat - 登录");
    setFixedSize(420, 380);
    setObjectName("loginWindow");
    


    // 应用样式表
    QFile styleFile("/home/xmy/code/src/styles.qss");
    if (styleFile.open(QIODevice::ReadOnly | QIODevice::Text)) {
        QString styleSheet = styleFile.readAll();
        setStyleSheet(styleSheet);
        styleFile.close();
        qDebug() << "样式表加载成功";
    } else {
        qDebug() << "样式表加载失败，使用默认样式";
        // 如果样式表文件无法加载，使用不包含Qt不支持属性的内联样式
        QString inlineStyle = ""
            "QWidget { font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif; font-size: 14px; color: #333; background-color: #f5f5f5; }" 
            "QLabel[class='titleLabel'] { font-size: 24px; font-weight: 600; color: #2c3e50; margin-bottom: 20px; }" 
            "QWidget[class='card'] { background-color: white; border-radius: 12px; padding: 30px; }" 
            "QLineEdit { height: 40px; border: 1px solid #ddd; border-radius: 8px; padding: 0 12px; font-size: 14px; background-color: white; }" 
            "QLineEdit:focus { border-color: #3498db; }" 
            "QPushButton { height: 40px; border: none; border-radius: 8px; font-size: 14px; font-weight: 500; padding: 0 20px; }" 
            "QPushButton[class='primaryButton'] { background-color: #3498db; color: white; }" 
            "QPushButton[class='primaryButton']:hover { background-color: #2980b9; }" 
            "QPushButton[class='primaryButton']:pressed { background-color: #2471a3; }" 
            "QPushButton[class='secondaryButton'] { background-color: #ecf0f1; color: #333; border: 1px solid #ddd; }" 
            "QPushButton[class='secondaryButton']:hover { background-color: #d5dbdb; }" 
            "QPushButton[class='secondaryButton']:pressed { background-color: #bdc3c7; }";
        setStyleSheet(inlineStyle);
    }

    // 创建聊天客户端实例
    chatClient = new ChatClient(this);
    connect(chatClient, &ChatClient::loginResponse, this, &LoginWindow::handleLoginResponse);
    connect(chatClient, &ChatClient::registerResponse, this, &LoginWindow::handleRegisterResponse);

    // 创建主容器
    QWidget *mainWidget = new QWidget;
    QVBoxLayout *mainLayout = new QVBoxLayout;
    mainLayout->setAlignment(Qt::AlignCenter);
    mainLayout->setContentsMargins(20, 20, 20, 20);
    mainWidget->setLayout(mainLayout);
    setCentralWidget(mainWidget);

    // 初始化登录界面
    loginWidget = new QWidget;
    loginWidget->setStyleSheet(
        "background-color: white; "
        "border-radius: 16px; "
        "padding: 40px 30px;"
    );
    
    loginTitleLabel = new QLabel("用户登录");
    QFont titleFont = loginTitleLabel->font();
    titleFont.setPointSize(24);
    titleFont.setBold(true);
    loginTitleLabel->setFont(titleFont);
    loginTitleLabel->setStyleSheet(
        "color: #2c3e50; "
        "margin-bottom: 25px; "
        "text-align: center;"
    );
    loginTitleLabel->setAlignment(Qt::AlignCenter);

    // 用户ID输入框
    idLabel = new QLabel("用户ID");
    idLabel->setStyleSheet(
        "color: #666; "
        "font-weight: 500; "
        "margin-bottom: 8px;"
    );
    
    idLineEdit = new QLineEdit;
    idLineEdit->setStyleSheet(
        "height: 44px; "
        "border: 1px solid #e0e0e0; "
        "border-radius: 8px; "
        "padding: 0 15px; "
        "font-size: 14px; "
        "background-color: #fafafa;"
    );
    
    // 密码输入框
    passwordLabel = new QLabel("密码");
    passwordLabel->setStyleSheet(
        "color: #666; "
        "font-weight: 500; "
        "margin-top: 18px; "
        "margin-bottom: 8px;"
    );
    
    passwordLineEdit = new QLineEdit;
    passwordLineEdit->setEchoMode(QLineEdit::Password);
    passwordLineEdit->setStyleSheet(
        "height: 44px; "
        "border: 1px solid #e0e0e0; "
        "border-radius: 8px; "
        "padding: 0 15px; "
        "font-size: 14px; "
        "background-color: #fafafa;"
    );

    // 按钮
    loginButton = new QPushButton("登录");
    loginButton->setStyleSheet(
        "height: 44px; "
        "background-color: #3498db; "
        "color: white; "
        "border: none; "
        "border-radius: 8px; "
        "font-size: 16px; "
        "font-weight: 500;"
    );
    
    registerButton = new QPushButton("注册");
    registerButton->setStyleSheet(
        "height: 44px; "
        "background-color: white; "
        "color: #3498db; "
        "border: 1px solid #3498db; "
        "border-radius: 8px; "
        "font-size: 16px; "
        "font-weight: 500;"
    );

    // 布局
    QVBoxLayout *loginLayout = new QVBoxLayout;
    loginLayout->setContentsMargins(0, 0, 0, 0);
    loginLayout->setSpacing(0);
    
    loginLayout->addWidget(loginTitleLabel);
    
    // 用户ID部分
    loginLayout->addWidget(idLabel);
    loginLayout->addWidget(idLineEdit);
    
    // 密码部分
    loginLayout->addWidget(passwordLabel);
    loginLayout->addWidget(passwordLineEdit);
    
    // 按钮部分
    loginLayout->addSpacing(25);
    
    QHBoxLayout *buttonLayout = new QHBoxLayout;
    buttonLayout->setSpacing(12);
    buttonLayout->addWidget(loginButton, 1);
    buttonLayout->addWidget(registerButton, 1);
    loginLayout->addLayout(buttonLayout);

    loginWidget->setLayout(loginLayout);

    // 初始化注册界面
    registerWidget = new QWidget;
    registerWidget->setStyleSheet(
        "background-color: white; "
        "border-radius: 16px; "
        "padding: 40px 30px;"
    );
    
    registerTitleLabel = new QLabel("用户注册");
    registerTitleLabel->setFont(titleFont);
    registerTitleLabel->setStyleSheet(
        "color: #2c3e50; "
        "margin-bottom: 25px; "
        "text-align: center;"
    );
    registerTitleLabel->setAlignment(Qt::AlignCenter);

    // 用户名输入框
    registerNameLabel = new QLabel("用户名");
    registerNameLabel->setStyleSheet(
        "color: #666; "
        "font-weight: 500; "
        "margin-bottom: 8px;"
    );
    registerNameLineEdit = new QLineEdit;
    registerNameLineEdit->setStyleSheet(
        "height: 44px; "
        "border: 1px solid #e0e0e0; "
        "border-radius: 8px; "
        "padding: 0 15px; "
        "font-size: 14px; "
        "background-color: #fafafa;"
    );
    
    // 密码输入框
    registerPasswordLabel = new QLabel("密码");
    registerPasswordLabel->setStyleSheet(
        "color: #666; "
        "font-weight: 500; "
        "margin-top: 18px; "
        "margin-bottom: 8px;"
    );
    registerPasswordLineEdit = new QLineEdit;
    registerPasswordLineEdit->setEchoMode(QLineEdit::Password);
    registerPasswordLineEdit->setStyleSheet(
        "height: 44px; "
        "border: 1px solid #e0e0e0; "
        "border-radius: 8px; "
        "padding: 0 15px; "
        "font-size: 14px; "
        "background-color: #fafafa;"
    );

    // 按钮
    registerSubmitButton = new QPushButton("注册");
    registerSubmitButton->setStyleSheet(
        "height: 44px; "
        "background-color: #3498db; "
        "color: white; "
        "border: none; "
        "border-radius: 8px; "
        "font-size: 16px; "
        "font-weight: 500;"
    );
    
    backToLoginButton = new QPushButton("返回登录");
    backToLoginButton->setStyleSheet(
        "height: 44px; "
        "background-color: white; "
        "color: #3498db; "
        "border: 1px solid #3498db; "
        "border-radius: 8px; "
        "font-size: 16px; "
        "font-weight: 500;"
    );

    // 布局
    QVBoxLayout *registerLayout = new QVBoxLayout;
    registerLayout->setContentsMargins(0, 0, 0, 0);
    registerLayout->setSpacing(0);
    
    registerLayout->addWidget(registerTitleLabel);
    
    // 用户名部分
    registerLayout->addWidget(registerNameLabel);
    registerLayout->addWidget(registerNameLineEdit);
    
    // 密码部分
    registerLayout->addWidget(registerPasswordLabel);
    registerLayout->addWidget(registerPasswordLineEdit);
    
    // 按钮部分
    registerLayout->addSpacing(25);
    
    QHBoxLayout *regButtonLayout = new QHBoxLayout;
    regButtonLayout->setSpacing(12);
    regButtonLayout->addWidget(registerSubmitButton, 1);
    regButtonLayout->addWidget(backToLoginButton, 1);
    registerLayout->addLayout(regButtonLayout);

    registerWidget->setLayout(registerLayout);

    // 创建堆栈窗口
    stackedWidget = new QStackedWidget;
    stackedWidget->addWidget(loginWidget);
    stackedWidget->addWidget(registerWidget);
    
    mainLayout->addWidget(stackedWidget);
    mainLayout->setAlignment(stackedWidget, Qt::AlignCenter);

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
        int userId = -1;
        QString userName = "未知用户";
        
        // 移除可能的特殊字符前缀
        QString cleanMessage = message;
        if (cleanMessage.startsWith("&")) {
            cleanMessage = cleanMessage.mid(1);
        }
        
        // 尝试解析JSON，获取用户ID和名称
        QJsonDocument doc = QJsonDocument::fromJson(cleanMessage.toUtf8());
        if (doc.isObject()) {
            QJsonObject obj = doc.object();
            // 从JSON中获取用户ID
            if (obj.contains("id")) {
                userId = obj["id"].toVariant().toLongLong();
                qDebug() << "[CRITICAL] Successfully parsed userId:" << userId;
            }
            // 从JSON中获取用户名
            if (obj.contains("name")) {
                userName = obj["name"].toString();
                qDebug() << "[CRITICAL] Successfully parsed username:" << userName;
            }
        } else {
            qDebug() << "[CRITICAL] Failed to parse JSON from message";
        }
        
        // 如果从JSON中没有获取到userId，尝试从idLineEdit获取（登录情况）
        if (userId == -1) {
            userId = idLineEdit->text().toInt();
            qDebug() << "[CRITICAL] Using userId from idLineEdit:" << userId;
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

        // 移除登录成功消息框，避免干扰窗口跳转
        // QMessageBox::information(this, "成功", message);
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
