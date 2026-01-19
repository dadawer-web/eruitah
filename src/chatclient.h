#ifndef CHATCLIENT_H
#define CHATCLIENT_H

// 跨平台网络头文件处理 - 注意：先包含Windows网络头文件，再包含Qt头文件，避免byte类型歧义
#ifdef _WIN32
    #include <winsock2.h>
    #include <ws2tcpip.h>
    // 防止Windows头文件中的byte类型与Qt冲突
    #undef byte
#endif

#include <QObject>
#include <QTcpSocket>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QMap>
#include <QMutex>
#include "public.h"
#include "models/user.h"
#include "models/group.h"

/**
 * @brief The ChatClient class
 * 
 * This class implements the client-side communication logic for the chat application.
 * It handles TCP socket communication, message serialization/deserialization,
 * and provides a high-level API for chat operations.
 */
class ChatClient : public QObject {
    Q_OBJECT

public:
    /**
     * @brief Constructor for ChatClient
     * @param parent Parent QObject
     */
    ChatClient(QObject *parent = nullptr);
    
    /**
     * @brief Destructor for ChatClient
     * 
     * Ensures proper cleanup of socket resources and disconnects from server.
     */
    ~ChatClient();

    /**
     * @brief Connect to the chat server
     * @param host Server hostname or IP address
     * @param port Server port number
     * @return true if connection was successful, false otherwise
     */
    bool connectToServer(const QString &host = "127.0.0.1", quint16 port = 6000);

    /**
     * @brief Login to the chat server
     * @param userId User identification number
     * @param password User password
     */
    void login(qint64 userId, const QString &password);

    /**
     * @brief Register a new user on the server
     * @param userName Desired username
     * @param password User password
     * @param avatarPath Path to avatar image (optional)
     */
    void registerUser(const QString &userName, const QString &password, const QString &avatarPath = "");
    
    /**
     * @brief Upload a new avatar to the server
     * @param userId Current user ID
     * @param avatarPath Path to avatar image
     */
    void uploadAvatar(int userId, const QString &avatarPath);
    
    /**
     * @brief Update the user's avatar on the server
     * @param userId Current user ID
     * @param avatarPath Path to new avatar image
     */
    void updateAvatar(int userId, const QString &avatarPath);

    /**
     * @brief Logout from the server
     * @param userId User identification number
     */
    void logout(int userId);

    /**
     * @brief Send a private message to another user
     * @param toId Recipient user ID
     * @param message Message content
     */
    void sendMessage(int toId, const QString &message);

    /**
     * @brief Send a message to a group
     * @param groupId Group identification number
     * @param message Message content
     */
    void sendGroupMessage(int groupId, const QString &message);
    
    /**
     * @brief Upload an emoji to the server
     * @param userId Current user ID
     * @param emojiName Emoji name
     * @param imageData Base64 encoded image data
     */
    void uploadEmoji(int userId, const QString &emojiName, const QString &imageData);
    
    /**
     * @brief Request user's emoji list from the server
     * @param userId Current user ID
     */
    void requestEmojiList(int userId);

    /**
     * @brief Send friend request to another user
     * @param userId Current user ID
     * @param friendId Target user ID to add as friend
     */
    void addFriend(int userId, int friendId);

    /**
     * @brief Create a new chat group
     * @param userId Creator user ID
     * @param groupName Name of the new group
     * @param groupDesc Description of the new group
     */
    void createGroup(int userId, const QString &groupName, const QString &groupDesc);

    /**
     * @brief Join an existing chat group
     * @param userId User ID requesting to join
     * @param groupId Group ID to join
     */
    void joinGroup(int userId, int groupId);

    /**
     * @brief Request the list of friends for a user
     * @param userId User ID to query
     */
    void requestFriendList(int userId);

    /**
     * @brief Request the list of groups for a user
     * @param userId User ID to query
     */
    void requestGroupList(int userId);

    /**
     * @brief Send file transfer request to another user
     * @param fromId Sender user ID
     * @param toId Recipient user ID
     * @param filename Name of the file to transfer
     * @param filesize Size of the file in bytes
     * @param fileId Unique identifier for the file transfer (optional, will be generated if not provided)
     */
    void sendFileRequest(int fromId, int toId, const QString &filename, qint64 filesize, const QString &fileId = QString());
    
    /**
     * @brief Send chunk of file data during file transfer
     * @param fromId Sender user ID
     * @param toId Recipient user ID
     * @param fileId Unique identifier for the file transfer
     * @param chunkIndex Index of the current data chunk
     * @param data Raw file data for this chunk
     */
    void sendFileData(int fromId, int toId, const QString &fileId, int chunkIndex, const QByteArray &data);
    
    /**
     * @brief Notify completion of file transfer
     * @param fromId Sender user ID
     * @param toId Recipient user ID
     * @param fileId Unique identifier for the file transfer
     * @param success Whether the transfer completed successfully
     */
    void sendFileTransferComplete(int fromId, int toId, const QString &fileId, bool success);
    
    /**
     * @brief Respond to a file transfer request
     * @param fromId Sender's user ID
     * @param toId Recipient's user ID
     * @param fileId Unique identifier for the file transfer
     * @param accept Whether to accept the file transfer
     */
    void acceptFileTransfer(int fromId, int toId, const QString &fileId, bool accept);

    /**
     * @brief Set the current user ID
     * @param id User ID
     */
    void setUserId(int id) { currentUserId = id; }
    
    /**
     * @brief Get the current user ID
     * @return Current user ID
     */
    int getUserId() const { return currentUserId; }
    
    /**
     * @brief Get the current user avatar
     * @return Current user avatar data (Base64 encoded)
     */
    QString getCurrentUserAvatar() const { return currentUserAvatar; }

private:
    QTcpSocket *socket;          // TCP socket for server communication
    QMutex mutex;                // Mutex to protect socket operations
    bool isConnected;            // Flag indicating connection status
    int currentUserId;           // Currently logged-in user ID
    QList<QJsonObject> offlineMessages; // Queue to store offline messages until ChatWindow is ready
    QString currentUserAvatar;    // Currently logged-in user avatar data (Base64 encoded)

public:
    /**
     * @brief Generate a unique file ID for file transfers
     * @return Unique string identifier
     */
    QString generateFileId();

    /**
     * @brief Send a JSON-formatted message to the server
     * @param message JSON object containing the message data
     */
    void sendJsonMessage(const QJsonObject &message);

    /**
     * @brief Process a message received from the server
     * @param message JSON object containing the message data
     * 
     * This method routes messages based on their type and emits appropriate signals.
     */
    void processMessage(const QJsonObject &message);
    
    /**
     * @brief Process an offline message from the server
     * @param message JSON object containing the offline message data
     * 
     * This method handles offline messages received during login and emits appropriate signals.
     */
    void processOfflineMessage(const QJsonObject &message);
    
    /**
     * @brief Process all stored offline messages
     * 
     * This method should be called after the ChatWindow has connected its signal handlers.
     * It processes all offline messages stored in the queue.
     */
    void processStoredOfflineMessages();

private slots:
    /**
     * @brief Slot called when connection to server is established
     */
    void onConnected();
    
    /**
     * @brief Slot called when connection to server is closed
     */
    void onDisconnected();
    
    /**
     * @brief Slot called when data is available to read from the socket
     */
    void onReadyRead();
    
    /**
     * @brief Slot called when a socket error occurs
     * @param socketError Error code
     */
    void onError(QAbstractSocket::SocketError socketError);

 signals:
    // Connection status signals
    void connected();                                 // Emitted when connection is established
    void disconnected();                              // Emitted when connection is closed
    void error(const QString &errorMsg);              // Emitted when an error occurs
    void connectionStateChanged(bool connected);      // Emitted when connection state changes

    // Login related signals
    void loginResponse(bool success, const QString &message);  // Response to login attempt

    // Message related signals
    void messageReceived(int fromId, const QString &message, const QString &fromName = "", bool isGroup = false, int groupId = -1, const QString &timestamp = "");
    void groupMessageReceived(int groupId, int fromId, const QString &userName, const QString &message, const QString &timestamp = "", const QString &avatar = "");

    // Friend related signals
    void friendListUpdated(const QList<User> &friends);        // New friend list available
    void friendAdded(bool success, const QString &message);    // Response to friend request
    void addFriendResponse(bool success, const QString &message);

    // Group related signals
    void groupListUpdated(const QList<Group> &groups);         // New group list available
    void groupCreated(bool success, const QString &message);   // Response to group creation
    void groupJoined(bool success, const QString &message);    // Response to group join request
    void createGroupResponse(bool success, const QString &message);
    void addGroupResponse(bool success, const QString &message);

    // File transfer related signals
    void fileTransferRequestReceived(int fromId, const QString &filename, qint64 filesize, const QString &fileId);
    void fileTransferAccepted(const QString &fileId, bool accepted);
    void fileTransferDataReceived(const QString &fileId, int chunkIndex, const QByteArray &data);
    void fileTransferCompleteReceived(const QString &fileId, bool success);
    void fileTransferError(const QString &fileId, int errorCode, const QString &errorMsg);
    void registerResponse(bool success, int userId, const QString &message);
    
    // Emoji related signals
    void emojiUploadResponse(bool success, const QString &message);
    void emojiListUpdated(const QList<QJsonObject> &emojis);
    
    // Avatar related signals
    void avatarUpdated(const QString &avatarPath);
    void userAvatarReceived(const QString &avatarPath);
    
    // User state update signal
    void friendStateUpdated(qint64 userId, const QString &state);
};

#endif // CHATCLIENT_H