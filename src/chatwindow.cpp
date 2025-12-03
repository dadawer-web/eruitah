#include "chatwindow.h"
#include <QDebug>
#include <QDateTime>
#include <QInputDialog>
#include <QCloseEvent>
#include <QMenu>
#include <QAction>
#include <QMessageBox>
#include <QToolBar>
#include <QStatusBar>
#include <QTimer>
#include <QFileDialog>
#include <QFileInfo>
#include <QCoreApplication>
#include <QThread>

ChatWindow::ChatWindow(int userId, const QString &userName, ChatClient *client, QWidget *parent) : QMainWindow(parent), userId(userId), userName(userName), chatClient(client), loginHandled(false), friendListLoaded(false), offlineMessagesProcessed(false), isLoggingOut(false) {
    // 设置窗口标题
    setWindowTitle(QString("Qt Chat - %1").arg(userName));
    setObjectName("chatWindow");
    setMinimumSize(800, 600);

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
            "QMainWindow[objectName='chatWindow'] { background-color: #f5f5f5; }" 
            "QTreeWidget { background-color: white; border: none; border-right: 1px solid #eee; }" 
            "QTreeWidget::item { height: 40px; padding: 0 10px; border-radius: 6px; margin: 2px 8px; }" 
            "QTreeWidget::item:hover { background-color: #f0f0f0; }" 
            "QTreeWidget::item:selected { background-color: #e3f2fd; color: #1976d2; }" 
            "QTabWidget::pane { background-color: white; border: none; }" 
            "QTabBar::tab { background-color: #f5f5f5; border: none; border-bottom: 2px solid transparent; padding: 10px 20px; margin-right: 2px; border-radius: 8px 8px 0 0; font-weight: 500; }" 
            "QTabBar::tab:selected { background-color: white; border-bottom-color: #3498db; color: #3498db; }" 
            "QTextBrowser { background-color: #fafafa; border: none; padding: 10px; border-radius: 8px; }" 
            "QLineEdit { height: 40px; border: 1px solid #ddd; border-radius: 8px; padding: 0 12px; font-size: 14px; background-color: white; }" 
            "QLineEdit:focus { border-color: #3498db; }" 
            "QPushButton { height: 40px; border: none; border-radius: 8px; font-size: 14px; font-weight: 500; padding: 0 20px; }" 
            "QPushButton[class='primaryButton'] { background-color: #3498db; color: white; }" 
            "QPushButton[class='primaryButton']:hover { background-color: #2980b9; }" 
            "QPushButton[class='primaryButton']:pressed { background-color: #2471a3; }" 
            "QPushButton[class='secondaryButton'] { background-color: #ecf0f1; color: #333; border: 1px solid #ddd; }" 
            "QPushButton[class='secondaryButton']:hover { background-color: #d5dbdb; }" 
            "QPushButton[class='secondaryButton']:pressed { background-color: #bdc3c7; }" 
            "QSplitter::handle { background-color: #eee; width: 1px; }" 
            "QFrame[class='separator'] { background-color: #eee; height: 1px; margin: 10px 0; }";
        setStyleSheet(inlineStyle);
    }

    // 使用传入的ChatClient实例或创建新实例
    if (client) {
        chatClient = client;
        // 确保ChatClient不会被销毁
        chatClient->setParent(this);
    } else {
        chatClient = new ChatClient(this);
    }
    // 连接信号槽
    connect(chatClient, &ChatClient::connected, this, &ChatWindow::onConnected);
    connect(chatClient, &ChatClient::disconnected, this, &ChatWindow::onDisconnected);
    connect(chatClient, &ChatClient::messageReceived, this, &ChatWindow::onReceiveMessage);
    connect(chatClient, &ChatClient::groupMessageReceived, this, &ChatWindow::onReceiveGroupMessage);
    connect(chatClient, &ChatClient::friendListUpdated, this, &ChatWindow::onFriendListUpdated);
    connect(chatClient, &ChatClient::groupListUpdated, this, &ChatWindow::onGroupListUpdated);
    connect(chatClient, &ChatClient::addFriendResponse, this, &ChatWindow::onAddFriendResponse);
    connect(chatClient, &ChatClient::addGroupResponse, this, &ChatWindow::onAddGroupResponse);
    connect(chatClient, &ChatClient::createGroupResponse, this, &ChatWindow::onCreateGroupResponse);
    // 文件传输相关信号连接
    connect(chatClient, &ChatClient::fileTransferRequestReceived, this, &ChatWindow::onFileTransferRequestReceived);
    connect(chatClient, &ChatClient::fileTransferAccepted, this, &ChatWindow::onFileTransferAccepted);
    connect(chatClient, &ChatClient::fileTransferDataReceived, this, &ChatWindow::onFileTransferDataReceived);
    connect(chatClient, &ChatClient::fileTransferCompleteReceived, this, &ChatWindow::onFileTransferCompleteReceived);
    connect(chatClient, &ChatClient::fileTransferError, this, &ChatWindow::onFileTransferError);

    // 初始化左侧联系人树
    contactTreeWidget = new QTreeWidget;
    contactTreeWidget->setHeaderLabel("联系人");
    contactTreeWidget->setContextMenuPolicy(Qt::CustomContextMenu);
    connect(contactTreeWidget, &QTreeWidget::itemClicked, this, &ChatWindow::onContactSelected);
    connect(contactTreeWidget, &QTreeWidget::customContextMenuRequested, this, &ChatWindow::showContextMenu);

    // 创建好友和群组节点
    friendRoot = new QTreeWidgetItem(contactTreeWidget);
    friendRoot->setText(0, "好友");
    friendRoot->setExpanded(true);
    
    groupRoot = new QTreeWidgetItem(contactTreeWidget);
    groupRoot->setText(0, "群组");
    groupRoot->setExpanded(true);

    // 初始化聊天标签页
    chatTabWidget = new QTabWidget;
    chatTabWidget->setTabsClosable(true);
    connect(chatTabWidget, &QTabWidget::tabCloseRequested, chatTabWidget, &QTabWidget::removeTab);

    // 创建主分割器
    mainSplitter = new QSplitter(Qt::Horizontal);
    mainSplitter->addWidget(contactTreeWidget);
    mainSplitter->addWidget(chatTabWidget);
    mainSplitter->setSizes({250, 550});
    mainSplitter->setHandleWidth(1);

    // 设置状态栏
    statusBarLabel = new QLabel(QString("已登录: %1").arg(userName));
    statusBar()->addWidget(statusBarLabel);

    // 创建工具栏
    QToolBar *toolBar = addToolBar("工具栏");
    toolBar->setMovable(false);
    toolBar->setFloatable(false);
    
    QAction *addFriendAction = toolBar->addAction(QIcon(), "添加好友");
    QAction *createGroupAction = toolBar->addAction(QIcon(), "创建群组");
    QAction *joinGroupAction = toolBar->addAction(QIcon(), "加入群组");
    toolBar->addSeparator();
    QAction *sendFileAction = toolBar->addAction(QIcon(), "发送文件");
    toolBar->addSeparator();
    QAction *logoutAction = toolBar->addAction(QIcon(), "注销");

    connect(addFriendAction, &QAction::triggered, this, &ChatWindow::onAddFriend);
    connect(createGroupAction, &QAction::triggered, this, &ChatWindow::onCreateGroup);
    connect(joinGroupAction, &QAction::triggered, this, &ChatWindow::onJoinGroup);
    connect(sendFileAction, &QAction::triggered, this, &ChatWindow::onSendFile);
    connect(logoutAction, &QAction::triggered, this, &ChatWindow::onLogout);

    setCentralWidget(mainSplitter);
    
    // 列表请求移至登录成功后执行，确保在正确的时机获取数据
    qDebug() << "ChatWindow initialized for userId:" << userId;

    // 初始化添加好友对话框
    addFriendDialog = new QDialog(this);
    addFriendDialog->setWindowTitle("添加好友");
    addFriendDialog->setFixedSize(320, 180);
    
    QVBoxLayout *addFriendLayout = new QVBoxLayout;
    addFriendLayout->setContentsMargins(20, 20, 20, 20);
    addFriendLayout->setSpacing(15);
    
    QLabel *addFriendTitle = new QLabel("添加好友");
    QFont font = addFriendTitle->font();
    font.setPointSize(16);
    font.setBold(true);
    addFriendTitle->setFont(font);
    addFriendTitle->setAlignment(Qt::AlignCenter);
    
    addFriendLayout->addWidget(addFriendTitle);
    addFriendLayout->addWidget(new QLabel("好友ID:"));
    addFriendIdEdit = new QLineEdit;
    addFriendLayout->addWidget(addFriendIdEdit);
    
    QHBoxLayout *addFriendButtonLayout = new QHBoxLayout;
    addFriendButtonLayout->setSpacing(10);
    
    QPushButton *addFriendOkButton = new QPushButton("确定");
    addFriendOkButton->setProperty("class", "primaryButton");
    
    QPushButton *addFriendCancelButton = new QPushButton("取消");
    addFriendCancelButton->setProperty("class", "secondaryButton");
    
    addFriendButtonLayout->addWidget(addFriendOkButton);
    addFriendButtonLayout->addWidget(addFriendCancelButton);
    addFriendLayout->addLayout(addFriendButtonLayout);
    
    addFriendDialog->setLayout(addFriendLayout);
    connect(addFriendOkButton, &QPushButton::clicked, this, &ChatWindow::onAddFriendConfirmed);
    connect(addFriendCancelButton, &QPushButton::clicked, addFriendDialog, &QDialog::close);
    
    // 处理存储的离线消息 - 移到构造函数末尾，确保所有UI元素都已初始化
    chatClient->processStoredOfflineMessages();

    // 初始化创建群组对话框
    createGroupDialog = new QDialog(this);
    createGroupDialog->setWindowTitle("创建群组");
    createGroupDialog->setFixedSize(350, 220);
    
    QVBoxLayout *createGroupLayout = new QVBoxLayout;
    createGroupLayout->setContentsMargins(20, 20, 20, 20);
    createGroupLayout->setSpacing(15);
    
    QLabel *createGroupTitle = new QLabel("创建群组");
    createGroupTitle->setFont(font);
    createGroupTitle->setAlignment(Qt::AlignCenter);
    
    createGroupLayout->addWidget(createGroupTitle);
    createGroupLayout->addWidget(new QLabel("群组名称:"));
    groupNameEdit = new QLineEdit;
    createGroupLayout->addWidget(groupNameEdit);
    createGroupLayout->addWidget(new QLabel("群组描述:"));
    groupDescEdit = new QLineEdit;
    createGroupLayout->addWidget(groupDescEdit);
    
    QHBoxLayout *createGroupButtonLayout = new QHBoxLayout;
    createGroupButtonLayout->setSpacing(10);
    
    QPushButton *createGroupOkButton = new QPushButton("确定");
    createGroupOkButton->setProperty("class", "primaryButton");
    
    QPushButton *createGroupCancelButton = new QPushButton("取消");
    createGroupCancelButton->setProperty("class", "secondaryButton");
    
    createGroupButtonLayout->addWidget(createGroupOkButton);
    createGroupButtonLayout->addWidget(createGroupCancelButton);
    createGroupLayout->addLayout(createGroupButtonLayout);
    
    createGroupDialog->setLayout(createGroupLayout);
    connect(createGroupOkButton, &QPushButton::clicked, this, &ChatWindow::onCreateGroupConfirmed);
    connect(createGroupCancelButton, &QPushButton::clicked, createGroupDialog, &QDialog::close);

    // 初始化加入群组对话框
    joinGroupDialog = new QDialog(this);
    joinGroupDialog->setWindowTitle("加入群组");
    joinGroupDialog->setFixedSize(320, 180);
    
    QVBoxLayout *joinGroupLayout = new QVBoxLayout;
    joinGroupLayout->setContentsMargins(20, 20, 20, 20);
    joinGroupLayout->setSpacing(15);
    
    QLabel *joinGroupTitle = new QLabel("加入群组");
    joinGroupTitle->setFont(font);
    joinGroupTitle->setAlignment(Qt::AlignCenter);
    
    joinGroupLayout->addWidget(joinGroupTitle);
    joinGroupLayout->addWidget(new QLabel("群组ID:"));
    joinGroupIdEdit = new QLineEdit;
    joinGroupLayout->addWidget(joinGroupIdEdit);
    
    QHBoxLayout *joinGroupButtonLayout = new QHBoxLayout;
    joinGroupButtonLayout->setSpacing(10);
    
    QPushButton *joinGroupOkButton = new QPushButton("确定");
    joinGroupOkButton->setProperty("class", "primaryButton");
    
    QPushButton *joinGroupCancelButton = new QPushButton("取消");
    joinGroupCancelButton->setProperty("class", "secondaryButton");
    
    joinGroupButtonLayout->addWidget(joinGroupOkButton);
    joinGroupButtonLayout->addWidget(joinGroupCancelButton);
    joinGroupLayout->addLayout(joinGroupButtonLayout);
    joinGroupDialog->setLayout(joinGroupLayout);
    connect(joinGroupOkButton, &QPushButton::clicked, this, &ChatWindow::onJoinGroupConfirmed);
    connect(joinGroupCancelButton, &QPushButton::clicked, joinGroupDialog, &QDialog::close);

    // 立即请求好友列表和群组列表，确保UI能够正确显示
    qDebug() << "[CRITICAL] ChatWindow constructor: Directly requesting friend and group lists for userId:" << userId;
    // 首先发送好友列表请求
    chatClient->requestFriendList(userId);
    // 增加延迟至500ms，确保消息不会在网络传输中合并
    QTimer::singleShot(500, this, [this, userId]() {
        chatClient->requestGroupList(userId);
    });
    
}

ChatWindow::~ChatWindow() {
}

void ChatWindow::onSendMessage() {
    // 获取当前聊天窗口的相关组件
    QWidget *currentWidget = chatTabWidget->currentWidget();
    if (!currentWidget) return;

    // 从映射中获取聊天组件
    if (!chatComponents.contains(currentWidget) || !inputLineEdits.contains(currentWidget)) return;
    
    ChatComponents components = chatComponents[currentWidget];
    QTextEdit *chatEdit = components.chatEdit;
    QLineEdit *inputEdit = inputLineEdits[currentWidget];
    
    QString message = inputEdit->text().trimmed();
    if (message.isEmpty()) return;

    // 获取标签页的用户数据（好友ID或群组ID）
    int chatId = currentWidget->property("chatId").toInt();
    bool isGroup = currentWidget->property("isGroup").toBool();

    // 显示自己发送的消息
    QString timeStr = QDateTime::currentDateTime().toString("hh:mm:ss");
    chatEdit->append(QString("我 [%1]: %2").arg(timeStr).arg(message));
    inputEdit->clear();

    // 发送消息
    if (isGroup) {
        chatClient->sendGroupMessage(chatId, message);
    } else {
        chatClient->sendMessage(chatId, message);
    }
}

void ChatWindow::createChatWidget(int chatId, const QString &chatName, bool isGroup) {
    // 检查是否已经打开了该聊天窗口
    for (int i = 0; i < chatTabWidget->count(); ++i) {
        if (chatTabWidget->widget(i)->property("chatId").toInt() == chatId &&
            chatTabWidget->widget(i)->property("isGroup").toBool() == isGroup) {
            // 直接删除现有窗口，重新创建
            chatTabWidget->removeTab(i);
            break;
        }
    }

    // 创建新的聊天窗口
    QWidget *chatWidget = new QWidget;
    chatWidget->setStyleSheet("background-color: white;");
    
    // 使用QVBoxLayout作为主布局
    QVBoxLayout *mainLayout = new QVBoxLayout;
    mainLayout->setContentsMargins(0, 0, 0, 0);
    mainLayout->setSpacing(0);
    
    // 聊天记录区域
    QTextEdit *chatEdit = new QTextEdit;
    chatEdit->setReadOnly(true);
    chatEdit->setMinimumHeight(400);
    chatEdit->setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOn);
    chatEdit->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    chatEdit->setStyleSheet("border: none; background-color: #fafafa; padding: 10px;");
    mainLayout->addWidget(chatEdit);
    
    // 分隔线
    QFrame *separator = new QFrame;
    separator->setFrameShape(QFrame::HLine);
    separator->setFrameShadow(QFrame::Sunken);
    separator->setStyleSheet("background-color: #eee;");
    mainLayout->addWidget(separator);
    
    // 输入区域
    QWidget *inputWidget = new QWidget;
    inputWidget->setStyleSheet("background-color: white;");
    QVBoxLayout *inputLayout = new QVBoxLayout;
    inputLayout->setContentsMargins(10, 10, 10, 10);
    inputLayout->setSpacing(10);
    
    // 输入框
    QLineEdit *inputEdit = new QLineEdit;
    inputEdit->setMinimumHeight(40);
    inputEdit->setStyleSheet("border: 1px solid #ddd; border-radius: 8px; padding: 0 12px;");
    inputLayout->addWidget(inputEdit);
    
    // 按钮区域
    QHBoxLayout *buttonLayout = new QHBoxLayout;
    buttonLayout->setContentsMargins(0, 0, 0, 0);
    buttonLayout->setSpacing(10);
    buttonLayout->setAlignment(Qt::AlignRight);
    
    // 创建发送按钮
    QPushButton *sendButton = new QPushButton("发送");
    sendButton->setMinimumHeight(40);
    sendButton->setFixedWidth(100);
    sendButton->setStyleSheet(
        "QPushButton { background-color: #3498db; color: white; border: none; border-radius: 8px; font-size: 14px; font-weight: 500; }"
        "QPushButton:hover { background-color: #2980b9; }"
        "QPushButton:pressed { background-color: #2471a3; }"
    );
    
    // 创建发送文件按钮
    QPushButton *sendFileButton = new QPushButton("发送文件");
    sendFileButton->setMinimumHeight(40);
    sendFileButton->setFixedWidth(100);
    sendFileButton->setStyleSheet(
        "QPushButton { background-color: #ecf0f1; color: #333; border: 1px solid #ddd; border-radius: 8px; font-size: 14px; font-weight: 500; }"
        "QPushButton:hover { background-color: #d5dbdb; }"
        "QPushButton:pressed { background-color: #bdc3c7; }"
    );
    
    // 添加按钮到布局
    buttonLayout->addWidget(sendButton);
    buttonLayout->addWidget(sendFileButton);
    
    // 将按钮布局添加到输入布局
    inputLayout->addLayout(buttonLayout);
    
    // 将输入布局添加到输入部件
    inputWidget->setLayout(inputLayout);
    
    // 将输入部件添加到主布局
    mainLayout->addWidget(inputWidget);
    
    // 将主布局设置到聊天部件
    chatWidget->setLayout(mainLayout);
    
    // 设置属性
    chatWidget->setProperty("chatId", chatId);
    chatWidget->setProperty("isGroup", isGroup);
    
    // 存储聊天组件的映射关系
    chatComponents[chatWidget] = {chatEdit, nullptr};
    
    // 连接信号
    connect(sendButton, &QPushButton::clicked, this, &ChatWindow::onSendMessage);
    connect(inputEdit, &QLineEdit::returnPressed, this, &ChatWindow::onSendMessage);
    connect(sendFileButton, &QPushButton::clicked, this, &ChatWindow::onSendFile);
    
    // 存储输入框的映射关系
    inputLineEdits[chatWidget] = inputEdit;
    
    // 添加到标签页
    chatTabWidget->addTab(chatWidget, chatName);
    chatTabWidget->setCurrentWidget(chatWidget);
}

void ChatWindow::onContactSelected() {
    QTreeWidgetItem *item = contactTreeWidget->currentItem();
    if (!item || !item->parent()) return; // 忽略根节点

    bool isGroup = (item->parent()->text(0) == "群组");
    int chatId = item->data(0, Qt::UserRole).toInt();
    QString chatName = item->text(0);

    // 首先修复所有现有窗口
    for (int i = 0; i < chatTabWidget->count(); ++i) {
        QWidget *existingWidget = chatTabWidget->widget(i);
        
        // 检查现有窗口是否有发送按钮，如果没有则修复
        QVBoxLayout *chatLayout = qobject_cast<QVBoxLayout*>(existingWidget->layout());
        if (chatLayout) {
            QWidget *inputWidget = chatLayout->itemAt(2)->widget();
            if (inputWidget) {
                QHBoxLayout *inputLayout = qobject_cast<QHBoxLayout*>(inputWidget->layout());
                if (inputLayout) {
                    // 检查是否有发送按钮
                    bool hasSendButton = false;
                    bool hasSendFileButton = false;
                    
                    // 遍历输入布局中的所有控件
                    for (int j = 0; j < inputLayout->count(); ++j) {
                        QWidget *widget = inputLayout->itemAt(j)->widget();
                        if (QPushButton *button = qobject_cast<QPushButton*>(widget)) {
                            if (button->text() == "发送") {
                                hasSendButton = true;
                            } else if (button->text() == "发送文件") {
                                hasSendFileButton = true;
                            }
                        }
                    }
                    
                    // 如果缺少发送按钮，添加它
                    if (!hasSendButton) {
                        QPushButton *sendButton = new QPushButton("发送");
                        sendButton->setProperty("class", "primaryButton");
                        sendButton->setFixedWidth(80);
                        
                        // 在发送文件按钮之前插入发送按钮
                        if (hasSendFileButton) {
                            // 找到发送文件按钮的位置
                            for (int j = 0; j < inputLayout->count(); ++j) {
                                QWidget *widget = inputLayout->itemAt(j)->widget();
                                if (QPushButton *button = qobject_cast<QPushButton*>(widget)) {
                                    if (button->text() == "发送文件") {
                                        inputLayout->insertWidget(j, sendButton);
                                        break;
                                    }
                                }
                            }
                        } else {
                            // 如果没有发送文件按钮，添加到末尾
                            inputLayout->addWidget(sendButton);
                        }
                        
                        // 连接信号
                        connect(sendButton, &QPushButton::clicked, this, &ChatWindow::onSendMessage);
                    }
                }
            }
        }
    }
    
    // 然后创建或切换到目标聊天窗口
    createChatWidget(chatId, chatName, isGroup);
}

void ChatWindow::onAddFriend() {
    addFriendDialog->show();
}

void ChatWindow::onAddFriendConfirmed() {
    QString idStr = addFriendIdEdit->text();
    bool ok;
    int friendId = idStr.toInt(&ok);
    
    if (!ok || friendId <= 0) {
        QMessageBox::warning(this, "警告", "请输入有效的好友ID");
        return;
    }
    
    chatClient->addFriend(userId, friendId);
    addFriendDialog->close();
    addFriendIdEdit->clear();
}

void ChatWindow::onCreateGroup() {
    createGroupDialog->show();
}

void ChatWindow::onCreateGroupConfirmed() {
    QString groupName = groupNameEdit->text();
    QString groupDesc = groupDescEdit->text();
    
    if (groupName.isEmpty()) {
        QMessageBox::warning(this, "警告", "请输入群组名称");
        return;
    }
    
    chatClient->createGroup(userId, groupName, groupDesc);
    createGroupDialog->close();
    groupNameEdit->clear();
    groupDescEdit->clear();
}

void ChatWindow::onJoinGroup() {
    joinGroupDialog->show();
}

void ChatWindow::onJoinGroupConfirmed() {
    QString idStr = joinGroupIdEdit->text();
    bool ok;
    int groupId = idStr.toInt(&ok);
    
    if (!ok || groupId <= 0) {
        QMessageBox::warning(this, "警告", "请输入有效的群组ID");
        return;
    }
    
    chatClient->joinGroup(userId, groupId);
    joinGroupDialog->close();
    joinGroupIdEdit->clear();
}

void ChatWindow::onReceiveMessage(int fromId, const QString &message, const QString &fromName, bool isGroup, int groupId, const QString &timestamp) {
    QString chatName;
    int chatId;
    
    if (isGroup) {
        chatId = groupId;
        if (groupMap.contains(groupId)) {
            chatName = QString::fromStdString(groupMap[groupId].getName());
        }
    } else {
        chatId = fromId;
        // 使用信号中提供的发送者名称，否则从friendMap获取，最后使用默认名称
        if (!fromName.isEmpty()) {
            chatName = fromName;
        } else if (friendMap.contains(fromId)) {
            chatName = QString::fromStdString(friendMap[fromId].getName());
        } else {
            chatName = QString("用户 %1").arg(fromId);
        }
    }

    // 查找或创建对应的聊天窗口
    QTextEdit *chatEdit = nullptr;
    QWidget *chatWidget = nullptr;
    
    // 查找是否已存在聊天窗口
    for (int i = 0; i < chatTabWidget->count(); ++i) {
        if (chatTabWidget->widget(i)->property("chatId").toInt() == chatId &&
            chatTabWidget->widget(i)->property("isGroup").toBool() == isGroup) {
            chatWidget = chatTabWidget->widget(i);
            chatEdit = qobject_cast<QTextEdit*>(chatWidget->layout()->itemAt(0)->widget());
            break;
        }
    }

    // 如果聊天窗口不存在，创建一个新的
    if (!chatEdit) {
        createChatWidget(chatId, chatName, isGroup);
        
        // 查找刚创建的聊天窗口
        for (int i = 0; i < chatTabWidget->count(); ++i) {
            if (chatTabWidget->widget(i)->property("chatId").toInt() == chatId &&
                chatTabWidget->widget(i)->property("isGroup").toBool() == isGroup) {
                chatWidget = chatTabWidget->widget(i);
                chatEdit = qobject_cast<QTextEdit*>(chatWidget->layout()->itemAt(0)->widget());
                break;
            }
        }
    }

    // 显示接收到的消息
    if (chatEdit) {
        QString timeStr;
        // 如果有时间戳，使用它，否则使用当前时间
        qDebug() << "[DEBUG] Received timestamp:" << timestamp << "isEmpty:" << timestamp.isEmpty();
        if (!timestamp.isEmpty()) {
            // 将服务器返回的UTC时间转换为本地时间显示
            qDebug() << "[DEBUG] Original timestamp:" << timestamp;
            
            // 解析服务器返回的UTC时间（格式: YYYYMMDD HH:MM:SS.mmmmmm）
            // 先尝试使用完整格式解析
            QString timeOnly = timestamp;
            QString dateOnly = timestamp;
            int spacePos = timestamp.indexOf(' ');
            if (spacePos != -1) {
                dateOnly = timestamp.left(spacePos);
                timeOnly = timestamp.mid(spacePos + 1);
            }
            
            // 去掉毫秒部分
            int dotPos = timeOnly.indexOf('.');
            if (dotPos != -1) {
                timeOnly = timeOnly.left(dotPos);
            }
            
            // 拼接成新的时间字符串（YYYYMMDD HH:MM:SS）
            QString datetimeStr = dateOnly + " " + timeOnly;
            
            // 使用简化格式解析
            QDateTime utcDateTime = QDateTime::fromString(datetimeStr, "yyyyMMdd HH:mm:ss");
            
            qDebug() << "[DEBUG] Original timestamp:" << timestamp;
            qDebug() << "[DEBUG] Date only:" << dateOnly;
            qDebug() << "[DEBUG] Time only:" << timeOnly;
            qDebug() << "[DEBUG] DateTime string:" << datetimeStr;
            qDebug() << "[DEBUG] Parsed datetime:" << utcDateTime << "isValid:" << utcDateTime.isValid();
            
            if (utcDateTime.isValid()) {
                // 设置为UTC时区
                utcDateTime.setTimeSpec(Qt::UTC);
                
                // 转换为本地时间
                QDateTime localDateTime = utcDateTime.toLocalTime();
                
                // 提取时间部分（HH:MM:SS）
                timeStr = localDateTime.toString("hh:mm:ss");
                
                qDebug() << "[DEBUG] UTC time:" << utcDateTime;
                qDebug() << "[DEBUG] Local time:" << localDateTime;
                qDebug() << "[DEBUG] Using local timestamp:" << timeStr;
            } else {
                // 如果解析失败，直接使用提取的时间部分
                timeStr = timeOnly;
                qDebug() << "[DEBUG] Failed to parse timestamp, using extracted time:" << timeStr;
            }
        } else {
            timeStr = QDateTime::currentDateTime().toString("hh:mm:ss");
            qDebug() << "[DEBUG] No timestamp, using current time:" << timeStr;
        }
        
        chatEdit->append(chatName + " [" + timeStr + "]: " + message);
        // 确保聊天窗口可见
        for (int i = 0; i < chatTabWidget->count(); ++i) {
            if (chatTabWidget->widget(i) == chatWidget) {
                chatTabWidget->setCurrentIndex(i);
                break;
            }
        }
    }
}

void ChatWindow::onReceiveGroupMessage(int groupId, int fromId, const QString &userName, const QString &message, const QString &timestamp) {
    QString groupName;
    if (groupMap.contains(groupId)) {
        groupName = QString::fromStdString(groupMap[groupId].getName());
    } else {
        groupName = QString("群组 %1").arg(groupId);
    }

    // 查找或创建对应的群聊窗口
    QTextEdit *chatEdit = nullptr;
    QWidget *chatWidget = nullptr;
    
    // 查找是否已存在聊天窗口
    for (int i = 0; i < chatTabWidget->count(); ++i) {
        if (chatTabWidget->widget(i)->property("chatId").toInt() == groupId &&
            chatTabWidget->widget(i)->property("isGroup").toBool() == true) {
            chatWidget = chatTabWidget->widget(i);
            chatEdit = qobject_cast<QTextEdit*>(chatWidget->layout()->itemAt(0)->widget());
            break;
        }
    }

    // 如果聊天窗口不存在，创建一个新的
    if (!chatEdit) {
        createChatWidget(groupId, groupName, true);
        
        // 查找刚创建的聊天窗口
        for (int i = 0; i < chatTabWidget->count(); ++i) {
            if (chatTabWidget->widget(i)->property("chatId").toInt() == groupId &&
                chatTabWidget->widget(i)->property("isGroup").toBool() == true) {
                chatWidget = chatTabWidget->widget(i);
                chatEdit = qobject_cast<QTextEdit*>(chatWidget->layout()->itemAt(0)->widget());
                break;
            }
        }
    }

    // 显示群消息
    if (chatEdit) {
        QString timeStr;
        // 如果有时间戳，使用它，否则使用当前时间
        qDebug() << "[DEBUG] Group message received timestamp:" << timestamp << "isEmpty:" << timestamp.isEmpty();
        if (!timestamp.isEmpty()) {
            // 将服务器返回的UTC时间转换为本地时间显示
            qDebug() << "[DEBUG] Group message original timestamp:" << timestamp;
            
            // 解析服务器返回的UTC时间（格式: YYYYMMDD HH:MM:SS.mmmmmm）
            // 先尝试使用完整格式解析
            QString timeOnly = timestamp;
            QString dateOnly = timestamp;
            int spacePos = timestamp.indexOf(' ');
            if (spacePos != -1) {
                dateOnly = timestamp.left(spacePos);
                timeOnly = timestamp.mid(spacePos + 1);
            }
            
            // 去掉毫秒部分
            int dotPos = timeOnly.indexOf('.');
            if (dotPos != -1) {
                timeOnly = timeOnly.left(dotPos);
            }
            
            // 拼接成新的时间字符串（YYYYMMDD HH:MM:SS）
            QString datetimeStr = dateOnly + " " + timeOnly;
            
            // 使用简化格式解析
            QDateTime utcDateTime = QDateTime::fromString(datetimeStr, "yyyyMMdd HH:mm:ss");
            
            qDebug() << "[DEBUG] Group message original timestamp:" << timestamp;
            qDebug() << "[DEBUG] Group message date only:" << dateOnly;
            qDebug() << "[DEBUG] Group message time only:" << timeOnly;
            qDebug() << "[DEBUG] Group message datetime string:" << datetimeStr;
            qDebug() << "[DEBUG] Group message parsed datetime:" << utcDateTime << "isValid:" << utcDateTime.isValid();
            
            if (utcDateTime.isValid()) {
                // 设置为UTC时区
                utcDateTime.setTimeSpec(Qt::UTC);
                
                // 转换为本地时间
                QDateTime localDateTime = utcDateTime.toLocalTime();
                
                // 提取时间部分（HH:MM:SS）
                timeStr = localDateTime.toString("hh:mm:ss");
                
                qDebug() << "[DEBUG] Group message UTC time:" << utcDateTime;
                qDebug() << "[DEBUG] Group message local time:" << localDateTime;
                qDebug() << "[DEBUG] Group message using local timestamp:" << timeStr;
            } else {
                // 如果解析失败，直接使用提取的时间部分
                timeStr = timeOnly;
                qDebug() << "[DEBUG] Group message failed to parse timestamp, using extracted time:" << timeStr;
            }
        } else {
            timeStr = QDateTime::currentDateTime().toString("hh:mm:ss");
            qDebug() << "[DEBUG] Group message no timestamp, using current time:" << timeStr;
        }
        
        chatEdit->append("[" + groupName + "] " + userName + " [" + timeStr + "]: " + message);
        // 确保聊天窗口可见
        for (int i = 0; i < chatTabWidget->count(); ++i) {
            if (chatTabWidget->widget(i) == chatWidget) {
                chatTabWidget->setCurrentIndex(i);
                break;
            }
        }
    }
}

void ChatWindow::onFriendListUpdated(const QList<User> &friends) {
    qDebug() << "[CRITICAL] Received friend list update, count:" << friends.size();
    
    // 确保contactTreeWidget已初始化
    if (!contactTreeWidget) {
        qDebug() << "[ERROR] contactTreeWidget is null";
        return;
    }
    
    // 打印收到的每个好友信息
    for (const User &user : friends) {
        qDebug() << "[CRITICAL] Friend - ID:" << user.getId() << "Name:" << QString::fromStdString(user.getName());
    }
    
    // 确保friendRoot有效，如果无效则尝试查找或创建
    if (!friendRoot) {
        qDebug() << "[ERROR] friendRoot is null, attempting to find or create";
        // 尝试从contactTreeWidget中查找好友根节点
        for (int i = 0; i < contactTreeWidget->topLevelItemCount(); ++i) {
            QTreeWidgetItem *item = contactTreeWidget->topLevelItem(i);
            if (item->text(0) == "好友") {
                friendRoot = item;
                break;
            }
        }
        
        // 如果仍然没有找到，创建一个新的
        if (!friendRoot) {
            qDebug() << "[DEBUG] Creating new friend root item";
            friendRoot = new QTreeWidgetItem(contactTreeWidget);
            friendRoot->setText(0, "好友");
            contactTreeWidget->addTopLevelItem(friendRoot);
        }
    }
    
    // 清空好友列表
    friendRoot->takeChildren();

    // 更新好友数据和列表
    friendMap.clear();
    for (const User &user : friends) {
        friendMap[user.getId()] = user;
        QTreeWidgetItem *item = new QTreeWidgetItem(friendRoot);
        QString friendName = QString::fromStdString(user.getName());
        item->setText(0, friendName + " (" + QString::number(user.getId()) + ")");
        item->setData(0, Qt::UserRole, user.getId());
        
        // 尝试获取并设置在线状态，避免方法不存在的错误
        try {
            QString stateText = QString::fromStdString(user.getState());
            item->setText(1, stateText);
            qDebug() << "[CRITICAL] Added friend with state:" << friendName << "State:" << stateText;
        } catch (...) {
            // 如果getState()方法不存在，忽略状态设置
            qDebug() << "[CRITICAL] Added friend (no state available):" << friendName;
        }
        
        qDebug() << "[CRITICAL] Added friend to UI list:" << friendName;
    }
    
    // 展开好友节点
    friendRoot->setExpanded(true);
    
    // 刷新UI
    contactTreeWidget->update();
    contactTreeWidget->repaint();
    
    // 标记好友列表已加载
    friendListLoaded = true;
    contactTreeWidget->repaint();
    qDebug() << "[CRITICAL] Friend list UI updated, expanded and repainted";
}

void ChatWindow::onGroupListUpdated(const QList<Group> &groups) {
    qDebug() << "[CRITICAL] Received group list update, count:" << groups.size();
    
    // 确保contactTreeWidget已初始化
    if (!contactTreeWidget) {
        qDebug() << "[ERROR] contactTreeWidget is null";
        return;
    }
    
    // 打印收到的每个群组信息
    for (const Group &group : groups) {
        qDebug() << "[CRITICAL] Group - ID:" << group.getId() << "Name:" << QString::fromStdString(group.getName())
                 << "Desc:" << QString::fromStdString(group.getDesc());
    }
    
    // 确保groupRoot有效，如果无效则尝试查找或创建
    if (!groupRoot) {
        qDebug() << "[ERROR] groupRoot is null, attempting to find or create";
        // 尝试从contactTreeWidget中查找群组根节点
        for (int i = 0; i < contactTreeWidget->topLevelItemCount(); ++i) {
            QTreeWidgetItem *item = contactTreeWidget->topLevelItem(i);
            if (item->text(0) == "群组") {
                groupRoot = item;
                break;
            }
        }
        
        // 如果仍然没有找到，创建一个新的
        if (!groupRoot) {
            qDebug() << "[DEBUG] Creating new group root item";
            groupRoot = new QTreeWidgetItem(contactTreeWidget);
            groupRoot->setText(0, "群组");
            contactTreeWidget->addTopLevelItem(groupRoot);
        }
    }
    
    // 清空群组列表
    groupRoot->takeChildren();

    // 更新群组数据和列表
    groupMap.clear();
    for (const Group &group : groups) {
        groupMap[group.getId()] = group;
        QTreeWidgetItem *item = new QTreeWidgetItem(groupRoot);
        QString groupName = QString::fromStdString(group.getName());
        item->setText(0, groupName + " (" + QString::number(group.getId()) + ")");
        item->setData(0, Qt::UserRole, group.getId());
        
        // 不尝试获取群组成员数，避免const和方法不存在的错误
        item->setText(1, "群组成员");
        qDebug() << "[CRITICAL] Added group:" << groupName << "(group member count skipped for compatibility)";
        
        qDebug() << "[CRITICAL] Added group to UI list:" << groupName;
    }
    
    // 展开群组节点
    groupRoot->setExpanded(true);
    
    // 刷新UI
    contactTreeWidget->update();
    contactTreeWidget->repaint();
    qDebug() << "[CRITICAL] Group list UI updated, expanded and repainted";
}

void ChatWindow::onAddFriendResponse(bool success, const QString &message) {
    if (success) {
        QMessageBox::information(this, "成功", "添加好友成功");
        // 重新获取好友列表
        chatClient->requestFriendList(userId);
    } else {
        QMessageBox::warning(this, "失败", message);
    }
}

void ChatWindow::onAddGroupResponse(bool success, const QString &message) {
    if (success) {
        QMessageBox::information(this, "成功", "加入群组成功！");
        // 重新请求群组列表
        chatClient->requestGroupList(userId);
    } else {
        QMessageBox::warning(this, "失败", message);
    }
}

void ChatWindow::onCreateGroupResponse(bool success, const QString &message) {
    if (success) {
        QMessageBox::information(this, "成功", "创建群组成功！");
        // 重新请求群组列表
        chatClient->requestGroupList(userId);
    } else {
        QMessageBox::warning(this, "失败", message);
    }
}

void ChatWindow::onLoginResponse(bool success, const QString &response) {
    // 首先检查是否已经处理过登录响应，防止重复处理
    if (loginHandled) {
        qDebug() << "[CRITICAL] ChatWindow::onLoginResponse - Already handled login response, ignoring duplicate call";
        return;
    }
    
    // 设置标志为已处理，防止后续重复处理
    loginHandled = true;
    
    qDebug() << "[DEBUG] ChatWindow received login response:" << success;
    qDebug() << "[DEBUG] Response message:" << response;
    
    if (success) {
        // 登录成功后立即请求好友列表和群组列表
        qDebug() << "[DEBUG] Login successful, user ID:" << userId << "Name:" << userName;
        
        // 直接发送请求，不需要定时器延迟，确保及时获取数据
        qDebug() << "[DEBUG] Requesting friend list for user ID:" << userId;
        chatClient->requestFriendList(userId);
        
        qDebug() << "[DEBUG] Requesting group list for user ID:" << userId;
        chatClient->requestGroupList(userId);
        
        // 添加3秒后再次请求，确保即使初始请求失败也能获取到数据
        QTimer::singleShot(3000, this, [this]() {
            qDebug() << "[DEBUG] Retry requesting friend list for user ID:" << userId;
            chatClient->requestFriendList(userId);
        });
        
    }
}

void ChatWindow::onConnected() {
    qDebug() << "ChatWindow connected to server";
    // 可以在这里添加连接成功的处理逻辑
}

void ChatWindow::onDisconnected() {
    qDebug() << "ChatWindow disconnected from server";
    
    // If we're actively logging out, don't show the message box or close the window
    // The logout signal will handle the cleanup and transition to login page
    if (isLoggingOut) {
        qDebug() << "ChatWindow: Disconnection during logout, skipping message box and close";
        return;
    }
    
    // For unexpected disconnections, show message and close
    QMessageBox::warning(this, "连接断开", "与服务器的连接已断开，请重新登录");
    close();
}

void ChatWindow::onLogout() {
    // Mark as logging out to prevent onDisconnected from interfering
    isLoggingOut = true;
    
    // Send logout message to server
    chatClient->logout(userId);
    
    // Disconnect all signals from chatClient to prevent race conditions
    disconnect(chatClient, nullptr, this, nullptr);
    
    // Close the chat window
    this->close();
    
    // Emit logout signal immediately, without delay
    emit logout();
}

void ChatWindow::showContextMenu(const QPoint &pos) {
    QTreeWidgetItem *item = contactTreeWidget->itemAt(pos);
    if (!item) return;

    QMenu *menu = new QMenu(this);
    
    if (item->parent() && item->parent()->text(0) == "好友") {
        QAction *sendMessageAction = menu->addAction("发送消息");
        QAction *sendFileAction = menu->addAction("发送文件");
        connect(sendMessageAction, &QAction::triggered, this, &ChatWindow::onContactSelected);
        connect(sendFileAction, &QAction::triggered, this, [=]() {
            // 先选中该好友，然后触发发送文件
            contactTreeWidget->setCurrentItem(item);
            onSendFile();
        });
    }
    
    if (item->text(0) == "好友") {
        QAction *addFriendAction = menu->addAction("添加好友");
        connect(addFriendAction, &QAction::triggered, this, &ChatWindow::onAddFriend);
    }
    
    if (item->text(0) == "群组") {
        QAction *createGroupAction = menu->addAction("创建群组");
        QAction *joinGroupAction = menu->addAction("加入群组");
        connect(createGroupAction, &QAction::triggered, this, &ChatWindow::onCreateGroup);
        connect(joinGroupAction, &QAction::triggered, this, &ChatWindow::onJoinGroup);
    }
    
    menu->popup(contactTreeWidget->viewport()->mapToGlobal(pos));
}

void ChatWindow::closeEvent(QCloseEvent *event) {
    if (QMessageBox::question(this, "确认退出", "确定要退出吗？") == QMessageBox::Yes) {
        chatClient->logout(userId);
        // 清理文件传输相关资源
        for (auto it = receivingFiles.begin(); it != receivingFiles.end(); ++it) {
            if (it.value()) {
                it.value()->close();
                delete it.value();
            }
        }
        receivingFiles.clear();
        
        for (auto it = fileProgressDialogs.begin(); it != fileProgressDialogs.end(); ++it) {
            if (it.value()) {
                delete it.value();
            }
        }
        fileProgressDialogs.clear();
        
        event->accept();
    } else {
        event->ignore();
    }
}

// 发送文件
void ChatWindow::onSendFile() {
    // 检查当前是否有选中的好友
    QWidget *currentWidget = chatTabWidget->currentWidget();
    if (!currentWidget) {
        QMessageBox::warning(this, "警告", "请先选择一个好友进行聊天");
        return;
    }
    
    int chatId = currentWidget->property("chatId").toInt();
    bool isGroup = currentWidget->property("isGroup").toBool();
    
    if (isGroup) {
        QMessageBox::warning(this, "警告", "暂不支持向群组发送文件");
        return;
    }
    
    // 选择文件
    QString filename = QFileDialog::getOpenFileName(this, "选择要发送的文件");
    if (filename.isEmpty()) {
        return;
    }
    
    // 获取文件信息
    QFileInfo fileInfo(filename);
    qint64 filesize = fileInfo.size();
    
    // 显示发送确认对话框
    QString message = QString("确定要将文件 '%1' (%2 KB) 发送给好友吗？")
                      .arg(fileInfo.fileName())
                      .arg(filesize / 1024.0, 0, 'f', 1);
    
    if (QMessageBox::question(this, "确认发送", message) != QMessageBox::Yes) {
        return;
    }
    
    // 创建进度对话框
    QProgressDialog *progressDialog = new QProgressDialog(this);
    progressDialog->setWindowTitle("文件发送中");
    progressDialog->setLabelText(QString("正在发送 '%1'...").arg(fileInfo.fileName()));
    progressDialog->setRange(0, filesize);
    progressDialog->setModal(true);
    
    // 记录文件传输信息
    FileTransferInfo info;
    info.filename = fileInfo.fileName();
    info.filesize = filesize;
    info.senderId = userId;
    info.receiverId = chatId;
    info.isSending = true;
    info.isCompleted = false;
    
    // 生成fileId
    QString fileId = chatClient->generateFileId();
    fileTransferInfo[fileId] = info;
    fileProgressDialogs[fileId] = progressDialog;
    
    // 发送文件传输请求
    chatClient->sendFileRequest(userId, chatId, fileInfo.fileName(), filesize);
}

// 处理收到的文件传输请求
void ChatWindow::onFileTransferRequestReceived(int fromId, const QString &filename, qint64 filesize, const QString &fileId) {
    QString senderName = getUserNameById(fromId);
    
    // 显示接收确认对话框
    QString message = QString("好友 '%1' 想要发送文件 '%2' (%3 KB)，是否接收？")
                      .arg(senderName)
                      .arg(filename)
                      .arg(filesize / 1024.0, 0, 'f', 1);
    
    int result = QMessageBox::question(this, "接收文件", message, 
                                      QMessageBox::Yes | QMessageBox::No);
    
    if (result == QMessageBox::Yes) {
        // 选择保存位置
        QString savePath = QFileDialog::getSaveFileName(this, "保存文件", filename);
        if (savePath.isEmpty()) {
            chatClient->acceptFileTransfer(userId, fromId, fileId, false);
            return;
        }
        
        // 打开文件准备写入
        QFile *file = new QFile(savePath);
        if (!file->open(QIODevice::WriteOnly)) {
            QMessageBox::warning(this, "错误", "无法打开文件进行写入");
            chatClient->acceptFileTransfer(userId, fromId, fileId, false);
            delete file;
            return;
        }
        
        // 创建进度对话框
        QProgressDialog *progressDialog = new QProgressDialog(this);
        progressDialog->setWindowTitle("文件接收中");
        progressDialog->setLabelText(QString("正在接收 '%1'...").arg(filename));
        progressDialog->setRange(0, filesize);
        progressDialog->setModal(true);
        
        // 记录文件传输信息
        FileTransferInfo info;
        info.filename = filename;
        info.filesize = filesize;
        info.senderId = fromId;
        info.receiverId = userId;
        info.isSending = false;
        info.isCompleted = false;
        
        receivingFiles[fileId] = file;
        receivedFilesSize[fileId] = 0;
        fileTransferInfo[fileId] = info;
        fileProgressDialogs[fileId] = progressDialog;
        
        // 接受文件传输
        chatClient->acceptFileTransfer(userId, fromId, fileId, true);
    } else {
        // 拒绝文件传输
        chatClient->acceptFileTransfer(userId, fromId, fileId, false);
    }
}

// 处理文件传输接受或拒绝的响应
void ChatWindow::onFileTransferAccepted(const QString &fileId, bool accept) {
    if (!fileTransferInfo.contains(fileId)) {
        return;
    }
    
    FileTransferInfo &info = fileTransferInfo[fileId];
    
    if (info.isSending) {
        if (accept) {
            // 对方接受了文件，开始发送文件内容
            sendFileContent(info.receiverId, info.filename, fileId);
        } else {
            // 对方拒绝了文件
            QMessageBox::information(this, "文件发送", "对方拒绝接收文件");
            // 清理进度对话框
            if (fileProgressDialogs.contains(fileId)) {
                delete fileProgressDialogs[fileId];
                fileProgressDialogs.remove(fileId);
            }
            fileTransferInfo.remove(fileId);
        }
    }
}

// 处理接收到的文件数据
void ChatWindow::onFileTransferDataReceived(const QString &fileId, int chunkIndex, const QByteArray &data) {
    if (!receivingFiles.contains(fileId) || !fileTransferInfo.contains(fileId)) {
        return;
    }
    
    QFile *file = receivingFiles[fileId];
    FileTransferInfo &info = fileTransferInfo[fileId];
    
    // 写入数据到文件
    qint64 written = file->write(data);
    if (written < 0) {
        QMessageBox::warning(this, "错误", "文件写入失败");
        chatClient->sendFileTransferComplete(userId, info.senderId, fileId, false);
        // 清理资源
        file->close();
        delete file;
        receivingFiles.remove(fileId);
        if (fileProgressDialogs.contains(fileId)) {
            delete fileProgressDialogs[fileId];
            fileProgressDialogs.remove(fileId);
        }
        fileTransferInfo.remove(fileId);
        return;
    }
    
    // 更新已接收的文件大小
    receivedFilesSize[fileId] += written;
    
    // 更新进度条
    if (fileProgressDialogs.contains(fileId)) {
        fileProgressDialogs[fileId]->setValue(receivedFilesSize[fileId]);
    }
    
    // 检查是否接收完成
    if (receivedFilesSize[fileId] >= info.filesize) {
        // 完成文件传输
        file->close();
        delete file;
        receivingFiles.remove(fileId);
        receivedFilesSize.remove(fileId);
        
        if (fileProgressDialogs.contains(fileId)) {
            fileProgressDialogs[fileId]->close();
            delete fileProgressDialogs[fileId];
            fileProgressDialogs.remove(fileId);
        }
        
        info.isCompleted = true;
        fileTransferInfo[fileId] = info;
        
        QMessageBox::information(this, "成功", QString("文件 '%1' 接收完成").arg(info.filename));
        
        // 通知发送方已完成接收
        chatClient->sendFileTransferComplete(userId, info.senderId, fileId, true);
    }
}

// 处理文件传输完成的通知
void ChatWindow::onFileTransferCompleteReceived(const QString &fileId, bool success) {
    if (!fileTransferInfo.contains(fileId) || !fileProgressDialogs.contains(fileId)) {
        return;
    }
    
    FileTransferInfo &info = fileTransferInfo[fileId];
    
    if (info.isSending) {
        // 文件发送方
        fileProgressDialogs[fileId]->close();
        delete fileProgressDialogs[fileId];
        fileProgressDialogs.remove(fileId);
        
        if (success) {
            QMessageBox::information(this, "成功", QString("文件 '%1' 发送成功").arg(info.filename));
        } else {
            QMessageBox::warning(this, "失败", QString("文件 '%1' 发送失败").arg(info.filename));
        }
        
        info.isCompleted = true;
        fileTransferInfo.remove(fileId);
    }
}

// 处理文件传输错误
void ChatWindow::onFileTransferError(const QString &fileId, int errorCode, const QString &errorMsg) {
    if (fileProgressDialogs.contains(fileId)) {
        fileProgressDialogs[fileId]->close();
        delete fileProgressDialogs[fileId];
        fileProgressDialogs.remove(fileId);
    }
    
    if (receivingFiles.contains(fileId)) {
        receivingFiles[fileId]->close();
        delete receivingFiles[fileId];
        receivingFiles.remove(fileId);
        receivedFilesSize.remove(fileId);
    }
    
    if (fileTransferInfo.contains(fileId)) {
        fileTransferInfo.remove(fileId);
    }
    
    QMessageBox::warning(this, "传输错误", QString("文件传输失败: %1 (错误代码: %2)").arg(errorMsg).arg(errorCode));
}

// 发送文件内容
void ChatWindow::sendFileContent(int toId, const QString &filename, const QString &fileId) {
    // 获取文件完整路径（可能需要用户重新选择，因为我们只有文件名）
    QString filePath = QFileDialog::getOpenFileName(this, "选择文件", QDir::homePath() + "/" + filename, 
                                                 filename + ";;所有文件 (*)");
    
    if (filePath.isEmpty()) {
        chatClient->sendFileTransferComplete(userId, toId, fileId, false);
        QMessageBox::warning(this, "发送取消", "文件发送已取消");
        // 清理资源
        if (fileProgressDialogs.contains(fileId)) {
            delete fileProgressDialogs[fileId];
            fileProgressDialogs.remove(fileId);
        }
        fileTransferInfo.remove(fileId);
        return;
    }
    
    QFile file(filePath);
    if (!file.open(QIODevice::ReadOnly)) {
        QMessageBox::warning(this, "错误", "无法打开文件进行读取");
        chatClient->sendFileTransferComplete(userId, toId, fileId, false);
        // 清理资源
        if (fileProgressDialogs.contains(fileId)) {
            delete fileProgressDialogs[fileId];
            fileProgressDialogs.remove(fileId);
        }
        fileTransferInfo.remove(fileId);
        return;
    }
    
    // 分块发送文件内容，每块1024字节
    const int chunkSize = 1024;
    int chunkIndex = 0;
    qint64 totalRead = 0;
    
    while (!file.atEnd()) {
        QByteArray chunk = file.read(chunkSize);
        chatClient->sendFileData(userId, toId, fileId, chunkIndex, chunk);
        
        totalRead += chunk.size();
        chunkIndex++;
        
        // 更新进度条
        if (fileProgressDialogs.contains(fileId)) {
            fileProgressDialogs[fileId]->setValue(totalRead);
        }
        
        // 短暂延迟，避免发送过快
        QCoreApplication::processEvents();
        QThread::msleep(50);
    }
    
    file.close();
    
    // 发送完成通知
    chatClient->sendFileTransferComplete(userId, toId, fileId, true);
}

// 处理接收到的文件
void ChatWindow::handleReceivedFile(const QString &fileId, const QString &filename, qint64 filesize) {
    // 此方法已在onFileTransferRequestReceived中实现主要逻辑
    // 这里仅作为备用或扩展
}

// 根据用户ID获取用户名
QString ChatWindow::getUserNameById(int userId) {
    if (friendMap.contains(userId)) {
        return QString::fromStdString(friendMap[userId].getName());
    }
    return QString("用户%1").arg(userId);
}

// 根据群组ID获取群组名称
QString ChatWindow::getGroupNameById(int groupId) {
    if (groupMap.contains(groupId)) {
        return QString::fromStdString(groupMap[groupId].getName());
    }
    return QString("群组%1").arg(groupId);
}