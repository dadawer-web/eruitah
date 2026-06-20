#include "petmqttclient.h"
#include <QJsonDocument>
#include <QJsonObject>
#include <QDebug>
#include <mosquitto.h>

PetMqttClient::PetMqttClient(QObject *parent)
    : QObject(parent)
    , m_mosq(nullptr)
    , m_readNotifier(nullptr)
    , m_writeNotifier(nullptr)
    , m_connected(false)
    , m_port(1883)
    , m_reconnectTimer(nullptr)
{
    mosquitto_lib_init();
}

PetMqttClient::~PetMqttClient() {
    disconnectFromBroker();
    mosquitto_lib_cleanup();
}

void PetMqttClient::connectToBroker(const QString &host, int port,
                                     const QString &username,
                                     const QString &password) {
    m_host = host;
    m_port = port;
    m_username = username;
    m_password = password;

    // 清理旧连接
    if (m_mosq) {
        cleanupSocketNotifiers();
        mosquitto_disconnect(m_mosq);
        mosquitto_destroy(m_mosq);
        m_mosq = nullptr;
        m_connected = false;
    }

    // 创建 mosquitto 实例（client ID 带 userId 后缀，多用户不冲突）
    QByteArray clientId = QString("desktop_pet_%1").arg(m_subscribedUserId).toUtf8();
    m_mosq = mosquitto_new(clientId.constData(), true, this);
    if (!m_mosq) {
        qWarning() << "[PetMqtt] 创建 mosquitto 实例失败";
        return;
    }

    // 设置认证
    if (!username.isEmpty()) {
        mosquitto_username_pw_set(m_mosq,
                                  username.toUtf8().constData(),
                                  password.toUtf8().constData());
    }

    // 注册回调
    mosquitto_connect_callback_set(m_mosq, onConnect);
    mosquitto_disconnect_callback_set(m_mosq, onDisconnect);
    mosquitto_message_callback_set(m_mosq, onMessage);

    // 连接
    int rc = mosquitto_connect(m_mosq,
                               host.toUtf8().constData(),
                               port,
                               60);  // 60秒心跳
    if (rc != MOSQ_ERR_SUCCESS) {
        qWarning() << "[PetMqtt] 连接失败:" << mosquitto_strerror(rc)
                   << "host=" << host << "port=" << port;
        tryReconnect();
        return;
    }

    // 设置 socket notifier 集成到 Qt 事件循环
    setupSocketNotifier();
}

void PetMqttClient::setupSocketNotifier() {
    if (!m_mosq) return;

    int fd = mosquitto_socket(m_mosq);
    if (fd < 0) {
        qWarning() << "[PetMqtt] 获取 socket fd 失败";
        return;
    }

    // 读监听
    m_readNotifier = new QSocketNotifier(fd, QSocketNotifier::Read, this);
    connect(m_readNotifier, &QSocketNotifier::activated,
            this, &PetMqttClient::onSocketReadyRead);
    m_readNotifier->setEnabled(true);

    // 写监听（用于处理待发送数据）
    m_writeNotifier = new QSocketNotifier(fd, QSocketNotifier::Write, this);
    m_writeNotifier->setEnabled(false);  // 默认禁用，有数据待发时才启用
}

void PetMqttClient::cleanupSocketNotifiers() {
    if (m_readNotifier) {
        m_readNotifier->setEnabled(false);
        delete m_readNotifier;
        m_readNotifier = nullptr;
    }
    if (m_writeNotifier) {
        m_writeNotifier->setEnabled(false);
        delete m_writeNotifier;
        m_writeNotifier = nullptr;
    }
}

void PetMqttClient::onSocketReadyRead() {
    if (!m_mosq) return;

    // 让 mosquitto 处理网络 I/O（非阻塞）
    int rc = mosquitto_loop_read(m_mosq, 1);
    if (rc != MOSQ_ERR_SUCCESS) {
        qWarning() << "[PetMqtt] loop_read 错误:" << mosquitto_strerror(rc);
        // 连接丢失，触发重连
        m_connected = false;
        cleanupSocketNotifiers();
        emit disconnected();
        tryReconnect();
        return;
    }

    // 处理写缓冲（如果有待发送消息）
    mosquitto_loop_write(m_mosq, 1);

    // 处理心跳和重连逻辑
    mosquitto_loop_misc(m_mosq);
}

void PetMqttClient::onConnect(struct mosquitto *mosq, void *userdata, int rc) {
    PetMqttClient *self = static_cast<PetMqttClient*>(userdata);
    if (!self) return;

    if (rc == 0) {
        self->m_connected = true;
        qDebug() << "[PetMqtt] 已连接到 RabbitMQ MQTT 接口";

        // 停止重连定时器
        if (self->m_reconnectTimer) {
            self->m_reconnectTimer->stop();
        }

        // 重新订阅（如果之前有订阅过）
        if (self->m_subscribedUserId > 0) {
            self->subscribeUserEvents(self->m_subscribedUserId);
        }

        emit self->connected();
    } else {
        self->m_connected = false;
        qWarning() << "[PetMqtt] 连接被拒绝, rc=" << rc;
        emit self->disconnected();
    }
}

void PetMqttClient::onDisconnect(struct mosquitto *mosq, void *userdata, int rc) {
    PetMqttClient *self = static_cast<PetMqttClient*>(userdata);
    if (!self) return;

    self->m_connected = false;
    self->cleanupSocketNotifiers();

    if (rc == 0) {
        qDebug() << "[PetMqtt] 正常断开连接";
    } else {
        qWarning() << "[PetMqtt] 意外断开连接, rc=" << rc
                   << mosquitto_strerror(rc);
        // 意外断开，触发自动重连
        self->tryReconnect();
    }

    emit self->disconnected();
}

void PetMqttClient::onMessage(struct mosquitto *mosq, void *userdata,
                               const struct mosquitto_message *msg) {
    PetMqttClient *self = static_cast<PetMqttClient*>(userdata);
    if (!self || !msg) return;

    QString topic(QString::fromUtf8(msg->topic));
    QByteArray payload(static_cast<const char*>(msg->payload), msg->payloadlen);

    qDebug() << "[PetMqtt] 收到消息:" << topic << payload;

    emit self->messageReceived(topic, payload);
}

void PetMqttClient::subscribeUserEvents(int userId) {
    m_subscribedUserId = userId;  // 记住，重连后自动重新订阅

    if (!m_mosq || !m_connected) {
        qWarning() << "[PetMqtt] 未连接，无法订阅（将在重连后自动订阅）";
        return;
    }

    // 主题: aios/events/user_{userId}/#
    QString topic = QString("aios/events/user_%1/#").arg(userId);
    int rc = mosquitto_subscribe(m_mosq, nullptr,
                                  topic.toUtf8().constData(),
                                  0);  // QoS 0
    if (rc == MOSQ_ERR_SUCCESS) {
        qDebug() << "[PetMqtt] 已订阅主题:" << topic;
    } else {
        qWarning() << "[PetMqtt] 订阅失败:" << mosquitto_strerror(rc)
                   << "topic=" << topic;
    }
}

void PetMqttClient::tryReconnect() {
    // 避免重复启动重连定时器
    if (m_reconnectTimer && m_reconnectTimer->isActive()) {
        return;
    }

    qWarning() << "[PetMqtt] 将在 3 秒后尝试重连...";

    if (!m_reconnectTimer) {
        m_reconnectTimer = new QTimer(this);
        m_reconnectTimer->setSingleShot(true);
        connect(m_reconnectTimer, &QTimer::timeout, this, [this]() {
            qDebug() << "[PetMqtt] 正在重连...";
            connectToBroker(m_host, m_port, m_username, m_password);
        });
    }

    m_reconnectTimer->start(3000);
}

void PetMqttClient::disconnectFromBroker() {
    if (m_reconnectTimer) {
        m_reconnectTimer->stop();
    }

    cleanupSocketNotifiers();

    if (m_mosq) {
        mosquitto_disconnect(m_mosq);
        mosquitto_destroy(m_mosq);
        m_mosq = nullptr;
    }

    m_connected = false;
    emit disconnected();
}
