#ifndef CHATSERVER_H
#define CHATSERVER_H

#include <QObject>
#include <QTcpServer>
#include <QTcpSocket>
#include <QMap>
#include <QMutex>
#include "models/usermodel.h"
#include "models/friendmodel.h"
#include "models/groupmodel.h"
#include "models/offlinemessagemodel.h"

/**
 * @brief The ChatServer class
 * 
 * This class implements the server-side logic for the chat application.
 * It manages client connections, processes messages, and coordinates
 * the various models for data storage and retrieval.
 */
class ChatServer : public QObject {
    Q_OBJECT

public:
    /**
     * @brief Constructor for ChatServer
     * @param parent Parent QObject
     */
    ChatServer(QObject *parent = nullptr);
    
    /**
     * @brief Destructor for ChatServer
     * 
     * Ensures proper cleanup of server resources and disconnects all clients.
     */
    ~ChatServer();

    /**
     * @brief Start the chat server
     * @param port Port number to listen on
     * @return true if server started successfully, false otherwise
     */
    bool startServer(quint16 port = 6000);
    
    /**
     * @brief Stop the chat server
     * 
     * Disconnects all clients and stops listening for new connections.
     */
    void stopServer();

private:
    QTcpServer *server;
    
    /**
     * @brief Map of client connections
     * 
     * Stores active client connections with user ID as the key and the corresponding socket as value.
     */
    QMap<int, QTcpSocket*> userConnections;
    QMutex mutex; // Mutex to protect the userConnections map
    
    // Data models
    UserModel userModel;       // Handles user registration and authentication
    FriendModel friendModel;   // Manages friend relationships
    GroupModel groupModel;     // Manages chat groups and memberships
    OfflineMsgModel offlineMsgModel; // Stores messages for offline users
    
    /**
     * @brief Handle a new client connection
     * 
     * Set up signal/slot connections for the new socket and prepare for message handling.
     */
    void handleNewConnection();
    
    /**
     * @brief Handle client disconnection
     * @param socket The socket that was disconnected
     * 
     * Clean up resources and update connection tracking.
     */
    void handleDisconnected(QTcpSocket *socket);
    
    /**
     * @brief Process data received from a client
     * @param socket The socket that received data
     * 
     * Read and parse messages from the socket buffer.
     */
    void handleReadyRead(QTcpSocket *socket);
    
    /**
     * @brief Parse JSON-formatted message
     * @param data Raw message data
     * @return Parsed JSON object
     */
    QJsonObject parseJsonMessage(const QByteArray &data);
    
    /**
     * @brief Send JSON-formatted message to client
     * @param socket Target socket
     * @param message JSON object to send
     */
    void sendJsonMessage(QTcpSocket *socket, const QJsonObject &message);
    
    // Message processing methods
    void processLogin(QTcpSocket *socket, const QJsonObject &message);
    void processRegister(QTcpSocket *socket, const QJsonObject &message);
    void processLogout(QTcpSocket *socket, const QJsonObject &message);
    void processChat(QTcpSocket *socket, const QJsonObject &message);
    void processGroupChat(QTcpSocket *socket, const QJsonObject &message);
    void processAddFriend(QTcpSocket *socket, const QJsonObject &message);
    void processCreateGroup(QTcpSocket *socket, const QJsonObject &message);
    void processAddGroup(QTcpSocket *socket, const QJsonObject &message);
    void processQueryFriend(QTcpSocket *socket, const QJsonObject &message);
    void processQueryGroup(QTcpSocket *socket, const QJsonObject &message);
    
    /**
     * @brief Get user ID associated with a socket
     * @param socket The socket to look up
     * @return User ID if found, -1 otherwise
     */
    int getUserIdBySocket(QTcpSocket *socket);
    
    /**
     * @brief Send stored offline messages to a newly connected user
     * @param userId User ID to send messages to
     * @param socket Target socket for delivery
     */
    void sendOfflineMessages(int userId, QTcpSocket *socket);

private slots:
    /**
     * @brief Slot called when a new client connects
     */
    void onNewConnection();
    
    /**
     * @brief Slot called when a client disconnects
     */
    void onDisconnected();
    
    /**
     * @brief Slot called when data is available from a client
     */
    void onReadyRead();
    
    /**
     * @brief Slot called when a socket error occurs
     * @param socketError Error code
     */
    void onError(QAbstractSocket::SocketError socketError);
};

#endif // CHATSERVER_H