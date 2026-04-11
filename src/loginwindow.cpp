#include "loginwindow.h"
#include <QDebug>
#include <QTimer>
#include <QCoreApplication>
#include <QFileDialog>
#include <QPixmap>
#include <QPainter>
#include <QPainterPath>
#include <QGraphicsDropShadowEffect>
#include <QMouseEvent>

// 跨平台网络头文件处理 - 注意：先包含Windows网络头文件，再包含Qt头文件，避免byte类型歧义
#ifdef _WIN32
    #include <winsock2.h>
    #include <ws2tcpip.h>
    // 防止Windows头文件中的byte类型与Qt冲突
    #undef byte
#endif

LoginWindow::LoginWindow(QWidget *parent) : QMainWindow(parent) {
    // 1. 无边框窗口设置
    setWindowFlags(Qt::FramelessWindowHint | Qt::WindowSystemMenuHint);
    setAttribute(Qt::WA_TranslucentBackground);
    setWindowTitle(QStringLiteral("Qt Chat - 登录"));
    setFixedSize(520, 620);
    setObjectName("loginWindow");

    // 2. 应用现代暗黑主题样式表
    setStyleSheet(R"(
        QMainWindow#loginWindow {
            background: transparent;
        }
        
        QWidget#centralWidget {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                        stop:0 #1A1A2E, stop:1 #16213E);
            border-radius: 16px;
        }
        
        QWidget#titleBar {
            background: transparent;
            min-height: 40px;
            max-height: 40px;
        }
        
        QPushButton#closeButton {
            background: transparent;
            border: none;
            color: #ffffff;
            font-size: 18px;
            font-weight: bold;
            min-width: 40px;
            min-height: 40px;
            border-radius: 20px;
        }
        
        QPushButton#closeButton:hover {
            background: rgba(255, 77, 77, 0.9);
        }
        
        QPushButton#minimizeButton {
            background: transparent;
            border: none;
            color: #ffffff;
            font-size: 18px;
            font-weight: bold;
            min-width: 40px;
            min-height: 40px;
            border-radius: 20px;
        }
        
        QPushButton#minimizeButton:hover {
            background: rgba(255, 255, 255, 0.1);
        }
        
        QWidget#loginCard {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 20px;
        }
        
        QLabel#titleLabel {
            color: #ffffff;
            font-size: 32px;
            font-weight: bold;
            background: transparent;
        }
        
        QLabel#subtitleLabel {
            color: rgba(255, 255, 255, 0.5);
            font-size: 13px;
            background: transparent;
        }
    )");

    // 3. 创建客户端 (传入 this 确保内存管理)
    chatClient = new ChatClient(this);
    connect(chatClient, &ChatClient::loginResponse, this, &LoginWindow::handleLoginResponse);
    connect(chatClient, &ChatClient::registerResponse, this, &LoginWindow::handleRegisterResponse);

    // 4. 创建中央容器
    QWidget *centralWidget = new QWidget(this);
    centralWidget->setObjectName("centralWidget");
    setCentralWidget(centralWidget);
    
    QVBoxLayout *mainLayout = new QVBoxLayout(centralWidget);
    mainLayout->setContentsMargins(0, 0, 0, 0);
    mainLayout->setSpacing(0);

    // 5. 创建自定义标题栏
    QWidget *titleBar = new QWidget(centralWidget);
    titleBar->setObjectName("titleBar");
    titleBar->setFixedHeight(40);
    
    QHBoxLayout *titleLayout = new QHBoxLayout(titleBar);
    titleLayout->setContentsMargins(16, 0, 8, 0);
    titleLayout->setSpacing(0);
    
    QLabel *appIcon = new QLabel(QStringLiteral("💬"), titleBar);
    appIcon->setStyleSheet("font-size: 20px; background: transparent; color: #00D2FF;");
    
    QLabel *appName = new QLabel(QStringLiteral("  Qt Chat"), titleBar);
    appName->setStyleSheet("color: rgba(255, 255, 255, 0.8); font-size: 13px; font-weight: 500; background: transparent;");
    
    titleLayout->addWidget(appIcon);
    titleLayout->addWidget(appName);
    titleLayout->addStretch();
    
    QPushButton *minimizeBtn = new QPushButton(QStringLiteral("—"), titleBar);
    minimizeBtn->setObjectName("minimizeButton");
    minimizeBtn->setCursor(Qt::PointingHandCursor);
    connect(minimizeBtn, &QPushButton::clicked, this, &LoginWindow::showMinimized);
    
    QPushButton *closeBtn = new QPushButton(QStringLiteral("×"), titleBar);
    closeBtn->setObjectName("closeButton");
    closeBtn->setCursor(Qt::PointingHandCursor);
    connect(closeBtn, &QPushButton::clicked, this, &LoginWindow::close);
    
    titleLayout->addWidget(minimizeBtn);
    titleLayout->addWidget(closeBtn);
    
    mainLayout->addWidget(titleBar);

    // 6. 创建内容区域
    QWidget *contentWidget = new QWidget(centralWidget);
    contentWidget->setStyleSheet("background: transparent;");
    QVBoxLayout *contentLayout = new QVBoxLayout(contentWidget);
    contentLayout->setContentsMargins(40, 20, 40, 40);
    contentLayout->setSpacing(0);

    // ================= 登录界面初始化 =================
    loginWidget = new QWidget(contentWidget);
    loginWidget->setObjectName("loginCard");
    loginWidget->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);

    // 登录标题
    loginTitleLabel = new QLabel(QStringLiteral("欢迎回来"), loginWidget);
    loginTitleLabel->setObjectName("titleLabel");
    loginTitleLabel->setAlignment(Qt::AlignCenter);
    
    QLabel *subtitleLabel = new QLabel(QStringLiteral("登录您的账号继续使用"), loginWidget);
    subtitleLabel->setObjectName("subtitleLabel");
    subtitleLabel->setAlignment(Qt::AlignCenter);

    // 服务器地址输入框 - Material Design风格
    serverLineEdit = new QtMaterialTextField(loginWidget);
    serverLineEdit->setLabel(QStringLiteral("服务器地址"));
    serverLineEdit->setText("127.0.0.1:6000");
    serverLineEdit->setMinimumHeight(50);
    serverLineEdit->setLabelColor(QColor("#8892b0"));
    serverLineEdit->setInkColor(QColor("#00D2FF"));
    serverLineEdit->setTextColor(QColor("#ffffff"));
    serverLineEdit->setInputLineColor(QColor("rgba(255, 255, 255, 0.1)"));

    // 用户ID输入框
    idLineEdit = new QtMaterialTextField(loginWidget);
    idLineEdit->setLabel(QStringLiteral("用户ID"));
    idLineEdit->setMinimumHeight(50);
    idLineEdit->setLabelColor(QColor("#8892b0"));
    idLineEdit->setInkColor(QColor("#00D2FF"));
    idLineEdit->setTextColor(QColor("#ffffff"));
    idLineEdit->setInputLineColor(QColor("rgba(255, 255, 255, 0.1)"));

    // 密码输入框
    passwordLineEdit = new QtMaterialTextField(loginWidget);
    passwordLineEdit->setLabel(QStringLiteral("密码"));
    passwordLineEdit->setEchoMode(QLineEdit::Password);
    passwordLineEdit->setMinimumHeight(50);
    passwordLineEdit->setLabelColor(QColor("#8892b0"));
    passwordLineEdit->setInkColor(QColor("#00D2FF"));
    passwordLineEdit->setTextColor(QColor("#ffffff"));
    passwordLineEdit->setInputLineColor(QColor("rgba(255, 255, 255, 0.1)"));

    // 登录按钮 - 主按钮，渐变背景
    loginButton = new QtMaterialRaisedButton(QStringLiteral("登  录"), loginWidget);
    loginButton->setMinimumHeight(48);
    loginButton->setCornerRadius(24);
    loginButton->setHaloVisible(true);
    loginButton->setOverlayStyle(Material::TintedOverlay);
    loginButton->setBackgroundColor(QColor("#00D2FF"));
    loginButton->setForegroundColor(QColor("#ffffff"));
    loginButton->setFontSize(15);

    // 注册按钮 - 次级按钮，幽灵设计
    registerButton = new QtMaterialFlatButton(QStringLiteral("还没有账号？立即注册"), loginWidget);
    registerButton->setMinimumHeight(48);
    registerButton->setCornerRadius(24);
    registerButton->setOverlayStyle(Material::TintedOverlay);
    registerButton->setForegroundColor(QColor("#00D2FF"));
    registerButton->setFontSize(14);

    // 登录界面布局
    QVBoxLayout *loginLayout = new QVBoxLayout(loginWidget);
    loginLayout->setContentsMargins(35, 40, 35, 40);
    loginLayout->setSpacing(0);
    
    loginLayout->addWidget(loginTitleLabel);
    loginLayout->addSpacing(8);
    loginLayout->addWidget(subtitleLabel);
    loginLayout->addSpacing(40);
    loginLayout->addWidget(serverLineEdit);
    loginLayout->addSpacing(25);
    loginLayout->addWidget(idLineEdit);
    loginLayout->addSpacing(25);
    loginLayout->addWidget(passwordLineEdit);
    loginLayout->addSpacing(40);
    loginLayout->addWidget(loginButton);
    loginLayout->addSpacing(15);
    loginLayout->addWidget(registerButton);
    loginLayout->addStretch();

    // ================= 注册界面初始化 =================
    registerWidget = new QWidget(contentWidget);
    registerWidget->setObjectName("loginCard");
    registerWidget->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);

    // 注册标题
    registerTitleLabel = new QLabel(QStringLiteral("创建账号"), registerWidget);
    registerTitleLabel->setObjectName("titleLabel");
    registerTitleLabel->setAlignment(Qt::AlignCenter);
    
    QLabel *regSubtitleLabel = new QLabel(QStringLiteral("注册新账号开始聊天"), registerWidget);
    regSubtitleLabel->setObjectName("subtitleLabel");
    regSubtitleLabel->setAlignment(Qt::AlignCenter);

    // 用户名输入框 - Material Design风格
    registerNameLineEdit = new QtMaterialTextField(registerWidget);
    registerNameLineEdit->setLabel(QStringLiteral("用户名"));
    registerNameLineEdit->setMinimumHeight(50);
    registerNameLineEdit->setLabelColor(QColor("#8892b0"));
    registerNameLineEdit->setInkColor(QColor("#00D2FF"));
    registerNameLineEdit->setTextColor(QColor("#ffffff"));
    registerNameLineEdit->setInputLineColor(QColor("rgba(255, 255, 255, 0.1)"));

    // 密码输入框
    registerPasswordLineEdit = new QtMaterialTextField(registerWidget);
    registerPasswordLineEdit->setLabel(QStringLiteral("密码"));
    registerPasswordLineEdit->setEchoMode(QLineEdit::Password);
    registerPasswordLineEdit->setMinimumHeight(50);
    registerPasswordLineEdit->setLabelColor(QColor("#8892b0"));
    registerPasswordLineEdit->setInkColor(QColor("#00D2FF"));
    registerPasswordLineEdit->setTextColor(QColor("#ffffff"));
    registerPasswordLineEdit->setInputLineColor(QColor("rgba(255, 255, 255, 0.1)"));

    // 头像标签和选择区域
    registerAvatarLabel = new QLabel(QStringLiteral("头像"), registerWidget);
    registerAvatarLabel->setStyleSheet(
        "color: #8892b0; "
        "font-size: 14px; "
        "font-weight: 500; "
        "background: transparent;"
    );

    // 头像区域 - 现代化布局
    QHBoxLayout *avatarLayout = new QHBoxLayout;
    avatarLayout->setSpacing(15);

    registerAvatarButton = new QtMaterialFlatButton(QStringLiteral("选择头像"), registerWidget);
    registerAvatarButton->setMinimumHeight(40);
    registerAvatarButton->setCornerRadius(20);
    registerAvatarButton->setOverlayStyle(Material::TintedOverlay);
    registerAvatarButton->setForegroundColor(QColor("#00D2FF"));

    avatarPreviewLabel = new QLabel(registerWidget);
    avatarPreviewLabel->setFixedSize(60, 60);
    avatarPreviewLabel->setStyleSheet(
        "border: 2px dashed rgba(255, 255, 255, 0.2); "
        "border-radius: 30px; "
        "background-color: rgba(255, 255, 255, 0.05);"
    );
    avatarPreviewLabel->setAlignment(Qt::AlignCenter);

    avatarLayout->addWidget(registerAvatarButton);
    avatarLayout->addWidget(avatarPreviewLabel);
    avatarLayout->addStretch();

    // 注册提交按钮 - 主按钮
    registerSubmitButton = new QtMaterialRaisedButton(QStringLiteral("注  册"), registerWidget);
    registerSubmitButton->setMinimumHeight(48);
    registerSubmitButton->setCornerRadius(24);
    registerSubmitButton->setHaloVisible(true);
    registerSubmitButton->setOverlayStyle(Material::TintedOverlay);
    registerSubmitButton->setBackgroundColor(QColor("#00D2FF"));
    registerSubmitButton->setForegroundColor(QColor("#ffffff"));
    registerSubmitButton->setFontSize(15);

    // 返回登录按钮 - 次级按钮
    backToLoginButton = new QtMaterialFlatButton(QStringLiteral("已有账号？立即登录"), registerWidget);
    backToLoginButton->setMinimumHeight(48);
    backToLoginButton->setCornerRadius(24);
    backToLoginButton->setOverlayStyle(Material::TintedOverlay);
    backToLoginButton->setForegroundColor(QColor("#00D2FF"));
    backToLoginButton->setFontSize(14);

    QVBoxLayout *registerLayout = new QVBoxLayout(registerWidget);
    registerLayout->setContentsMargins(35, 40, 35, 40);
    registerLayout->setSpacing(0);
    
    registerLayout->addWidget(registerTitleLabel);
    registerLayout->addSpacing(8);
    registerLayout->addWidget(regSubtitleLabel);
    registerLayout->addSpacing(40);
    registerLayout->addWidget(registerNameLineEdit);
    registerLayout->addSpacing(25);
    registerLayout->addWidget(registerPasswordLineEdit);
    registerLayout->addSpacing(25);
    registerLayout->addWidget(registerAvatarLabel);
    registerLayout->addSpacing(10);
    registerLayout->addLayout(avatarLayout);
    registerLayout->addSpacing(40);
    registerLayout->addWidget(registerSubmitButton);
    registerLayout->addSpacing(15);
    registerLayout->addWidget(backToLoginButton);
    registerLayout->addStretch();

    // ================= 堆栈窗口组装 =================
    stackedWidget = new QStackedWidget(contentWidget);
    stackedWidget->addWidget(loginWidget);
    stackedWidget->addWidget(registerWidget);
    stackedWidget->setCurrentWidget(loginWidget);
    
    contentLayout->addWidget(stackedWidget);
    mainLayout->addWidget(contentWidget); 
    
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

// ================= 窗口拖动支持 =================
void LoginWindow::mousePressEvent(QMouseEvent *event) {
    if (event->button() == Qt::LeftButton) {
        m_dragging = true;
        m_dragPosition = event->globalPos() - this->pos();
        event->accept();
    }
}

void LoginWindow::mouseMoveEvent(QMouseEvent *event) {
    if (m_dragging && (event->buttons() & Qt::LeftButton)) {
        this->move(event->globalPos() - m_dragPosition);
        event->accept();
    }
}

void LoginWindow::mouseReleaseEvent(QMouseEvent *event) {
    if (event->button() == Qt::LeftButton) {
        m_dragging = false;
        event->accept();
    }
}
