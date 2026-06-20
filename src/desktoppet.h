#ifndef DESKTOPPET_H
#define DESKTOPPET_H

#include <QWidget>
#include <QLabel>
#include <QMovie>
#include <QPoint>
#include <QTimer>
#include <QPropertyAnimation>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include "servicemonitor.h"
#include "petmqttclient.h"
#include "globaleventbus.h"
#include "messagebubble.h"

enum class PetState { Idle, Thinking, Working, Error, Success };

/**
 * @brief 桌面宠物 + 微服务大管家
 *
 * 除了基本的待机动画和拖拽，还内置 ServiceMonitor，
 * 周期性监控 butcanthic / sandbox / ai-service 三个微服务的健康状态，
 * 通过状态机和气泡向用户实时报告。
 */
class DesktopPetWidget : public QWidget {
    Q_OBJECT

public:
    explicit DesktopPetWidget(QWidget *parent = nullptr);
    ~DesktopPetWidget();

    void changeState(PetState newState, const QString &message = "");

    /// 启动微服务监控（大管家模式）
    void startSupervising();

    /// 设置当前用户 ID（供 MainWindow 注入，碎碎念需要）
    void setUserId(const QString &userId);

protected:
    void mousePressEvent(QMouseEvent *event) override;
    void mouseMoveEvent(QMouseEvent *event) override;
    void moveEvent(QMoveEvent *event) override;
    void contextMenuEvent(QContextMenuEvent *event) override;

private slots:
    void onServiceStatusChanged(const QString &name, bool healthy, const QString &message);
    void onCheckCompleted(bool allHealthy);
    void onMumbleTimeout();
    void onMumbleReplyFinished(QNetworkReply *reply);

public slots:
    void handleGlobalEvent(const QString &source, const QString &action, const QString &message);

private:
    QLabel *petLabel;
    QMovie *petMovie;
    QPoint dragPosition;
    PetState currentState = PetState::Idle;

    // 自定义消息气泡（独立窗口）
    MessageBubble *m_bubble;

    // 回退定时器
    QTimer *fallbackTimer;

    // 大管家：微服务监控
    ServiceMonitor *monitor;
    bool firstCheckDone = false;

    // 事件总线：通过 GlobalEventBus 单例接收（不再自建 MQTT 连接）

    // 碎碎念：Idle 时拉取闪卡知识
    QTimer *m_mumbleTimer;
    QNetworkAccessManager *m_networkManager;
    QString m_currentUserId;

    QString stateToGif(PetState state) const;
    void showBubble(const QString &message);
    void hideBubble();
    void showStatusReport();
};

#endif // DESKTOPPET_H
