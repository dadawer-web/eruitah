#include "desktoppet.h"
#include <QMouseEvent>
#include <QMoveEvent>
#include <QApplication>
#include <QScreen>
#include <QMenu>
#include <QAction>
#include <QContextMenuEvent>
#include <QMessageBox>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QNetworkRequest>
#include <QUrl>
#include <QRandomGenerator>

DesktopPetWidget::DesktopPetWidget(QWidget *parent)
    : QWidget(nullptr, Qt::FramelessWindowHint | Qt::WindowStaysOnTopHint | Qt::Tool)
{
    setAttribute(Qt::WA_TranslucentBackground);
    // 强制干掉全局 QSS 赋予的背景色和边框
    this->setStyleSheet("background: transparent; border: none;");

    setFixedSize(192, 240); // 加高以容纳气泡

    petLabel = new QLabel(this);
    petLabel->setAttribute(Qt::WA_TranslucentBackground);
    petLabel->setStyleSheet("background: transparent; border: none;");
    petMovie = new QMovie(":/icons/pet_idle.gif");
    petMovie->setScaledSize(QSize(192, 192));
    petLabel->setMovie(petMovie);
    petLabel->setGeometry(0, 48, 192, 192); // 下移给气泡留空间
    petMovie->start();

    // 自定义消息气泡（独立窗口，不传 parent）
    m_bubble = new MessageBubble();

    // 回退定时器
    fallbackTimer = new QTimer(this);
    fallbackTimer->setSingleShot(true);
    connect(fallbackTimer, &QTimer::timeout, this, [this]() {
        changeState(PetState::Idle);
    });

    // 大管家：微服务监控器
    monitor = new ServiceMonitor(this);
    monitor->addService("butcanthic", "http://127.0.0.1:8002/api/v1/health");
    monitor->addService("sandbox",    "http://127.0.0.1:8001/api/v1/health");
    monitor->addService("ai-service", "http://127.0.0.1:8081/api/ai/health");

    connect(monitor, &ServiceMonitor::serviceStatusChanged,
            this, &DesktopPetWidget::onServiceStatusChanged);
    connect(monitor, &ServiceMonitor::checkCompleted,
            this, &DesktopPetWidget::onCheckCompleted);

    // 事件总线：通过 GlobalEventBus 单例接收 MQTT 事件
    connect(&GlobalEventBus::instance(),
            &GlobalEventBus::globalEventReceived,
            this, &DesktopPetWidget::handleGlobalEvent);

    // 碎碎念：Idle 时定时拉取闪卡知识
    m_mumbleTimer = new QTimer(this);
    m_mumbleTimer->setSingleShot(false);
    connect(m_mumbleTimer, &QTimer::timeout,
            this, &DesktopPetWidget::onMumbleTimeout);

    m_networkManager = new QNetworkAccessManager(this);
    connect(m_networkManager, &QNetworkAccessManager::finished,
            this, &DesktopPetWidget::onMumbleReplyFinished);

    // 初始位置：屏幕右下角
    QScreen *screen = QApplication::primaryScreen();
    if (screen) {
        QRect screenGeometry = screen->geometry();
        move(screenGeometry.right() - 160,
             screenGeometry.bottom() - 190);
    }
}

DesktopPetWidget::~DesktopPetWidget() {
    if (petMovie) {
        petMovie->stop();
        delete petMovie;
    }
    delete m_bubble;
}

void DesktopPetWidget::startSupervising() {
    changeState(PetState::Thinking, "正在检查微服务...");
    monitor->startMonitoring(10000); // 每10秒轮询一次
}

void DesktopPetWidget::setUserId(const QString &userId) {
    m_currentUserId = userId;
    // 初始化全局事件总线（单例 MQTT 连接）
    GlobalEventBus::instance().init(userId);
    // 如果当前是 Idle，立即启动碎碎念
    if (currentState == PetState::Idle && !userId.isEmpty()) {
        m_mumbleTimer->start(30000);
    }
}

void DesktopPetWidget::handleGlobalEvent(const QString &source, const QString &action, const QString &message) {
    qDebug() << "[DesktopPet] 收到全局事件:" << source << action << message;

    // 构造气泡提示文本（带上来源标识）
    QString bubbleText = QString("[%1] %2").arg(source, message);

    if (action == "working") {
        changeState(PetState::Working, bubbleText);
    } else if (action == "error") {
        changeState(PetState::Error, bubbleText);
    } else if (action == "success") {
        changeState(PetState::Success, bubbleText);
    } else if (action == "notify") {
        // notify：仅弹出气泡提示，不切换 GIF（保持当前状态）
        showBubble(bubbleText);
    } else if (action == "thinking") {
        changeState(PetState::Thinking, bubbleText);
    } else if (action == "idle") {
        changeState(PetState::Idle, bubbleText);
    }
}

QString DesktopPetWidget::stateToGif(PetState state) const {
    switch (state) {
    case PetState::Thinking: return ":/icons/pet_thinking.gif";
    case PetState::Working:  return ":/icons/pet_working.gif";
    case PetState::Error:    return ":/icons/pet_error.gif";
    case PetState::Success:  return ":/icons/pet_success.gif";
    case PetState::Idle:
    default:                 return ":/icons/pet_idle.gif";
    }
}

void DesktopPetWidget::changeState(PetState newState, const QString &message) {
    if (currentState == newState && message.isEmpty())
        return;

    currentState = newState;

    // 切换 GIF
    petMovie->stop();
    petMovie->setFileName(stateToGif(newState));
    petMovie->start();

    // 气泡
    if (!message.isEmpty()) {
        showBubble(message);
    } else {
        hideBubble();
    }

    // Error / Success 5秒后回退到 Idle
    fallbackTimer->stop();
    if (newState == PetState::Error || newState == PetState::Success) {
        fallbackTimer->start(5000);
    }

    // 碎碎念：Idle 时启动定时器，非 Idle 时停止
    if (newState == PetState::Idle) {
        if (!m_currentUserId.isEmpty()) {
            m_mumbleTimer->start(30000); // 每30秒碎碎念一次
        }
    } else {
        m_mumbleTimer->stop();
    }
}

void DesktopPetWidget::onServiceStatusChanged(const QString &name, bool healthy, const QString &message) {
    if (healthy) {
        changeState(PetState::Success, message);
    } else {
        changeState(PetState::Error, message);
    }
}

void DesktopPetWidget::onCheckCompleted(bool allHealthy) {
    if (!firstCheckDone) {
        firstCheckDone = true;
        if (allHealthy) {
            changeState(PetState::Success, "所有服务正常运行!");
        } else {
            // 已有 Error 状态由 onServiceStatusChanged 处理
            // 汇总一下哪些挂了
            QStringList downList;
            for (const ServiceInfo &info : monitor->getAllStatus()) {
                if (!info.healthy) {
                    downList << info.name;
                }
            }
            if (!downList.isEmpty()) {
                changeState(PetState::Error, QString("异常: %1").arg(downList.join(", ")));
            }
        }
    }
    // 后续检查只在状态变化时才改变宠物状态（由 onServiceStatusChanged 处理）
}

void DesktopPetWidget::showStatusReport() {
    QStringList lines;
    lines << "===== 微服务状态报告 =====";
    for (const ServiceInfo &info : monitor->getAllStatus()) {
        QString status = info.healthy ? "✅ 正常" : "❌ 异常";
        QString detail = info.lastError.isEmpty() ? "" : QString(" (%1)").arg(info.lastError);
        lines << QString("%1: %2%3").arg(info.name, status, detail);
    }
    QMessageBox::information(this, "桌宠大管家", lines.join("\n"));
}

void DesktopPetWidget::showBubble(const QString &message) {
    m_bubble->showMessage(message, geometry().topLeft());
}

void DesktopPetWidget::hideBubble() {
    m_bubble->hide();
}

void DesktopPetWidget::moveEvent(QMoveEvent *event) {
    QWidget::moveEvent(event);
    // 拖拽时气泡跟着走
    if (m_bubble && m_bubble->isVisible()) {
        m_bubble->updatePosition(geometry().topLeft());
    }
}

void DesktopPetWidget::mousePressEvent(QMouseEvent *event) {
    if (event->button() == Qt::LeftButton) {
        dragPosition = event->globalPos() - frameGeometry().topLeft();
        event->accept();
    }
}

void DesktopPetWidget::mouseMoveEvent(QMouseEvent *event) {
    if (event->buttons() & Qt::LeftButton) {
        move(event->globalPos() - dragPosition);
        event->accept();
    }
}

void DesktopPetWidget::contextMenuEvent(QContextMenuEvent *event) {
    QMenu menu(this);

    QAction *statusAction = menu.addAction("📊 服务状态报告");
    QAction *checkAction  = menu.addAction("🔍 立即检查");
    menu.addSeparator();
    QAction *hideAction   = menu.addAction("🙈 隐藏桌宠");

    QAction *selected = menu.exec(event->globalPos());

    if (selected == statusAction) {
        showStatusReport();
    } else if (selected == checkAction) {
        changeState(PetState::Thinking, "正在检查...");
        monitor->checkNow();
    } else if (selected == hideAction) {
        hide();
    }
}

void DesktopPetWidget::onMumbleTimeout() {
    if (m_currentUserId.isEmpty() || currentState != PetState::Idle) {
        return;
    }

    // 关怀语料库
    static const QStringList relaxingMessages = {
        "主人，盯屏幕这么久了，闭上眼睛转转眼球吧~ 喵！",
        "408虽然难，但身体更重要哦，站起来伸个懒腰吧！",
        "代码是写不完的，去喝杯温水休息一下怎么样？",
        "喵~ 农场的植物们都在努力生长，你也要好好照顾自己呀！",
        "别太累啦，深呼吸，AI 管家一直在陪着你哦~",
        "主人，该喝水啦！久坐伤身，起来走两步吧~",
        "学习很重要，但你的眼睛更需要休息，看看远处吧！",
        "喵呜~ 检测到主人已连续作战，建议摸鱼5分钟！",
    };

    // 概率扭蛋：60% 闪卡 / 40% 关怀
    int roll = QRandomGenerator::global()->bounded(100);

    if (roll < 60) {
        // 60%：向后端拉取知识闪卡（使用 X-User-Id 请求头，符合 butcanthic 接口规范）
        QString url = QString("http://127.0.0.1:8002/api/v1/flashcards/draw?limit=1");
        QNetworkRequest request{QUrl(url)};
        request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");
        request.setRawHeader("X-User-Id", m_currentUserId.toUtf8());

        qDebug() << "[DesktopPet] 碎碎念(闪卡 roll=" << roll << "):" << url
                 << "X-User-Id=" << m_currentUserId;
        m_networkManager->get(request);
    } else {
        // 40%：随机抽取关怀话术
        int idx = QRandomGenerator::global()->bounded(relaxingMessages.size());
        QString msg = relaxingMessages[idx];

        qDebug() << "[DesktopPet] 碎碎念(关怀 roll=" << roll << "):" << msg;

        // 切换卖萌动画（notification GIF，6秒后回 Idle）
        petMovie->stop();
        petMovie->setFileName(":/icons/pet_notification.gif"); // 卖萌/通知动画
        petMovie->start();

        showBubble(msg);

        // 6 秒后恢复 Idle 动画
        QTimer::singleShot(6000, this, [this]() {
            if (currentState == PetState::Idle) {
                petMovie->stop();
                petMovie->setFileName(":/icons/pet_idle.gif");
                petMovie->start();
            }
        });
    }
}

void DesktopPetWidget::onMumbleReplyFinished(QNetworkReply *reply) {
    // 内存安全：确保 reply 被释放
    QScopedPointer<QNetworkReply, QScopedPointerDeleteLater> guard(reply);

    if (reply->error() != QNetworkReply::NoError) {
        qDebug() << "[DesktopPet] 碎碎念请求失败:" << reply->errorString();
        return;
    }

    QByteArray data = reply->readAll();
    QJsonParseError parseErr;
    QJsonDocument doc = QJsonDocument::fromJson(data, &parseErr);

    if (parseErr.error != QJsonParseError::NoError) {
        qDebug() << "[DesktopPet] 碎碎念 JSON 解析失败:" << parseErr.errorString();
        return;
    }

    QJsonObject obj = doc.object();

    // butcanthic /flashcards/draw 返回：{"status":"success","total":N,"cards":[{question,answer,...}]}
    QJsonArray cardsArray = obj.value("cards").toArray();
    if (cardsArray.isEmpty()) {
        qDebug() << "[DesktopPet] 碎碎念：闪卡列表为空，跳过"
                 << "(reason=" << obj.value("reason").toString() << ")";
        return;
    }

    // 随机抽取一张闪卡展示（避免每次都展示第一张）
    int cardIdx = QRandomGenerator::global()->bounded(cardsArray.size());
    QJsonObject card = cardsArray.at(cardIdx).toObject();

    // 兼容多种字段名：question/front/question_text
    QString question = card.value("question").toString();
    if (question.isEmpty()) {
        question = card.value("front").toString();
    }
    if (question.isEmpty()) {
        question = card.value("question_text").toString();
    }

    // 兼容多种字段名：answer/back/answer_text
    QString answer = card.value("answer").toString();
    if (answer.isEmpty()) {
        answer = card.value("back").toString();
    }

    if (!question.isEmpty()) {
        QString mumble = QString("主人考考你：%1").arg(question);
        showBubble(mumble);
        qDebug() << "[DesktopPet] 碎碎念(闪卡" << (cardIdx + 1) << "/" << cardsArray.size()
                 << "):" << mumble;
    } else {
        qDebug() << "[DesktopPet] 碎碎念：闪卡 question 字段为空，跳过";
    }
}
