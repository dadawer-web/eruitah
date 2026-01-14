#include "loginwindow.h"
#include <QDebug>
#include <QTimer>
#include <QCoreApplication>
#include <QFileDialog>
#include <QPixmap>
#include <QPainter>
#include <QPainterPath>

// 跨平台网络头文件处理 - 注意：先包含Windows网络头文件，再包含Qt头文件，避免byte类型歧义
#ifdef _WIN32
    #include <winsock2.h>
    #include <ws2tcpip.h>
    // 防止Windows头文件中的byte类型与Qt冲突
    #undef byte
#endif

LoginWindow::LoginWindow(QWidget *parent) : QMainWindow(parent) {
    // 1. 基础设置
    setWindowTitle(QStringLiteral("Qt Chat - 登录"));
    setFixedSize(520, 480);
    setObjectName("loginWindow");

    // 2. 加载样式表
    QFile file(":/styles.qss");
    if(file.open(QFile::ReadOnly)) {
        QString styleSheet = file.readAll();
        // 注意：这里追加样式，而不是覆盖，防止破坏子控件样式
        this->setStyleSheet(this->styleSheet() + styleSheet); 
        file.close();
        qDebug() << "登录窗口样式表加载成功";
    }

    // 3. 创建客户端 (传入 this 确保内存管理)
    chatClient = new ChatClient(this);
    connect(chatClient, &ChatClient::loginResponse, this, &LoginWindow::handleLoginResponse);
    connect(chatClient, &ChatClient::registerResponse, this, &LoginWindow::handleRegisterResponse);

    // 4. 创建主容器 【修复点：必须传入 this】
    QWidget *mainWidget = new QWidget(this);
    // 【修复点：设置主容器背景透明，防止它遮挡住背景图（如果有的话）】
    mainWidget->setAttribute(Qt::WA_TranslucentBackground); 
    
    QVBoxLayout *mainLayout = new QVBoxLayout(mainWidget);
    // 【关键修复】：Windows下不要过度使用 AlignCenter，容易把控件压成0
    // 我们保留边距，但去掉布局的强制居中，让 stackedWidget 自己去填充
    mainLayout->setContentsMargins(20, 20, 20, 20);
    mainLayout->setSpacing(10);
    
    // 这一步必须做
    setCentralWidget(mainWidget);

    // ================= 登录界面初始化 =================
    loginWidget = new QWidget(this); // 【修复点：传入this】
    // 强制指定登录框的大小策略，防止被压缩
    loginWidget->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Preferred);
    loginWidget->setStyleSheet(
        "QWidget#loginWidget {" // 加上ID选择器，防止污染子控件
        "background-color: white; "
        "border-radius: 16px; "
        "padding: 40px 30px; "
        "color: #000000;"
        "}"
    );
    loginWidget->setObjectName("loginWidget"); // 配合上面的样式选择器

    loginTitleLabel = new QLabel(QStringLiteral("用户登录"), loginWidget);
    loginTitleLabel->setStyleSheet("color: #2c3e50; font-size: 20px; font-weight: bold; margin-bottom: 25px;");
    loginTitleLabel->setAlignment(Qt::AlignCenter);

    serverLabel = new QLabel(QStringLiteral("服务器地址"), loginWidget);
    serverLabel->setStyleSheet("color: #333333; font-size: 14px;");
    serverLineEdit = new QLineEdit(loginWidget);
    serverLineEdit->setText("127.0.0.1:6000");

    idLabel = new QLabel(QStringLiteral("用户ID"), loginWidget);
    idLabel->setStyleSheet("color: #333333; font-size: 14px;");
    idLineEdit = new QLineEdit(loginWidget);

    passwordLabel = new QLabel(QStringLiteral("密码"), loginWidget);
    passwordLabel->setStyleSheet("color: #333333; font-size: 14px;");
    passwordLineEdit = new QLineEdit(loginWidget);
    passwordLineEdit->setEchoMode(QLineEdit::Password);

    loginButton = new QPushButton(QStringLiteral("登录"), loginWidget);
    registerButton = new QPushButton(QStringLiteral("注册"), loginWidget);

    QVBoxLayout *loginLayout = new QVBoxLayout(loginWidget);
    loginLayout->addWidget(loginTitleLabel);
    loginLayout->addWidget(serverLabel);
    loginLayout->addWidget(serverLineEdit);
    loginLayout->addWidget(idLabel);
    loginLayout->addWidget(idLineEdit);
    loginLayout->addWidget(passwordLabel);
    loginLayout->addWidget(passwordLineEdit);
    loginLayout->addSpacing(25);
    
    QHBoxLayout *buttonLayout = new QHBoxLayout;
    buttonLayout->addWidget(loginButton);
    buttonLayout->addWidget(registerButton);
    loginLayout->addLayout(buttonLayout);

    // ================= 注册界面初始化 =================
    registerWidget = new QWidget(this); // 【修复点：传入this】
    registerWidget->setObjectName("registerWidget");
    registerWidget->setStyleSheet(
        "QWidget#registerWidget {"
        "background-color: white; "
        "border-radius: 16px; "
        "padding: 40px 30px; "
        "color: #000000;"
        "}"
    );

    registerTitleLabel = new QLabel(QStringLiteral("用户注册"), registerWidget);
    registerTitleLabel->setStyleSheet("color: #2c3e50; font-size: 20px; font-weight: bold; margin-bottom: 25px;");
    registerTitleLabel->setAlignment(Qt::AlignCenter);

    registerNameLabel = new QLabel(QStringLiteral("用户名"), registerWidget);
    registerNameLineEdit = new QLineEdit(registerWidget);

    registerPasswordLabel = new QLabel(QStringLiteral("密码"), registerWidget);
    registerPasswordLineEdit = new QLineEdit(registerWidget);
    registerPasswordLineEdit->setEchoMode(QLineEdit::Password);

    registerAvatarLabel = new QLabel(QStringLiteral("头像"), registerWidget);
    
    // 头像区域
    QHBoxLayout *avatarLayout = new QHBoxLayout;
    registerAvatarButton = new QPushButton(QStringLiteral("选择头像"), registerWidget);
    avatarPreviewLabel = new QLabel(registerWidget);
    avatarPreviewLabel->setFixedSize(60, 60); //稍微改小一点防止撑爆窗口
    avatarPreviewLabel->setStyleSheet("border: 1px solid #e0e0e0; border-radius: 30px; background-color: #fafafa;");
    avatarLayout->addWidget(registerAvatarButton);
    avatarLayout->addWidget(avatarPreviewLabel);

    registerSubmitButton = new QPushButton(QStringLiteral("注册提交"), registerWidget);
    backToLoginButton = new QPushButton(QStringLiteral("返回登录"), registerWidget);

    QVBoxLayout *registerLayout = new QVBoxLayout(registerWidget);
    registerLayout->addWidget(registerTitleLabel);
    registerLayout->addWidget(registerNameLabel);
    registerLayout->addWidget(registerNameLineEdit);
    registerLayout->addWidget(registerPasswordLabel);
    registerLayout->addWidget(registerPasswordLineEdit);
    registerLayout->addWidget(registerAvatarLabel);
    registerLayout->addLayout(avatarLayout);
    registerLayout->addSpacing(20);

    QHBoxLayout *regButtonLayout = new QHBoxLayout;
    regButtonLayout->addWidget(registerSubmitButton);
    regButtonLayout->addWidget(backToLoginButton);
    registerLayout->addLayout(regButtonLayout);

    // ================= 堆栈窗口组装 =================
    stackedWidget = new QStackedWidget(this); // 【修复点：传入this】
    stackedWidget->addWidget(loginWidget);
    stackedWidget->addWidget(registerWidget);
    
    // 【关键修复】：确保堆栈窗口默认显示第一页
    stackedWidget->setCurrentWidget(loginWidget);

    // 【关键修复】：去掉 alignment 参数，让 stackedWidget 填满 mainWidget
    // 之前是 mainLayout->setAlignment(stackedWidget, Qt::AlignCenter); 这句在 Windows 上会导致 stackedWidget 变为空
    mainLayout->addWidget(stackedWidget); 
    
    // ================= 信号连接 (保持不变) =================
    connect(loginButton, &QPushButton::clicked, this, &LoginWindow::handleLogin);
    connect(registerButton, &QPushButton::clicked, this, &LoginWindow::switchToRegister);
    connect(registerSubmitButton, &QPushButton::clicked, this, &LoginWindow::handleRegister);
    connect(backToLoginButton, &QPushButton::clicked, this, &LoginWindow::switchToLogin);
    connect(registerAvatarButton, &QPushButton::clicked, this, [=]() {
        QString filePath = QFileDialog::getOpenFileName(this, "选择头像", ".", "图像文件 (*.png *.jpg *.jpeg)");
        if (!filePath.isEmpty()) {
            avatarPath = filePath;
            QPixmap pixmap(filePath);
            QPixmap scaledPixmap = pixmap.scaled(avatarPreviewLabel->size(), Qt::KeepAspectRatio, Qt::SmoothTransformation);
            avatarPreviewLabel->setPixmap(scaledPixmap);
            avatarPreviewLabel->setAlignment(Qt::AlignCenter);
        }
    });

    connect(chatClient, &ChatClient::userAvatarReceived, this, [=](const QString &avatarPath) {
        qDebug() << "Received user avatar path:" << avatarPath;
    });
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

    // 解析服务器地址
    QString serverAddress = serverLineEdit->text().trimmed();
    QString host = "127.0.0.1";
    quint16 port = 6000;
    
    if (!serverAddress.isEmpty()) {
        QStringList parts = serverAddress.split(":");
        if (parts.size() == 2) {
            host = parts[0].trimmed();
            port = parts[1].toUShort();
        }
    }
    
    // 先连接服务器，再登录
    if (!chatClient->connectToServer(host, port)) {
        QMessageBox::warning(this, "连接失败", "无法连接到服务器，请检查服务器地址是否正确");
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

    // 解析服务器地址
    QString serverAddress = serverLineEdit->text().trimmed();
    QString host = "127.0.0.1";
    quint16 port = 6000;
    
    if (!serverAddress.isEmpty()) {
        QStringList parts = serverAddress.split(":");
        if (parts.size() == 2) {
            host = parts[0].trimmed();
            port = parts[1].toUShort();
        }
    }
    
    // 先连接服务器，再注册
    if (!chatClient->connectToServer(host, port)) {
        QMessageBox::warning(this, "连接失败", "无法连接到服务器，请检查服务器地址是否正确");
        return;
    }

    // 调用客户端注册方法，传入头像路径
    chatClient->registerUser(name, password, avatarPath);
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
        
        // 延迟发出登录成功信号，确保ChatClient的processMessage方法已经处理完登录响应
        // 这样ChatWindow创建时，currentUserAvatar已经被正确设置
        QTimer::singleShot(200, this, [=]() {
            // 检查头像数据是否已经被保存
            QString avatarData = chatClient->getCurrentUserAvatar();
            qDebug() << "[CRITICAL] Avatar data before emitting loginSuccess:" << avatarData.left(50) << (avatarData.length() > 50 ? "..." : "") << "length:" << avatarData.length();
            
            // 发出登录成功信号，传递用户ID和名称
            emit loginSuccess(userId, userName);
            
            // 注意：移除登录成功消息框，避免干扰窗口跳转
            qDebug() << "[CRITICAL] Login success signal emitted after delay, window switching should proceed";

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
