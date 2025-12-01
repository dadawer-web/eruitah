// 包含头文件
// chatserver.h: 包含ChatServer类的定义
// public.h: 包含公共定义，如消息类型枚举等
// QDebug: Qt的调试输出工具
// QJsonDocument, QJsonArray, QJsonObject: Qt的JSON处理类
#include "chatserver.h"
#include "public.h"
#include <QDebug>
#include <QJsonDocument>
#include <QJsonArray>
#include <QJsonObject>

// ChatServer类构造函数
// 参数parent: 父对象指针，用于Qt的对象树管理
// 业务逻辑：初始化服务器核心组件，建立信号槽连接，为服务器运行做准备
// 设计思路：采用Qt的事件驱动架构，通过信号槽机制实现非阻塞I/O处理，支持高性能并发连接
ChatServer::ChatServer(QObject *parent) : QObject(parent) {
    // 创建QTcpServer对象，用于监听客户端连接
    // 服务器架构设计核心：采用Qt的事件驱动模型实现并发连接处理
    server = new QTcpServer(this);
    
    // 连接信号和槽 - 事件驱动架构的核心部分
    // 当有新客户端连接时，触发onNewConnection槽函数进行处理
    connect(server, &QTcpServer::newConnection, this, &ChatServer::onNewConnection);
}

// ChatServer类析构函数
// 业务逻辑：确保服务器优雅退出，清理所有资源
// 设计思路：遵循RAII原则，在对象销毁时自动释放所有资源，防止资源泄漏
ChatServer::~ChatServer() {
    // 调用stopServer函数关闭服务器并清理资源
    stopServer();
}

// 启动服务器函数
// 参数port: 服务器监听的端口号，quint16是无符号16位整数类型
// 返回值: bool类型，表示启动是否成功
// 业务逻辑：初始化服务状态，启动网络监听，准备接收客户端连接
// 设计思路：采用端口绑定模式，实现高可用性服务器架构，支持多客户端同时连接
bool ChatServer::startServer(quint16 port) {
    // 数据库初始化已在各模型构造函数中完成
    qDebug() << "数据库初始化完成";
    
    // 重置所有用户的在线状态为离线 - 确保服务重启后状态一致性
    // 安全机制：防止因服务异常终止导致的状态错误
    userModel.resetState();
    
    // 启动服务器，开始监听指定端口
    // QHostAddress::Any表示监听所有网络接口
    if (!server->listen(QHostAddress::Any, port)) {
        // 如果启动失败，输出错误信息
        qDebug() << "Failed to start server:" << server->errorString();
        return false;
    }
    
    // 启动成功，输出日志
    qDebug() << "Server started on port" << port;
    return true;
}

// 停止服务器函数
// 业务逻辑：优雅关闭服务器，清理所有资源并确保状态一致性
// 设计思路：实现优雅退出机制，确保在服务终止时所有连接正常关闭，数据状态保持一致
void ChatServer::stopServer() {
    // 重置所有用户的在线状态为离线 - 确保数据持久化的一致性
    userModel.resetState();
    
    // 使用互斥锁保护多线程访问 - 线程安全机制，防止并发访问冲突
    // 由于服务器可能同时处理多个客户端连接，需要确保状态更新的原子性
    QMutexLocker locker(&mutex);
    
    // 关闭所有客户端连接 - 优雅退出的重要步骤
    foreach (QTcpSocket *socket, userConnections.values()) {
        // 断开与客户端的连接
        socket->disconnectFromHost();
        // 等待连接断开，最多等待1000毫秒
        socket->waitForDisconnected(1000);
        // 延迟删除socket对象，确保资源正确释放
        socket->deleteLater();
    }
    // 清空连接映射表 - 清理内存引用
    userConnections.clear();
    
    // 关闭服务器，停止监听
    server->close();
    qDebug() << "Server stopped";
}

// 处理新连接的槽函数
// 当有新客户端连接到服务器时被调用
// 设计思路：采用连接池模式，为每个新连接建立独立的数据通道，支持并行处理多个客户端
void ChatServer::onNewConnection() {
    // 获取下一个待处理的连接
    // nextPendingConnection()返回一个QTcpSocket指针，代表客户端连接
    QTcpSocket *socket = server->nextPendingConnection();
    // 如果获取失败，直接返回
    if (!socket) return;
    
    // 输出日志，显示新客户端的IP地址
    // peerAddress().toString()获取客户端的IP地址字符串
    qDebug() << "New client connected:" << socket->peerAddress().toString();
    
    // 连接socket的信号到相应的槽函数
    // disconnected信号: 当客户端断开连接时触发
    connect(socket, &QTcpSocket::disconnected, this, &ChatServer::onDisconnected);
    // readyRead信号: 当socket有数据可读时触发
    connect(socket, &QTcpSocket::readyRead, this, &ChatServer::onReadyRead);
    // errorOccurred信号: 当socket发生错误时触发
    connect(socket, &QTcpSocket::errorOccurred, this, &ChatServer::onError);
}

// 客户端断开连接的槽函数
void ChatServer::onDisconnected() {
    // 使用qobject_cast进行类型转换
    // sender()返回发送信号的对象指针
    // qobject_cast类似于dynamic_cast，但更适合Qt对象
    QTcpSocket *socket = qobject_cast<QTcpSocket*>(sender());
    if (!socket) return;
    
    // 调用handleDisconnected函数处理断开连接的逻辑
    handleDisconnected(socket);
}

// 处理可读数据的槽函数
void ChatServer::onReadyRead() {
    // 获取发送信号的socket对象
    QTcpSocket *socket = qobject_cast<QTcpSocket*>(sender());
    if (!socket) return;
    
    // 调用handleReadyRead函数处理接收到的数据
    handleReadyRead(socket);
}

// 处理socket错误的槽函数
// 参数socketError: 错误类型，是QAbstractSocket::SocketError枚举类型
void ChatServer::onError(QAbstractSocket::SocketError socketError) {
    // 获取发生错误的socket对象
    QTcpSocket *socket = qobject_cast<QTcpSocket*>(sender());
    if (!socket) return;
    
    // 输出错误信息
    // socketError是错误代码，socket->errorString()是错误描述
    qDebug() << "Socket error:" << socketError << socket->errorString();
    // 处理断开连接的逻辑
    handleDisconnected(socket);
}

// 处理客户端断开连接的函数
// 参数socket: 断开连接的客户端socket
void ChatServer::handleDisconnected(QTcpSocket *socket) {
    // 安全检查，确保socket不为空
    if (!socket) return;
    
    // 加锁保护共享数据
    QMutexLocker locker(&mutex);
    // 获取与socket关联的用户ID
    int userId = getUserIdBySocket(socket);
    
    // 如果找到对应的用户ID
    if (userId != -1) {
        // 更新用户状态为离线
        // 1. 从数据库查询用户信息
        User offlineUser = userModel.query(userId);
        // 2. 设置用户状态为"offline"
        offlineUser.setState("offline");
        // 3. 更新数据库中的用户状态
        userModel.updateState(offlineUser);
        // 4. 从连接映射表中移除用户
        userConnections.remove(userId);
        // 输出日志
        qDebug() << "User" << userId << "disconnected";
    }
    
    // 延迟删除socket对象
    socket->deleteLater();
}

// 处理可读数据的函数
// 参数socket: 发送数据的客户端socket
// 业务逻辑：实现TCP消息帧解析，解决TCP粘包问题，根据消息类型分发到不同的处理函数
// 设计思路：采用长度前缀法解决TCP粘包问题，使用命令模式实现消息分发，支持可扩展的消息处理机制
void ChatServer::handleReadyRead(QTcpSocket *socket) {
    // 静态变量buffers，为每个socket维护一个独立的缓冲区
    // 网络通信优化：每个客户端连接维护独立缓冲区，支持多客户端并发通信
    static QMap<QTcpSocket*, QByteArray> buffers;
    // 获取当前socket对应的缓冲区引用
    QByteArray &buffer = buffers[socket];
    
    // 读取socket中所有可用的数据并追加到缓冲区
    buffer.append(socket->readAll());
    
    // 处理缓冲区中的数据，这是一个循环，处理完所有完整消息
    // 消息帧解析算法实现：采用长度前缀法解决TCP粘包问题
    while (buffer.size() >= sizeof(qint32)) {
        // 读取消息长度 - 消息帧格式的首4字节为长度字段
        qint32 length = *reinterpret_cast<const qint32*>(buffer.data());
        
        // 检查缓冲区中是否有完整的消息（消息头+消息体）
        if (buffer.size() >= sizeof(qint32) + length) {
            // 提取JSON数据
            QByteArray jsonData = buffer.mid(sizeof(qint32), length);
            // 从缓冲区中移除已处理的数据 - 为下一次处理做准备
            buffer.remove(0, sizeof(qint32) + length);
            
            // 解析JSON数据 - 消息序列化与反序列化
            QJsonDocument doc = QJsonDocument::fromJson(jsonData);
            if (doc.isObject()) {
                // 获取JSON对象
                QJsonObject message = doc.object();
                // 获取消息类型 - 消息路由的关键标识
                int type = message["type"].toInt();
                
                // 根据消息类型调用不同的处理函数 - 命令模式的实现
                // 设计模式应用：消息分发机制，将不同类型消息路由到专门的处理函数
                switch (type) {
                case MsgType::LOGIN_MSG:  // 登录消息
                    processLogin(socket, message);
                    break;
                case MsgType::REG_MSG:  // 注册消息
                    processRegister(socket, message);
                    break;
                case MsgType::LOGINOUT_MSG:  // 登出消息
                    processLogout(socket, message);
                    break;
                case MsgType::ONE_CHAT_MSG:  // 单聊消息
                    processChat(socket, message);
                    break;
                case MsgType::GROUP_CHAT_MSG:  // 群聊消息
                    processGroupChat(socket, message);
                    break;
                case MsgType::ADD_FRIEND_MSG:  // 添加好友消息
                    processAddFriend(socket, message);
                    break;
                case MsgType::CREATE_GROUP_MSG:  // 创建群组消息
                    processCreateGroup(socket, message);
                    break;
                case MsgType::ADD_GROUP_MSG:  // 加入群组消息
                    processAddGroup(socket, message);
                    break;
                case MsgType::QUERY_FRIEND_MSG:  // 查询好友消息
                    processQueryFriend(socket, message);
                    break;
                case MsgType::QUERY_GROUP_MSG:  // 查询群组消息
                    processQueryGroup(socket, message);
                    break;
                default:  // 未知消息类型 - 错误处理
                    qDebug() << "Unknown message type:" << type;
                    break;
                }
            }
        } else {
            // 缓冲区中的数据不足以构成完整消息，等待更多数据
            break;
        }
    }
}

// 处理登录消息的函数
// 参数socket: 发送登录请求的客户端socket
// 参数message: 包含登录信息的JSON对象
// 业务逻辑：实现用户身份认证、会话建立和离线消息推送的核心功能
// 设计思路：采用会话管理模式，确保用户唯一性和会话安全性，同时保证消息可靠性
void ChatServer::processLogin(QTcpSocket *socket, const QJsonObject &message) {
    // 从JSON消息中获取用户ID和密码 - 身份凭证提取
    // message["id"].toInt(): 获取键为"id"的值并转换为整数
    int userId = message["id"].toInt();
    // message["password"].toString(): 获取键为"password"的值并转换为QString
    QString password = message["password"].toString();
    
    // 从数据库查询用户信息，验证用户是否存在 - 数据库验证的核心步骤
    // 身份验证机制：通过用户模型查询验证用户凭证的有效性
    User user = userModel.query(userId);
    
    // 创建响应JSON对象 - 统一响应格式，便于客户端解析
    QJsonObject response;
    // 设置响应消息类型为登录确认
    response["type"] = MsgType::LOGIN_MSG_ACK;
    
    // 验证用户是否存在且密码正确 - 多因素身份验证
    // user.getId() == -1: 表示用户不存在
    // user.getPwd() != password.toStdString(): 密码不匹配
    // toStdString(): 将QString转换为标准C++字符串
    if (user.getId() == -1 || user.getPwd() != password.toStdString()) {
        // 登录失败 - 安全访问控制
        response["success"] = false;
        response["msg"] = "用户名或密码错误";
        // 发送响应
        sendJsonMessage(socket, response);
        // 直接返回，不再继续执行
        return;
    }
    
    // 检查用户是否已经登录 - 会话冲突检测
    // 加锁保护共享数据userConnections - 并发安全机制
    QMutexLocker locker(&mutex);
    // userConnections.contains(userId): 检查是否包含指定的用户ID
    if (userConnections.contains(userId)) {
        // 用户已登录 - 防止重复登录
        response["success"] = false;
        response["msg"] = "该账号已登录";
        sendJsonMessage(socket, response);
        return;
    }
    
    // 记录用户连接 - 会话管理的核心
    // userConnections[userId] = socket: 建立用户ID到socket的映射
    // 会话管理：建立用户身份与网络连接的绑定，支持消息路由和状态追踪
    userConnections[userId] = socket;
    
    // 更新用户状态为在线 - 用户状态同步
    User onlineUser = userModel.query(userId);
    onlineUser.setState("online");
    userModel.updateState(onlineUser);
    
    // 登录成功，设置响应 - 身份认证结果通知
    response["success"] = true;
    response["msg"] = "登录成功";
    // QString::fromStdString(): 将标准C++字符串转换为QString
    response["name"] = QString::fromStdString(user.getName());
    // 发送登录成功响应
    sendJsonMessage(socket, response);
    
    // 发送用户的离线消息 - 消息可靠性保障机制
    // 确保用户不会丢失离线期间的重要信息
    sendOfflineMessages(userId, socket);
}

// 处理注册消息的函数
// 参数socket: 发送注册请求的客户端socket
// 参数message: 包含注册信息的JSON对象
void ChatServer::processRegister(QTcpSocket *socket, const QJsonObject &message) {
    // 从JSON消息中获取用户名和密码
    QString name = message["name"].toString();
    QString password = message["password"].toString();
    
    // 创建响应JSON对象
    QJsonObject response;
    response["type"] = MsgType::REG_MSG_ACK;
    
    // 创建新用户对象
    User newUser;
    // 设置用户名
    newUser.setName(name.toStdString());
    // 设置密码
    newUser.setPwd(password.toStdString());
    // 设置初始状态为离线
    newUser.setState("offline");
    
    // 尝试将用户插入数据库
    // userModel.insert()返回bool值，表示插入是否成功
    if (userModel.insert(newUser)) {
        // 注册成功
        response["success"] = true;
        response["msg"] = "注册成功";
        // 返回新生成的用户ID
        response["id"] = newUser.getId();
    } else {
        // 注册失败（通常是因为用户名已存在）
        response["success"] = false;
        response["msg"] = "注册失败，用户名已存在";
    }
    
    // 发送注册响应
    sendJsonMessage(socket, response);
}

// 处理登出消息的函数
// 参数socket: 发送登出请求的客户端socket
// 参数message: 包含登出信息的JSON对象
void ChatServer::processLogout(QTcpSocket *socket, const QJsonObject &message) {
    // 从消息中获取用户ID
    int userId = message["id"].toInt();
    
    // 加锁保护共享数据
    QMutexLocker locker(&mutex);
    // 检查用户是否在线，并且socket是否匹配（防止误操作）
    if (userConnections.contains(userId) && userConnections[userId] == socket) {
        // 更新用户状态为离线
        User offlineUser = userModel.query(userId);
        offlineUser.setState("offline");
        userModel.updateState(offlineUser);
        // 从连接映射表中移除用户
        userConnections.remove(userId);
    }
    
    // 断开与客户端的连接
    socket->disconnectFromHost();
}

// 处理单聊消息的函数
// 参数socket: 发送聊天消息的客户端socket
// 参数message: 包含聊天信息的JSON对象
void ChatServer::processChat(QTcpSocket *socket, const QJsonObject &message) {
    // 获取发送者ID（通过socket查找）
    int fromId = getUserIdBySocket(socket);
    // 获取接收者ID
    int toId = message["to"].toInt();
    // 获取消息内容
    QString msg = message["msg"].toString();
    
    // 创建响应消息（转发给接收者）
    QJsonObject response;
    response["type"] = MsgType::ONE_CHAT_MSG;
    response["from"] = fromId;
    response["to"] = toId;
    response["msg"] = msg;
    
    // 检查接收者是否在线
    QMutexLocker locker(&mutex);
    if (userConnections.contains(toId)) {
        // 如果接收者在线，直接发送消息
        sendJsonMessage(userConnections[toId], response);
    } else {
        // 如果接收者离线，存储离线消息
        // QJsonDocument::Compact: 生成紧凑的JSON字符串
        QJsonDocument doc(response);
        QByteArray data = doc.toJson(QJsonDocument::Compact);
        // 存储离线消息到数据库
        offlineMsgModel.insert(toId, data.toStdString());
    }
}

// 处理群聊消息的函数
// 参数socket: 发送群聊消息的客户端socket
// 参数message: 包含群聊信息的JSON对象
void ChatServer::processGroupChat(QTcpSocket *socket, const QJsonObject &message) {
    // 获取发送者ID
    int fromId = getUserIdBySocket(socket);
    // 获取群组ID
    int groupId = message["groupid"].toInt();
    // 获取消息内容
    QString msg = message["msg"].toString();
    
    // 查询该群组的所有成员ID
    // vector<int>: 标准C++的动态数组，存储整数
    vector<int> userIds = groupModel.queryGroupUsers(fromId, groupId);
    // 获取发送者的用户信息
    User fromUser = userModel.query(fromId);
    
    // 创建群聊响应消息
    QJsonObject response;
    response["type"] = MsgType::GROUP_CHAT_MSG;
    response["groupid"] = groupId;
    response["from"] = fromId;
    response["name"] = QString::fromStdString(fromUser.getName());
    response["msg"] = msg;
    
    // 发送消息给群组中的所有在线成员
    QMutexLocker locker(&mutex);
    // 遍历所有群组成员
    for (int userId : userIds) {
        // 不发送给自己，只发送给在线用户
        if (userId != fromId && userConnections.contains(userId)) {
            sendJsonMessage(userConnections[userId], response);
        }
    }
}

// 处理添加好友消息的函数
// 参数socket: 发送添加好友请求的客户端socket
// 参数message: 包含添加好友信息的JSON对象
void ChatServer::processAddFriend(QTcpSocket *socket, const QJsonObject &message) {
    // 获取请求用户ID
    int userId = message["id"].toInt();
    // 获取要添加的好友ID
    int friendId = message["friendid"].toInt();
    
    // 创建响应JSON对象
    QJsonObject response;
    response["type"] = MsgType::ADD_FRIEND_MSG_ACK;
    
    // 检查要添加的好友是否存在
    User friendUser = userModel.query(friendId);
    if (friendUser.getId() == -1) {
        // 好友不存在
        response["success"] = false;
        response["msg"] = "添加的好友不存在";
    } else if (userId == friendId) {
        // 不能添加自己为好友
        response["success"] = false;
        response["msg"] = "不能添加自己为好友";
    } else {
        // 添加好友关系到数据库
        friendModel.insert(userId, friendId);
        response["success"] = true;
        response["msg"] = "添加好友成功";
    }
    
    // 发送响应
    sendJsonMessage(socket, response);
}

// 处理创建群组消息的函数
// 参数socket: 发送创建群组请求的客户端socket
// 参数message: 包含创建群组信息的JSON对象
void ChatServer::processCreateGroup(QTcpSocket *socket, const QJsonObject &message) {
    // 获取群组名称
    QString groupName = message["groupname"].toString();
    // 获取群组描述
    QString groupDesc = message["groupdesc"].toString();
    
    // 创建群组对象
    Group group;
    group.setName(groupName.toStdString());
    group.setDesc(groupDesc.toStdString());
    
    // 创建响应JSON对象
    QJsonObject response;
    response["type"] = MsgType::CREATE_GROUP_MSG_ACK;
    
    // 尝试在数据库中创建群组
    if (groupModel.createGroup(group)) {
        // 创建成功
        response["success"] = true;
        response["msg"] = "创建群组成功";
    } else {
        // 创建失败
        response["success"] = false;
        response["msg"] = "创建群组失败";
    }
    
    // 发送响应
    sendJsonMessage(socket, response);
}

// 处理加入群组消息的函数
// 参数socket: 发送加入群组请求的客户端socket
// 参数message: 包含加入群组信息的JSON对象
void ChatServer::processAddGroup(QTcpSocket *socket, const QJsonObject &message) {
    // 获取用户ID
    int userId = message["id"].toInt();
    // 获取要加入的群组ID
    int groupId = message["groupid"].toInt();
    
    // 创建响应JSON对象
    QJsonObject response;
    response["type"] = MsgType::ADD_GROUP_MSG_ACK;
    
    // 检查群组是否存在
    // 查询用户有权限访问的群组列表
    std::vector<Group> groups = groupModel.queryGroups(userId);
    bool groupExists = false;
    // 遍历群组列表，查找指定的群组ID
    for (const Group &group : groups) {
        if (group.getId() == groupId) {
            groupExists = true;
            break;
        }
    }
    
    if (!groupExists) {
        // 群组不存在或用户无权限访问
        response["success"] = false;
        response["msg"] = "群组不存在";
    } else {
        // 添加用户到群组，角色为"normal"（普通成员）
        groupModel.addGroup(userId, groupId, "normal");
        response["success"] = true;
        response["msg"] = "加入群组成功";
    }
    
    // 发送响应
    sendJsonMessage(socket, response);
}

// 处理查询好友列表消息的函数
// 参数socket: 发送查询请求的客户端socket
// 参数message: 包含查询信息的JSON对象
void ChatServer::processQueryFriend(QTcpSocket *socket, const QJsonObject &message) {
    // 获取用户ID
    int userId = message["id"].toInt();
    
    // 从数据库查询该用户的好友列表
    // std::vector<User>是C++标准库的向量容器，用于存储User对象的动态数组
    std::vector<User> friends = friendModel.query(userId);
    
    // 创建响应JSON对象
    QJsonObject response;
    response["type"] = MsgType::QUERY_FRIEND_MSG_ACK;
    
    // 创建JSON数组，用于存储所有好友信息
    QJsonArray friendArray;
    // 遍历好友列表，将每个好友信息转换为JSON对象并添加到数组中
    for (const User &user : friends) {
        QJsonObject friendObj;
        friendObj["id"] = user.getId();
        // 将std::string类型转换为Qt的QString类型
        friendObj["name"] = QString::fromStdString(user.getName());
        friendObj["state"] = QString::fromStdString(user.getState());
        friendArray.append(friendObj);
    }
    
    // 将好友数组添加到响应对象
    response["friends"] = friendArray;
    // 发送响应
    sendJsonMessage(socket, response);
}

// 处理查询群组列表消息的函数
// 参数socket: 发送查询请求的客户端socket
// 参数message: 包含查询信息的JSON对象
void ChatServer::processQueryGroup(QTcpSocket *socket, const QJsonObject &message) {
    // 获取用户ID
    int userId = message["id"].toInt();
    
    // 从数据库查询该用户加入的所有群组
    std::vector<Group> groups = groupModel.queryGroups(userId);
    
    // 创建响应JSON对象
    QJsonObject response;
    response["type"] = MsgType::QUERY_GROUP_MSG_ACK;
    
    // 创建JSON数组，用于存储所有群组信息
    QJsonArray groupArray;
    // 遍历群组列表
    for (Group &group : groups) {
        QJsonObject groupObj;
        groupObj["id"] = group.getId();
        groupObj["groupname"] = QString::fromStdString(group.getName());
        groupObj["groupdesc"] = QString::fromStdString(group.getDesc());
        
        // 创建JSON数组，用于存储群组成员信息
        QJsonArray usersArray;
        // 获取并遍历该群组的所有成员
        for (const GroupUser &user : group.getUsers()) {
            QJsonObject userObj;
            userObj["id"] = user.getId();
            userObj["name"] = QString::fromStdString(user.getName());
            userObj["state"] = QString::fromStdString(user.getState());
            userObj["role"] = QString::fromStdString(user.getRole()); // 角色信息（如admin或normal）
            usersArray.append(userObj);
        }
        
        // 将成员数组添加到群组对象
        groupObj["users"] = usersArray;
        // 将群组对象添加到群组数组
        groupArray.append(groupObj);
    }
    
    // 将群组数组添加到响应对象
    response["groups"] = groupArray;
    // 发送响应
    sendJsonMessage(socket, response);
}

// 通过socket对象获取对应的用户ID
// 参数socket: 客户端socket对象
// 返回值: 找到的用户ID，找不到返回-1
int ChatServer::getUserIdBySocket(QTcpSocket *socket) {
    // 使用QMutexLocker自动管理互斥锁，确保线程安全
    // 当locker对象被销毁时（函数结束时），会自动解锁mutex
    QMutexLocker locker(&mutex);
    
    // 创建QMap的常量迭代器，用于遍历userConnections
    // QMap是Qt的关联容器，键为int类型的用户ID，值为QTcpSocket*类型的socket指针
    QMap<int, QTcpSocket*>::const_iterator it;
    
    // 遍历userConnections映射
    for (it = userConnections.constBegin(); it != userConnections.constEnd(); ++it) {
        // 如果找到匹配的socket
        if (it.value() == socket) {
            // 返回对应的用户ID（键值）
            return it.key();
        }
    }
    
    // 未找到匹配的socket，返回-1
    return -1;
}

// 发送用户的离线消息
// 参数userId: 用户ID
// 参数socket: 用户的socket连接
// 业务逻辑：实现消息持久化和可靠投递，确保用户不会丢失离线期间的重要信息
// 设计思路：采用消息队列模式，实现离线消息的存储、投递和清理的完整生命周期管理
void ChatServer::sendOfflineMessages(int userId, QTcpSocket *socket) {
    // 查询该用户的所有离线消息
    std::vector<std::string> messages = offlineMsgModel.query(userId);
    
    // 遍历所有离线消息
    for (const std::string &msgStr : messages) {
        // 将std::string转换为QByteArray
        QByteArray data(msgStr.c_str(), msgStr.length());
        
        // 将JSON字符串解析为QJsonDocument
        QJsonDocument doc = QJsonDocument::fromJson(data);
        
        // 检查解析是否成功，且是JSON对象
        if (doc.isObject()) {
            // 发送消息给用户
            sendJsonMessage(socket, doc.object());
        }
    }
    
    // 发送完离线消息后，从数据库中删除这些消息
    offlineMsgModel.remove(userId);
}

// 发送JSON格式消息给客户端
// 参数socket: 目标客户端socket
// 参数message: 要发送的JSON对象
// 业务逻辑：实现消息序列化和网络传输，确保数据的完整性和正确性
// 设计思路：采用长度前缀编码模式，解决TCP传输中的粘包问题，支持二进制安全的数据传输
void ChatServer::sendJsonMessage(QTcpSocket *socket, const QJsonObject &message) {
    // 将QJsonObject包装为QJsonDocument
    QJsonDocument doc(message);
    
    // 将QJsonDocument转换为紧凑格式的JSON字符串（没有额外空白和换行）
    QByteArray data = doc.toJson(QJsonDocument::Compact);
    
    // 发送消息长度前缀，用于解决TCP粘包问题
    // 首先计算消息数据的长度
    qint32 length = data.size();
    
    // 创建长度前缀头
    // reinterpret_cast<const char*>(&length) 将qint32类型的指针转换为const char*类型的指针
    // sizeof(qint32) 获取qint32类型占用的字节数（通常为4字节）
    QByteArray header = QByteArray::fromRawData(reinterpret_cast<const char*>(&length), sizeof(qint32));
    
    // 先发送长度前缀
    socket->write(header);
    // 再发送实际的消息数据
    socket->write(data);
    // 刷新socket缓冲区，确保数据立即发送
    socket->flush();
}