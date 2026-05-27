#include "career_dashboard_dialog.h"
#include <QMouseEvent>
#include <QFrame>
#include <QSplitter>
#include <QScrollBar>
#include <QFileDialog>
#include <QFile>
#include <QMessageBox>
#include <QDesktopServices>
#include <QUrl>
#include <QStandardPaths>
#include <QNetworkRequest>
#include <QJsonDocument>
#include <QTimer>
#include <QWebEnginePage>

CareerDashboardDialog::CareerDashboardDialog(int userId, QWidget *parent)
    : QDialog(parent, Qt::FramelessWindowHint | Qt::Dialog)
    , m_userId(userId)
    , m_networkManager(new QNetworkAccessManager(this))
    , m_isWebViewLoaded(false)
    , m_dataRequestSent(false)
{
    setAttribute(Qt::WA_TranslucentBackground);
    setupUI();

    connect(m_btnExport, &QPushButton::clicked, this, &CareerDashboardDialog::onExportClicked);
    connect(m_btnReset, &QPushButton::clicked, this, &CareerDashboardDialog::onResetClicked);
    connect(m_networkManager, &QNetworkAccessManager::finished, this, &CareerDashboardDialog::onServerDataReceived);
    connect(&CareerHistoryManager::instance(), &CareerHistoryManager::careerDataUpdated,
            this, &CareerDashboardDialog::refreshData);

    connect(m_webView, &QWebEngineView::loadFinished, this, [this](bool ok) {
        if (ok) {
            m_isWebViewLoaded = true;
            qDebug() << "🎓 [CareerDashboard] WebView loadFinished, pending=" << !m_pendingChartData.isEmpty();
            if (!m_pendingChartData.isEmpty()) {
                m_webView->page()->runJavaScript(m_pendingChartData);
                m_pendingChartData.clear();
            }
        }
    });

    m_webView->load(QUrl("qrc:/html/career_radar.html"));

    initData();
}

CareerDashboardDialog::~CareerDashboardDialog()
{
}

void CareerDashboardDialog::mousePressEvent(QMouseEvent *event)
{
    if (event->button() == Qt::LeftButton) {
        m_dragPos = event->globalPos() - frameGeometry().topLeft();
        event->accept();
    }
}

void CareerDashboardDialog::mouseMoveEvent(QMouseEvent *event)
{
    if (event->buttons() & Qt::LeftButton) {
        move(event->globalPos() - m_dragPos);
        event->accept();
    }
}

void CareerDashboardDialog::setupUI()
{
    setFixedSize(860, 560);
    setWindowTitle(QString::fromUtf8("职业档案"));

    QWidget *root = new QWidget(this);
    root->setObjectName("dialogRoot");
    root->setGeometry(0, 0, 860, 560);

    QVBoxLayout *rootLayout = new QVBoxLayout(root);
    rootLayout->setContentsMargins(1, 1, 1, 1);
    rootLayout->setSpacing(0);

    QWidget *container = new QWidget;
    container->setObjectName("container");
    rootLayout->addWidget(container);

    QVBoxLayout *mainLayout = new QVBoxLayout(container);
    mainLayout->setContentsMargins(20, 16, 20, 16);
    mainLayout->setSpacing(12);

    QHBoxLayout *headerLayout = new QHBoxLayout;
    headerLayout->setSpacing(10);

    QLabel *titleLabel = new QLabel(QString::fromUtf8("⚡ 职业档案"));
    titleLabel->setObjectName("titleLabel");
    headerLayout->addWidget(titleLabel);

    headerLayout->addStretch();

    m_btnExport = new QPushButton(QString::fromUtf8("📁 导出为简历"));
    m_btnExport->setObjectName("btnExport");
    m_btnExport->setFixedSize(130, 32);
    m_btnExport->setEnabled(false);
    headerLayout->addWidget(m_btnExport);

    m_btnReset = new QPushButton(QString::fromUtf8("🗑️ 重置档案"));
    m_btnReset->setObjectName("btnReset");
    m_btnReset->setFixedSize(110, 32);
    headerLayout->addWidget(m_btnReset);

    m_statusLabel = new QLabel("");
    m_statusLabel->setObjectName("statusLabel");
    m_statusLabel->setStyleSheet("color: #64748B; font-size: 11px;");
    m_statusLabel->hide();
    headerLayout->addWidget(m_statusLabel);

    m_btnClose = new QPushButton("✕");
    m_btnClose->setObjectName("btnClose");
    m_btnClose->setFixedSize(32, 32);
    connect(m_btnClose, &QPushButton::clicked, this, &QDialog::close);
    headerLayout->addWidget(m_btnClose);

    mainLayout->addLayout(headerLayout);

    QFrame *headerLine = new QFrame;
    headerLine->setFrameShape(QFrame::HLine);
    headerLine->setObjectName("headerLine");
    headerLine->setFixedHeight(1);
    mainLayout->addWidget(headerLine);

    QSplitter *splitter = new QSplitter(Qt::Horizontal);
    splitter->setObjectName("splitter");
    splitter->setHandleWidth(1);

    QWidget *leftPanel = new QWidget;
    leftPanel->setObjectName("leftPanel");
    leftPanel->setFixedWidth(340);
    QVBoxLayout *leftLayout = new QVBoxLayout(leftPanel);
    leftLayout->setContentsMargins(8, 8, 8, 8);
    leftLayout->setSpacing(6);

    QLabel *radarHeader = new QLabel(QString::fromUtf8("⚡ 技能星图"));
    radarHeader->setObjectName("sectionHeader");
    leftLayout->addWidget(radarHeader);

    m_webView = new QWebEngineView;
    m_webView->setObjectName("radarWebView");
    m_webView->setMinimumHeight(350);
    m_webView->setStyleSheet("QWebEngineView { background: transparent; border: 1px solid rgba(56, 189, 248, 25); border-radius: 10px; }");
    leftLayout->addWidget(m_webView);

    QLabel *skillHeader = new QLabel(QString::fromUtf8("🏆 已解锁技能"));
    skillHeader->setObjectName("sectionHeader");
    leftLayout->addWidget(skillHeader);

    m_skillList = new QListWidget;
    m_skillList->setObjectName("skillList");
    m_skillList->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    m_skillList->setVerticalScrollMode(QAbstractItemView::ScrollPerPixel);
    m_skillList->setMaximumHeight(120);
    leftLayout->addWidget(m_skillList);

    splitter->addWidget(leftPanel);

    QWidget *rightPanel = new QWidget;
    rightPanel->setObjectName("rightPanel");
    QVBoxLayout *rightLayout = new QVBoxLayout(rightPanel);
    rightLayout->setContentsMargins(4, 4, 4, 4);
    rightLayout->setSpacing(6);

    QLabel *timelineHeader = new QLabel(QString::fromUtf8("📜 成长时间轴"));
    timelineHeader->setObjectName("sectionHeader");
    rightLayout->addWidget(timelineHeader);

    m_timelineArea = new QScrollArea;
    m_timelineArea->setObjectName("timelineArea");
    m_timelineArea->setWidgetResizable(true);
    m_timelineArea->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);

    QWidget *timelineContent = new QWidget;
    timelineContent->setObjectName("timelineContent");
    m_timelineLayout = new QVBoxLayout(timelineContent);
    m_timelineLayout->setContentsMargins(12, 8, 12, 8);
    m_timelineLayout->setSpacing(16);
    m_timelineLayout->addStretch();

    m_timelineArea->setWidget(timelineContent);
    rightLayout->addWidget(m_timelineArea);

    splitter->addWidget(rightPanel);
    splitter->setStretchFactor(0, 0);
    splitter->setStretchFactor(1, 1);

    mainLayout->addWidget(splitter);

    root->setStyleSheet(R"(
        #dialogRoot { background: transparent; }
        #container {
            background: #0F172A;
            border: 1px solid rgba(56, 189, 248, 30);
            border-radius: 16px;
        }
        #titleLabel {
            color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #38BDF8, stop:0.5 #818CF8, stop:1 #38BDF8);
            font-size: 22px; font-weight: bold; letter-spacing: 2px;
        }
        #btnExport {
            background: transparent; color: #38BDF8;
            border: 1.5px solid #38BDF8; border-radius: 6px;
            font-size: 12px; font-weight: bold; padding: 4px 16px;
        }
        #btnExport:hover { background: #0EA5E9; color: #0F172A; border-color: #0EA5E9; }
        #btnExport:disabled { color: #334155; border-color: #1E293B; background: transparent; }
        #btnReset {
            background: transparent; color: #EF4444;
            border: 1.5px solid #EF4444; border-radius: 6px;
            font-size: 12px; font-weight: bold; padding: 4px 16px;
        }
        #btnReset:hover { background: #EF4444; color: #0F172A; border-color: #EF4444; }
        #btnClose {
            background: transparent; color: #475569;
            border: 1px solid #1E293B; border-radius: 16px;
            font-size: 16px; font-weight: bold;
        }
        #btnClose:hover { background: #EF4444; color: white; border-color: #EF4444; }
        #headerLine {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 transparent, stop:0.15 #38BDF8, stop:0.5 #818CF8, stop:0.85 #38BDF8, stop:1 transparent);
            max-height: 1px;
        }
        #splitter::handle { background: rgba(56, 189, 248, 20); width: 1px; }
        #leftPanel {
            background: rgba(30, 41, 59, 70);
            border: 1px solid rgba(255, 255, 255, 10); border-radius: 12px;
        }
        #sectionHeader {
            color: #38BDF8; font-size: 14px; font-weight: bold;
            padding: 6px 4px; letter-spacing: 1px;
        }
        #skillList { background: transparent; border: none; outline: none; }
        #skillList::item {
            background: rgba(56, 189, 248, 12); color: #38BDF8;
            border: 1px solid rgba(56, 189, 248, 30); border-radius: 10px;
            padding: 4px 10px; margin: 2px 1px; font-size: 11px; font-weight: bold;
            font-family: 'Consolas', 'Courier New', monospace;
        }
        #skillList::item:hover { background: rgba(56, 189, 248, 25); border-color: rgba(56, 189, 248, 60); }
        #skillList::item:selected { background: rgba(56, 189, 248, 35); border-color: #38BDF8; }
        #rightPanel {
            background: rgba(30, 41, 59, 50);
            border: 1px solid rgba(255, 255, 255, 10); border-radius: 12px;
        }
        #timelineArea { background: transparent; border: none; }
        #timelineContent { background: transparent; }
        QScrollBar:vertical { background: transparent; width: 4px; margin: 0; }
        QScrollBar::handle:vertical { background: rgba(56, 189, 248, 40); border-radius: 2px; min-height: 30px; }
        QScrollBar::handle:vertical:hover { background: rgba(56, 189, 248, 80); }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
    )");
}

QString CareerDashboardDialog::extractSkills(const QJsonObject &record) const
{
    QJsonValue skillsVal = record.value("skills");
    if (skillsVal.isArray()) {
        QStringList parts;
        for (const QJsonValue &v : skillsVal.toArray()) {
            parts << v.toString();
        }
        return parts.join(", ");
    }
    return skillsVal.toString();
}

void CareerDashboardDialog::loadSkillBadges()
{
    m_uniqueSkills.clear();
    m_skillList->clear();

    for (const QJsonValue &val : m_records) {
        QJsonObject rec = val.toObject();
        QString skillsStr = extractSkills(rec);
        QStringList skillList = skillsStr.split(",", Qt::SkipEmptyParts);
        for (QString &s : skillList) {
            s = s.trimmed();
            if (!s.isEmpty()) {
                m_uniqueSkills.insert(s);
            }
        }
    }

    QStringList sorted = m_uniqueSkills.values();
    std::sort(sorted.begin(), sorted.end());

    for (const QString &skill : sorted) {
        QListWidgetItem *item = new QListWidgetItem(m_skillList);
        item->setText("⚡ " + skill);
        item->setTextAlignment(Qt::AlignCenter);
        item->setFlags(item->flags() & ~Qt::ItemIsSelectable);
        item->setSizeHint(QSize(0, 30));
        m_skillList->addItem(item);
    }
}

void CareerDashboardDialog::loadTimeline()
{
    m_cards.clear();

    QLayoutItem *child;
    while ((child = m_timelineLayout->takeAt(0)) != nullptr) {
        if (child->widget()) {
            child->widget()->hide();
            child->widget()->deleteLater();
        }
        delete child;
    }

    if (m_records.isEmpty()) {
        QLabel *emptyLabel = new QLabel(QString::fromUtf8("暂无职业档案记录\n完成编程任务后将自动生成"));
        emptyLabel->setObjectName("emptyLabel");
        emptyLabel->setAlignment(Qt::AlignCenter);
        emptyLabel->setStyleSheet("color: #475569; font-size: 14px; padding: 40px;");
        m_timelineLayout->addWidget(emptyLabel);
        m_timelineLayout->addStretch();
        return;
    }

    for (int i = 0; i < m_records.size(); ++i) {
        QJsonObject rec = m_records[i].toObject();
        CareerCardWidget *card = new CareerCardWidget(rec, i);
        connect(card, &CareerCardWidget::deleteRequested,
                this, &CareerDashboardDialog::onDeleteCard);
        m_cards.append(card);
        m_timelineLayout->addWidget(card);
    }
    m_timelineLayout->addStretch();
}

void CareerDashboardDialog::initData()
{
    m_records = CareerHistoryManager::instance().getAllRecords();
    loadSkillBadges();
    loadTimeline();

    if (!m_records.isEmpty()) {
        QJsonObject latest = m_records[0].toObject();
        QJsonArray skills;
        QJsonValue skillsVal = latest.value("skills");
        if (skillsVal.isArray()) {
            skills = skillsVal.toArray();
        } else {
            for (const QString &p : skillsVal.toString().split(",", Qt::SkipEmptyParts)) {
                QString t = p.trimmed();
                if (!t.isEmpty()) skills.append(t);
            }
        }
        if (!skills.isEmpty()) {
            m_latestSkills = skills;
            injectRadarChart();
        }
        m_btnExport->setEnabled(true);
    }

    if (m_userId > 0 && !m_dataRequestSent) {
        m_dataRequestSent = true;

        m_statusLabel->setText(QString::fromUtf8("⏳ 同步服务端数据..."));
        m_statusLabel->setStyleSheet("color: #38BDF8; font-size: 11px;");
        m_statusLabel->show();

        QString url = QString("http://127.0.0.1:8081/api/analysis/career-advice/profile?userId=%1")
                         .arg(m_userId);
        QUrl requestUrl(url);
        QNetworkRequest request(requestUrl);
        request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");
        request.setTransferTimeout(10000);
        m_networkManager->get(request);

        QTimer::singleShot(12000, this, [this]() {
            if (m_statusLabel && m_statusLabel->isVisible()) {
                m_statusLabel->setText(QString::fromUtf8("服务端暂不可用"));
                m_statusLabel->setStyleSheet("color: #64748B; font-size: 11px;");
                QTimer::singleShot(3000, m_statusLabel, &QLabel::hide);
            }
        });
    }
}

void CareerDashboardDialog::injectRadarChart()
{
    QJsonDocument doc(m_latestSkills);
    QString jsonString = doc.toJson(QJsonDocument::Compact);

    QString jsCode;

    if (m_latestSkills.isEmpty()) {
        jsCode = QString(
            "if (typeof window.updateSkillsData === 'function') {"
            "  window.updateSkillsData([]);"
            "}"
        );
    } else {
        jsCode = QString(
            "if (typeof window.updateSkillsData === 'function') {"
            "  window.updateSkillsData(%1);"
            "}"
        ).arg(jsonString);
    }

    qDebug() << "🎓 [CareerDashboard] injectRadarChart: webViewLoaded=" << m_isWebViewLoaded
             << "skills=" << m_latestSkills.size();

    if (m_isWebViewLoaded) {
        m_webView->page()->runJavaScript(jsCode);
    } else {
        m_pendingChartData = jsCode;
    }
}

void CareerDashboardDialog::applyCareerData(const QString &highlight, const QJsonArray &skills, const QString &advice)
{
    qDebug() << "⚡ [CareerDashboard] applyCareerData: highlightLen=" << highlight.length()
             << "skills=" << skills.size();

    QJsonObject record;
    record["resume_highlight"] = highlight;
    record["next_suggestion"] = advice;
    record["skills"] = skills;
    record["category"] = QString::fromUtf8("职业档案");
    record["timestamp"] = QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm");

    CareerHistoryManager::instance().appendRecord(record);

    m_records = CareerHistoryManager::instance().getAllRecords();
    loadSkillBadges();
    loadTimeline();

    m_latestSkills = skills;
    injectRadarChart();

    m_btnExport->setEnabled(true);
}

void CareerDashboardDialog::refreshData()
{
    qDebug() << "🔄 [CareerDashboard] refreshData triggered";

    m_records = CareerHistoryManager::instance().getAllRecords();
    loadSkillBadges();
    loadTimeline();

    if (!m_records.isEmpty()) {
        QJsonObject latest = m_records[0].toObject();
        QJsonArray skills;
        QJsonValue skillsVal = latest.value("skills");
        if (skillsVal.isArray()) {
            skills = skillsVal.toArray();
        } else {
            for (const QString &p : skillsVal.toString().split(",", Qt::SkipEmptyParts)) {
                QString t = p.trimmed();
                if (!t.isEmpty()) skills.append(t);
            }
        }
        if (!skills.isEmpty()) {
            m_latestSkills = skills;
            injectRadarChart();
        }
        m_btnExport->setEnabled(true);
    } else {
        m_latestSkills = QJsonArray();
        injectRadarChart();
        m_btnExport->setEnabled(false);
    }
}

void CareerDashboardDialog::onDeleteCard(int index, const QString &highlightText)
{
    if (index < 0 || index >= m_cards.size()) {
        return;
    }

    CareerCardWidget *card = m_cards.at(index);
    QPushButton *btn = card->findChild<QPushButton*>("btnDeleteCard");
    if (btn) {
        btn->setEnabled(false);
        btn->setText("⏳");
    }

    if (m_userId > 0) {
        QString encodedHighlight = QUrl::toPercentEncoding(highlightText);
        QString url = QString("http://127.0.0.1:8081/api/v1/career-advice/record?userId=%1&highlightText=%2")
                         .arg(m_userId).arg(encodedHighlight);
        QUrl deleteUrl(url);
        QNetworkRequest request(deleteUrl);
        request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");
        request.setTransferTimeout(5000);
        request.setAttribute(QNetworkRequest::User, "single_record_delete");

        qDebug() << "🗑️ [CareerDashboard] DELETE record:" << url;
        m_networkManager->deleteResource(request);
    } else {
        CareerHistoryManager::instance().deleteRecord(index);
        refreshData();
    }
}

void CareerDashboardDialog::onServerDataReceived(QNetworkReply *reply)
{
    if (!m_statusLabel) return;

    int httpStatus = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
    QNetworkAccessManager::Operation op = reply->operation();

    if (op == QNetworkAccessManager::DeleteOperation) {
        reply->deleteLater();
        m_btnReset->setEnabled(true);

        if (reply->error() != QNetworkReply::NoError || httpStatus >= 500) {
            qDebug() << "❌ [CareerDashboard] DELETE failed";
            m_statusLabel->setText(QString::fromUtf8("删除失败"));
            m_statusLabel->setStyleSheet("color: #EF4444; font-size: 11px;");
            m_statusLabel->show();
            QTimer::singleShot(3000, m_statusLabel, &QLabel::hide);
            return;
        }

        QVariant attr = reply->request().attribute(QNetworkRequest::User);
        bool isSingleDelete = (attr.toString() == "single_record_delete");

        if (isSingleDelete) {
            qDebug() << "🗑️ [CareerDashboard] Single record DELETE success, re-fetching profile...";
            m_statusLabel->setText(QString::fromUtf8("⏳ 刷新中..."));
            m_statusLabel->setStyleSheet("color: #38BDF8; font-size: 11px;");
            m_statusLabel->show();

            QString url = QString("http://127.0.0.1:8081/api/analysis/career-advice/profile?userId=%1")
                             .arg(m_userId);
            QUrl requestUrl(url);
            QNetworkRequest request(requestUrl);
            request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");
            request.setTransferTimeout(10000);
            m_networkManager->get(request);
            return;
        }

        qDebug() << "🗑️ [CareerDashboard] Full profile DELETE success, clearing local data";

        CareerHistoryManager::instance().clearAllRecords();

        m_records = QJsonArray();
        m_latestSkills = QJsonArray();
        m_uniqueSkills.clear();
        m_skillList->clear();
        loadTimeline();
        injectRadarChart();
        m_btnExport->setEnabled(false);

        m_statusLabel->setText(QString::fromUtf8("✅ 档案已重置"));
        m_statusLabel->setStyleSheet("color: #34D399; font-size: 11px;");
        m_statusLabel->show();
        QTimer::singleShot(3000, m_statusLabel, &QLabel::hide);
        return;
    }

    if (reply->error() != QNetworkReply::NoError) {
        m_statusLabel->setText(QString::fromUtf8("网络请求失败"));
        m_statusLabel->setStyleSheet("color: #EF4444; font-size: 11px;");
        m_statusLabel->show();
        QTimer::singleShot(5000, m_statusLabel, &QLabel::hide);
        reply->deleteLater();
        return;
    }

    QByteArray data = reply->readAll();
    reply->deleteLater();

    QJsonParseError parseError;
    QJsonDocument doc = QJsonDocument::fromJson(data, &parseError);
    if (parseError.error != QJsonParseError::NoError || !doc.isObject()) {
        m_statusLabel->setText(QString::fromUtf8("数据解析失败"));
        m_statusLabel->setStyleSheet("color: #EF4444; font-size: 11px;");
        m_statusLabel->show();
        QTimer::singleShot(3000, m_statusLabel, &QLabel::hide);
        return;
    }

    QJsonObject serverObj = doc.object();

    if (serverObj.contains("code") && serverObj.contains("data")) {
        int code = serverObj.value("code").toInt();
        if (code != 200) {
            m_statusLabel->setText(QString::fromUtf8("服务端返回错误"));
            m_statusLabel->setStyleSheet("color: #EF4444; font-size: 11px;");
            m_statusLabel->show();
            QTimer::singleShot(3000, m_statusLabel, &QLabel::hide);
            return;
        }
        QJsonValue dataVal = serverObj.value("data");
        if (dataVal.isObject()) {
            serverObj = dataVal.toObject();
        }
    }

    QString source = serverObj.value("source").toString();
    if (source == "default" || source == "fallback") {
        m_statusLabel->setText(QString::fromUtf8("📭 暂无档案，请多和 AI 交流"));
        m_statusLabel->setStyleSheet("color: #FBBF24; font-size: 11px;");
        m_statusLabel->show();
        QTimer::singleShot(5000, m_statusLabel, &QLabel::hide);
        return;
    }

    QString resumeHighlight = serverObj.value("resumeHighlight").toString();
    if (resumeHighlight.isEmpty()) {
        resumeHighlight = serverObj.value("resume_highlight").toString();
    }
    QString learningAdvice = serverObj.value("learningAdvice").toString();
    if (learningAdvice.isEmpty()) {
        learningAdvice = serverObj.value("next_suggestion").toString();
    }
    QJsonArray skillsArr = serverObj.value("skills").toArray();

    if (resumeHighlight.isEmpty() && learningAdvice.isEmpty() && skillsArr.isEmpty()) {
        m_statusLabel->setText(QString::fromUtf8("暂无数据"));
        m_statusLabel->setStyleSheet("color: #FBBF24; font-size: 11px;");
        m_statusLabel->show();
        QTimer::singleShot(3000, m_statusLabel, &QLabel::hide);
        return;
    }

    applyCareerData(resumeHighlight, skillsArr, learningAdvice);

    m_statusLabel->setText(QString::fromUtf8("✅ 同步完成"));
    m_statusLabel->setStyleSheet("color: #34D399; font-size: 11px;");
    m_statusLabel->show();
    QTimer::singleShot(3000, m_statusLabel, &QLabel::hide);
}

void CareerDashboardDialog::onResetClicked()
{
    QMessageBox::StandardButton confirm = QMessageBox::warning(
        this,
        QString::fromUtf8("⚠️ 重置职业档案"),
        QString::fromUtf8("警告：此操作将清空您所有的实战档案与技能雷达图，是否继续？"),
        QMessageBox::Yes | QMessageBox::No,
        QMessageBox::No
    );

    if (confirm != QMessageBox::Yes) {
        return;
    }

    m_btnReset->setEnabled(false);
    m_statusLabel->setText(QString::fromUtf8("⏳ 正在重置..."));
    m_statusLabel->setStyleSheet("color: #EF4444; font-size: 11px;");
    m_statusLabel->show();

    QString url = QString("http://127.0.0.1:8081/api/analysis/career-advice/profile?userId=%1")
                     .arg(m_userId);
    QUrl deleteUrl(url);
    QNetworkRequest request(deleteUrl);
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");
    request.setTransferTimeout(10000);

    m_networkManager->deleteResource(request);
}

void CareerDashboardDialog::onExportClicked()
{
    QString desktopPath = QStandardPaths::writableLocation(QStandardPaths::DesktopLocation);
    QString defaultPath = desktopPath + "/AI_Generated_Resume.md";

    QString filePath = QFileDialog::getSaveFileName(
        this,
        QString::fromUtf8("导出简历"),
        defaultPath,
        "Markdown Files (*.md)"
    );

    if (filePath.isEmpty()) {
        return;
    }

    QString content;
    content += "# AI 智能生成 - 我的项目经历与技术亮点\n\n";

    for (const QJsonValue &val : m_records) {
        QJsonObject rec = val.toObject();

        QString category = rec.value("category").toString(QString::fromUtf8("职业档案"));
        QString timestamp = rec.value("timestamp").toString(QString::fromUtf8("未知时间"));

        content += "---\n\n";
        content += "### 💼 项目核心模块：" + category + "\n\n";
        content += "**解锁时间**：" + timestamp + "\n\n";

        QString skillsStr = extractSkills(rec);
        if (!skillsStr.isEmpty()) {
            QStringList skillParts = skillsStr.split(",", Qt::SkipEmptyParts);
            QStringList badgeParts;
            for (const QString &s : skillParts) {
                QString trimmed = s.trimmed();
                if (!trimmed.isEmpty()) {
                    badgeParts << "`" + trimmed + "`";
                }
            }
            if (!badgeParts.isEmpty()) {
                content += "**核心技能标签**：" + badgeParts.join(" ") + "\n\n";
            }
        }

        QString resumeHighlight = rec.value("resume_highlight").toString();
        if (resumeHighlight.isEmpty()) {
            resumeHighlight = rec.value("resumeHighlight").toString();
        }
        if (!resumeHighlight.isEmpty()) {
            content += "#### 🎯 秋招简历亮点描述 (STAR法则)\n\n";
            content += "> " + resumeHighlight + "\n\n";
        }

        QString nextSuggestion = rec.value("next_suggestion").toString();
        if (nextSuggestion.isEmpty()) {
            nextSuggestion = rec.value("learningAdvice").toString();
        }
        if (!nextSuggestion.isEmpty()) {
            content += "#### 🚀 个人进阶方向\n\n";
            content += "- " + nextSuggestion + "\n\n";
        }
    }

    QFile file(filePath);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Text)) {
        QMessageBox::warning(this,
            QString::fromUtf8("导出失败"),
            QString::fromUtf8("无法创建文件，请检查路径权限。"));
        return;
    }
    file.write(content.toUtf8());
    file.close();

    QMessageBox::information(this,
        QString::fromUtf8("导出成功"),
        QString::fromUtf8("简历已成功导出至桌面！"));

    QDesktopServices::openUrl(QUrl::fromLocalFile(filePath));
}
