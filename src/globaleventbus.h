#ifndef GLOBALEVENTBUS_H
#define GLOBALEVENTBUS_H

#include <QObject>
#include <QString>

class PetMqttClient;

/**
 * @brief 全局事件总线（企业级单例）
 *
 * 作为 C++ 桌面端的中央事件枢纽，通过 MQTT 连接 RabbitMQ，
 * 接收全网微服务状态事件，并广播给所有订阅者（如桌宠）。
 *
 * 线程安全：基于 C++11 magic statics，instance() 调用线程安全。
 * 请在主线程调用 init() 以确保信号槽正常工作。
 */
class GlobalEventBus : public QObject {
    Q_OBJECT

public:
    /// 获取单例实例（线程安全，C++11 magic statics）
    static GlobalEventBus& instance();

    /// 初始化事件总线（在主线程调用）
    /// @param userId 当前登录用户 ID，用于订阅 MQTT 主题
    void init(const QString& userId);

    /// 禁用拷贝和赋值
    GlobalEventBus(const GlobalEventBus&) = delete;
    GlobalEventBus& operator=(const GlobalEventBus&) = delete;

signals:
    /// 全局事件到达信号
    /// @param source  事件来源（如 "butcanthic", "sandbox", "ai-service"）
    /// @param action  动作类型（如 "working", "error", "success", "notify"）
    /// @param message 人类可读的消息内容
    void globalEventReceived(const QString& source, const QString& action, const QString& message);

private:
    GlobalEventBus(QObject *parent = nullptr);
    ~GlobalEventBus() = default;

    /// 连接到消息代理（RabbitMQ MQTT 接口）
    void connectToMessageBroker();

    PetMqttClient *m_mqttClient;
    QString m_userId;

private slots:
    void onMqttConnected();
    void onMqttMessage(const QString &topic, const QByteArray &payload);
};

#endif // GLOBALEVENTBUS_H
