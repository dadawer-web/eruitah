#include "companionreadingdialog.h"
#include <QMessageBox>
#include <QDebug>
#include <QMouseEvent>
#include <QApplication>
#include <QScreen>
#include <QScrollBar>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QWebEnginePage>
#include <QWebEngineProfile>
#include <QFileDialog>
#include <QHttpMultiPart>
#include <QRegularExpression>

Live2DUrlInterceptor::Live2DUrlInterceptor(const QString &baseDir, QObject *parent)
    : QWebEngineUrlRequestInterceptor(parent)
    , m_baseDir(baseDir)
{
}

void Live2DUrlInterceptor::interceptRequest(QWebEngineUrlRequestInfo &info)
{
    QUrl url = info.requestUrl();
    QString path = url.path();

    if (path.contains("/live2d/")) {
        int idx = path.indexOf("/live2d/");
        QString relativePath = path.mid(idx + 1);
        QString localPath = m_baseDir + "/" + relativePath;
        QFileInfo fi(localPath);
        if (fi.exists()) {
            info.redirect(QUrl::fromLocalFile(fi.absoluteFilePath()));
        }
    }
}

CompanionReadingDialog::CompanionReadingDialog(int userId, QWidget *parent)
    : QDialog(parent)
    , m_userId(userId)
    , m_networkManager(new QNetworkAccessManager(this))
    , m_fileUploadManager(new QNetworkAccessManager(this))
    , m_audioDownloadManager(new QNetworkAccessManager(this))
    , m_explainBtnVisible(false)
    , m_urlInterceptor(nullptr)
    , m_currentAudioFile(nullptr)
    , m_currentAudioReply(nullptr)
{
    deployLive2DAssets();
    setupUI();
    loadDefaultContent();

    connect(m_ebookBrowser, &QTextBrowser::selectionChanged, this, &CompanionReadingDialog::onSelectionChanged);
    connect(m_networkManager, &QNetworkAccessManager::finished, this, &CompanionReadingDialog::onCompanionReadReply);
    connect(m_fileUploadManager, &QNetworkAccessManager::finished, this, &CompanionReadingDialog::onPdfParseReply);
    connect(m_audioDownloadManager, &QNetworkAccessManager::finished, this, &CompanionReadingDialog::onAudioDownloadFinished);

    m_ebookBrowser->viewport()->installEventFilter(this);
}

CompanionReadingDialog::~CompanionReadingDialog()
{
}

void CompanionReadingDialog::deployLive2DAssets()
{
    m_assetDir = QCoreApplication::applicationDirPath() + "/live2d_assets";

    QDir assetDir(m_assetDir);
    if (assetDir.exists("hiyori/hiyori_pro_t11.model3.json")) {
        return;
    }

    QString srcDir = QCoreApplication::applicationDirPath() + "/../src/live2d";
    if (!QDir(srcDir).exists()) {
        srcDir = "/home/xmy/code/src/live2d";
    }

    QDir srcHiyori(srcDir + "/hiyori");
    if (!srcHiyori.exists()) {
        qWarning() << "Live2D source not found:" << srcDir;
        return;
    }

    QDir destHiyori(m_assetDir + "/hiyori");
    destHiyori.mkpath(".");

    QStringList entries = srcHiyori.entryList(QDir::Files | QDir::NoDotAndDotDot);
    for (const QString &file : entries) {
        QFile::copy(srcHiyori.filePath(file), destHiyori.filePath(file));
    }

    QDir srcTexture(srcDir + "/hiyori/hiyori_pro_t11.2048");
    QDir destTexture(m_assetDir + "/hiyori/hiyori_pro_t11.2048");
    if (srcTexture.exists()) {
        destTexture.mkpath(".");
        QStringList texFiles = srcTexture.entryList(QDir::Files | QDir::NoDotAndDotDot);
        for (const QString &file : texFiles) {
            QFile::copy(srcTexture.filePath(file), destTexture.filePath(file));
        }
    }

    QDir srcMotion(srcDir + "/hiyori/motion");
    QDir destMotion(m_assetDir + "/hiyori/motion");
    if (srcMotion.exists()) {
        destMotion.mkpath(".");
        QStringList motionFiles = srcMotion.entryList(QDir::Files | QDir::NoDotAndDotDot);
        for (const QString &file : motionFiles) {
            QFile::copy(srcMotion.filePath(file), destMotion.filePath(file));
        }
    }

    qDebug() << "Live2D assets deployed to:" << m_assetDir;
}

void CompanionReadingDialog::setupUI()
{
    setWindowTitle(QString::fromUtf8("📖 AI伴读 - 请上传电子书"));
    setMinimumSize(1200, 800);
    setStyleSheet(R"(
        QDialog {
            background-color: #0b0f1a;
        }
        QLabel {
            color: #e0e0e0;
        }
        QPushButton {
            background-color: #4a4e69;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #5c6378;
        }
        QPushButton:pressed {
            background-color: #3a3e59;
        }
        QProgressBar {
            border: 1px solid rgba(0, 242, 254, 0.2);
            border-radius: 4px;
            background-color: #1a2332;
            height: 6px;
            text-align: center;
        }
        QProgressBar::chunk {
            background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7c3aed, stop:1 #a855f7);
            border-radius: 3px;
        }
    )");

    QVBoxLayout *mainLayout = new QVBoxLayout(this);
    mainLayout->setContentsMargins(15, 15, 15, 15);
    mainLayout->setSpacing(10);

    QHBoxLayout *headerLayout = new QHBoxLayout;

    QLabel *titleLabel = new QLabel(QString::fromUtf8("📖 AI伴读"));
    titleLabel->setStyleSheet("font-size: 22px; font-weight: bold; color: #00f2fe;");
    headerLayout->addWidget(titleLabel);

    m_fileLabel = new QLabel(QString::fromUtf8("未加载文件"));
    m_fileLabel->setStyleSheet("font-size: 12px; color: #8392A5; padding: 4px 12px; background: rgba(19, 26, 40, 0.6); border-radius: 4px;");
    headerLayout->addWidget(m_fileLabel);

    headerLayout->addStretch();

    m_uploadBtn = new QPushButton(QString::fromUtf8("📁 上传电子书"));
    m_uploadBtn->setStyleSheet(R"(
        QPushButton {
            background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #22c55e, stop:1 #16a34a);
            color: white;
            border: none;
            border-radius: 6px;
            font-size: 13px;
            font-weight: bold;
            padding: 8px 16px;
        }
        QPushButton:hover {
            background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #16a34a, stop:1 #15803d);
        }
    )");
    connect(m_uploadBtn, &QPushButton::clicked, this, &CompanionReadingDialog::onUploadFileClicked);
    headerLayout->addWidget(m_uploadBtn);

    QLabel *tipLabel = new QLabel(QString::fromUtf8("💡 划选文字后点击「✨ 学长讲讲」"));
    tipLabel->setStyleSheet("font-size: 12px; color: #8392A5; padding: 4px;");
    headerLayout->addWidget(tipLabel);

    mainLayout->addLayout(headerLayout);

    m_statusLabel = new QLabel(QString::fromUtf8("⏳ 请上传 PDF 或 Markdown 文件开始伴读"));
    m_statusLabel->setStyleSheet("font-size: 12px; color: #8392A5; padding: 4px;");
    mainLayout->addWidget(m_statusLabel);

    m_progressBar = new QProgressBar;
    m_progressBar->setRange(0, 100);
    m_progressBar->setValue(0);
    m_progressBar->setTextVisible(false);
    m_progressBar->setFixedHeight(4);
    m_progressBar->hide();
    mainLayout->addWidget(m_progressBar);

    QHBoxLayout *contentLayout = new QHBoxLayout;
    contentLayout->setSpacing(12);

    m_ebookBrowser = new QTextBrowser;
    m_ebookBrowser->setStyleSheet(R"(
        QTextBrowser {
            background-color: #131a28;
            color: #e0e6ed;
            border: 2px solid rgba(0, 242, 254, 0.2);
            border-radius: 8px;
            padding: 20px;
            font-size: 15px;
            line-height: 1.8;
            selection-background-color: #264f78;
            selection-color: #ffffff;
        }
        QScrollBar:vertical {
            background: #1a2332;
            width: 8px;
            border-radius: 4px;
        }
        QScrollBar::handle:vertical {
            background: #3a4a5c;
            border-radius: 4px;
            min-height: 30px;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
    )");
    m_ebookBrowser->setOpenExternalLinks(false);
    contentLayout->addWidget(m_ebookBrowser, 3);

    m_avatarView = new QWebEngineView;
    m_avatarView->setMinimumWidth(380);
    m_avatarView->setMaximumWidth(420);
    m_avatarView->setStyleSheet("QWebEngineView { border: 2px solid rgba(0, 242, 254, 0.2); border-radius: 8px; }");

    m_urlInterceptor = new Live2DUrlInterceptor(m_assetDir, this);
    QWebEngineProfile *profile = m_avatarView->page()->profile();
    profile->setUrlRequestInterceptor(m_urlInterceptor);

    contentLayout->addWidget(m_avatarView, 1);

    mainLayout->addLayout(contentLayout);

    m_explainBtn = new QPushButton(QString::fromUtf8("✨ 学长讲讲"), this);
    m_explainBtn->setFixedSize(140, 40);
    m_explainBtn->setStyleSheet(R"(
        QPushButton {
            background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7c3aed, stop:1 #a855f7);
            color: white;
            border: none;
            border-radius: 20px;
            font-size: 14px;
            font-weight: bold;
            padding: 8px 16px;
        }
        QPushButton:hover {
            background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6d28d9, stop:1 #9333ea);
        }
        QPushButton:pressed {
            background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #5b21b6, stop:1 #7e22ce);
        }
    )");

    QGraphicsDropShadowEffect *shadow = new QGraphicsDropShadowEffect(this);
    shadow->setOffset(0, 4);
    shadow->setBlurRadius(16);
    shadow->setColor(QColor(124, 58, 237, 120));
    m_explainBtn->setGraphicsEffect(shadow);

    m_explainBtn->hide();
    connect(m_explainBtn, &QPushButton::clicked, this, &CompanionReadingDialog::onExplainButtonClicked);

    QString htmlPath = QCoreApplication::applicationDirPath() + "/avatar.html";
    if (!QFile::exists(htmlPath)) {
        htmlPath = "/home/xmy/code/build/src/client/avatar.html";
    }
    if (!QFile::exists(htmlPath)) {
        htmlPath = "/home/xmy/code/build/avatar.html";
    }
    if (!QFile::exists(htmlPath)) {
        htmlPath = m_assetDir + "/avatar.html";
    }
    if (!QFile::exists(htmlPath)) {
        htmlPath = "/home/xmy/code/src/html/avatar.html";
    }

    QString modelPath = QCoreApplication::applicationDirPath() + "/live2d/hiyori/hiyori_pro_t11.model3.json";
    if (!QFile::exists(modelPath)) {
        modelPath = "/home/xmy/code/build/src/client/live2d/hiyori/hiyori_pro_t11.model3.json";
    }
    if (!QFile::exists(modelPath)) {
        modelPath = "/home/xmy/code/build/live2d/hiyori/hiyori_pro_t11.model3.json";
    }
    if (!QFile::exists(modelPath)) {
        modelPath = QCoreApplication::applicationDirPath() + "/../live2d/hiyori/hiyori_pro_t11.model3.json";
    }
    if (!QFile::exists(modelPath)) {
        modelPath = "/home/xmy/code/bin/live2d_assets/hiyori/hiyori_pro_t11.model3.json";
    }
    if (!QFile::exists(modelPath)) {
        modelPath = m_assetDir + "/hiyori/hiyori_pro_t11.model3.json";
    }
    if (!QFile::exists(modelPath)) {
        modelPath = "/home/xmy/code/src/live2d/hiyori/hiyori_pro_t11.model3.json";
    }

    qDebug() << "HTML path:" << htmlPath;
    qDebug() << "Model path:" << modelPath;

    if (QFile::exists(htmlPath)) {
        m_avatarView->load(QUrl::fromLocalFile(htmlPath));

        QTimer::singleShot(2000, this, [this, modelPath]() {
            QString escapedPath = modelPath;
            escapedPath.replace("\\", "\\\\").replace("'", "\\'");
            QString jsCode = QString("loadModel('%1');").arg(escapedPath);
            qDebug() << "Calling JS:" << jsCode;
            m_avatarView->page()->runJavaScript(jsCode);
        });
    } else {
        m_avatarView->load(QUrl("http://localhost:8081/avatar.html"));
    }
}

void CompanionReadingDialog::loadDefaultContent()
{
    QString html = R"(
    <html>
    <head>
    <style>
        body {
            font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
            color: #8392A5;
            background-color: #131a28;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 80vh;
            text-align: center;
        }
        .icon {
            font-size: 64px;
            margin-bottom: 20px;
        }
        .title {
            font-size: 20px;
            color: #e0e6ed;
            margin-bottom: 12px;
        }
        .desc {
            font-size: 14px;
            color: #6b7280;
            line-height: 1.8;
        }
        .formats {
            margin-top: 20px;
            padding: 12px 24px;
            background: rgba(124, 58, 237, 0.1);
            border-radius: 8px;
            border: 1px solid rgba(124, 58, 237, 0.2);
        }
        .formats span {
            color: #a855f7;
            font-weight: bold;
        }
    </style>
    </head>
    <body>
        <div class="icon">📚</div>
        <div class="title">欢迎来到 AI 伴读</div>
        <div class="desc">
            点击右上角「上传电子书」按钮<br>
            上传您的 PDF 或 Markdown 学习资料<br>
            学姐将陪伴您一起学习
        </div>
        <div class="formats">
            支持格式：<span>.pdf</span> <span>.md</span> <span>.markdown</span> <span>.txt</span>
        </div>
    </body>
    </html>
    )";

    m_ebookBrowser->setHtml(html);
}

void CompanionReadingDialog::onUploadFileClicked()
{
    QString filePath = QFileDialog::getOpenFileName(
        this,
        QString::fromUtf8("选择电子书文件"),
        QDir::homePath(),
        QString::fromUtf8("电子书文件 (*.pdf *.md *.markdown *.txt);;PDF文件 (*.pdf);;Markdown文件 (*.md *.markdown);;文本文件 (*.txt);;所有文件 (*)")
    );

    if (filePath.isEmpty()) {
        return;
    }

    QFileInfo fi(filePath);
    m_currentFilePath = filePath;
    m_currentFileName = fi.fileName();

    m_fileLabel->setText(m_currentFileName);
    m_fileLabel->setStyleSheet("font-size: 12px; color: #22c55e; padding: 4px 12px; background: rgba(34, 197, 94, 0.1); border-radius: 4px; border: 1px solid rgba(34, 197, 94, 0.2);");

    QString suffix = fi.suffix().toLower();

    if (suffix == "md" || suffix == "markdown") {
        loadMarkdownFile(filePath);
    } else if (suffix == "pdf") {
        loadPdfFile(filePath);
    } else if (suffix == "txt") {
        loadMarkdownFile(filePath);
    } else {
        m_statusLabel->setText(QString::fromUtf8("⚠️ 不支持的文件格式"));
    }
}

void CompanionReadingDialog::loadMarkdownFile(const QString &filePath)
{
    QFile file(filePath);
    if (!file.open(QIODevice::ReadOnly | QIODevice::Text)) {
        m_statusLabel->setText(QString::fromUtf8("❌ 无法打开文件"));
        return;
    }

    QString content = QString::fromUtf8(file.readAll());
    file.close();

    QString html = markdownToHtml(content);
    m_ebookBrowser->setHtml(html);

    m_statusLabel->setText(QString::fromUtf8("✅ 已加载: ") + m_currentFileName);
    updateWindowTitle();
}

QString CompanionReadingDialog::markdownToHtml(const QString &markdown)
{
    QString html = R"(
    <html>
    <head>
    <style>
        body {
            font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
            color: #e0e6ed;
            background-color: #131a28;
            line-height: 1.9;
            font-size: 15px;
            padding: 10px;
        }
        h1 { color: #00f2fe; font-size: 24px; border-bottom: 2px solid rgba(0, 242, 254, 0.3); padding-bottom: 10px; margin-top: 20px; }
        h2 { color: #7c3aed; font-size: 20px; margin-top: 25px; }
        h3 { color: #a855f7; font-size: 17px; margin-top: 20px; }
        h4 { color: #c084fc; font-size: 15px; }
        p { margin: 12px 0; }
        ul, ol { margin: 10px 0; padding-left: 25px; }
        li { margin: 6px 0; }
        code {
            background-color: #1e293b;
            padding: 2px 6px;
            border-radius: 4px;
            color: #22d3ee;
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 13px;
        }
        pre {
            background-color: #1e293b;
            padding: 12px 16px;
            border-radius: 8px;
            overflow-x: auto;
            border: 1px solid rgba(0, 242, 254, 0.1);
        }
        pre code {
            background: none;
            padding: 0;
        }
        blockquote {
            border-left: 4px solid #7c3aed;
            padding-left: 16px;
            margin: 12px 0;
            color: #9ca3af;
            background: rgba(124, 58, 237, 0.05);
            padding: 8px 16px;
            border-radius: 0 8px 8px 0;
        }
        strong { color: #f59e0b; }
        em { color: #a78bfa; }
        a { color: #00f2fe; text-decoration: none; }
        a:hover { text-decoration: underline; }
        table { border-collapse: collapse; width: 100%; margin: 12px 0; }
        th, td { border: 1px solid rgba(0, 242, 254, 0.2); padding: 8px 12px; text-align: left; }
        th { background-color: rgba(0, 242, 254, 0.1); color: #00f2fe; }
        hr { border: none; border-top: 1px solid rgba(0, 242, 254, 0.2); margin: 20px 0; }
        img { max-width: 100%; border-radius: 8px; }
    </style>
    </head>
    <body>
    )";

    QString processed = markdown;

    processed.replace(QRegularExpression("```(\\w*)\\n([\\s\\S]*?)```"), "<pre><code>\\2</code></pre>");
    processed.replace(QRegularExpression("`(.*?)`"), "<code>\\1</code>");
    processed.replace(QRegularExpression("^### (.+)$", QRegularExpression::MultilineOption), "<h3>\\1</h3>");
    processed.replace(QRegularExpression("^## (.+)$", QRegularExpression::MultilineOption), "<h2>\\1</h2>");
    processed.replace(QRegularExpression("^# (.+)$", QRegularExpression::MultilineOption), "<h1>\\1</h1>");
    processed.replace(QRegularExpression("^#### (.+)$", QRegularExpression::MultilineOption), "<h4>\\1</h4>");
    processed.replace(QRegularExpression("^> (.+)$", QRegularExpression::MultilineOption), "<blockquote>\\1</blockquote>");
    processed.replace(QRegularExpression("\\*\\*(.+?)\\*\\*"), "<strong>\\1</strong>");
    processed.replace(QRegularExpression("\\*(.+?)\\*"), "<em>\\1</em>");
    processed.replace(QRegularExpression("^(\\d+)\\. (.+)$", QRegularExpression::MultilineOption), "<li>\\2</li>");
    processed.replace(QRegularExpression("^- (.+)$", QRegularExpression::MultilineOption), "<li>\\1</li>");
    processed.replace(QRegularExpression("\\n\\n"), "</p><p>");
    processed.replace(QRegularExpression("\\[(.+?)\\]\\((.+?)\\)"), "<a href=\"\\2\">\\1</a>");
    processed.replace(QRegularExpression("^---$", QRegularExpression::MultilineOption), "<hr>");

    html += "<p>" + processed + "</p>";
    html += "</body></html>";

    return html;
}

void CompanionReadingDialog::loadPdfFile(const QString &filePath)
{
    m_statusLabel->setText(QString::fromUtf8("⏳ 正在解析 PDF 文件..."));
    m_progressBar->show();
    m_progressBar->setValue(0);
    m_uploadBtn->setEnabled(false);

    QFile *file = new QFile(filePath);
    if (!file->open(QIODevice::ReadOnly)) {
        m_statusLabel->setText(QString::fromUtf8("❌ 无法打开 PDF 文件"));
        m_progressBar->hide();
        m_uploadBtn->setEnabled(true);
        delete file;
        return;
    }

    QHttpMultiPart *multiPart = new QHttpMultiPart(QHttpMultiPart::FormDataType);

    QHttpPart filePart;
    filePart.setHeader(QNetworkRequest::ContentTypeHeader, "application/pdf");
    filePart.setHeader(QNetworkRequest::ContentDispositionHeader, QVariant("form-data; name=\"file\"; filename=\"" + m_currentFileName + "\""));
    filePart.setBodyDevice(file);
    file->setParent(multiPart);
    multiPart->append(filePart);

    QUrl url("http://localhost:8081/api/ai/parse-pdf");
    QNetworkRequest request(url);

    QNetworkReply *reply = m_fileUploadManager->post(request, multiPart);
    multiPart->setParent(reply);

    connect(reply, &QNetworkReply::uploadProgress, this, &CompanionReadingDialog::onFileUploadProgress);
}

void CompanionReadingDialog::onFileUploadProgress(qint64 bytesSent, qint64 bytesTotal)
{
    if (bytesTotal > 0) {
        int progress = static_cast<int>(bytesSent * 100 / bytesTotal);
        m_progressBar->setValue(progress);
    }
}

void CompanionReadingDialog::onPdfParseReply(QNetworkReply *reply)
{
    m_progressBar->hide();
    m_uploadBtn->setEnabled(true);

    if (reply->error() != QNetworkReply::NoError) {
        m_statusLabel->setText(QString::fromUtf8("❌ PDF 解析失败: ") + reply->errorString());
        reply->deleteLater();
        return;
    }

    QByteArray data = reply->readAll();
    QJsonDocument doc = QJsonDocument::fromJson(data);

    if (!doc.isObject()) {
        m_statusLabel->setText(QString::fromUtf8("❌ 返回数据格式错误"));
        reply->deleteLater();
        return;
    }

    QJsonObject obj = doc.object();
    QString text = obj["text"].toString();

    if (text.isEmpty()) {
        m_statusLabel->setText(QString::fromUtf8("❌ PDF 内容为空"));
        reply->deleteLater();
        return;
    }

    QString html = markdownToHtml(text);
    m_ebookBrowser->setHtml(html);

    m_statusLabel->setText(QString::fromUtf8("✅ 已加载: ") + m_currentFileName);
    updateWindowTitle();

    reply->deleteLater();
}

void CompanionReadingDialog::updateWindowTitle()
{
    QString title = QString::fromUtf8("📖 AI伴读 - %1").arg(m_currentFileName);
    setWindowTitle(title);
}

void CompanionReadingDialog::onSelectionChanged()
{
    QString selected = m_ebookBrowser->textCursor().selectedText();
    if (selected.trimmed().isEmpty()) {
        QTimer::singleShot(200, this, [this]() {
            if (m_ebookBrowser->textCursor().selectedText().trimmed().isEmpty()) {
                hideExplainButton();
            }
        });
        return;
    }

    m_selectedText = selected.trimmed();
}

bool CompanionReadingDialog::eventFilter(QObject *watched, QEvent *event)
{
    if (watched == m_ebookBrowser->viewport()) {
        if (event->type() == QEvent::MouseButtonRelease) {
            QMouseEvent *mouseEvent = static_cast<QMouseEvent *>(event);
            if (mouseEvent->button() == Qt::LeftButton) {
                QString selected = m_ebookBrowser->textCursor().selectedText().trimmed();
                qDebug() << "[CompanionReading] MouseButtonRelease, selected text:" << selected.left(50);
                if (!selected.isEmpty()) {
                    m_selectedText = selected;
                    QPoint globalPos = m_ebookBrowser->viewport()->mapToGlobal(mouseEvent->pos());
                    qDebug() << "[CompanionReading] Showing button at global pos:" << globalPos;
                    QTimer::singleShot(50, this, [this, globalPos]() {
                        showExplainButton(globalPos);
                    });
                }
            }
        }
    }
    return QDialog::eventFilter(watched, event);
}

void CompanionReadingDialog::showExplainButton(const QPoint &globalPos)
{
    qDebug() << "[CompanionReading] showExplainButton called, globalPos:" << globalPos;
    
    QPoint adjustedPos(globalPos.x() - m_explainBtn->width() / 2,
                       globalPos.y() - m_explainBtn->height() - 12);

    QRect screenRect = QApplication::primaryScreen()->availableGeometry();
    if (adjustedPos.x() < screenRect.left()) {
        adjustedPos.setX(screenRect.left());
    }
    if (adjustedPos.x() + m_explainBtn->width() > screenRect.right()) {
        adjustedPos.setX(screenRect.right() - m_explainBtn->width());
    }
    if (adjustedPos.y() < screenRect.top()) {
        adjustedPos.setY(globalPos.y() + 20);
    }

    qDebug() << "[CompanionReading] adjustedPos:" << adjustedPos << "btn size:" << m_explainBtn->size();
    
    m_explainBtn->move(adjustedPos);
    m_explainBtn->raise();
    m_explainBtn->show();
    m_explainBtnVisible = true;
    
    qDebug() << "[CompanionReading] Button visible:" << m_explainBtn->isVisible() << "geometry:" << m_explainBtn->geometry();
}

void CompanionReadingDialog::hideExplainButton()
{
    m_explainBtn->hide();
    m_explainBtnVisible = false;
}

void CompanionReadingDialog::onExplainButtonClicked()
{
    if (m_selectedText.isEmpty()) {
        m_statusLabel->setText(QString::fromUtf8("⚠️ 未选中任何文字"));
        hideExplainButton();
        return;
    }

    hideExplainButton();
    m_statusLabel->setText(QString::fromUtf8("⏳ 学姐正在思考..."));
    sendCompanionReadRequest(m_selectedText);
}

void CompanionReadingDialog::sendCompanionReadRequest(const QString &selectedText)
{
    QJsonObject json;
    json["action"] = "companion_read";
    json["text"] = selectedText;
    json["userId"] = m_userId;

    QJsonDocument doc(json);
    QByteArray data = doc.toJson(QJsonDocument::Compact);

    QUrl url("http://localhost:8081/api/ai/companion-read");
    QNetworkRequest request(url);
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");

    m_networkManager->post(request, data);
}

void CompanionReadingDialog::onCompanionReadReply(QNetworkReply *reply)
{
    if (reply->error() != QNetworkReply::NoError) {
        m_statusLabel->setText(QString::fromUtf8("❌ 请求失败: ") + reply->errorString());
        reply->deleteLater();
        return;
    }

    QByteArray responseData = reply->readAll();
    QJsonDocument doc = QJsonDocument::fromJson(responseData);

    if (!doc.isObject()) {
        m_statusLabel->setText(QString::fromUtf8("❌ 返回数据格式错误"));
        reply->deleteLater();
        return;
    }

    QJsonObject obj = doc.object();

    if (obj.contains("error") && !obj["error"].toString().isEmpty()) {
        m_statusLabel->setText(QString::fromUtf8("❌ ") + obj["error"].toString());
        reply->deleteLater();
        return;
    }

    QString audioUrl = obj["audioUrl"].toString();
    QString explanationText = obj["explanationText"].toString();

    if (explanationText.isEmpty()) {
        m_statusLabel->setText(QString::fromUtf8("❌ 讲解内容为空"));
        reply->deleteLater();
        return;
    }

    m_statusLabel->setText(QString::fromUtf8("✨ 学姐讲解中..."));

    if (!audioUrl.isEmpty() && audioUrl != "null" && audioUrl != "undefined") {
        downloadAndPlayAudio(audioUrl, explanationText);
    } else {
        playAvatarAudio("", explanationText);
    }

    reply->deleteLater();
}

void CompanionReadingDialog::downloadAndPlayAudio(const QString &audioUrl, const QString &text)
{
    m_pendingExplanationText = text;
    
    if (m_currentAudioReply) {
        qDebug() << "[CompanionReading] Cancelling previous audio download";
        m_currentAudioReply->abort();
        m_currentAudioReply->deleteLater();
        m_currentAudioReply = nullptr;
    }
    
    if (m_currentAudioFile) {
        m_currentAudioFile->close();
        m_currentAudioFile->remove();
        delete m_currentAudioFile;
        m_currentAudioFile = nullptr;
    }
    
    QString audioDir = QCoreApplication::applicationDirPath() + "/audio_cache";
    QDir dir(audioDir);
    if (!dir.exists()) {
        dir.mkpath(".");
    }
    
    QString fileName = QUrl(audioUrl).fileName();
    QString localPath = audioDir + "/" + fileName;
    
    m_currentAudioFile = new QFile(localPath);
    if (m_currentAudioFile->exists()) {
        qDebug() << "[CompanionReading] Audio already cached:" << localPath;
        playAvatarAudio(localPath, text);
        delete m_currentAudioFile;
        m_currentAudioFile = nullptr;
        return;
    }
    
    if (!m_currentAudioFile->open(QIODevice::WriteOnly)) {
        qDebug() << "[CompanionReading] Cannot create audio file:" << localPath;
        playAvatarAudio("", text);
        delete m_currentAudioFile;
        m_currentAudioFile = nullptr;
        return;
    }
    
    qDebug() << "[CompanionReading] Downloading audio:" << audioUrl;
    QNetworkRequest request{QUrl(audioUrl)};
    m_currentAudioReply = m_audioDownloadManager->get(request);
}

void CompanionReadingDialog::onAudioDownloadFinished(QNetworkReply *reply)
{
    if (reply != m_currentAudioReply) {
        qDebug() << "[CompanionReading] Ignoring stale audio download reply";
        reply->deleteLater();
        return;
    }
    
    m_currentAudioReply = nullptr;
    
    if (reply->error() != QNetworkReply::NoError) {
        qDebug() << "[CompanionReading] Audio download failed:" << reply->errorString();
        playAvatarAudioBase64(QByteArray(), "", m_pendingExplanationText);
        reply->deleteLater();
        if (m_currentAudioFile) {
            m_currentAudioFile->close();
            m_currentAudioFile->remove();
            delete m_currentAudioFile;
            m_currentAudioFile = nullptr;
        }
        return;
    }
    
    QByteArray audioData = reply->readAll();
    qDebug() << "[CompanionReading] Audio downloaded, size:" << audioData.size() << "bytes";
    
    QString localPath;
    if (m_currentAudioFile && m_currentAudioFile->isOpen()) {
        m_currentAudioFile->write(audioData);
        m_currentAudioFile->close();
        localPath = m_currentAudioFile->fileName();
        delete m_currentAudioFile;
        m_currentAudioFile = nullptr;
    }
    
    QString mimeType = "audio/wav";
    playAvatarAudioBase64(audioData, mimeType, m_pendingExplanationText);
    
    reply->deleteLater();
}

void CompanionReadingDialog::playAvatarAudioBase64(const QByteArray &audioData, const QString &mimeType, const QString &text)
{
    QString escapedText = text;
    escapedText.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "\\r");

    QString audioUrl;
    if (!audioData.isEmpty()) {
        QString base64Audio = QString(audioData.toBase64());
        audioUrl = QString("data:%1;base64,%2").arg(mimeType).arg(base64Audio);
        qDebug() << "[CompanionReading] Playing audio as Base64, data URL length:" << audioUrl.length();
    } else {
        audioUrl = "";
    }
    
    QString escapedUrl = audioUrl;
    escapedUrl.replace("\\", "\\\\").replace("'", "\\'");
    
    QString jsCode = QString("playAvatarAudio('%1', '%2');").arg(escapedUrl).arg(escapedText);
    m_avatarView->page()->runJavaScript(jsCode);

    QTimer::singleShot(3000, this, [this]() {
        m_statusLabel->setText(QString::fromUtf8("✅ 学姐讲解完毕，继续划选文字吧"));
    });
}

void CompanionReadingDialog::playAvatarAudio(const QString &localAudioPath, const QString &text)
{
    QString escapedText = text;
    escapedText.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "\\r");

    QString audioUrl;
    if (localAudioPath.isEmpty()) {
        audioUrl = "";
    } else {
        audioUrl = QUrl::fromLocalFile(localAudioPath).toString();
    }
    
    QString escapedUrl = audioUrl;
    escapedUrl.replace("\\", "\\\\").replace("'", "\\'");

    qDebug() << "[CompanionReading] Playing audio:" << audioUrl;
    
    QString jsCode = QString("playAvatarAudio('%1', '%2');").arg(escapedUrl).arg(escapedText);
    m_avatarView->page()->runJavaScript(jsCode);

    QTimer::singleShot(3000, this, [this]() {
        m_statusLabel->setText(QString::fromUtf8("✅ 学姐讲解完毕，继续划选文字吧"));
    });
}
