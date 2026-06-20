#include "mainwindow.h"
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QGridLayout>
#include <QMessageBox>
#include <QDateTime>
#include <QCoreApplication>
#include <QDesktopServices>
#include <QUrl>
#include <QFile>
#include <QTextStream>
#include "chatwindow.h"

MainWindow::MainWindow(QWidget *parent) : QMainWindow(parent) {
    server = nullptr;
    serverThread = nullptr;
    serverRunning = false;
    loginWindow = nullptr;

    initUI();
    setWindowTitle("QtChat 主程序");
    resize(600, 400);

    // 创建桌面宠物
    desktopPet = new DesktopPetWidget(this);
    desktopPet->show();
    desktopPet->startSupervising();
}

MainWindow::~MainWindow() {
    stopServer();
    if (loginWindow) {
        delete loginWindow;
    }
}

void MainWindow::initUI() {
    centralWidget = new QWidget(this);
    setCentralWidget(centralWidget);

    mainLayout = new QVBoxLayout(centralWidget);
    mainLayout->setContentsMargins(10, 10, 10, 10);
    mainLayout->setSpacing(10);

    // 端口设置
    QHBoxLayout *portLayout = new QHBoxLayout();
    portLayout->setContentsMargins(0, 0, 0, 0);
    portLayout->setSpacing(10);
    portLabel = new QLabel("端口:", this);
    portEdit = new QLineEdit(this);
    portEdit->setText("8000");
    portLayout->addWidget(portLabel);
    portLayout->addWidget(portEdit);

    // 按钮布局
    buttonLayout = new QHBoxLayout();
    buttonLayout->setContentsMargins(0, 0, 0, 0);
    buttonLayout->setSpacing(10);
    startServerButton = new QPushButton("启动服务器", this);
    stopServerButton = new QPushButton("停止服务器", this);
    startClientButton = new QPushButton("启动客户端", this);
    codingAgentButton = new QPushButton("💻 编程 Agent", this);

    stopServerButton->setEnabled(false);

    codingAgentButton->setStyleSheet(
        "QPushButton {"
        "  background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #007acc, stop:1 #0098ff);"
        "  border: none;"
        "  color: white;"
        "  font-size: 13px;"
        "  padding: 6px 12px;"
        "  border-radius: 4px;"
        "  font-weight: bold;"
        "}"
        "QPushButton:hover {"
        "  background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #005a9e, stop:1 #0078d4);"
        "}"
        "QPushButton:pressed {"
        "  background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #004578, stop:1 #0066b3);"
        "}"
    );

    buttonLayout->addWidget(startServerButton);
    buttonLayout->addWidget(stopServerButton);
    buttonLayout->addWidget(startClientButton);
    buttonLayout->addWidget(codingAgentButton);

    // 日志显示
    logTextEdit = new QTextEdit(this);
    logTextEdit->setReadOnly(true);

    mainLayout->addLayout(portLayout);
    mainLayout->addLayout(buttonLayout);
    mainLayout->addWidget(logTextEdit);

    // 连接信号槽
    connect(startServerButton, &QPushButton::clicked, this, &MainWindow::startServer);
    connect(stopServerButton, &QPushButton::clicked, this, &MainWindow::stopServer);
    connect(startClientButton, &QPushButton::clicked, this, &MainWindow::startClient);
    connect(codingAgentButton, &QPushButton::clicked, this, &MainWindow::onOpenCodingAgent);

    addLog("欢迎使用 QtChat 聊天系统");
}

void MainWindow::startServer() {
    quint16 port = portEdit->text().toUShort();

    if (serverRunning) {
        QMessageBox::warning(this, "警告", "服务器已经在运行中");
        return;
    }

    server = new ChatServer();
    serverThread = new QThread();
    server->moveToThread(serverThread);

    // 连接信号槽
    connect(serverThread, &QThread::started, [=]() {
        bool success = server->startServer(port);
        onServerStarted(success);
    });
    connect(serverThread, &QThread::finished, server, &QObject::deleteLater);
    connect(serverThread, &QThread::finished, serverThread, &QObject::deleteLater);

    serverThread->start();

    startServerButton->setEnabled(false);
    stopServerButton->setEnabled(true);
    portEdit->setEnabled(false);

    addLog(QString("正在启动服务器，端口: %1").arg(port));
}

void MainWindow::stopServer() {
    if (!serverRunning) {
        return;
    }

    if (serverThread && serverThread->isRunning()) {
        server->stopServer();
        onServerStopped();
        serverThread->quit();
        serverThread->wait();
    }

    serverRunning = false;
    startServerButton->setEnabled(true);
    stopServerButton->setEnabled(false);
    portEdit->setEnabled(true);

    addLog("服务器已停止");
}

void MainWindow::startClient() {
    // 写入日志文件，记录客户端启动
    QString logFilePath = QCoreApplication::applicationDirPath() + "/login_debug.log";
    QFile logFile(logFilePath);
    if (logFile.open(QIODevice::Append | QIODevice::Text)) {
        QTextStream out(&logFile);
        out << "[" << QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss") << "] " 
            << "MainWindow::startClient() called" << Qt::endl;
        logFile.close();
    }

    if (!loginWindow) {
        loginWindow = new LoginWindow();

        // 写入日志文件，记录LoginWindow创建
            QString logFilePath = QCoreApplication::applicationDirPath() + "/login_debug.log";
            QFile logFile(logFilePath);
            if (logFile.open(QIODevice::Append | QIODevice::Text)) {
                QTextStream out(&logFile);
                out << "[" << QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss") << "] " 
                    << "MainWindow::startClient(): created new LoginWindow at:" << (void*)loginWindow << Qt::endl;
                logFile.close();
            }

            // 连接登录成功信号到槽函数
            bool connectResult = connect(loginWindow, &LoginWindow::loginSuccess, this, &MainWindow::handleLoginSuccess);

            // 写入日志文件，记录信号槽连接结果
            logFilePath = QCoreApplication::applicationDirPath() + "/login_debug.log";
            logFile.setFileName(logFilePath);
            if (logFile.open(QIODevice::Append | QIODevice::Text)) {
                QTextStream out(&logFile);
                out << "[" << QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss") << "] " 
                    << "MainWindow::startClient(): connect signal-slot result:" << (connectResult ? "SUCCESS" : "FAILED") << Qt::endl;
                logFile.close();
            }

        // 直接在程序中添加日志输出
        addLog("信号槽连接: " + QString(connectResult ? "成功" : "失败"));
    }

    loginWindow->show();

    addLog("客户端已启动");
}

void MainWindow::onServerStarted(bool success) {
    if (success) {
        serverRunning = true;
        addLog("服务器启动成功");
    } else {
        addLog("服务器启动失败");
        startServerButton->setEnabled(true);
        stopServerButton->setEnabled(false);
        portEdit->setEnabled(true);
    }
}

void MainWindow::onClientConnected() {
    addLog("客户端连接成功");
}

void MainWindow::onServerStopped() {
    // 实现服务器停止的处理逻辑
    addLog("服务器已停止信号处理");
}

void MainWindow::handleLoginSuccess(int userId, const QString &userName) {
    // 保存当前登录的 userId
    m_userId = userId;

    // 桌宠设置用户 ID（事件总线已由 ChatWindow 初始化）
    if (desktopPet) {
        desktopPet->setUserId(QString::number(userId));
    }

    // 初始化全局事件总线
    GlobalEventBus::instance().init(QString::number(userId));

    // 将调试信息写入文件，便于在无图形界面环境下诊断
    QString logFilePath = QCoreApplication::applicationDirPath() + "/login_debug.log";
    QFile logFile(logFilePath);
    if (logFile.open(QIODevice::Append | QIODevice::Text)) {
        QTextStream out(&logFile);
        out << "[" << QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss") << "] " 
            << "handleLoginSuccess called with userId:" << userId << " userName:" << userName << Qt::endl;
        logFile.close();
    }

    // 获取chatClient
    ChatClient *client = nullptr;
    if (loginWindow) {
        client = loginWindow->getChatClient();

        // 写入日志
        if (logFile.open(QIODevice::Append | QIODevice::Text)) {
            QTextStream out(&logFile);
            out << "[" << QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss") << "] " 
                  << "loginWindow is valid" << Qt::endl;
            out << "[" << QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss") << "] " 
                  << "Got chatClient from loginWindow:" << (client ? "valid" : "NULL") << Qt::endl;
            logFile.close();
        }
    } else {
        // 写入日志
        if (logFile.open(QIODevice::Append | QIODevice::Text)) {
            QTextStream out(&logFile);
            out << "[" << QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss") << "] " 
                  << "ERROR: loginWindow is NULL" << Qt::endl;
            logFile.close();
        }
    }

    // 隐藏登录窗口
    if (loginWindow) {
        loginWindow->hide();
    }

    // 创建并显示聊天窗口（只创建一次）
    ChatWindow *chatWindow = new ChatWindow(userId, userName, client, this);

    // 写入日志
    if (logFile.open(QIODevice::Append | QIODevice::Text)) {
        QTextStream out(&logFile);
        out << "[" << QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss") << "] " 
              << "Created chatWindow at:" << (void*)chatWindow << Qt::endl;

        chatWindow->show();

        out << "[" << QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss") << "] " 
              << "Called chatWindow->show()" << Qt::endl;
        out << "[" << QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss") << "] " 
              << "User" << userName << "(ID:" << userId << ") logged in successfully, chat window opened" << Qt::endl;
        logFile.close();
    } else {
        // 如果无法写入日志，至少确保聊天窗口显示
        chatWindow->show();
    }

    addLog(QString("用户 %1 (ID: %2) 登录成功，已打开聊天窗口").arg(userName).arg(userId));
}

void MainWindow::onOpenCodingAgent() {
    QString hostEnv = qEnvironmentVariable("ERUITAH_SANDBOX_HOST", "");
    QString url;
    if (!hostEnv.isEmpty()) {
        url = QString("http://%1/ide?userId=%2").arg(hostEnv).arg(m_userId);
    } else {
        url = QString("http://127.0.0.1:8001/ide?userId=%1").arg(m_userId);
    }

    bool success = QDesktopServices::openUrl(QUrl(url));
    if (!success) {
        qDebug() << "Failed to open browser for URL:" << url;
        QMessageBox::warning(this, "打开失败", "无法打开系统浏览器，请手动访问:\n" + url);
    } else {
        addLog("已通过浏览器打开 Eruitah 编程 Agent: " + url);
    }
}

void MainWindow::addLog(const QString &log) {
    QString timestamp = QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss");
    logTextEdit->append(QString("[%1] %2").arg(timestamp).arg(log));
}
