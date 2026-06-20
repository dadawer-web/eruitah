#ifndef SERVICEMONITOR_H
#define SERVICEMONITOR_H

#include <QObject>
#include <QNetworkAccessManager>
#include <QTimer>
#include <QMap>
#include <QString>
#include <QList>

struct ServiceInfo {
    QString name;
    QString healthUrl;
    bool healthy = false;
    bool firstCheck = true;
    QString lastError;
};

/**
 * @brief 微服务健康监控器
 *
 * 负责周期性轮询各微服务的健康检查端点，
 * 当服务状态发生变化时发出信号。
 *
 * 未来可被 RabbitMQ 推送模式替代——
 * 只需创建另一个 notifier 发射相同的 serviceStatusChanged 信号即可。
 */
class ServiceMonitor : public QObject {
    Q_OBJECT

public:
    explicit ServiceMonitor(QObject *parent = nullptr);
    ~ServiceMonitor();

    void addService(const QString &name, const QString &healthUrl);
    void startMonitoring(int intervalMs = 10000);
    void stopMonitoring();
    void checkNow();
    QList<ServiceInfo> getAllStatus() const;
    bool allHealthy() const;

signals:
    /// 某个服务状态发生变化（上线/下线）时发出
    void serviceStatusChanged(const QString &name, bool healthy, const QString &message);
    /// 一轮完整检查结束后发出
    void checkCompleted(bool allHealthy);

private:
    QNetworkAccessManager *networkManager;
    QTimer *pollTimer;
    QMap<QString, ServiceInfo> services;
    int pendingChecks = 0;

    void checkService(const QString &name);
    void onReplyFinished(const QString &name, QNetworkReply *reply);
};

#endif // SERVICEMONITOR_H
