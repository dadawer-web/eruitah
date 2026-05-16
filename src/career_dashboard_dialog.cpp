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

CareerDashboardDialog::CareerDashboardDialog(QWidget *parent)
    : QDialog(parent, Qt::FramelessWindowHint | Qt::Dialog)
{
    setAttribute(Qt::WA_TranslucentBackground);
    setupUI();
    loadSkillBadges();
    loadTimeline();

    connect(m_btnExport, &QPushButton::clicked, this, &CareerDashboardDialog::onExportClicked);
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
    setFixedSize(700, 500);
    setWindowTitle(QString::fromUtf8("职业档案"));

    QWidget *root = new QWidget(this);
    root->setObjectName("dialogRoot");
    root->setGeometry(0, 0, 700, 500);

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
    headerLayout->addWidget(m_btnExport);

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
    leftPanel->setFixedWidth(180);
    QVBoxLayout *leftLayout = new QVBoxLayout(leftPanel);
    leftLayout->setContentsMargins(8, 8, 8, 8);
    leftLayout->setSpacing(6);

    QLabel *skillHeader = new QLabel(QString::fromUtf8("🏆 已解锁技能"));
    skillHeader->setObjectName("sectionHeader");
    leftLayout->addWidget(skillHeader);

    m_skillList = new QListWidget;
    m_skillList->setObjectName("skillList");
    m_skillList->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    m_skillList->setVerticalScrollMode(QAbstractItemView::ScrollPerPixel);
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
        #dialogRoot {
            background: transparent;
        }
        #container {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #0f0c29, stop:0.5 #1a1a3e, stop:1 #0f0c29);
            border: 1px solid #2a2a5a;
            border-radius: 14px;
        }
        #titleLabel {
            color: #00f2fe;
            font-size: 20px;
            font-weight: bold;
        }
        #btnExport {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #00b894, stop:1 #00cec9);
            color: #0a0a1a;
            border: none;
            border-radius: 8px;
            font-size: 12px;
            font-weight: bold;
        }
        #btnExport:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #00cec9, stop:1 #00f2fe);
        }
        #btnClose {
            background: transparent;
            color: #666;
            border: 1px solid #333;
            border-radius: 16px;
            font-size: 14px;
        }
        #btnClose:hover {
            background: #e74c3c;
            color: white;
            border-color: #e74c3c;
        }
        #headerLine {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 transparent, stop:0.2 #00f2fe, stop:0.8 #00f2fe, stop:1 transparent);
            max-height: 1px;
        }
        #splitter::handle {
            background: #2a2a5a;
        }
        #leftPanel {
            background: rgba(15, 12, 41, 180);
            border-right: 1px solid #1a1a4a;
            border-radius: 10px;
        }
        #sectionHeader {
            color: #64ffda;
            font-size: 13px;
            font-weight: bold;
            padding: 4px 0;
        }
        #skillList {
            background: transparent;
            border: none;
            outline: none;
        }
        #skillList::item {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 rgba(0, 242, 254, 20), stop:1 rgba(0, 206, 201, 10));
            color: #64ffda;
            border: 1px solid rgba(0, 242, 254, 40);
            border-radius: 12px;
            padding: 5px 10px;
            margin: 3px 2px;
            font-size: 11px;
            font-weight: bold;
        }
        #skillList::item:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 rgba(0, 242, 254, 50), stop:1 rgba(0, 206, 201, 30));
            border-color: rgba(0, 242, 254, 80);
        }
        #skillList::item:selected {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 rgba(0, 242, 254, 70), stop:1 rgba(0, 206, 201, 40));
            border-color: #00f2fe;
        }
        #rightPanel {
            background: transparent;
        }
        #timelineArea {
            background: transparent;
            border: none;
        }
        #timelineContent {
            background: transparent;
        }
        QScrollBar:vertical {
            background: transparent;
            width: 6px;
            margin: 0;
        }
        QScrollBar::handle:vertical {
            background: rgba(100, 255, 218, 60);
            border-radius: 3px;
            min-height: 30px;
        }
        QScrollBar::handle:vertical:hover {
            background: rgba(100, 255, 218, 120);
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0;
        }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
            background: none;
        }
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
    m_records = CareerHistoryManager::instance().getAllRecords();
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
    QLayoutItem *child;
    while ((child = m_timelineLayout->takeAt(0)) != nullptr) {
        delete child->widget();
        delete child;
    }

    if (m_records.isEmpty()) {
        QLabel *emptyLabel = new QLabel(QString::fromUtf8("暂无职业档案记录\n完成编程任务后将自动生成"));
        emptyLabel->setObjectName("emptyLabel");
        emptyLabel->setAlignment(Qt::AlignCenter);
        emptyLabel->setStyleSheet("color: #555; font-size: 14px; padding: 40px;");
        m_timelineLayout->addWidget(emptyLabel);
        m_timelineLayout->addStretch();
        return;
    }

    int index = 0;
    for (const QJsonValue &val : m_records) {
        QJsonObject rec = val.toObject();
        QWidget *card = createTimelineCard(rec, index);
        m_timelineLayout->addWidget(card);
        index++;
    }
    m_timelineLayout->addStretch();
}

QWidget* CareerDashboardDialog::createTimelineCard(const QJsonObject &record, int index)
{
    QWidget *card = new QWidget;
    card->setObjectName("timelineCard");

    QVBoxLayout *cardLayout = new QVBoxLayout(card);
    cardLayout->setContentsMargins(14, 12, 14, 12);
    cardLayout->setSpacing(8);

    QString timestamp = record.value("timestamp").toString(QString::fromUtf8("未知时间"));
    QString category = record.value("category").toString(QString::fromUtf8("代码分析"));

    QHBoxLayout *topRow = new QHBoxLayout;
    topRow->setSpacing(8);

    QLabel *dotLabel = new QLabel("●");
    dotLabel->setObjectName("timelineDot");
    dotLabel->setFixedSize(10, 10);
    dotLabel->setStyleSheet("color: #00f2fe; font-size: 10px;");
    topRow->addWidget(dotLabel);

    QLabel *timeLabel = new QLabel(timestamp);
    timeLabel->setObjectName("timeLabel");
    timeLabel->setStyleSheet("color: #888; font-size: 11px;");
    topRow->addWidget(timeLabel);

    topRow->addStretch();

    QLabel *catLabel = new QLabel(category);
    catLabel->setObjectName("catLabel");
    catLabel->setStyleSheet(
        "color: #00f2fe; font-size: 10px; font-weight: bold;"
        "background: rgba(0, 242, 254, 15);"
        "border: 1px solid rgba(0, 242, 254, 40);"
        "border-radius: 8px; padding: 2px 8px;"
    );
    topRow->addWidget(catLabel);

    cardLayout->addLayout(topRow);

    QString resumeHighlight = record.value("resume_highlight").toString();
    if (resumeHighlight.isEmpty()) {
        resumeHighlight = record.value("resumeHighlight").toString();
    }
    if (!resumeHighlight.isEmpty()) {
        QLabel *resumeHeader = new QLabel(QString::fromUtf8("📝 简历亮点 (STAR法则)"));
        resumeHeader->setObjectName("cardSectionHeader");
        resumeHeader->setStyleSheet("color: #64ffda; font-size: 11px; font-weight: bold;");
        cardLayout->addWidget(resumeHeader);

        QLabel *resumeContent = new QLabel(resumeHighlight);
        resumeContent->setObjectName("resumeContent");
        resumeContent->setWordWrap(true);
        resumeContent->setStyleSheet(
            "color: #e0e0e0; font-size: 12px; line-height: 1.5;"
            "background: rgba(100, 255, 218, 8);"
            "border-left: 3px solid #64ffda;"
            "border-radius: 0 6px 6px 0;"
            "padding: 8px 10px;"
        );
        cardLayout->addWidget(resumeContent);
    }

    QString nextSuggestion = record.value("next_suggestion").toString();
    if (nextSuggestion.isEmpty()) {
        nextSuggestion = record.value("learningAdvice").toString();
    }
    if (!nextSuggestion.isEmpty()) {
        QLabel *adviceHeader = new QLabel(QString::fromUtf8("🎯 导师进阶建议"));
        adviceHeader->setObjectName("cardSectionHeader");
        adviceHeader->setStyleSheet("color: #ffd54f; font-size: 11px; font-weight: bold;");
        cardLayout->addWidget(adviceHeader);

        QLabel *adviceContent = new QLabel(nextSuggestion);
        adviceContent->setObjectName("adviceContent");
        adviceContent->setWordWrap(true);
        adviceContent->setStyleSheet(
            "color: #ccc; font-size: 12px; line-height: 1.5;"
            "background: rgba(255, 213, 79, 8);"
            "border-left: 3px solid #ffd54f;"
            "border-radius: 0 6px 6px 0;"
            "padding: 8px 10px;"
        );
        cardLayout->addWidget(adviceContent);
    }

    QString skillsStr = extractSkills(record);
    if (!skillsStr.isEmpty()) {
        QLabel *skillsLabel = new QLabel("🛠 " + skillsStr);
        skillsLabel->setObjectName("skillsInCard");
        skillsLabel->setWordWrap(true);
        skillsLabel->setStyleSheet(
            "color: #64ffda; font-size: 10px;"
            "background: rgba(0, 242, 254, 10);"
            "border: 1px solid rgba(0, 242, 254, 25);"
            "border-radius: 10px; padding: 3px 10px;"
        );
        cardLayout->addWidget(skillsLabel);
    }

    QString borderAccent = (index % 2 == 0) ? "#00f2fe" : "#7c4dff";
    card->setStyleSheet(QString(
        "#timelineCard {"
        "   background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
        "       stop:0 rgba(26, 26, 62, 200), stop:1 rgba(15, 12, 41, 200));"
        "   border: 1px solid %1;"
        "   border-radius: 10px;"
        "}"
    ).arg(borderAccent));

    return card;
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

        QString category = rec.value("category").toString(QString::fromUtf8("代码分析"));
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
