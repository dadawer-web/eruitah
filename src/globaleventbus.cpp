#include "globaleventbus.h"
#include "petmqttclient.h"
#include <QDebug>
#include <QJsonDocument>
#include <QJsonObject>

GlobalEventBus& GlobalEventBus::instance() {
    static GlobalEventBus s_instance;
    return s_instance;
}

GlobalEventBus::GlobalEventBus(QObject *parent)
    : QObject(parent)
    , m_mqttClient(nullptr)
{
}

void GlobalEventBus::init(const QString& userId) {
    // 防止重复初始化（单例只连一次 MQTT）
    if (m_mqttClient) {
        qDebug() << "[GlobalEventBus] 已初始化，跳过重复调用";
        return;
    }
    m_userId = userId;
    qDebug() << "[GlobalEventBus] 初始化, userId =" << userId;
    connectToMessageBroker();
}

void GlobalEventBus::connectToMessageBroker() {
    m_mqttClient = new PetMqttClient(this);

    connect(m_mqttClient, &PetMqttClient::connected,
            this, &GlobalEventBus::onMqttConnected);
    connect(m_mqttClient, &PetMqttClient::messageReceived,
            this, &GlobalEventBus::onMqttMessage);

    // 先设置订阅用户 ID（connectToBroker 需要它生成唯一 client ID）
    m_mqttClient->subscribeUserEvents(m_userId.toInt());

    m_mqttClient->connectToBroker("127.0.0.1", 1883, "admin", "eruitah2026");
    qDebug() << "[GlobalEventBus] 正在连接 MQTT 消息代理 127.0.0.1:1883";
}

void GlobalEventBus::onMqttConnected() {
    qDebug() << "[GlobalEventBus] MQTT 已连接，用户" << m_userId << "的事件已订阅";
    // 订阅已在 connectToBroker 前设置，onConnect 回调会自动重新订阅
    // 这里不再重复调用 subscribeUserEvents
}

void GlobalEventBus::onMqttMessage(const QString &topic, const QByteArray &payload) {
    // 解析 JSON
    QJsonParseError parseErr;
    QJsonDocument doc = QJsonDocument::fromJson(payload, &parseErr);
    if (parseErr.error != QJsonParseError::NoError) {
        qWarning() << "[GlobalEventBus] JSON 解析失败:" << parseErr.errorString();
        return;
    }

    QJsonObject obj = doc.object();
    QString action = obj.value("action").toString();
    QString message = obj.value("msg").toString();
    if (message.isEmpty()) {
        message = obj.value("message").toString();
    }

    // 从 topic 提取 source（最后一段）
    // topic 格式: aios.events.user_{userId}.{source}
    QString source = topic.section('/', -1);
    if (source.isEmpty()) {
        source = obj.value("source").toString("unknown");
    }

    qDebug() << "[GlobalEventBus] 收到事件 → source:" << source
             << "action:" << action << "message:" << message;

    emit globalEventReceived(source, action, message);
}
