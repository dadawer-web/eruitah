#include "farmdialog.h"
#include "chatclient.h"
#include "public.h"
#include <QGraphicsGridLayout>
#include <QTimer>
#include <QPropertyAnimation>

FarmDialog::FarmDialog(int userId, const QString &userName, ChatClient *client, QWidget *parent)
    : QDialog(parent)
    , m_userId(userId)
    , m_userName(userName)
    , m_chatClient(client)
    , m_currentVisitUserId(userId)
    , m_currentVisitUserName(userName)
    , m_coins(0)
    , m_exp(0)
{
    setupUI();
    requestFarmState();
}

FarmDialog::~FarmDialog()
{
}

void FarmDialog::setupUI()
{
    setWindowTitle("408农场 - 种下疑问，收获知识");
    setMinimumSize(620, 750);
    setStyleSheet(R"(
        QDialog {
            background-color: #1a1a2e;
        }
        QLabel {
            color: #e0e0e0;
        }
        QPushButton {
            background-color: #2d6a4f;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #40916c;
        }
        QPushButton:pressed {
            background-color: #1b4332;
        }
    )");

    QVBoxLayout *mainLayout = new QVBoxLayout(this);
    mainLayout->setContentsMargins(15, 15, 15, 15);
    mainLayout->setSpacing(10);

    QHBoxLayout *headerLayout = new QHBoxLayout;

    m_titleLabel = new QLabel(QString::fromUtf8("\xF0\x9F\x8C\xBE 408农场"));
    m_titleLabel->setStyleSheet("font-size: 22px; font-weight: bold; color: #ffd700;");
    headerLayout->addWidget(m_titleLabel);

    headerLayout->addStretch();

    m_coinsLabel = new QLabel(QString::fromUtf8("\xF0\x9F\x92\xB0 金币: 0"));
    m_coinsLabel->setStyleSheet("font-size: 14px; color: #ffd700; padding: 4px 12px; background-color: #2a2a3e; border-radius: 8px;");
    headerLayout->addWidget(m_coinsLabel);

    m_expLabel = new QLabel(QString::fromUtf8("\xE2\xAD\x90 经验: 0"));
    m_expLabel->setStyleSheet("font-size: 14px; color: #7ec8e3; padding: 4px 12px; background-color: #2a2a3e; border-radius: 8px;");
    headerLayout->addWidget(m_expLabel);

    mainLayout->addLayout(headerLayout);

    QHBoxLayout *navLayout = new QHBoxLayout;

    m_myFarmBtn = new QPushButton(QString::fromUtf8("\xF0\x9F\x8F\xA0 我的农场"));
    m_myFarmBtn->setStyleSheet("background-color: #2d6a4f;");
    navLayout->addWidget(m_myFarmBtn);

    m_visitBtn = new QPushButton(QString::fromUtf8("\xF0\x9F\x91\x80 逛逛别人"));
    m_visitBtn->setStyleSheet("background-color: #1a759f;");
    navLayout->addWidget(m_visitBtn);

    m_refreshBtn = new QPushButton(QString::fromUtf8("\xF0\x9F\x94\x84 刷新"));
    m_refreshBtn->setStyleSheet("background-color: #6c757d;");
    navLayout->addWidget(m_refreshBtn);

    navLayout->addStretch();

    mainLayout->addLayout(navLayout);

    m_scene = new QGraphicsScene(this);
    m_scene->setBackgroundBrush(QColor("#0d1b0e"));

    m_view = new QGraphicsView(m_scene);
    m_view->setRenderHints(QPainter::Antialiasing | QPainter::SmoothPixmapTransform);
    m_view->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    m_view->setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    m_view->setStyleSheet("QGraphicsView { border: 2px solid #2d6a4f; border-radius: 8px; background-color: #0d1b0e; }");
    m_view->setFixedSize(500, 500);
    m_view->setSceneRect(0, 0, 500, 500);

    for (int row = 0; row < 3; ++row) {
        for (int col = 0; col < 3; ++col) {
            int plotId = row * 3 + col;
            FarmPlotItem *plot = new FarmPlotItem(plotId);
            qreal x = 15 + col * 160;
            qreal y = 15 + row * 160;
            plot->setPos(x, y);
            m_scene->addItem(plot);
            m_plots[plotId] = plot;

            connect(plot, &FarmPlotItem::plotClicked, this, &FarmDialog::onPlotClicked);
        }
    }

    QHBoxLayout *farmLayout = new QHBoxLayout;
    farmLayout->addStretch();
    farmLayout->addWidget(m_view);
    farmLayout->addStretch();
    mainLayout->addLayout(farmLayout);

    m_broadcastLabel = new QLabel(QString::fromUtf8("\xF0\x9F\x93\xA2 欢迎来到408农场！种下你的疑问，让别人来回答吧~"));
    m_broadcastLabel->setStyleSheet(
        "font-size: 12px; color: #aaaaaa; padding: 8px 12px; "
        "background-color: #2a2a3e; border-radius: 6px; "
        "border: 1px solid #3a3a4e;"
    );
    m_broadcastLabel->setWordWrap(true);
    mainLayout->addWidget(m_broadcastLabel);

    connect(m_refreshBtn, &QPushButton::clicked, this, &FarmDialog::onRefreshFarm);
    connect(m_visitBtn, &QPushButton::clicked, this, &FarmDialog::onVisitFarm);
    connect(m_myFarmBtn, &QPushButton::clicked, this, &FarmDialog::onMyFarm);
}

void FarmDialog::onPlotClicked(int plotId, int state)
{
    FarmPlotItem::PlotState plotState = static_cast<FarmPlotItem::PlotState>(state);

    if (plotState == FarmPlotItem::EMPTY) {
        bool ok = false;
        QString question = QInputDialog::getMultiLineText(
            this,
            QString::fromUtf8("\xF0\x9F\x8C\xB1 种下你的疑问"),
            QString::fromUtf8("输入一个408相关问题，种在这块地里让别人来回答："),
            "",
            &ok
        );
        if (ok && !question.trimmed().isEmpty()) {
            QStringList tags = { "OS", "NET", "DS", "CO" };
            QString tag = QInputDialog::getItem(
                this,
                QString::fromUtf8("\xF0\x9F\x8F\xB7\xEF\xB8\x8F 选择科目标签"),
                QString::fromUtf8("这个问题属于哪个科目？"),
                tags, 0, false, &ok
            );
            if (ok) {
                QJsonObject farmMsg;
                farmMsg["msgid"] = MsgType::FARM_PLANT_MSG;
                farmMsg["userid"] = m_userId;
                farmMsg["plotid"] = plotId;
                farmMsg["question"] = question.trimmed();
                farmMsg["subject"] = tag;
                m_chatClient->sendJsonMessage(farmMsg);

                m_plots[plotId]->setState(FarmPlotItem::GROWING);
                m_plots[plotId]->setQuestion(question.trimmed());
                m_plots[plotId]->setSubjectTag(tag);
                m_plots[plotId]->setOwnerInfo(m_userId, m_userName);
            }
        }
    } else if (plotState == FarmPlotItem::GROWING) {
        FarmPlotItem *plot = m_plots.value(plotId, nullptr);
        if (!plot) return;

        if (plot->ownerUserId() == m_userId) {
            QMessageBox::information(
                this,
                QString::fromUtf8("\xF0\x9F\x8C\xB1 自己的菜"),
                QString::fromUtf8("这是你自己种的问题哦！\n问题：%1\n\n等待别人来回答吧~").arg(plot->question())
            );
            return;
        }

        bool ok = false;
        QString answer = QInputDialog::getMultiLineText(
            this,
            QString::fromUtf8("\xF0\x9F\x92\xA7 浇水答题"),
            QString::fromUtf8("问题：%1\n\n请输入你的答案：").arg(plot->question()),
            "",
            &ok
        );
        if (ok && !answer.trimmed().isEmpty()) {
            QJsonObject farmMsg;
            farmMsg["msgid"] = MsgType::FARM_ANSWER_MSG;
            farmMsg["userid"] = m_userId;
            farmMsg["plotid"] = plotId;
            farmMsg["ownerid"] = plot->ownerUserId();
            farmMsg["question"] = plot->question();
            farmMsg["answer"] = answer.trimmed();
            m_chatClient->sendJsonMessage(farmMsg);

            m_broadcastLabel->setText(QString::fromUtf8("\xF0\x9F\x91\xA8\xE2\x80\x8D\xF0\x9F\x8C\xBE AI判卷中，请稍候..."));
        }
    } else if (plotState == FarmPlotItem::RIPE) {
        FarmPlotItem *plot = m_plots.value(plotId, nullptr);
        if (!plot) return;

        QJsonObject farmMsg;
        farmMsg["msgid"] = MsgType::FARM_HARVEST_MSG;
        farmMsg["userid"] = m_userId;
        farmMsg["plotid"] = plotId;
        farmMsg["ownerid"] = plot->ownerUserId();
        m_chatClient->sendJsonMessage(farmMsg);

        plot->setState(FarmPlotItem::HARVESTED);
        m_coins += 50;
        m_coinsLabel->setText(QString::fromUtf8("\xF0\x9F\x92\xB0 金币: %1").arg(m_coins));
        QMessageBox::information(this, QString::fromUtf8("\xF0\x9F\x8E\x89 收菜成功"),
                                 QString::fromUtf8("金币 +50！\n当前金币：%1").arg(m_coins));
    } else if (plotState == FarmPlotItem::HARVESTED) {
        QMessageBox::information(this, QString::fromUtf8("\xF0\x9F\x92\xA8 空坑"),
                                 QString::fromUtf8("这块地已经被收割了，等待重新种植~"));
    }
}

void FarmDialog::onRefreshFarm()
{
    requestFarmState();
}

void FarmDialog::onVisitFarm()
{
    bool ok = false;
    int targetId = QInputDialog::getInt(
        this,
        QString::fromUtf8("\xF0\x9F\x91\x80 逛逛别人的农场"),
        QString::fromUtf8("输入用户ID来参观TA的农场："),
        1, 1, 999999, 1, &ok
    );
    if (ok) {
        if (targetId == m_userId) {
            onMyFarm();
            return;
        }
        m_currentVisitUserId = targetId;
        m_currentVisitUserName = QString("User#%1").arg(targetId);
        m_titleLabel->setText(QString::fromUtf8("\xF0\x9F\x91\x80 %1 的农场").arg(m_currentVisitUserName));

        QJsonObject farmMsg;
        farmMsg["msgid"] = MsgType::FARM_QUERY_MSG;
        farmMsg["userid"] = m_userId;
        farmMsg["targetid"] = targetId;
        m_chatClient->sendJsonMessage(farmMsg);
    }
}

void FarmDialog::onMyFarm()
{
    m_currentVisitUserId = m_userId;
    m_currentVisitUserName = m_userName;
    m_titleLabel->setText(QString::fromUtf8("\xF0\x9F\x8C\xBE 408农场"));
    requestFarmState();
}

void FarmDialog::requestFarmState()
{
    QJsonObject farmMsg;
    farmMsg["msgid"] = MsgType::FARM_QUERY_MSG;
    farmMsg["userid"] = m_userId;
    farmMsg["targetid"] = m_currentVisitUserId;
    m_chatClient->sendJsonMessage(farmMsg);
}

void FarmDialog::updatePlotFromServer(int plotId, int state, const QString &question,
                                       int ownerUserId, const QString &ownerName,
                                       const QString &subjectTag)
{
    if (m_plots.contains(plotId)) {
        FarmPlotItem *plot = m_plots[plotId];
        plot->setState(static_cast<FarmPlotItem::PlotState>(state));
        plot->setQuestion(question);
        plot->setOwnerInfo(ownerUserId, ownerName);
        plot->setSubjectTag(subjectTag);

        m_plotData[plotId].state = state;
        m_plotData[plotId].question = question;
        m_plotData[plotId].ownerUserId = ownerUserId;
        m_plotData[plotId].ownerName = ownerName;
        m_plotData[plotId].subjectTag = subjectTag;
    }
}

void FarmDialog::updateUserStats(int coins, int exp)
{
    m_coins = coins;
    m_exp = exp;
    m_coinsLabel->setText(QString::fromUtf8("\xF0\x9F\x92\xB0 金币: %1").arg(coins));
    m_expLabel->setText(QString::fromUtf8("\xE2\xAD\x90 经验: %1").arg(exp));
}

void FarmDialog::handlePlantResponse(bool success, int plotId, const QString &message)
{
    if (success) {
        if (m_plots.contains(plotId)) {
            m_plots[plotId]->setState(FarmPlotItem::GROWING);
        }
        m_broadcastLabel->setText(QString::fromUtf8("\xF0\x9F\x8C\xB1 种菜成功！") + message);
    } else {
        if (m_plots.contains(plotId)) {
            m_plots[plotId]->setState(FarmPlotItem::EMPTY);
        }
        QMessageBox::warning(this, QString::fromUtf8("\xE2\x9D\x8C 种菜失败"), message);
    }
}

void FarmDialog::handleAnswerResponse(bool success, int plotId, const QString &feedback, int score, bool canHarvest)
{
    if (success && canHarvest) {
        m_coins += 50;
        m_coinsLabel->setText(QString::fromUtf8("\xF0\x9F\x92\xB0 金币: %1").arg(m_coins));

        QString resultMsg = QString::fromUtf8("\xF0\x9F\x8E\x89 AI判定：回答正确！\n"
                                               "得分：%1/100\n"
                                               "评语：%2\n"
                                               "金币 +50！").arg(score).arg(feedback);
        m_broadcastLabel->setText(resultMsg);
        QMessageBox::information(this, QString::fromUtf8("\xF0\x9F\x8E\x89 收菜成功！"), resultMsg);

        if (m_plots.contains(plotId)) {
            m_plots[plotId]->setState(FarmPlotItem::EMPTY);
            m_plots[plotId]->setQuestion("");
            m_plots[plotId]->setSubjectTag("");
        }
    } else {
        QString resultMsg = QString::fromUtf8("\xE2\x9D\x8C AI判定：回答不够正确~\n"
                                               "得分：%1/100\n"
                                               "评语：%2").arg(score).arg(feedback);
        m_broadcastLabel->setText(resultMsg);
        QMessageBox::information(this, QString::fromUtf8("\xF0\x9F\x98\x85 答题失败"), resultMsg);
    }
}

void FarmDialog::handlePlotHarvested(int plotId, int ownerId)
{
    if (ownerId == m_userId && m_plots.contains(plotId)) {
        m_plots[plotId]->setState(FarmPlotItem::EMPTY);
        m_plots[plotId]->setQuestion("");
        m_plots[plotId]->setSubjectTag("");
        m_broadcastLabel->setText(QString::fromUtf8("\xF0\x9F\x8E\x89 你的地块 %1 被收割了！经验 +10").arg(plotId));
    }
}

void FarmDialog::handleFarmBroadcast(const QString &message)
{
    m_broadcastLabel->setText(QString::fromUtf8("\xF0\x9F\x93\xA2 ") + message);
}
