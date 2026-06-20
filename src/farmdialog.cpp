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
}

FarmDialog::~FarmDialog()
{
}

void FarmDialog::showEvent(QShowEvent *event)
{
    QDialog::showEvent(event);
    requestFarmState();
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

    m_logBtn = new QPushButton(QString::fromUtf8("\xF0\x9F\x93\x9C 收菜日志"));
    m_logBtn->setStyleSheet("background-color: #e76f51;");
    navLayout->addWidget(m_logBtn);

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
    connect(m_logBtn, &QPushButton::clicked, this, &FarmDialog::onFarmLogClicked);
    connect(m_chatClient, &ChatClient::farmLogReceived, this, &FarmDialog::onFarmLogReceived);
    connect(m_chatClient, &ChatClient::farmLogDeleted, this, &FarmDialog::onFarmLogDeleted);
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

void FarmDialog::onFarmLogClicked()
{
    QJsonObject farmMsg;
    farmMsg["msgid"] = MsgType::FARM_LOG_REQ;
    farmMsg["userid"] = m_userId;
    if (!m_currentSubject.isEmpty() && m_currentSubject != QString::fromUtf8("全部")) {
        farmMsg["subject"] = m_currentSubject;
    }
    m_chatClient->sendJsonMessage(farmMsg);
    m_broadcastLabel->setText(QString::fromUtf8("\xF0\x9F\x93\x9C 正在加载收菜日志..."));
}

void FarmDialog::onFarmLogReceived(const QJsonArray &logs)
{
    // Close old dialog if still open
    if (m_currentLogDialog && m_currentLogDialog->isVisible()) {
        m_currentLogDialog->close();
    }

    QDialog *logDialog = new QDialog(this);
    logDialog->setWindowTitle(QString::fromUtf8("\xF0\x9F\x93\x96 疑问本"));
    logDialog->setMinimumSize(600, 500);
    logDialog->setStyleSheet(R"(
        QDialog { background-color: #1a1a2e; }
        QLabel { color: #e0e0e0; }
        QScrollArea { border: none; background-color: #1a1a2e; }
        QComboBox {
            background-color: #2a2a3e;
            color: #ffd700;
            border: 1px solid #3a3a4e;
            border-radius: 6px;
            padding: 6px 12px;
            font-size: 13px;
            font-weight: bold;
            min-width: 160px;
        }
        QComboBox::drop-down { border: none; }
        QComboBox QAbstractItemView {
            background-color: #2a2a3e;
            color: #e0e0e0;
            selection-background-color: #3a3a5e;
            border: 1px solid #3a3a4e;
        }
    )");

    m_currentLogDialog = logDialog;

    QVBoxLayout *mainLayout = new QVBoxLayout(logDialog);

    // Subject filter row
    QHBoxLayout *filterRow = new QHBoxLayout;
    QLabel *filterLabel = new QLabel(QString::fromUtf8("\xF0\x9F\x8F\xB7\xEF\xB8\x8F 学科筛选:"));
    filterLabel->setStyleSheet("font-size: 13px; font-weight: bold; color: #ffd700;");
    filterRow->addWidget(filterLabel);

    QComboBox *subjectCombo = new QComboBox;
    QStringList subjects = {QString::fromUtf8("全部"),
                            QString::fromUtf8("DS - 数据结构"),
                            QString::fromUtf8("CO - 计算机组成原理"),
                            QString::fromUtf8("OS - 操作系统"),
                            QString::fromUtf8("NET - 计算机网络")};
    QStringList subjectCodes = {"", "DS", "CO", "OS", "NET"};
    subjectCombo->addItems(subjects);
    // Restore current selection (block signals to avoid re-triggering onFarmLogClicked during init)
    subjectCombo->blockSignals(true);
    int idx = subjectCodes.indexOf(m_currentSubject);
    if (idx >= 0) {
        subjectCombo->setCurrentIndex(idx);
    }
    subjectCombo->blockSignals(false);
    filterRow->addWidget(subjectCombo);
    filterRow->addStretch();
    mainLayout->addLayout(filterRow);

    // Connect filter change
    connect(subjectCombo, QOverload<int>::of(&QComboBox::currentIndexChanged), this, [this, subjectCombo, subjectCodes]() {
        int idx = subjectCombo->currentIndex();
        m_currentSubject = subjectCodes.value(idx, "");
        // Re-query with new subject filter
        onFarmLogClicked();
    });

    if (logs.isEmpty()) {
        QLabel *emptyLabel = new QLabel(QString::fromUtf8("\xF0\x9F\x98\xB4 还没有收菜记录，快去答题吧~"));
        emptyLabel->setStyleSheet("font-size: 16px; color: #888; padding: 40px;");
        emptyLabel->setAlignment(Qt::AlignCenter);
        mainLayout->addWidget(emptyLabel);
    } else {
        QLabel *countLabel = new QLabel(QString::fromUtf8("\xE2\x9C\x85 共 %1 条记录").arg(logs.size()));
        countLabel->setStyleSheet("font-size: 14px; color: #ffd700; font-weight: bold; padding: 5px;");
        mainLayout->addWidget(countLabel);

        QScrollArea *scrollArea = new QScrollArea;
        scrollArea->setWidgetResizable(true);
        QWidget *scrollContent = new QWidget;
        scrollContent->setStyleSheet("background-color: #1a1a2e;");
        QVBoxLayout *scrollLayout = new QVBoxLayout(scrollContent);
        scrollLayout->setSpacing(8);

        for (int i = logs.size() - 1; i >= 0; --i) {
            QJsonObject log = logs[i].toObject();
            int logId = log["id"].toInt(-1);
            int answererId = log["answererid"].toInt(-1);
            QString question = log["question"].toString();
            QString answer = log["answer"].toString();
            int score = log["score"].toInt(0);
            QString feedback = log["feedback"].toString();
            QString subject = log["subject"].toString();

            QFrame *card = new QFrame;
            card->setStyleSheet(R"(
                QFrame {
                    background-color: #2a2a3e;
                    border-radius: 8px;
                    padding: 10px;
                    border: 1px solid #3a3a4e;
                }
            )");
            QVBoxLayout *cardLayout = new QVBoxLayout(card);
            cardLayout->setSpacing(4);

            QHBoxLayout *headerRow = new QHBoxLayout;
            QString header = QString::fromUtf8("\xF0\x9F\x91\xA4 答题人: User#%1").arg(answererId);
            if (!subject.isEmpty()) {
                header += QString("  [%1]").arg(subject);
            }
            header += QString::fromUtf8("  \xE2\xAD\x90 %1/100").arg(score);

            QLabel *headerLabel = new QLabel(header);
            headerLabel->setStyleSheet("font-weight: bold; font-size: 13px; color: #ffd700;");
            headerRow->addWidget(headerLabel);
            headerRow->addStretch();

            QPushButton *deleteBtn = new QPushButton(QString::fromUtf8("\xE2\x9C\x85 斩！已掌握"));
            deleteBtn->setStyleSheet("background-color: #27ae60; color: white; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: bold;");
            deleteBtn->setProperty("logId", logId);
            connect(deleteBtn, &QPushButton::clicked, this, [this, card, logId]() {
                QJsonObject farmMsg;
                farmMsg["msgid"] = MsgType::FARM_LOG_DELETE_REQ;
                farmMsg["userid"] = m_userId;
                farmMsg["logid"] = logId;
                m_chatClient->sendJsonMessage(farmMsg);
                card->hide();
            });
            headerRow->addWidget(deleteBtn);

            cardLayout->addLayout(headerRow);

            QLabel *questionLabel = new QLabel(QString::fromUtf8("\xF0\x9F\x93\x8D ") + question);
            questionLabel->setStyleSheet("color: #7ec8e3; font-size: 13px;");
            questionLabel->setWordWrap(true);
            cardLayout->addWidget(questionLabel);

            QLabel *answerLabel = new QLabel(QString::fromUtf8("\xE2\x9C\x8D ") + answer);
            answerLabel->setStyleSheet("color: #a8dadc; font-size: 12px;");
            answerLabel->setWordWrap(true);
            cardLayout->addWidget(answerLabel);

            if (!feedback.isEmpty()) {
                QLabel *feedbackLabel = new QLabel(QString::fromUtf8("\xF0\x9F\xA4\x96 AI: ") + feedback);
                feedbackLabel->setStyleSheet("color: #aaa; font-size: 11px; font-style: italic;");
                feedbackLabel->setWordWrap(true);
                cardLayout->addWidget(feedbackLabel);
            }

            scrollLayout->addWidget(card);
        }

        scrollLayout->addStretch();
        scrollArea->setWidget(scrollContent);
        mainLayout->addWidget(scrollArea);
    }

    QPushButton *closeBtn = new QPushButton(QString::fromUtf8("\xE5\x85\xB3\xE9\x97\xAD"));
    closeBtn->setStyleSheet("background-color: #6c757d; color: white; padding: 8px 24px; border-radius: 6px; font-weight: bold;");
    connect(closeBtn, &QPushButton::clicked, logDialog, &QDialog::accept);
    mainLayout->addWidget(closeBtn, 0, Qt::AlignCenter);

    logDialog->setAttribute(Qt::WA_DeleteOnClose);
    connect(logDialog, &QObject::destroyed, this, [this]() {
        m_currentLogDialog = nullptr;
    });
    logDialog->show();
}

void FarmDialog::onFarmLogDeleted(int logId, bool success, const QString &message)
{
    if (success) {
        m_broadcastLabel->setText(QString::fromUtf8("\xE2\x9C\x85 已斩！知识点已掌握"));
    } else {
        m_broadcastLabel->setText(QString::fromUtf8("\xE2\x9D\x8C 删除失败：") + message);
    }
}
