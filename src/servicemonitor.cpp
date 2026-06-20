#include "servicemonitor.h"
#include <QNetworkRequest>
#include <QNetworkReply>
#include <QUrl>

ServiceMonitor::ServiceMonitor(QObject *parent)
    : QObject(parent)
    , networkManager(new QNetworkAccessManager(this))
    , pollTimer(new QTimer(this))
{
    pollTimer->setSingleShot(false);
    connect(pollTimer, &QTimer::timeout, this, &ServiceMonitor::checkNow);
}

ServiceMonitor::~ServiceMonitor() {
    stopMonitoring();
}

void ServiceMonitor::addService(const QString &name, const QString &healthUrl) {
    ServiceInfo info;
    info.name = name;
    info.healthUrl = healthUrl;
    info.healthy = false;
    info.firstCheck = true;
    services.insert(name, info);
}

void ServiceMonitor::startMonitoring(int intervalMs) {
    pollTimer->start(intervalMs);
    // 立即执行首轮检查
    checkNow();
}

void ServiceMonitor::stopMonitoring() {
    if (pollTimer->isActive()) {
        pollTimer->stop();
    }
}

void ServiceMonitor::checkNow() {
    if (services.isEmpty()) {
        return;
    }
    pendingChecks = services.size();
    for (const QString &name : services.keys()) {
        checkService(name);
    }
}

void ServiceMonitor::checkService(const QString &name) {
    const ServiceInfo &info = services.value(name);
    QNetworkRequest request{QUrl(info.healthUrl)};
    request.setRawHeader("User-Agent", "DesktopPet/1.0");
    request.setTransferTimeout(5000); // 5秒超时

    QNetworkReply *reply = networkManager->get(request);
    connect(reply, &QNetworkReply::finished, this, [this, name, reply]() {
        onReplyFinished(name, reply);
    });
}

void ServiceMonitor::onReplyFinished(const QString &name, QNetworkReply *reply) {
    ServiceInfo &info = services[name];
    bool wasHealthy = info.healthy;
    bool nowHealthy = false;
    QString message;

    if (reply->error() == QNetworkReply::NoError) {
        int statusCode = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        if (statusCode >= 200 && statusCode < 300) {
            nowHealthy = true;
            info.lastError.clear();
        } else {
            info.lastError = QString("HTTP %1").arg(statusCode);
        }
    } else {
        info.lastError = reply->errorString();
    }

    info.healthy = nowHealthy;

    // 状态发生变化或首次检查
    if (info.firstCheck || wasHealthy != nowHealthy) {
        if (nowHealthy) {
            message = QString("%1 已上线").arg(name);
        } else {
            message = QString("%1 不可用: %2").arg(name, info.lastError);
        }
        emit serviceStatusChanged(name, nowHealthy, message);
    }

    info.firstCheck = false;

    reply->deleteLater();

    pendingChecks--;
    if (pendingChecks <= 0) {
        emit checkCompleted(allHealthy());
    }
}

QList<ServiceInfo> ServiceMonitor::getAllStatus() const {
    return services.values();
}

bool ServiceMonitor::allHealthy() const {
    for (const ServiceInfo &info : services) {
        if (!info.healthy) {
            return false;
        }
    }
    return !services.isEmpty();
}
