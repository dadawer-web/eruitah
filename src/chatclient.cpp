// 跨平台网络头文件处理 - 注意：先包含Windows网络头文件，再包含Qt头文件，避免byte类型歧义
#ifdef _WIN32
    #include <winsock2.h>
    #include <ws2tcpip.h>
    // 防止Windows头文件中的byte类型与Qt冲突
    #undef byte
#else
    #include <arpa/inet.h>  // 用于ntohl函数
#endif

#include "chatclient.h"
#include "public.h"
#include <QByteArray>
#include <QDataStream>
#include <QDebug>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QTimer>
#include <QThread>
#include <QRandomGenerator>
#include <QFile>
#include <QIODevice>
#include <QFileInfo>
#include <string>



// ChatClient类实现 - 客户端核心通信模块
// 设计思路：采用事件驱动架构，基于Qt的信号槽机制实现异步网络通信
// 主要职责：管理与服务器的连接、消息收发、用户认证和文件传输
ChatClient::ChatClient(QObject *parent) : QObject(parent) {
    socket = new QTcpSocket(this);
    isConnected = false;
    currentUserId = 0;
    currentUserAvatar = "";
    
    // 连接信号和槽 - 实现异步事件处理模式
    // 设计亮点：使用lambda表达式实现简洁的事件处理，提高代码可读性
    qDebug() << "ChatClient: Setting up signal connections";
    connect(socket, &QTcpSocket::connected, this, [=]() {
        qDebug() << "ChatClient: Connected signal emitted";
        isConnected = true;
        emit connectionStateChanged(true);
        qDebug() << "ChatClient: Connection state updated to true, socket state:" << socket->state();
    });
    
    connect(socket, &QTcpSocket::disconnected, this, [=]() {
        qDebug() << "ChatClient: Disconnected signal emitted";
        isConnected = false;
        emit connectionStateChanged(false);
    });
    
    connect(socket, &QTcpSocket::readyRead, this, &ChatClient::onReadyRead);
    
    connect(socket, &QTcpSocket::errorOccurred, this, [=](QAbstractSocket::SocketError socketError) {
        qDebug() << "ChatClient: Socket error:" << socketError << socket->errorString();
        isConnected = false;
        emit connectionStateChanged(false);
    });
    
    // 连接到服务器 - 默认连接到本地，实际公网运行时会通过connectToServer方法重新连接
    qDebug() << "ChatClient: Initializing socket, will connect to server later";
    isConnected = false;
    qDebug() << "ChatClient: Socket initialized, waiting for explicit connectToServer call";
    
    qDebug() << "ChatClient: Signal connections set up successfully";
    
    // 连接成功后等待用户手动登录
    qDebug() << "ChatClient: 等待用户手动登录...";
}

// 析构函数 - 实现RAII原则，确保资源正确释放
// 设计亮点：优雅关闭网络连接，避免资源泄露
ChatClient::~ChatClient() {
    // 安全断开连接，处理不同连接状态
    if (socket->state() == QTcpSocket::ConnectedState || socket->state() == QTcpSocket::ConnectingState) {
        socket->disconnectFromHost();
        if (socket->state() != QTcpSocket::UnconnectedState) {
            socket->waitForDisconnected(1000);
        }
    }
}

// 连接服务器函数 - 提供可配置的服务器连接功能
// 线程安全设计：使用QMutexLocker确保多线程环境下的安全访问
// 健壮性保障：处理各种边缘情况，如已有连接存在、连接失败等
bool ChatClient::connectToServer(const QString &host, quint16 port) {
    QMutexLocker locker(&mutex);  // 线程安全锁，确保并发访问安全
    
    qDebug() << "ChatClient: Attempting to connect to server at" << host << ":" << port;
    
    // 避免重复连接，先断开现有连接
    if (socket->isOpen()) {
        qDebug() << "ChatClient: Socket already open, disconnecting first";
        socket->disconnectFromHost();
        // 修复：在调用waitForDisconnected前检查socket状态
        if (socket->state() != QAbstractSocket::UnconnectedState) {
            if (!socket->waitForDisconnected(1000)) {
                qDebug() << "ChatClient: Force closing socket";
                socket->abort();
            }
        } else {
            qDebug() << "ChatClient: Socket already in UnconnectedState, skipping waitForDisconnected";
        }
    }
    
    isConnected = false;
    socket->connectToHost(host, port);
    bool connected = socket->waitForConnected(5000);
    
    if (connected) {
        qDebug() << "ChatClient: Successfully connected to server";
        isConnected = true;
        emit connectionStateChanged(true);
        qDebug() << "ChatClient: Connection established, socket state:" << socket->state() << "connected:" << socket->isOpen();
    } else {
        qDebug() << "ChatClient: Failed to connect to server, error:" << socket->errorString();
        qDebug() << "ChatClient: Socket state after connection attempt:" << socket->state();
    }
    
    return connected;
}

// 登录功能 - 用户身份认证
// 设计思路：封装用户凭证，通过消息ID标识为登录请求
void ChatClient::login(qint64 userId, const QString &password) {
    qDebug() << "[CRITICAL] login called with userId:" << userId << "password:" << password;
    this->currentUserId = userId; // 保存当前用户ID - 状态管理设计
    // 清空当前用户头像数据，确保每次登录都能获取最新头像
    this->currentUserAvatar = "";
    QJsonObject message;
    message["msgid"] = MsgType::LOGIN_MSG;
    message["id"] = userId;
    message["password"] = password;
    sendJsonMessage(message);
    qDebug() << "[CRITICAL] Login request sent successfully";
}

// 注册功能 - 创建新用户账户
// 设计思路：封装用户信息，通过消息ID标识为注册请求
void ChatClient::registerUser(const QString &userName, const QString &password, const QString &avatarPath) {
    QJsonObject message;
    message["msgid"] = MsgType::REG_MSG;
    message["name"] = userName;
    message["password"] = password;
    
    // 如果提供了头像路径，添加头像数据
    if (!avatarPath.isEmpty()) {
        QFile file(avatarPath);
        if (file.open(QIODevice::ReadOnly)) {
            QByteArray fileData = file.readAll();
            QString base64Data = fileData.toBase64();
            // 跨平台兼容的文件名提取
            message["avatarName"] = QFileInfo(avatarPath).fileName();
            message["avatarData"] = base64Data;
            file.close();
        }
    }
    
    sendJsonMessage(message);
}

// 上传头像功能 - 为用户上传或更新头像
// 设计思路：将头像文件转换为Base64编码，通过JSON消息发送到服务器
void ChatClient::uploadAvatar(int userId, const QString &avatarPath) {
    QFile file(avatarPath);
    if (!file.open(QIODevice::ReadOnly)) {
        qDebug() << "ChatClient: Failed to open avatar file:" << avatarPath;
        return;
    }
    
    QByteArray fileData = file.readAll();
    QString base64Data = fileData.toBase64();
    file.close();
    
    QJsonObject message;
    message["msgid"] = MsgType::UPLOAD_AVATAR_MSG;
    message["id"] = userId;
    // 跨平台兼容的文件名提取
    message["avatarName"] = QFileInfo(avatarPath).fileName();
    message["avatarData"] = base64Data;
    
    sendJsonMessage(message);
}

// 更新头像功能 - 更新用户现有头像
// 设计思路：与上传头像类似，但使用不同的消息类型
void ChatClient::updateAvatar(int userId, const QString &avatarPath) {
    QFile file(avatarPath);
    if (!file.open(QIODevice::ReadOnly)) {
        qDebug() << "ChatClient: Failed to open avatar file:" << avatarPath;
        return;
    }
    
    QByteArray fileData = file.readAll();
    QString base64Data = fileData.toBase64();
    file.close();
    
    QJsonObject message;
    message["msgid"] = MsgType::UPDATE_AVATAR_MSG;
    message["id"] = userId;
    // 跨平台兼容的文件名提取
    message["avatarName"] = QFileInfo(avatarPath).fileName();
    message["avatarData"] = base64Data;
    
    sendJsonMessage(message);
}

// 登出功能 - 用户退出系统
// 设计思路：简化的请求格式，仅包含用户ID和消息类型
void ChatClient::logout(int userId) {
    QJsonObject message;
    message["msgid"] = MsgType::LOGINOUT_MSG;
    message["id"] = userId;
    sendJsonMessage(message);
    // 清空当前用户头像数据，确保下次登录时不会使用旧数据
    this->currentUserAvatar = "";
}

// 发送私聊消息 - 实现一对一通信
// 设计思路：封装消息接收方ID和内容，支持用户间私密通信
void ChatClient::sendMessage(int toId, const QString &message) {
    QJsonObject msgObj;
    msgObj["msgid"] = MsgType::ONE_CHAT_MSG;
    msgObj["from"] = -1; // 将由服务器填充 - 安全性设计，防止伪造发送者
    msgObj["to"] = toId;
    msgObj["msg"] = message;
    sendJsonMessage(msgObj);
}

// 发送群聊消息 - 实现一对多通信
// 设计思路：通过群组ID标识目标群组，实现广播式消息分发
void ChatClient::sendGroupMessage(int groupId, const QString &message) {
    QJsonObject msgObj;
    msgObj["msgid"] = MsgType::GROUP_CHAT_MSG;
    msgObj["from"] = -1; // 将由服务器填充
    msgObj["groupid"] = groupId;
    msgObj["msg"] = message;
    sendJsonMessage(msgObj);
}

// 上传表情包到服务器
void ChatClient::uploadEmoji(int userId, const QString &emojiName, const QString &imageData) {
    QJsonObject message;
    message["msgid"] = MsgType::UPLOAD_EMOJI_MSG; // 假设服务器支持的消息类型
    message["id"] = userId;
    message["name"] = emojiName;
    message["imageData"] = imageData;
    sendJsonMessage(message);
}

// 请求用户表情包列表
void ChatClient::requestEmojiList(int userId) {
    QJsonObject message;
    message["msgid"] = MsgType::QUERY_EMOJI_LIST_MSG; // 假设服务器支持的消息类型
    message["id"] = userId;
    sendJsonMessage(message);
}

void ChatClient::addFriend(int userId, int friendId) {
    QJsonObject message;
    message["msgid"] = MsgType::ADD_FRIEND_MSG;
    message["id"] = userId;
    message["friendid"] = friendId;
    sendJsonMessage(message);
}

void ChatClient::createGroup(int userId, const QString &groupName, const QString &groupDesc) {
    QJsonObject message;
    message["msgid"] = MsgType::CREATE_GROUP_MSG;
    message["id"] = userId;
    message["groupname"] = groupName;
    message["groupdesc"] = groupDesc;
    sendJsonMessage(message);
}

void ChatClient::joinGroup(int userId, int groupId) {
    QJsonObject message;
    message["msgid"] = MsgType::ADD_GROUP_MSG;
    message["id"] = userId;
    message["groupid"] = groupId;
    sendJsonMessage(message);
}

void ChatClient::inviteToGroup(int userId, int groupId, int targetId) {
    QJsonObject message;
    message["msgid"] = MsgType::INVITE_GROUP_MSG;
    message["id"] = userId;
    message["groupid"] = groupId;
    message["targetid"] = targetId;
    sendJsonMessage(message);
}

void ChatClient::requestFriendList(int userId) {
    qDebug() << "[CRITICAL] requestFriendList called with userId:" << userId;
    QJsonObject message;
    message["msgid"] = MsgType::QUERY_FRIEND_MSG;
    message["id"] = userId;
    sendJsonMessage(message);
    qDebug() << "[CRITICAL] Friend list request sent successfully";
}

void ChatClient::requestGroupList(int userId) {
    qDebug() << "[CRITICAL] requestGroupList called with userId:" << userId;
    QJsonObject message;
    message["msgid"] = MsgType::QUERY_GROUP_MSG;
    message["id"] = userId;
    sendJsonMessage(message);
    qDebug() << "[CRITICAL] Group list request sent successfully";
}

// 生成唯一的文件ID
QString ChatClient::generateFileId() {
    // 使用时间戳和随机数组合生成唯一ID
    QString timestamp = QString::number(QDateTime::currentMSecsSinceEpoch());
#ifdef _WIN32
    // Windows平台使用QRandomGenerator
    QString randomNum = QString::number(QRandomGenerator::global()->bounded(10000));
#else
    // Linux平台使用qrand
    QString randomNum = QString::number(qrand() % 10000);
#endif
    return timestamp + "_" + randomNum;
}

// 文件传输相关函数实现
void ChatClient::sendFileRequest(int fromId, int toId, const QString &filename, long long filesize, const QString &fileId) {
    QJsonObject message;
    message["msgid"] = MsgType::FILE_TRANSFER_REQ;
    message["from"] = fromId;
    message["to"] = toId;
    message["filename"] = filename;
    message["filesize"] = filesize;
    message["fileid"] = fileId.isEmpty() ? generateFileId() : fileId; // 使用传入的fileId或生成新的
    
    sendJsonMessage(message);
}

void ChatClient::sendFileTransferComplete(int fromId, int toId, const QString &fileId, bool success) {
    QJsonObject message;
    message["msgid"] = MsgType::FILE_TRANSFER_COMPLETE;
    message["from"] = fromId;
    message["to"] = toId;
    message["fileid"] = fileId;
    message["success"] = success;
    sendJsonMessage(message);
}

void ChatClient::acceptFileTransfer(int fromId, int toId, const QString &fileId, bool accept) {
    QJsonObject message;
    message["msgid"] = MsgType::FILE_TRANSFER_ACK;
    message["from"] = fromId;
    message["to"] = toId;
    message["fileid"] = fileId;
    message["accepted"] = accept;
    sendJsonMessage(message);
}

void ChatClient::sendFileData(int fromId, int toId, const QString &fileId, int chunkIndex, const QByteArray &data) {
    QJsonObject message;
    message["msgid"] = MsgType::FILE_TRANSFER_DATA;
    message["from"] = fromId;
    message["to"] = toId;
    message["fileid"] = fileId;
    message["chunkindex"] = chunkIndex;
    message["data"] = QString::fromUtf8(data.toBase64());
    sendJsonMessage(message);
}

// 发送JSON消息 - 客户端核心通信方法
// 设计亮点：
// 1. 线程安全实现：使用QMutexLocker确保多线程环境下的安全发送
// 2. 兼容性处理：自动设置type字段与msgid保持一致，确保与服务器兼容
// 3. 可靠传输：使用长度前缀法，解决粘包问题
// 4. 延迟机制：增加等待时间确保数据写入和消息分离
void ChatClient::sendJsonMessage(const QJsonObject &message) {
    QMutexLocker locker(&mutex); // 线程安全锁，确保并发发送安全
    
    // 健壮性检查：确保socket可用
    if (!socket || !socket->isOpen() || !socket->isWritable()) {
        qDebug() << "ChatClient: Cannot send message, socket not ready";
        return;
    }
    
    // 兼容性处理：确保同时设置type字段
    // 设计思路：解决客户端与服务器端消息格式差异，增强系统健壮性
    QJsonObject msgCopy = message;
    if (msgCopy.contains("msgid")) {
        int msgId = msgCopy["msgid"].toInt();
        msgCopy["type"] = msgId;
        qDebug() << "Setting 'type' field to match 'msgid':" << msgId;
    }
    
    QJsonDocument doc(msgCopy);
    QByteArray jsonData = doc.toJson(QJsonDocument::Compact);
    
    // 使用长度前缀法，在消息前添加4字节的长度信息，解决TCP粘包问题
    // 注意：这里使用大端字节序，与服务器端保持一致
    qint32 length = jsonData.size();
    QByteArray lengthBytes;
    QDataStream stream(&lengthBytes, QIODevice::WriteOnly);
    stream.setByteOrder(QDataStream::BigEndian);
    stream << length;
    
    // 拼接长度前缀和JSON数据
    QByteArray data = lengthBytes + jsonData;
    
    // 发送带长度前缀的JSON数据
    qint64 bytesWritten = socket->write(data);
    
    // 强制刷新socket缓冲区，确保数据立即发送
    socket->flush();
    
    // 对于登出消息，不要阻塞等待写入完成，因为服务器会立即关闭连接
    int msgid = message["msgid"].toInt();
    if (msgid != MsgType::LOGINOUT_MSG) {
        // 对于普通消息，等待写入完成
        bool bytesWrittenSuccess = socket->waitForBytesWritten(500); // 增加到500ms
        qDebug() << "Message sent, msgid:" << msgid << 
                    "length:" << data.size() << "bytes written:" << bytesWritten << "success:" << bytesWrittenSuccess;

    } else {
        // 对于登出消息，立即返回，不等待，因为服务器会立即关闭连接
        qDebug() << "Logout message sent, msgid:" << msgid << 
                    "length:" << data.size() << "bytes written:" << bytesWritten;
    }
}

// 处理消息 - 消息解析与路由核心实现
// 设计亮点：
// 1. 命令模式实现：基于消息类型分发到不同处理逻辑
// 2. 健壮性设计：支持多种数据格式解析，包括嵌套JSON字符串处理
// 3. 降级处理：当JSON解析失败时，使用正则表达式进行备选解析
// 4. 信号通知：处理完成后通过信号通知UI层更新
void ChatClient::processMessage(const QJsonObject &message) {
    qDebug() << "Processing message with keys:" << message.keys();
    
    // 消息类型检测 - 支持两种格式以增强兼容性
    // 健壮性设计：同时检查msgid和type字段，确保消息能正确识别
    int msgType = -1;
    if (message.contains("msgid")) {
        msgType = message["msgid"].toInt();
    } else if (message.contains("type")) {
        msgType = message["type"].toInt();
    }
    
    // 根据消息类型分发处理 - 命令模式实现
    switch (msgType) {
    case MsgType::LOGIN_MSG_ACK: {
        qDebug() << "Processing LOGIN_MSG_ACK";
        // 登录响应处理 - 安全认证与状态管理
        // 设计思路：通过errno判断登录成功状态，获取用户基本信息
        // 安全性保障：验证服务器返回的用户ID与请求一致
        int errno_val = message["errno"].toInt();
        if (errno_val != 0) {
            // 登录失败处理
            QString errorMsg = message["errmsg"].toString();
            qDebug() << "Login failed with error:" << errorMsg;
            emit loginResponse(false, errorMsg);
        } else {
            // 登录成功处理
            qint64 userId = message["id"].toVariant().toLongLong();
            QString userName = message["name"].toString();
            qDebug() << "Login successful for user:" << userId << "(" << userName << ")";
            
            // 验证用户ID一致性 - 安全验证设计
            if (userId != this->currentUserId && this->currentUserId != 0) {
                qWarning() << "Security warning: User ID mismatch in login response!";
            }
            
            // 更新当前用户状态
            this->currentUserId = userId;
            // 保存用户ID即可，用户名可以从服务器获取
            
            // 处理当前用户头像
            if (message.contains("avatar")) {
                QString avatarData = message["avatar"].toString();
                qDebug() << "[CRITICAL] User avatar from login response, length:" << avatarData.length();
                
                // 输出头像数据的前50个字符，查看数据格式
                qDebug() << "[CRITICAL] Avatar data preview:" << avatarData.left(50) << (avatarData.length() > 50 ? "..." : "");
                
                // 存储当前用户头像数据
                currentUserAvatar = avatarData;
                qDebug() << "[CRITICAL] Stored avatar data, currentUserAvatar length:" << currentUserAvatar.length();
                
                // 立即检查存储的数据
                QString storedAvatar = getCurrentUserAvatar();
                qDebug() << "[CRITICAL] getCurrentUserAvatar() returned, length:" << storedAvatar.length();
                
                // 确保我们发出的是从登录响应中获取的原始avatarData，而不是可能为空的storedAvatar
                qDebug() << "[CRITICAL] Emitting avatarUpdated with data length:" << avatarData.length();
                emit avatarUpdated(avatarData);
            } else {
                // 如果登录响应中没有头像字段，尝试直接查询用户头像
                qDebug() << "[CRITICAL] No avatar in login response, querying user avatar...";
                // 清空当前用户头像数据
                currentUserAvatar = "";
                qDebug() << "[CRITICAL] Cleared currentUserAvatar, length:" << currentUserAvatar.length();
                // 这里可以添加查询用户头像的逻辑
            }
            
            // 处理登录响应中的好友列表
            if (message.contains("friends")) {
                QList<User> friendList;
                if (message["friends"].isArray()) {
                    QJsonArray friendsArray = message["friends"].toArray();
                    for (const QJsonValue &value : friendsArray) {
                        if (value.isObject()) {
                            QJsonObject friendObj = value.toObject();
                            User friendInfo;
                            friendInfo.setId(friendObj["id"].toVariant().toLongLong());
                            friendInfo.setName(friendObj["name"].toString().toStdString());
                            friendInfo.setState(friendObj["state"].toString().toStdString());
                            // 处理好友头像
                            if (friendObj.contains("avatar")) {
                                friendInfo.setAvatar(friendObj["avatar"].toString().toStdString());
                            }
                            friendList.append(friendInfo);
                        } else if (value.isString()) {
                            // 处理字符串形式的好友信息
                            QString friendStr = value.toString();
                            QJsonDocument doc = QJsonDocument::fromJson(friendStr.toUtf8());
                            if (doc.isObject()) {
                                QJsonObject friendObj = doc.object();
                                User friendInfo;
                                friendInfo.setId(friendObj["id"].toVariant().toLongLong());
                                friendInfo.setName(friendObj["name"].toString().toStdString());
                                friendInfo.setState(friendObj["state"].toString().toStdString());
                                // 处理好友头像
                                if (friendObj.contains("avatar")) {
                                    friendInfo.setAvatar(friendObj["avatar"].toString().toStdString());
                                }
                                friendList.append(friendInfo);
                            }
                        }
                    }
                    qDebug() << "Received friend list from login response with" << friendList.size() << "friends";
                    emit friendListUpdated(friendList);
                }
            }
            
            // 处理登录响应中的群组列表
            if (message.contains("groups")) {
                QList<Group> groupList;
                if (message["groups"].isArray()) {
                    QJsonArray groupsArray = message["groups"].toArray();
                    for (const QJsonValue &value : groupsArray) {
                        if (value.isObject()) {
                            QJsonObject groupObj = value.toObject();
                            Group groupInfo;
                            groupInfo.setId(groupObj["id"].toInt());
                            groupInfo.setName(groupObj["groupname"].toString().toStdString());
                            groupInfo.setDesc(groupObj["groupdesc"].toString().toStdString());
                            // 调试日志：打印解析出的群组成员数量
                            qDebug() << "Parsed group" << groupInfo.getId() << "with" << groupInfo.getUsers().size() << "members";
                            groupList.append(groupInfo);
                        } else if (value.isString()) {
                            // 处理字符串形式的群组信息
                            QString groupStr = value.toString();
                            QJsonDocument doc = QJsonDocument::fromJson(groupStr.toUtf8());
                            if (doc.isObject()) {
                                QJsonObject groupObj = doc.object();
                                Group groupInfo;
                                groupInfo.setId(groupObj["id"].toInt());
                                groupInfo.setName(groupObj["groupname"].toString().toStdString());
                                groupInfo.setDesc(groupObj["groupdesc"].toString().toStdString());
                                groupList.append(groupInfo);
                            }
                        }
                    }
                    qDebug() << "Received group list from login response with" << groupList.size() << "groups";
                    emit groupListUpdated(groupList);
                }
            }
            
            // 处理登录响应中的离线消息
            if (message.contains("offlinemsg")) {
                if (message["offlinemsg"].isArray()) {
                    QJsonArray offlineMsgsArray = message["offlinemsg"].toArray();
                    qDebug() << "[DEBUG] Found offline messages array, size:" << offlineMsgsArray.size();
                    for (const QJsonValue &value : offlineMsgsArray) {
                        if (value.isObject()) {
                            QJsonObject offlineMsgObj = value.toObject();
                            qDebug() << "[DEBUG] Processing offline message object:" << offlineMsgObj;
                            processOfflineMessage(offlineMsgObj);
                        } else if (value.isString()) {
                            // 处理字符串形式的离线消息
                            QString offlineMsgStr = value.toString();
                            qDebug() << "[DEBUG] Processing offline message string:" << offlineMsgStr;
                            QJsonParseError error;
                            QJsonDocument doc = QJsonDocument::fromJson(offlineMsgStr.toUtf8(), &error);
                            if (error.error == QJsonParseError::NoError && doc.isObject()) {
                                QJsonObject offlineMsgObj = doc.object();
                                qDebug() << "[DEBUG] Parsed offline message object:" << offlineMsgObj;
                                processOfflineMessage(offlineMsgObj);
                            } else {
                                qDebug() << "[DEBUG] Failed to parse offline message string:" << error.errorString();
                            }
                        }
                    }
                }
            }

            // 登录成功后自动请求表情包列表 - 已注释，改为懒加载
            // requestEmojiList(currentUserId);

            // 再次检查并确保头像数据已正确保存
            QString storedAvatar = getCurrentUserAvatar();
            qDebug() << "[CRITICAL] Before emitting loginResponse, getCurrentUserAvatar() returned, length:" << storedAvatar.length();

            // 通知UI层登录成功
            emit loginResponse(true, "登录成功");
            
            // 延迟一小段时间后再次发送头像更新信号，确保ChatWindow已经创建并连接了信号
            // 增加延迟时间到300ms，确保在LoginWindow的200ms延迟后ChatWindow已经创建
            QTimer::singleShot(300, this, [this]() {
                QString delayedAvatar = getCurrentUserAvatar();
                qDebug() << "[CRITICAL] Delayed avatar update signal, getCurrentUserAvatar() returned, length:" << delayedAvatar.length();
                emit avatarUpdated(delayedAvatar);
            });
        }
        break;
    }
    
    case MsgType::REG_MSG_ACK: {
        qDebug() << "Processing REG_MSG_ACK";
        // 注册响应处理 - 新用户创建反馈
        // 设计思路：通过errno判断注册成功状态，返回新用户ID
        int errno_val = message["errno"].toInt();
        if (errno_val != 0) {
            // 注册失败处理
            QString errorMsg = message["errmsg"].toString();
            qDebug() << "Registration failed with error:" << errorMsg;
            emit loginResponse(false, errorMsg);
        } else {
            // 注册成功处理
            qint64 userId = message["id"].toVariant().toLongLong();
            QString userName = message["name"].toString();
            
            // 处理头像数据
            if (message.contains("avatar")) {
                QString avatarData = message["avatar"].toString();
                this->currentUserAvatar = avatarData;
                qDebug() << "Registration successful, saved avatar data length:" << avatarData.length();
            } else {
                qDebug() << "Registration successful, no avatar data provided";
            }
            
            qDebug() << "Registration successful for user:" << userId << "(" << userName << ")";
            
            // 构建包含用户信息的JSON消息
            QJsonObject responseObj;
            responseObj["id"] = userId;
            responseObj["name"] = userName;
            QJsonDocument doc(responseObj);
            QString jsonMessage = doc.toJson(QJsonDocument::Compact);
            
            // 通知UI层注册成功，传递包含用户信息的JSON
            emit loginResponse(true, jsonMessage);
        }
        break;
    }
    
    case MsgType::ONE_CHAT_MSG: {
        qDebug() << "Processing ONE_CHAT_MSG";
        // 私聊消息处理 - 点对点通信实现
        // 设计思路：提取发送者信息和消息内容，转发给UI层展示
        qint64 fromId = message["from"].toVariant().toLongLong();
        QString fromName = message.contains("fromName") ? message["fromName"].toString() : message["name"].toString();
        QString msgContent = message["msg"].toString();
        qint64 toId = message["to"].toVariant().toLongLong();
        QString timestamp = message.contains("timestamp") ? message["timestamp"].toString() : "";
        
        // 消息过滤 - 只处理发给当前用户的消息
        if (toId == this->currentUserId) {
            qDebug() << "Received private message from" << fromId << "(" << fromName << "):" << msgContent << "at" << timestamp;
            emit messageReceived(fromId, msgContent, fromName, false, -1, timestamp);
        }
        break;
    }
    
    case MsgType::GROUP_CHAT_MSG: {
        qDebug() << "Processing GROUP_CHAT_MSG";
        // 群聊消息处理 - 群组通信实现
        // 设计思路：提取群组信息、发送者信息和消息内容，转发给UI层展示
        int groupId = message["groupid"].toInt();
        qint64 fromId = message["from"].toVariant().toLongLong();
        QString fromName = message["fromName"].toString();
        QString msgContent = message["msg"].toString();
        QString timestamp = message.contains("timestamp") ? message["timestamp"].toString() : "";
        
        qDebug() << "Received group message from" << fromId << "in group" << groupId << ":" << msgContent << "at" << timestamp;
        emit groupMessageReceived(groupId, fromId, fromName, msgContent, timestamp);
        break;
    }
    
    case MsgType::QUERY_FRIEND_MSG_ACK: {
        qDebug() << "Processing QUERY_FRIEND_MSG_ACK (message type:" << msgType << ")";
        // 好友列表查询响应处理 - 关系数据管理
        // 设计思路：
        // 1. 支持多种数据格式：处理JSON数组和字符串两种表示形式
        // 2. 降级解析：当JSON解析失败时，使用正则表达式作为备选方案
        // 3. 健壮性保障：对特殊字符进行转义处理，确保数据完整性
        
        // 检查好友列表数据是否存在
        if (message.contains("friends")) {
            QList<User> friendList;
            
            // 处理两种可能的数据格式：直接JSON数组或字符串形式的JSON数组
            if (message["friends"].isArray()) {
                // 直接处理JSON数组格式
                qDebug() << "Processing friends as JSON array";
                QJsonArray friendsArray = message["friends"].toArray();
                for (const QJsonValue &value : friendsArray) {
                    if (value.isObject()) {
                        QJsonObject friendObj = value.toObject();
                        User friendInfo;
                        friendInfo.setId(friendObj["id"].toVariant().toLongLong());
                        friendInfo.setName(friendObj["name"].toString().toStdString());
                        friendInfo.setState(friendObj["state"].toString().toStdString());
                        if (friendObj.contains("avatar")) {
                            friendInfo.setAvatar(friendObj["avatar"].toString().toStdString());
                        }
                        friendList.append(friendInfo);
                    } else if (value.isString()) {
                        // 处理字符串形式的好友信息
                        QString friendStr = value.toString();
                        QJsonDocument doc = QJsonDocument::fromJson(friendStr.toUtf8());
                        if (doc.isObject()) {
                            QJsonObject friendObj = doc.object();
                                User friendInfo;
                                friendInfo.setId(friendObj["id"].toVariant().toLongLong());
                                friendInfo.setName(friendObj["name"].toString().toStdString());
                                friendInfo.setState(friendObj["state"].toString().toStdString());
                                if (friendObj.contains("avatar")) {
                                    friendInfo.setAvatar(friendObj["avatar"].toString().toStdString());
                                }
                                friendList.append(friendInfo);
                        }
                    }
                }
            } else if (message["friends"].isString()) {
                // 处理字符串形式的JSON数组 - 增强兼容性设计
                qDebug() << "Processing friends as JSON string";
                QString friendsJsonString = message["friends"].toString();
                
                // 尝试直接解析JSON
                QJsonDocument doc = QJsonDocument::fromJson(friendsJsonString.toUtf8());
                if (doc.isArray()) {
                    QJsonArray friendsArray = doc.array();
                    for (const QJsonValue &value : friendsArray) {
                        if (value.isObject()) {
                            QJsonObject friendObj = value.toObject();
                            User friendInfo;
                            friendInfo.setId(friendObj["id"].toVariant().toLongLong());
                            friendInfo.setName(friendObj["name"].toString().toStdString());
                            friendInfo.setState(friendObj["state"].toString().toStdString());
                            friendList.append(friendInfo);
                        } else if (value.isString()) {
                            // 处理字符串形式的好友信息
                            QString friendStr = value.toString();
                            QJsonDocument doc = QJsonDocument::fromJson(friendStr.toUtf8());
                            if (doc.isObject()) {
                                QJsonObject friendObj = doc.object();
                                User friendInfo;
                                friendInfo.setId(friendObj["id"].toVariant().toLongLong());
                                friendInfo.setName(friendObj["name"].toString().toStdString());
                                friendInfo.setState(friendObj["state"].toString().toStdString());
                                if (friendObj.contains("avatar")) {
                                    friendInfo.setAvatar(friendObj["avatar"].toString().toStdString());
                                }
                                friendList.append(friendInfo);
                            }
                        }
                    }
                } else {
                    // 尝试移除可能的外部引号，处理转义字符 - 数据清洗设计
                    QString cleanJsonString = friendsJsonString;
                    if (cleanJsonString.startsWith("[")) {
                        // 尝试直接解析
                        QJsonDocument doc = QJsonDocument::fromJson(cleanJsonString.toUtf8());
                        if (doc.isArray()) {
                            QJsonArray friendsArray = doc.array();
                            for (const QJsonValue &value : friendsArray) {
                                if (value.isObject()) {
                                    QJsonObject friendObj = value.toObject();
                                    User friendInfo;
                                    friendInfo.setId(friendObj["id"].toVariant().toLongLong());
                                    friendInfo.setName(friendObj["name"].toString().toStdString());
                                    friendInfo.setState(friendObj["state"].toString().toStdString());
                                    if (friendObj.contains("avatar")) {
                                        friendInfo.setAvatar(friendObj["avatar"].toString().toStdString());
                                    }
                                    friendList.append(friendInfo);
                                } else if (value.isString()) {
                                    // 处理字符串形式的好友信息
                                    QString friendStr = value.toString();
                                    QJsonDocument doc = QJsonDocument::fromJson(friendStr.toUtf8());
                                    if (doc.isObject()) {
                                        QJsonObject friendObj = doc.object();
                                        User friendInfo;
                                        friendInfo.setId(friendObj["id"].toVariant().toLongLong());
                                        friendInfo.setName(friendObj["name"].toString().toStdString());
                                        friendInfo.setState(friendObj["state"].toString().toStdString());
                                        if (friendObj.contains("avatar")) {
                                            friendInfo.setAvatar(friendObj["avatar"].toString().toStdString());
                                        }
                                        friendList.append(friendInfo);
                                    }
                                }
                            }
                        } else {
                            // 降级方案：使用正则表达式解析 - 健壮性保障
                            qDebug() << "Falling back to regex parsing for friends data";
                            QRegularExpression regex("\\{[^}]*\\}");
                            QRegularExpressionMatchIterator matchIterator = regex.globalMatch(cleanJsonString);
                            
                            while (matchIterator.hasNext()) {
                                QRegularExpressionMatch match = matchIterator.next();
                                QString jsonObjectStr = match.captured(0);
                                
                                // 解析单个好友对象
                                QJsonDocument objDoc = QJsonDocument::fromJson(jsonObjectStr.toUtf8());
                                if (objDoc.isObject()) {
                                    QJsonObject friendObj = objDoc.object();
                                    User friendInfo;
                                    friendInfo.setId(friendObj["id"].toVariant().toLongLong());
                                    friendInfo.setName(friendObj["name"].toString().toStdString());
                                    friendInfo.setState(friendObj["state"].toString().toStdString());
                                    if (friendObj.contains("avatar")) {
                                        friendInfo.setAvatar(friendObj["avatar"].toString().toStdString());
                                    }
                                    friendList.append(friendInfo);
                                }
                            }
                        }
                    } else {
                        // 处理单个好友对象字符串
                        QJsonDocument doc = QJsonDocument::fromJson(cleanJsonString.toUtf8());
                        if (doc.isObject()) {
                            QJsonObject friendObj = doc.object();
                            User friendInfo;
                            friendInfo.setId(friendObj["id"].toVariant().toLongLong());
                            friendInfo.setName(friendObj["name"].toString().toStdString());
                            friendInfo.setState(friendObj["state"].toString().toStdString());
                            if (friendObj.contains("avatar")) {
                                friendInfo.setAvatar(friendObj["avatar"].toString().toStdString());
                            }
                            friendList.append(friendInfo);
                        } else {
                            // 尝试解析包含多个好友对象的字符串
                            QRegularExpression regex("\\{[^}]*\\}");
                            QRegularExpressionMatchIterator matchIterator = regex.globalMatch(cleanJsonString);
                            
                            while (matchIterator.hasNext()) {
                                QRegularExpressionMatch match = matchIterator.next();
                                QString jsonObjectStr = match.captured(0);
                                
                                // 解析单个好友对象
                                QJsonDocument objDoc = QJsonDocument::fromJson(jsonObjectStr.toUtf8());
                                if (objDoc.isObject()) {
                                    QJsonObject friendObj = objDoc.object();
                                    User friendInfo;
                                    friendInfo.setId(friendObj["id"].toVariant().toLongLong());
                                    friendInfo.setName(friendObj["name"].toString().toStdString());
                                    friendInfo.setState(friendObj["state"].toString().toStdString());
                                    if (friendObj.contains("avatar")) {
                                        friendInfo.setAvatar(friendObj["avatar"].toString().toStdString());
                                    }
                                    friendList.append(friendInfo);
                                }
                            }
                        }
                    }
                }
            }
            
            qDebug() << "Received friend list with" << friendList.size() << "friends";
            emit friendListUpdated(friendList);
        }
        break;
    }
    
    case MsgType::CREATE_GROUP_MSG_ACK: {
        qDebug() << "Processing CREATE_GROUP_MSG_ACK";
        
        bool success = message["success"].toBool();
        QString msg = message["msg"].toString();
        
        if (success) {
            qDebug() << "Group created successfully:" << msg;
            emit groupCreated(true, msg);
            // 创建成功后自动刷新群组列表
            requestGroupList(currentUserId);
        } else {
            qDebug() << "Group creation failed:" << msg;
            emit groupCreated(false, msg);
        }
        break;
    }
    
    case MsgType::INVITE_GROUP_MSG_ACK: {
        qDebug() << "Processing INVITE_GROUP_MSG_ACK";
        int errno_val = message["errno"].toInt();
        if (errno_val != 0) {
            QString errorMsg = message["errmsg"].toString("Invite to group failed");
            qDebug() << "Invite to group failed:" << errorMsg;
            emit inviteGroupResponse(false, errorMsg);
        } else {
            qDebug() << "Invite to group success";
            emit inviteGroupResponse(true, "Invite to group success");
            if (message.contains("groups")) {
                QList<Group> groupList;
                if (message["groups"].isArray()) {
                    QJsonArray groupsArray = message["groups"].toArray();
                    for (const QJsonValue &value : groupsArray) {
                        if (value.isString()) {
                            QString groupStr = value.toString();
                            QJsonDocument doc = QJsonDocument::fromJson(groupStr.toUtf8());
                            if (doc.isObject()) {
                                QJsonObject groupObj = doc.object();
                                Group groupInfo;
                                groupInfo.setId(groupObj["id"].toInt());
                                groupInfo.setName(groupObj["groupname"].toString().toStdString());
                                groupInfo.setDesc(groupObj["groupdesc"].toString().toStdString());
                                if (groupObj.contains("users") && groupObj["users"].isArray()) {
                                    QJsonArray usersArray = groupObj["users"].toArray();
                                    for (const QJsonValue &userValue : usersArray) {
                                        GroupUser user;
                                        if (userValue.isString()) {
                                            QString userStr = userValue.toString();
                                            QJsonDocument userDoc = QJsonDocument::fromJson(userStr.toUtf8());
                                            if (userDoc.isObject()) {
                                                QJsonObject userObj = userDoc.object();
                                                user.setId(userObj["id"].toVariant().toLongLong());
                                                user.setName(userObj["name"].toString().toStdString());
                                                user.setState(userObj["state"].toString().toStdString());
                                                user.setRole(userObj["role"].toString().toStdString());
                                                groupInfo.getUsers().push_back(user);
                                            }
                                        } else if (userValue.isObject()) {
                                            QJsonObject userObj = userValue.toObject();
                                            user.setId(userObj["id"].toVariant().toLongLong());
                                            user.setName(userObj["name"].toString().toStdString());
                                            user.setState(userObj["state"].toString().toStdString());
                                            user.setRole(userObj["role"].toString().toStdString());
                                            groupInfo.getUsers().push_back(user);
                                        }
                                    }
                                }
                                groupList.append(groupInfo);
                            }
                        } else if (value.isObject()) {
                            QJsonObject groupObj = value.toObject();
                            Group groupInfo;
                            groupInfo.setId(groupObj["id"].toInt());
                            groupInfo.setName(groupObj["groupname"].toString().toStdString());
                            groupInfo.setDesc(groupObj["groupdesc"].toString().toStdString());
                            if (groupObj.contains("users") && groupObj["users"].isArray()) {
                                QJsonArray usersArray = groupObj["users"].toArray();
                                for (const QJsonValue &userValue : usersArray) {
                                    GroupUser user;
                                    if (userValue.isString()) {
                                        QString userStr = userValue.toString();
                                        QJsonDocument userDoc = QJsonDocument::fromJson(userStr.toUtf8());
                                        if (userDoc.isObject()) {
                                            QJsonObject userObj = userDoc.object();
                                            user.setId(userObj["id"].toVariant().toLongLong());
                                            user.setName(userObj["name"].toString().toStdString());
                                            user.setState(userObj["state"].toString().toStdString());
                                            user.setRole(userObj["role"].toString().toStdString());
                                            groupInfo.getUsers().push_back(user);
                                        }
                                    } else if (userValue.isObject()) {
                                        QJsonObject userObj = userValue.toObject();
                                        user.setId(userObj["id"].toVariant().toLongLong());
                                        user.setName(userObj["name"].toString().toStdString());
                                        user.setState(userObj["state"].toString().toStdString());
                                        user.setRole(userObj["role"].toString().toStdString());
                                        groupInfo.getUsers().push_back(user);
                                    }
                                }
                            }
                            groupList.append(groupInfo);
                        }
                    }
                }
                if (!groupList.isEmpty()) {
                    emit groupListUpdated(groupList);
                }
            }
        }
        break;
    }
    
    case MsgType::QUERY_GROUP_MSG_ACK: {
        qDebug() << "Processing QUERY_GROUP_MSG_ACK (message type:" << msgType << ")";
        // 群组列表查询响应处理 - 群组数据管理
        // 设计思路：
        // 1. 支持多种数据格式：处理JSON数组和字符串两种表示形式
        // 2. 数据嵌套解析：处理群组信息和群组成员列表的嵌套结构
        // 3. 降级处理：当JSON解析失败时，使用正则表达式作为备选方案
        
        // 检查群组列表数据是否存在
        if (message.contains("groups")) {
            QList<Group> groupList;
            
            // 处理两种可能的数据格式：直接JSON数组或字符串形式的JSON数组
            if (message["groups"].isArray()) {
                // 直接处理JSON数组格式
                qDebug() << "Processing groups as JSON array";
                QJsonArray groupsArray = message["groups"].toArray();
                for (const QJsonValue &value : groupsArray) {
                    if (value.isObject()) {
                        QJsonObject groupObj = value.toObject();
                        Group groupInfo;
                        groupInfo.setId(groupObj["id"].toInt());
                        groupInfo.setName(groupObj["groupname"].toString().toStdString());
                        groupInfo.setDesc(groupObj["groupdesc"].toString().toStdString());
                        
                        // 解析群组成员列表
                        if (groupObj.contains("users") && groupObj["users"].isArray()) {
                            QJsonArray usersArray = groupObj["users"].toArray();
                            for (const QJsonValue &userValue : usersArray) {
                                GroupUser user;
                                if (userValue.isString()) {
                                    // 处理字符串形式的用户对象（服务器返回的格式）
                                    QString userStr = userValue.toString();
                                    QJsonDocument userDoc = QJsonDocument::fromJson(userStr.toUtf8());
                                    if (userDoc.isObject()) {
                                        QJsonObject userObj = userDoc.object();
                                        user.setId(userObj["id"].toVariant().toLongLong());
                                        user.setName(userObj["name"].toString().toStdString());
                                        user.setState(userObj["state"].toString().toStdString());
                                        user.setRole(userObj["role"].toString().toStdString());
                                        groupInfo.getUsers().push_back(user);
                                    }
                                } else if (userValue.isObject()) {
                                    // 处理直接的用户对象
                                    QJsonObject userObj = userValue.toObject();
                                    user.setId(userObj["id"].toVariant().toLongLong());
                                    user.setName(userObj["name"].toString().toStdString());
                                    user.setState(userObj["state"].toString().toStdString());
                                    user.setRole(userObj["role"].toString().toStdString());
                                    groupInfo.getUsers().push_back(user);
                                }
                            }
                        }
                        
                        groupList.append(groupInfo);
                    } else if (value.isString()) {
                        // 处理字符串形式的群组信息
                        QString groupStr = value.toString();
                        QJsonDocument doc = QJsonDocument::fromJson(groupStr.toUtf8());
                        if (doc.isObject()) {
                            QJsonObject groupObj = doc.object();
                            Group groupInfo;
                            groupInfo.setId(groupObj["id"].toInt());
                            groupInfo.setName(groupObj["groupname"].toString().toStdString());
                            groupInfo.setDesc(groupObj["groupdesc"].toString().toStdString());
                            
                            // 解析群组成员列表
                            if (groupObj.contains("users")) {
                                const QJsonValue &usersValue = groupObj["users"];
                                if (usersValue.isArray()) {
                                    // 直接处理JSON数组格式的成员
                                    QJsonArray usersArray = usersValue.toArray();
                                    for (const QJsonValue &userValue : usersArray) {
                                        if (userValue.isObject()) {
                                            QJsonObject userObj = userValue.toObject();
                                            GroupUser user;
                                            user.setId(userObj["id"].toVariant().toLongLong());
                                            user.setName(userObj["name"].toString().toStdString());
                                            user.setState(userObj["state"].toString().toStdString());
                                            user.setRole(userObj["role"].toString().toStdString());
                                            groupInfo.getUsers().push_back(user);
                                        } else if (userValue.isString()) {
                                            // 处理字符串形式的单个成员
                                            QString userStr = userValue.toString();
                                            QJsonDocument userDoc = QJsonDocument::fromJson(userStr.toUtf8());
                                            if (userDoc.isObject()) {
                                                QJsonObject userObj = userDoc.object();
                                                GroupUser user;
                                                user.setId(userObj["id"].toVariant().toLongLong());
                                                user.setName(userObj["name"].toString().toStdString());
                                                user.setState(userObj["state"].toString().toStdString());
                                                user.setRole(userObj["role"].toString().toStdString());
                                                groupInfo.getUsers().push_back(user);
                                            }
                                        }
                                    }
                                } else if (usersValue.isString()) {
                                    // 处理字符串形式的成员数组
                                    QString usersStr = usersValue.toString();
                                    QJsonDocument usersDoc = QJsonDocument::fromJson(usersStr.toUtf8());
                                    if (usersDoc.isArray()) {
                                        QJsonArray usersArray = usersDoc.array();
                                        for (const QJsonValue &userValue : usersArray) {
                                            if (userValue.isObject()) {
                                                QJsonObject userObj = userValue.toObject();
                                                GroupUser user;
                                                user.setId(userObj["id"].toVariant().toLongLong());
                                                user.setName(userObj["name"].toString().toStdString());
                                                user.setState(userObj["state"].toString().toStdString());
                                                user.setRole(userObj["role"].toString().toStdString());
                                                groupInfo.getUsers().push_back(user);
                                            } else if (userValue.isString()) {
                                                // 处理字符串形式的单个成员
                                                QString userStr = userValue.toString();
                                                QJsonDocument userDoc = QJsonDocument::fromJson(userStr.toUtf8());
                                                if (userDoc.isObject()) {
                                                    QJsonObject userObj = userDoc.object();
                                                    GroupUser user;
                                                    user.setId(userObj["id"].toVariant().toLongLong());
                                                    user.setName(userObj["name"].toString().toStdString());
                                                    user.setState(userObj["state"].toString().toStdString());
                                                    user.setRole(userObj["role"].toString().toStdString());
                                                    groupInfo.getUsers().push_back(user);
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                            
                            groupList.append(groupInfo);
                        }
                    }
                }
            } else if (message["groups"].isString()) {
                // 处理字符串形式的JSON数组 - 增强兼容性设计
                qDebug() << "Processing groups as JSON string";
                QString groupsJsonString = message["groups"].toString();
                
                // 尝试直接解析JSON
                QJsonDocument doc = QJsonDocument::fromJson(groupsJsonString.toUtf8());
                if (doc.isArray()) {
                    QJsonArray groupsArray = doc.array();
                    for (const QJsonValue &value : groupsArray) {
                        if (value.isObject()) {
                            QJsonObject groupObj = value.toObject();
                            Group groupInfo;
                            groupInfo.setId(groupObj["id"].toInt());
                            groupInfo.setName(groupObj["groupname"].toString().toStdString());
                            groupInfo.setDesc(groupObj["groupdesc"].toString().toStdString());
                            groupList.append(groupInfo);
                        } else if (value.isString()) {
                            // 处理字符串形式的群组信息
                            QString groupStr = value.toString();
                            QJsonDocument doc = QJsonDocument::fromJson(groupStr.toUtf8());
                            if (doc.isObject()) {
                                QJsonObject groupObj = doc.object();
                                Group groupInfo;
                                groupInfo.setId(groupObj["id"].toInt());
                                groupInfo.setName(groupObj["groupname"].toString().toStdString());
                                groupInfo.setDesc(groupObj["groupdesc"].toString().toStdString());
                                groupList.append(groupInfo);
                            }
                        }
                    }
                } else {
                    // 尝试移除可能的外部引号，处理转义字符 - 数据清洗设计
                    QString cleanJsonString = groupsJsonString;
                    if (cleanJsonString.startsWith("[")) {
                        // 尝试直接解析
                        QJsonDocument doc = QJsonDocument::fromJson(cleanJsonString.toUtf8());
                        if (doc.isArray()) {
                            QJsonArray groupsArray = doc.array();
                            for (const QJsonValue &value : groupsArray) {
                                if (value.isObject()) {
                                    QJsonObject groupObj = value.toObject();
                                    Group groupInfo;
                                    groupInfo.setId(groupObj["id"].toInt());
                                    groupInfo.setName(groupObj["groupname"].toString().toStdString());
                                    groupInfo.setDesc(groupObj["groupdesc"].toString().toStdString());
                                    groupList.append(groupInfo);
                                } else if (value.isString()) {
                                    // 处理字符串形式的群组信息
                                    QString groupStr = value.toString();
                                    QJsonDocument doc = QJsonDocument::fromJson(groupStr.toUtf8());
                                    if (doc.isObject()) {
                                        QJsonObject groupObj = doc.object();
                                        Group groupInfo;
                                        groupInfo.setId(groupObj["id"].toInt());
                                        groupInfo.setName(groupObj["groupname"].toString().toStdString());
                                        groupInfo.setDesc(groupObj["groupdesc"].toString().toStdString());
                                        groupList.append(groupInfo);
                                    }
                                }
                            }
                        } else {
                            // 降级方案：使用正则表达式解析 - 健壮性保障
                            qDebug() << "Falling back to regex parsing for groups data";
                            QRegularExpression regex("\\{[^}]*\\}");
                            QRegularExpressionMatchIterator matchIterator = regex.globalMatch(cleanJsonString);
                            
                            while (matchIterator.hasNext()) {
                                QRegularExpressionMatch match = matchIterator.next();
                                QString jsonObjectStr = match.captured(0);
                                
                                // 解析单个群组对象
                                QJsonDocument objDoc = QJsonDocument::fromJson(jsonObjectStr.toUtf8());
                                if (objDoc.isObject()) {
                                    QJsonObject groupObj = objDoc.object();
                                    Group groupInfo;
                                    groupInfo.setId(groupObj["id"].toInt());
                                    groupInfo.setName(groupObj["groupname"].toString().toStdString());
                                    groupInfo.setDesc(groupObj["groupdesc"].toString().toStdString());
                                    groupList.append(groupInfo);
                                }
                            }
                        }
                    } else {
                        // 处理单个群组对象字符串
                        QJsonDocument doc = QJsonDocument::fromJson(cleanJsonString.toUtf8());
                        if (doc.isObject()) {
                            QJsonObject groupObj = doc.object();
                            Group groupInfo;
                            groupInfo.setId(groupObj["id"].toInt());
                            groupInfo.setName(groupObj["groupname"].toString().toStdString());
                            groupInfo.setDesc(groupObj["groupdesc"].toString().toStdString());
                            groupList.append(groupInfo);
                        } else {
                            // 尝试解析包含多个群组对象的字符串
                            QRegularExpression regex("\\{[^}]*\\}");
                            QRegularExpressionMatchIterator matchIterator = regex.globalMatch(cleanJsonString);
                            
                            while (matchIterator.hasNext()) {
                                QRegularExpressionMatch match = matchIterator.next();
                                QString jsonObjectStr = match.captured(0);
                                
                                // 解析单个群组对象
                                QJsonDocument objDoc = QJsonDocument::fromJson(jsonObjectStr.toUtf8());
                                if (objDoc.isObject()) {
                                    QJsonObject groupObj = objDoc.object();
                                    Group groupInfo;
                                    groupInfo.setId(groupObj["id"].toInt());
                                    groupInfo.setName(groupObj["groupname"].toString().toStdString());
                                    groupInfo.setDesc(groupObj["groupdesc"].toString().toStdString());
                                    groupList.append(groupInfo);
                                }
                            }
                        }
                    }
                }
            }
            
            qDebug() << "Received group list with" << groupList.size() << "groups";
            // 输出群组列表的详细信息，便于调试
            for (const Group &group : groupList) {
                qDebug() << "Group ID:" << group.getId() << "Name:" << QString::fromStdString(group.getName()) << "Desc:" << QString::fromStdString(group.getDesc());
            }
            emit groupListUpdated(groupList);
        }
        break;
    }
    
    // 文件传输相关消息处理
    case MsgType::FILE_TRANSFER_REQ: {
        qDebug() << "Processing FILE_TRANSFER_REQ";
        // 文件传输请求处理 - 实现文件传输的协商阶段
        // 设计思路：提取文件信息，发送确认请求给用户
        int fromId = message["from"].toInt();
        QString fromName = message["fromName"].toString();
        QString filename = message["filename"].toString();
        qint64 filesize = message["filesize"].toVariant().toLongLong();
        QString fileId = message["fileid"].toString();
        
        qDebug() << "Received file transfer request from" << fromId << ":" << filename << "(" << filesize << " bytes)";
        emit fileTransferRequestReceived(fromId, filename, filesize, fileId);
        break;
    }
    
    case MsgType::FILE_TRANSFER_DATA: {
        qDebug() << "Processing FILE_TRANSFER_DATA";
        // 文件数据传输处理 - 实现文件数据的接收
        // 设计思路：接收并解码文件数据块，按序重组
        int fromId = message["from"].toInt();
        QString fileId = message["fileid"].toString();
        int chunkIndex = message["chunkindex"].toInt();
        QByteArray data = QByteArray::fromBase64(message["data"].toString().toUtf8());
        
        qDebug() << "Received file data chunk" << chunkIndex << "for fileId:" << fileId;
        emit fileTransferDataReceived(fileId, chunkIndex, data);
        break;
    }
    
    case MsgType::FILE_TRANSFER_COMPLETE: {
        qDebug() << "Processing FILE_TRANSFER_COMPLETE";
        // 文件传输完成通知处理 - 实现文件传输的收尾
        // 设计思路：通知用户文件传输状态，便于清理资源
        int fromId = message["from"].toInt();
        QString fileId = message["fileid"].toString();
        bool success = message["success"].toBool();
        
        qDebug() << "File transfer complete for fileId:" << fileId << "success:" << success;
        emit fileTransferCompleteReceived(fileId, success);
        break;
    }
    
    case MsgType::FILE_TRANSFER_ACK: {
        qDebug() << "Processing FILE_TRANSFER_ACK";
        // 文件传输确认处理 - 处理用户对文件传输请求的响应
        // 设计思路：根据用户选择，决定是否继续文件传输
        QString fileId = message["fileid"].toString();
        bool accept = message["accepted"].toBool();
        
        qDebug() << "File transfer" << (accept ? "accepted" : "rejected") << "for fileId:" << fileId;
        emit fileTransferAccepted(fileId, accept);
        break;
    }
    
    case MsgType::UPLOAD_EMOJI_MSG_ACK: {
        qDebug() << "Processing UPLOAD_EMOJI_MSG_ACK (message type:" << msgType << ")";
        int errno_val = message["errno"].toInt();
        if (errno_val != 0) {
            QString errorMsg = message["errmsg"].toString();
            qDebug() << "Emoji upload failed:" << errorMsg;
            emit emojiUploadResponse(false, errorMsg);
        } else {
            // 获取表情包信息
            long long emojiId = message["emojiId"].toVariant().toLongLong();
            QString name = message["name"].toString();
            qDebug() << "Emoji upload successful! ID:" << emojiId << "Name:" << name;
            emit emojiUploadResponse(true, "");
            // 上传成功后，应该刷新表情包列表
            requestEmojiList(currentUserId);
        }
        break;
    }
    
    case MsgType::QUERY_EMOJI_LIST_MSG_ACK: {
        qDebug() << "Processing QUERY_EMOJI_LIST_MSG_ACK (message type:" << msgType << ")";
        int errno_val = message["errno"].toInt();
        if (errno_val == 0) {
            QList<QJsonObject> emojiList;
            if (message.contains("emojis")) {
                if (message["emojis"].isArray()) {
                    QJsonArray emojisArray = message["emojis"].toArray();
                    for (const QJsonValue &value : emojisArray) {
                        if (value.isString()) {
                            // 处理字符串形式的表情包信息
                            QString emojiStr = value.toString();
                            QJsonDocument doc = QJsonDocument::fromJson(emojiStr.toUtf8());
                            if (doc.isObject()) {
                                emojiList.append(doc.object());
                            }
                        } else if (value.isObject()) {
                            // 直接处理对象形式的表情包信息
                            emojiList.append(value.toObject());
                        }
                    }
                }
            }
            qDebug() << "Received emoji list with" << emojiList.size() << "emojis";
            emit emojiListUpdated(emojiList);
        }
        break;
    }
    
    case MsgType::UPLOAD_AVATAR_MSG_ACK: 
    case MsgType::UPDATE_AVATAR_MSG_ACK: {
        qDebug() << "Processing avatar update response (message type:" << msgType << ")";
        int errno_val = message["errno"].toInt();
        if (errno_val == 0) {
            // 头像更新成功
            qDebug() << "Avatar update successful";
            if (message.contains("avatar")) {
                QString avatarPath = message["avatar"].toString();
                emit avatarUpdated(avatarPath);
            } else {
                // 如果没有返回avatar字段，也发射信号，UI层会处理
                emit avatarUpdated("");
            }
        } else {
            // 头像更新失败
            QString errorMsg = message["errmsg"].toString();
            qDebug() << "Avatar update failed:" << errorMsg;
        }
        break;
    }
    
    case MsgType::STATE_UPDATE_MSG: {
        qDebug() << "Processing STATE_UPDATE_MSG";
        // 用户状态更新处理
        if (message.contains("userid") && message.contains("state")) {
            qint64 userId = message["userid"].toVariant().toLongLong();
            QString state = message["state"].toString();
            qDebug() << "Friend state updated: User" << userId << "state changed to" << state;
            emit friendStateUpdated(userId, state);
        }
        break;
    }
    
    default: {
        // 未知消息类型处理 - 增强系统健壮性
        qWarning() << "Unknown message type:" << msgType;
        break;
    }
    }
}

// 处理离线消息
// 设计思路：将离线消息存储在队列中，等待ChatWindow准备就绪后再发送
void ChatClient::processOfflineMessage(const QJsonObject &message) {
    qDebug() << "Processing offline message with keys:" << message.keys();
    
    // Store the offline message in the queue to process later
    offlineMessages.append(message);
    qDebug() << "Stored offline message, queue size:" << offlineMessages.size();
}

// Process stored offline messages
// This method should be called after ChatWindow has connected its signal handlers
void ChatClient::processStoredOfflineMessages() {
    qDebug() << "Processing stored offline messages, count:" << offlineMessages.size();
    
    // Process all stored offline messages
    while (!offlineMessages.isEmpty()) {
        QJsonObject message = offlineMessages.takeFirst();
        qDebug() << "Processing queued offline message with keys:" << message.keys();
        
        int msgType = message["msgid"].toInt();
        
        switch (msgType) {
        case MsgType::ONE_CHAT_MSG:
        {
            // 处理离线私聊消息
            qint64 fromId = message["from"].toVariant().toLongLong();
            QString msgContent = message["msg"].toString();
            QString fromName = message["name"].toString();
            QString timestamp = message.contains("timestamp") ? message["timestamp"].toString() : "";
            
            qDebug() << "[DEBUG] Processing queued offline private message from" << fromId << "(" << fromName << "):" << msgContent << "with timestamp:" << timestamp;
            emit messageReceived(fromId, msgContent, fromName, false, -1, timestamp);
            break;
        }
        case MsgType::GROUP_CHAT_MSG:
        {
            // 处理离线群聊消息
            int groupId = message["groupid"].toInt();
            qint64 fromId = message["from"].toVariant().toLongLong();
            QString msgContent = message["msg"].toString();
            QString fromName = message.contains("fromName") ? message["fromName"].toString() : message["name"].toString();
            QString timestamp = message.contains("timestamp") ? message["timestamp"].toString() : "";
            
            qDebug() << "[DEBUG] Processing queued offline group message from" << fromId << "(" << fromName << ") in group" << groupId << ":" << msgContent << "with timestamp:" << timestamp;
            emit groupMessageReceived(groupId, fromId, fromName, msgContent, timestamp);
            break;
        }
        default:
            qDebug() << "Unknown offline message type:" << msgType;
            break;
        }
    }
}

void ChatClient::onConnected() {
    qDebug() << "Connected to server";
    isConnected = true;
    emit connectionStateChanged(true);
}

void ChatClient::onDisconnected() {
    qDebug() << "Disconnected from server";
    isConnected = false;
    emit connectionStateChanged(false);
}

void ChatClient::onReadyRead() {
    static QByteArray buffer;
    
    // 读取所有可用数据
    QByteArray newData = socket->readAll();
    if (newData.isEmpty()) {
        return;
    }
    
    // 添加到缓冲区
    buffer.append(newData);
    qDebug() << "[CRITICAL] Received data, buffer size:" << buffer.size();
    
    // 尝试直接解析JSON数据（服务器期望的格式）
    while (!buffer.isEmpty()) {
        qDebug() << "[CRITICAL] Trying to parse JSON from buffer";
        
        // 尝试在缓冲区中找到JSON对象
        int jsonStart = buffer.indexOf('{');
        int jsonEnd = -1;
        int braceCount = 0;
        bool inString = false;
        
        if (jsonStart != -1) {
            qDebug() << "[CRITICAL] Found JSON start at position:" << jsonStart;
            // 尝试找到匹配的结束括号
            for (int i = jsonStart; i < buffer.size(); i++) {
                if (buffer[i] == '"' && (i == 0 || buffer[i-1] != '\\')) {
                    inString = !inString;
                }
                
                if (!inString) {
                    if (buffer[i] == '{') {
                        braceCount++;
                    } else if (buffer[i] == '}') {
                        braceCount--;
                        if (braceCount == 0) {
                            jsonEnd = i;
                            qDebug() << "[CRITICAL] Found matching JSON end at position:" << jsonEnd;
                            break;
                        }
                    }
                }
            }
        } else {
            qDebug() << "[CRITICAL] No JSON start found in buffer";
            // 如果没有找到JSON开始，可能缓冲区数据不完整，等待更多数据
            break;
        }
        
        // 如果找到完整的JSON数据
        if (jsonStart != -1 && jsonEnd != -1 && jsonStart < jsonEnd) {
            QByteArray jsonData = buffer.mid(jsonStart, jsonEnd - jsonStart + 1);
            buffer.remove(0, jsonEnd + 1);
            
            qDebug() << "[CRITICAL] Extracted JSON data of length:" << jsonData.size();
            qDebug() << "[CRITICAL] JSON data content:" << jsonData.mid(0, 100) << (jsonData.size() > 100 ? "..." : "");
            
            QJsonParseError error;
            QJsonDocument doc = QJsonDocument::fromJson(jsonData, &error);
            if (error.error == QJsonParseError::NoError && doc.isObject()) {
                QJsonObject message = doc.object();
                qDebug() << "[CRITICAL] Successfully parsed JSON with keys:" << message.keys();
                
                // 特别标记处理好友列表和群组列表数据的调试信息
                if (message.contains("friends") || message.contains("groups") || 
                    (message.contains("type") && (message["type"].toInt() == MsgType::QUERY_FRIEND_MSG_ACK || 
                                                 message["type"].toInt() == MsgType::QUERY_GROUP_MSG_ACK))) {
                    qDebug() << "[CRITICAL] Processing friend/group list data";
                }
                
                processMessage(message);
                
                // 继续处理缓冲区中的下一条消息
                qDebug() << "[CRITICAL] Processed message, remaining buffer size:" << buffer.size();
                continue;
            } else {
                qDebug() << "[CRITICAL] Error parsing JSON:" << error.errorString();
                // 如果解析失败，可能是JSON格式问题，尝试跳过一些字节继续查找
                buffer.remove(0, jsonStart + 1);
                qDebug() << "[CRITICAL] Skipping problematic JSON start, trying again";
            }
        } else {
            qDebug() << "[CRITICAL] No complete JSON found in buffer, waiting for more data";
            // 没有找到完整的JSON，等待更多数据
            break;
        }
    }
}

void ChatClient::onError(QAbstractSocket::SocketError socketError) {
    qDebug() << "Socket error:" << socketError << socket->errorString();
    if (isConnected) {
        isConnected = false;
        emit connectionStateChanged(false);
    }
}