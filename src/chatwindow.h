#ifndef CHATWINDOW_H
#define CHATWINDOW_H

// 跨平台网络头文件处理 - 注意：先包含Windows网络头文件，再包含Qt头文件，避免byte类型歧义
#ifdef _WIN32
    #include <winsock2.h>
    #include <ws2tcpip.h>
    // 防止Windows头文件中的byte类型与Qt冲突
    #undef byte
#endif

#include <QMainWindow>
#include <QWidget>
#include <QTreeWidget>
#include <QTextEdit>
#include <QLineEdit>
#include <QPushButton>
#include <QSplitter>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QLabel>
#include <QTabWidget>
#include <QMap>
#include <QMessageBox>
#include <QDialog>
#include <QProgressDialog>
#include <QFileDialog>
#include <QFile>
#include <QScrollArea>
#include <QGridLayout>
#include <QListWidget>
#include <QScrollBar>
#include "chatclient.h"
#include "models/user.h"
#include "models/group.h"

// 未处理消息结构体
struct PendingMessage {
    int fromId;
    QString message;
    QString fromName;
    bool isGroup;
    int groupId;
    QString timestamp;
};

// 文件传输信息结构体
struct FileTransferInfo {
    QString filename;     // 文件名
    QString filePath;     // 文件完整路径
    qint64 filesize;      // 文件大小
    int senderId;         // 发送者ID
    int receiverId;       // 接收者ID
    bool isSending;       // 是否是发送方
    bool isCompleted;     // 是否已完成
};

class ChatWindow : public QMainWindow {
    Q_OBJECT

public:
    ChatWindow(int userId, const QString &userName, ChatClient *client = nullptr, QWidget *parent = nullptr);
    ~ChatWindow();

private:
    int userId;
    QString userName;
    
    // UI组件
    QSplitter *mainSplitter;
    QTreeWidget *contactTreeWidget;
    QTabWidget *chatTabWidget;
    QLabel *statusBarLabel;
    
    // 客户端实例
    ChatClient *chatClient;
    
    // 防止重复处理登录响应的标志
    bool loginHandled; // 添加此标志以防止重复处理登录响应
    
    // 标记是否正在处理登出，用于区分正常登出和意外断开连接
    bool isLoggingOut; // 用于防止登出时的冲突
    
    // 联系人数据
    QMap<int, User> friendMap;
    QMap<int, Group> groupMap;
    
    // 状态标志
    bool friendListLoaded; // 标记好友列表是否已加载
    bool offlineMessagesProcessed; // 标记离线消息是否已处理
    
    // 未处理消息队列（用于好友列表加载前的消息）
    QList<PendingMessage> pendingMessages;
    
    // 联系人树根节点
    QTreeWidgetItem *friendRoot;
    QTreeWidgetItem *groupRoot;
    
    // 添加好友和创建群组的对话框
    QDialog *addFriendDialog;
    QLineEdit *addFriendIdEdit;
    QDialog *createGroupDialog;
    QLineEdit *groupNameEdit;
    QLineEdit *groupDescEdit;
    QDialog *joinGroupDialog;
    QLineEdit *joinGroupIdEdit;
    
    // 聊天组件结构体
    typedef struct {
        QListWidget *chatListWidget; // 聊天记录显示区域
        QListWidget *memberListWidget; // 群组成员列表（仅群组聊天使用）
    } ChatComponents;

    // 聊天组件映射
    QMap<QWidget*, ChatComponents> chatComponents;
    
    // 输入框映射
    QMap<QWidget*, QLineEdit*> inputLineEdits;
    
    // 未读消息计数映射 (chatId_isGroup -> count)
    QMap<QString, int> unreadMessageCounts;
    
    // 表情包相关
    QMap<int, QByteArray> emojiList; // 存储用户的表情包，key为表情ID，value为图片数据
    bool isLoadingEmojis; // 标记是否正在加载表情包
    QDialog *currentEmojiDialog; // 当前显示的表情包对话框
    
    // 头像相关
    QLabel *avatarLabel; // 当前用户头像显示标签
    QDialog *changeAvatarDialog; // 修改头像对话框
    QPushButton *changeAvatarButton; // 修改头像按钮
    QString currentUserAvatarData; // 当前用户头像数据（Base64或Data URL）

    // 文件传输相关成员变量
    QMap<QString, QFile*> receivingFiles;    // 接收中的文件映射 (fileId -> QFile*)
    QMap<QString, qint64> receivedFilesSize; // 已接收的文件大小映射 (fileId -> size)
    QMap<QString, QProgressDialog*> fileProgressDialogs; // 文件传输进度对话框 (fileId -> QProgressDialog*)
    QMap<QString, FileTransferInfo> fileTransferInfo; // 文件传输信息 (fileId -> FileTransferInfo)
    
    // 发送文件相关辅助方法
    void sendFileContent(int toId, const QString &filename, const QString &fileId);
    void handleReceivedFile(const QString &fileId, const QString &filename, qint64 filesize);
    
    // 查找联系人方法
    QString getUserNameById(int userId);
    QString getGroupNameById(int groupId);
    
    // 创建聊天窗口的辅助方法
    void createChatWidget(int chatId, const QString &chatName, bool isGroup);
    
    // 辅助方法
    QString generateChatKey(int chatId, bool isGroup);
    void updateTabText(int chatId, bool isGroup, const QString &chatName);
    void addMessageToChatList(QListWidget *listWidget, bool isSender, const QString &message, const QString &avatarPath, const QString &timeStr);

public slots:
    // 连接相关槽函数
    void onConnected();
    void onDisconnected();
    
    // 登录相关槽函数
    void onLoginResponse(bool success, const QString &response);
    
    // 消息相关槽函数
    void onSendMessage();
    void onSendImage();
    void onSendEmoji();
    void onReceiveMessage(int fromId, const QString &message, const QString &fromName = "", bool isGroup = false, int groupId = -1, const QString &timestamp = "");
    void onReceiveGroupMessage(int groupId, int fromId, const QString &userName, const QString &message, const QString &timestamp = "");
    
    // 列表更新槽函数
    void onFriendListUpdated(const QList<User> &friends);
    void onGroupListUpdated(const QList<Group> &groups);
    void onFriendStateUpdated(qint64 userId, const QString &state);
    
    // 添加好友相关槽函数
    void onAddFriend();
    void onAddFriendConfirmed();
    void onAddFriendResponse(bool success, const QString &message);
    
    // 创建群组相关槽函数
    void onCreateGroup();
    void onCreateGroupConfirmed();
    void onCreateGroupResponse(bool success, const QString &message);
    
    // 加入群组相关槽函数
    void onJoinGroup();
    void onJoinGroupConfirmed();
    void onAddGroupResponse(bool success, const QString &message);
    
    // 文件传输相关槽函数
    void onSendFile();
    void onFileTransferRequestReceived(int fromId, const QString &filename, qint64 filesize, const QString &fileId);
    void onFileTransferAccepted(const QString &fileId, bool accept);
    void onFileTransferDataReceived(const QString &fileId, int chunkIndex, const QByteArray &data);
    void onFileTransferCompleteReceived(const QString &fileId, bool success);
    void onFileTransferError(const QString &fileId, int errorCode, const QString &errorMsg);
    
    // 其他槽函数
    void onContactSelected();
    void onLogout();
    void showContextMenu(const QPoint &pos);
    
    // 表情包相关槽函数
    void onEmojiListUpdated(const QList<QJsonObject> &emojis);
    
    // 显示表情包对话框
    void showEmojiDialog();

protected:
    void closeEvent(QCloseEvent *event) override;

signals:
    void logout();
};

#endif // CHATWINDOW_H