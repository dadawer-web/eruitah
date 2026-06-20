#ifndef PETMQTTCLIENT_H
#define PETMQTTCLIENT_H

#include <QObject>
#include <QString>
#include <QSocketNotifier>
#include <QTimer>

struct mosquitto;
struct mosquitto_message;

class PetMqttClient : public QObject {
    Q_OBJECT

public:
    explicit PetMqttClient(QObject *parent = nullptr);
    ~PetMqttClient();

    void connectToBroker(const QString &host = "127.0.0.1", int port = 1883,
                         const QString &username = "admin",
                         const QString &password = "eruitah2026");

    /// 订阅指定用户的所有微服务事件
    void subscribeUserEvents(int userId);

    void disconnectFromBroker();

    bool isConnected() const { return m_connected; }

signals:
    void connected();
    void disconnected();
    void messageReceived(const QString &topic, const QByteArray &payload);

private slots:
    void onSocketReadyRead();

private:
    struct mosquitto *m_mosq;
    QSocketNotifier *m_readNotifier;
    QSocketNotifier *m_writeNotifier;
    bool m_connected;
    QString m_host;
    int m_port;
    QString m_username;
    QString m_password;
    int m_subscribedUserId = 0;
    QTimer *m_reconnectTimer;

    static void onConnect(struct mosquitto *mosq, void *userdata, int rc);
    static void onDisconnect(struct mosquitto *mosq, void *userdata, int rc);
    static void onMessage(struct mosquitto *mosq, void *userdata,
                          const struct mosquitto_message *msg);

    void setupSocketNotifier();
    void cleanupSocketNotifiers();
    void tryReconnect();
};

#endif // PETMQTTCLIENT_H
