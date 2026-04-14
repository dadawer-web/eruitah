#include "messagewidget.h"
#include <QApplication>
#include <QPixmap>
#include <QPainter>
#include <QBrush>
#include <QPen>
#include <QPainterPath>
#include <QDebug>
#include <QRegularExpression>
#include <QNetworkAccessManager>
#include <QNetworkRequest>
#include <QNetworkReply>
#include <QEventLoop>
#include <QListWidget>
#include <QScrollBar>
#include <QTextDocument>
#include <QTextBlock>
#include <QTextBlockFormat>
#include <QTextCursor>
#include <QAbstractTextDocumentLayout>
#include <QBuffer>
#include <QtMath>
#include <QStackedWidget>
#include <QVBoxLayout>
#include <QByteArray>
#include <QWebEngineView>
#include <QWebEngineSettings>
#include <QRandomGenerator>

#include "qtmaterialavatar.h"
#include "lib/qtmaterialtheme.h"

#ifdef _WIN32
    #include <winsock2.h>
    #include <ws2tcpip.h>
    #undef byte
#endif

MessageWidget::MessageWidget(bool isSender, const QString &text, const QString &avatarPath, 
                             const QString &senderName, const QString &timeStr, 
                             QWidget *parent)
    : QWidget(parent)
    , m_isSender(isSender)
    , m_senderName(senderName)
    , m_rawText(text)
    , m_avatarPath(avatarPath)
    , m_headerWidget(nullptr)
    , m_contentContainer(nullptr)
    , m_bubbleWidget(nullptr)
    , m_avatarLabel(nullptr)
    , m_nameLabel(nullptr)
    , m_contentStack(nullptr)
    , m_contentBrowser(nullptr)
    , m_imageContainer(nullptr)
    , m_imageLabel(nullptr)
    , m_mermaidView(nullptr)
    , m_timeLabel(nullptr)
    , m_voiceContainer(nullptr)
    , m_playVoiceBtn(nullptr)
    , m_mediaPlayer(nullptr)
    , m_voiceDuration(0)
{
    setupUI(avatarPath, senderName, timeStr);
    applyStyles();
    processAndSetContent(text);
}

void MessageWidget::setupUI(const QString &avatarPath, const QString &senderName, const QString &timeStr)
{
    setStyleSheet("background: transparent;");
    
    QString displayName = senderName.isEmpty() 
        ? (m_isSender ? "You" : "User") 
        : senderName;
    QString initial = displayName.isEmpty() ? "U" : QString(displayName[0]).toUpper();
    
    m_avatarLabel = new QtMaterialAvatar(QChar(initial[0]), this);
    m_avatarLabel->setSize(40);
    
    if (!avatarPath.isEmpty()) {
        QImage avatarImage;
        if (avatarImage.load(avatarPath)) {
            m_avatarLabel->setImage(avatarImage);
        }
    }
    
    if (m_isSender) {
        m_avatarLabel->setBackgroundColor(QColor("#3b82f6"));
        m_avatarLabel->setTextColor(QColor("#ffffff"));
    } else {
        m_avatarLabel->setBackgroundColor(QColor("#10a37f"));
        m_avatarLabel->setTextColor(QColor("#ffffff"));
    }
    
    m_nameLabel = new QLabel(this);
    m_nameLabel->setText(displayName);
    
    m_timeLabel = new QLabel(this);
    m_timeLabel->setText(timeStr.isEmpty() 
        ? QDateTime::currentDateTime().toString("hh:mm") 
        : timeStr);
    
    m_headerWidget = new QWidget(this);
    m_headerWidget->setStyleSheet("background: transparent;");
    QHBoxLayout *headerLayout = new QHBoxLayout(m_headerWidget);
    headerLayout->setContentsMargins(0, 0, 0, 0);
    headerLayout->setSpacing(8);
    
    if (!m_isSender) {
        headerLayout->addWidget(m_nameLabel, 0, Qt::AlignLeft);
        headerLayout->addStretch();
        headerLayout->addWidget(m_timeLabel, 0, Qt::AlignRight);
    } else {
        headerLayout->addWidget(m_timeLabel, 0, Qt::AlignLeft);
        headerLayout->addStretch();
        headerLayout->addWidget(m_nameLabel, 0, Qt::AlignRight);
    }
    
    m_bubbleWidget = new QWidget(this);
    m_bubbleWidget->setObjectName("messageBubble");
    QVBoxLayout *bubbleLayout = new QVBoxLayout(m_bubbleWidget);
    bubbleLayout->setContentsMargins(12, 8, 12, 8);
    bubbleLayout->setSpacing(4);
    
    m_contentStack = new QStackedWidget(m_bubbleWidget);
    m_contentStack->setStyleSheet("background: transparent;");
    
    m_contentBrowser = new QTextBrowser(m_bubbleWidget);
    m_contentBrowser->setOpenExternalLinks(true);
    m_contentBrowser->setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    m_contentBrowser->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    m_contentBrowser->setFrameShape(QFrame::NoFrame);
    m_contentBrowser->setFrameStyle(QFrame::NoFrame);
    m_contentBrowser->setLineWidth(0);
    m_contentBrowser->setMidLineWidth(0);
    m_contentBrowser->setLineWrapMode(QTextBrowser::WidgetWidth);
    m_contentBrowser->document()->setDocumentMargin(0);
    m_contentBrowser->viewport()->setContentsMargins(0, 0, 0, 0);
    m_contentBrowser->viewport()->setAutoFillBackground(false);
    m_contentBrowser->setAttribute(Qt::WA_TransparentForMouseEvents, true);
    m_contentBrowser->setTextInteractionFlags(Qt::TextBrowserInteraction | Qt::TextSelectableByMouse);
    m_contentBrowser->setMinimumWidth(60);
    m_contentStack->addWidget(m_contentBrowser);
    
    m_imageContainer = new QWidget(m_bubbleWidget);
    m_imageContainer->setStyleSheet("background: transparent;");
    QVBoxLayout *imageLayout = new QVBoxLayout(m_imageContainer);
    imageLayout->setContentsMargins(0, 0, 0, 0);
    imageLayout->setSpacing(4);
    m_contentStack->addWidget(m_imageContainer);
    
    m_mermaidView = new QWebEngineView(m_bubbleWidget);
    m_mermaidView->setStyleSheet("background: transparent;");
    m_mermaidView->page()->setBackgroundColor(Qt::transparent);
    m_contentStack->addWidget(m_mermaidView);
    
    m_voiceContainer = new QWidget(m_bubbleWidget);
    m_voiceContainer->setStyleSheet("background: transparent;");
    QHBoxLayout *voiceLayout = new QHBoxLayout(m_voiceContainer);
    voiceLayout->setContentsMargins(8, 4, 8, 4);
    voiceLayout->setSpacing(8);
    
    m_playVoiceBtn = new QPushButton("▶️ 语音消息", m_voiceContainer);
    m_playVoiceBtn->setStyleSheet(
        "QPushButton { background-color: #3b82f6; color: #ffffff; border: none; border-radius: 16px; "
        "padding: 8px 16px; font-size: 14px; min-width: 120px; }"
        "QPushButton:hover { background-color: #2563eb; }"
        "QPushButton:pressed { background-color: #1d4ed8; }"
    );
    m_playVoiceBtn->setCursor(Qt::PointingHandCursor);
    voiceLayout->addWidget(m_playVoiceBtn);
    voiceLayout->addStretch();
    
    m_contentStack->addWidget(m_voiceContainer);
    m_voiceContainer->hide();
    
    m_mediaPlayer = new QMediaPlayer(this);
    connect(m_mediaPlayer, &QMediaPlayer::stateChanged, this, &MessageWidget::onMediaStateChanged);
    connect(m_mediaPlayer, &QMediaPlayer::positionChanged, this, [this](qint64 position) {
        if (m_mediaPlayer && m_mediaPlayer->duration() > 0) {
            if (position >= m_mediaPlayer->duration() - 100) {
                qDebug() << "Voice playback finished (position:" << position << "duration:" << m_mediaPlayer->duration() << ")";
                QString btnText = m_voiceDuration > 0 
                    ? QString("▶️ 语音消息 %1s").arg(m_voiceDuration) 
                    : QString("▶️ 语音消息");
                m_playVoiceBtn->setText(btnText);
                m_playVoiceBtn->setStyleSheet(
                    "QPushButton { background-color: #3b82f6; color: #ffffff; border: none; border-radius: 16px; "
                    "padding: 8px 16px; font-size: 14px; min-width: 120px; }"
                    "QPushButton:hover { background-color: #2563eb; }"
                    "QPushButton:pressed { background-color: #1d4ed8; }"
                );
            }
        }
    });
    connect(m_mediaPlayer, QOverload<QMediaPlayer::Error>::of(&QMediaPlayer::error), this, [this](QMediaPlayer::Error error) {
        qDebug() << "Media player error:" << error;
        QString btnText = m_voiceDuration > 0 
            ? QString("▶️ 语音消息 %1s").arg(m_voiceDuration) 
            : QString("▶️ 语音消息");
        m_playVoiceBtn->setText(btnText);
    });
    connect(m_playVoiceBtn, &QPushButton::clicked, this, &MessageWidget::onPlayVoiceClicked);
    
    m_contentStack->setCurrentWidget(m_contentBrowser);
    
    bubbleLayout->addWidget(m_contentStack);
    
    m_contentContainer = new QWidget(this);
    m_contentContainer->setStyleSheet("background: transparent;");
    QVBoxLayout *bodyLayout = new QVBoxLayout(m_contentContainer);
    bodyLayout->setContentsMargins(0, 0, 0, 0);
    bodyLayout->setSpacing(4);
    bodyLayout->addWidget(m_headerWidget);
    if (!m_isSender) {
        bodyLayout->addWidget(m_bubbleWidget, 0, Qt::AlignLeft);
    } else {
        bodyLayout->addWidget(m_bubbleWidget, 0, Qt::AlignRight);
    }
    
    QHBoxLayout *mainLayout = new QHBoxLayout(this);
    mainLayout->setContentsMargins(12, 4, 12, 4);
    mainLayout->setSpacing(8);
    
    if (!m_isSender) {
        mainLayout->addWidget(m_avatarLabel, 0, Qt::AlignTop);
        mainLayout->addWidget(m_contentContainer, 0);
        mainLayout->addStretch(1);
    } else {
        mainLayout->addStretch(1);
        mainLayout->addWidget(m_contentContainer, 0);
        mainLayout->addWidget(m_avatarLabel, 0, Qt::AlignTop);
    }
    
    setLayout(mainLayout);
    setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Minimum);
}

void MessageWidget::applyStyles()
{
    setStyleSheet("background: transparent;");
    
    QString nameColor = m_isSender ? "#60a5fa" : "#34d399";
    QString nameStyle = QString(
        "QLabel { color: %1; font-size: 14px; font-weight: 600; background: transparent; }"
    ).arg(nameColor);
    m_nameLabel->setStyleSheet(nameStyle);
    
    QString timeStyle = QString(
        "QLabel { color: #6b7280; font-size: 11px; background: transparent; }"
    );
    m_timeLabel->setStyleSheet(timeStyle);
    
    m_headerWidget->setStyleSheet("background: transparent;");
    m_contentContainer->setStyleSheet("background: transparent;");
    
    QString bubbleBgColor = m_isSender ? "#2d3748" : "#1e293b";
    QString borderColor = m_isSender ? "#3d4a5c" : "#2d3c4e";
    
    QString bubbleStyle = QString(
        "QWidget#messageBubble { background-color: %1; border: 1px solid %2; border-radius: 12px; }"
    ).arg(bubbleBgColor).arg(borderColor);
    
    if (m_bubbleWidget) {
        m_bubbleWidget->setStyleSheet(bubbleStyle);
    }
    
    QString browserStyle = QString(
        "QTextBrowser { background-color: transparent; color: #f1f5f9; font-size: 14px; border: none; padding: 0; margin: 0; }"
        "QTextBrowser::selection { background-color: #3b82f6; color: #ffffff; }"
        "QTextBrowser viewport { background-color: transparent; padding: 0; margin: 0; }"
    );
    if (m_contentBrowser) {
        m_contentBrowser->setStyleSheet(browserStyle);
    }
}

void MessageWidget::processAndSetContent(const QString &text)
{
    QString processedText = text.trimmed();
    
    if (containsImage(processedText)) {
        processedText = extractAndDisplayImages(processedText);
    }
    
    if (containsMermaid(processedText)) {
        QString mermaidCode;
        QRegularExpression mermaidRegex("```mermaid\\s*\\n([\\s\\S]*?)\\n```");
        QRegularExpressionMatch match = mermaidRegex.match(processedText);
        if (match.hasMatch()) {
            mermaidCode = match.captured(1);
            renderMermaidDiagram(mermaidCode);
            processedText = processMermaidInText(processedText);
        }
    }
    
    bool isCodeContent = looksLikeCode(processedText);
    
    if (isCodeContent) {
        QString escapedCode = escapeForMarkdown(processedText);
        m_contentBrowser->setMarkdown("```\n" + escapedCode + "\n```");
        m_rawText = processedText;
        
        m_contentBrowser->setStyleSheet(
            "QTextBrowser { background-color: transparent; color: #f1f5f9; font-family: 'Consolas', 'Monaco', 'Courier New', monospace; font-size: 13px; border: none; padding: 0; margin: 0; }"
            "QTextBrowser::selection { background-color: #3b82f6; color: #ffffff; }"
            "QTextBrowser viewport { background-color: transparent; padding: 0; margin: 0; }"
        );
    } else {
        m_contentBrowser->setMarkdown(processedText);
        m_rawText = processedText;
    }
    
    QTextDocument *doc = m_contentBrowser->document();
    doc->setDocumentMargin(0);
    
    for (QTextBlock block = doc->begin(); block.isValid(); block = block.next()) {
        QTextCursor cursor(block);
        QTextBlockFormat blockFormat = block.blockFormat();
        blockFormat.setTopMargin(0);
        blockFormat.setBottomMargin(0);
        blockFormat.setNonBreakableLines(false);
        cursor.setBlockFormat(blockFormat);
    }
    
    const int maxBubbleWidth = 600;
    const int minBubbleWidth = 200;
    const int horizontalPadding = 24;
    const int verticalPadding = 16;
    
    doc->setTextWidth(maxBubbleWidth);
    doc->adjustSize();
    
    int textWidth = qCeil(doc->idealWidth());
    int textHeight = qCeil(doc->size().height());
    
    int contentWidth = qMin(textWidth, maxBubbleWidth - horizontalPadding * 2);
    contentWidth = qMax(minBubbleWidth - horizontalPadding * 2, contentWidth);
    
    if (textWidth > contentWidth) {
        doc->setTextWidth(contentWidth);
        doc->adjustSize();
        textHeight = qCeil(doc->size().height());
    }
    
    int bubbleWidth = contentWidth + horizontalPadding * 2;
    int bubbleHeight = textHeight + verticalPadding * 2;
    
    if (!m_imageLabels.isEmpty()) {
        int totalImageHeight = 0;
        for (QLabel *imgLabel : m_imageLabels) {
            totalImageHeight += imgLabel->sizeHint().height() + 8;
        }
        bubbleHeight += totalImageHeight;
        bubbleWidth = qMax(bubbleWidth, 350);
    }
    
    if (m_mermaidView && m_contentStack->currentWidget() == m_mermaidView) {
        bubbleWidth = 500;
        bubbleHeight = 400;
    }
    
    m_contentBrowser->setMinimumWidth(contentWidth);
    m_contentBrowser->setMaximumWidth(contentWidth);
    m_contentBrowser->setMinimumHeight(textHeight + 10);
    m_contentBrowser->setMaximumHeight(textHeight + 10);
    
    m_bubbleWidget->setMinimumWidth(bubbleWidth);
    m_bubbleWidget->setMaximumWidth(bubbleWidth);
    m_bubbleWidget->setMinimumHeight(bubbleHeight);
    m_bubbleWidget->setMaximumHeight(bubbleHeight);
    
    m_contentBrowser->updateGeometry();
    m_bubbleWidget->updateGeometry();
    updateGeometry();
}

bool MessageWidget::containsImage(const QString &text)
{
    return text.contains("[IMAGE]");
}

QString MessageWidget::extractAndDisplayImages(const QString &text)
{
    QString result = text;
    QRegularExpression imageRegex("\\[IMAGE\\]([^,]+),([^\\[]+)");
    QRegularExpressionMatchIterator it = imageRegex.globalMatch(text);
    
    while (it.hasNext()) {
        QRegularExpressionMatch match = it.next();
        QString imageType = match.captured(1);
        QString base64Data = match.captured(2);
        
        QByteArray imageData = QByteArray::fromBase64(base64Data.toUtf8());
        QPixmap pixmap;
        if (pixmap.loadFromData(imageData)) {
            if (pixmap.width() > 300 || pixmap.height() > 300) {
                pixmap = pixmap.scaled(300, 300, Qt::KeepAspectRatio, Qt::SmoothTransformation);
            }
            
            QLabel *imageLabel = new QLabel(m_imageContainer);
            imageLabel->setPixmap(pixmap);
            imageLabel->setStyleSheet("border-radius: 8px; background: transparent;");
            imageLabel->setFixedSize(pixmap.size());
            
            QVBoxLayout *layout = qobject_cast<QVBoxLayout*>(m_imageContainer->layout());
            if (layout) {
                layout->addWidget(imageLabel);
            }
            
            m_imageLabels.append(imageLabel);
        }
        
        result.remove(match.captured(0));
    }
    
    if (!m_imageLabels.isEmpty()) {
        m_contentStack->setCurrentWidget(m_imageContainer);
    }
    
    return result.trimmed();
}

bool MessageWidget::containsMermaid(const QString &text)
{
    return text.contains("```mermaid");
}

void MessageWidget::renderMermaidDiagram(const QString &mermaidCode)
{
    QString html = QString(R"(
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <style>
        body {
            background: transparent;
            margin: 0;
            padding: 10px;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .mermaid {
            background: transparent;
        }
        .mermaid svg {
            max-width: 100%%;
            height: auto;
        }
    </style>
</head>
<body>
    <div class="mermaid">%1</div>
    <script>
        mermaid.initialize({ 
            startOnLoad: true,
            theme: 'dark',
            themeVariables: {
                primaryColor: '#3b82f6',
                primaryTextColor: '#fff',
                primaryBorderColor: '#60a5fa',
                lineColor: '#94a3b8',
                secondaryColor: '#1e293b',
                tertiaryColor: '#1e293b',
                background: '#1e293b',
                mainBkg: '#1e293b',
                nodeBorder: '#3b82f6',
                clusterBkg: '#1e293b',
                titleColor: '#f1f5f9',
                edgeLabelBackground: '#1e293b'
            }
        });
    </script>
</body>
</html>
)").arg(mermaidCode.toHtmlEscaped());
    
    m_mermaidView->setHtml(html);
    m_contentStack->setCurrentWidget(m_mermaidView);
}

QString MessageWidget::processMermaidInText(const QString &text)
{
    QString result = text;
    QRegularExpression mermaidRegex("```mermaid\\s*\\n[\\s\\S]*?\\n```");
    result.remove(mermaidRegex);
    return result.trimmed();
}

bool MessageWidget::looksLikeCode(const QString &text)
{
    static QRegularExpression codePatterns[] = {
        QRegularExpression(R"(#include\s*<[^>]+>)"),
        QRegularExpression(R"(#include\s*"[^"]+")"),
        QRegularExpression(R"(\b(int|float|double|char|void|return|if|else|for|while|class|struct|public|private|protected|new|delete|cout|cin|std::|printf|scanf)\b)"),
        QRegularExpression(R"(\b(def |import |from |print\(|function |var |let |const |=>|\$\{)\b)"),
        QRegularExpression(R"(\{[\s\S]*\})"),
        QRegularExpression(R"([\[\](){};]=*)"),
    };
    
    int codeIndicators = 0;
    for (const auto& pattern : codePatterns) {
        if (pattern.match(text).hasMatch()) {
            codeIndicators++;
        }
    }
    
    if (codeIndicators >= 2) return true;
    
    int lineCount = text.count('\n') + 1;
    if (lineCount >= 3 && (text.contains(';') || text.contains('{') || text.contains('}'))) {
        return true;
    }
    
    if (text.contains("//") || text.contains("/*") || text.contains("#!")) {
        return true;
    }
    
    return false;
}

QString MessageWidget::escapeForMarkdown(const QString &text)
{
    QString result = text;
    result.replace("\\", "\\\\");
    result.replace("`", "\\`");
    result.replace("*", "\\*");
    result.replace("_", "\\_");
    result.replace("#", "\\#");
    result.replace("+", "\\+");
    result.replace("-", "\\-");
    result.replace("!", "\\!");
    result.replace("|", "\\|");
    result.replace("<", "&lt;");
    result.replace(">", "&gt;");
    result.replace("&", "&amp;");
    return result;
}

void MessageWidget::appendText(const QString &text)
{
    if (m_contentBrowser) {
        m_rawText += text;
        
        QTextDocument *doc = m_contentBrowser->document();
        doc->setDocumentMargin(0);
        
        m_contentBrowser->setMarkdown(m_rawText);
        
        for (QTextBlock block = doc->begin(); block.isValid(); block = block.next()) {
            QTextCursor cursor(block);
            QTextBlockFormat blockFormat = block.blockFormat();
            blockFormat.setTopMargin(0);
            blockFormat.setBottomMargin(0);
            cursor.setBlockFormat(blockFormat);
        }
        
        const int maxBubbleWidth = 600;
        const int horizontalPadding = 24;
        const int verticalPadding = 16;
        const int maxTextWidth = maxBubbleWidth - horizontalPadding * 2;
        
        doc->setTextWidth(maxTextWidth);
        doc->adjustSize();
        
        int textWidth = qCeil(doc->idealWidth());
        int textHeight = qCeil(doc->size().height());
        
        int contentWidth = qMin(textWidth, maxTextWidth);
        
        if (textWidth > contentWidth) {
            doc->setTextWidth(contentWidth);
            doc->adjustSize();
            textHeight = qCeil(doc->size().height());
        }
        
        int bubbleWidth = contentWidth + horizontalPadding * 2;
        int bubbleHeight = textHeight + verticalPadding * 2;
        
        m_contentBrowser->setMinimumWidth(contentWidth);
        m_contentBrowser->setMaximumWidth(contentWidth);
        m_contentBrowser->setMinimumHeight(textHeight + 10);
        m_contentBrowser->setMaximumHeight(textHeight + 10);
        
        m_bubbleWidget->setMinimumWidth(bubbleWidth);
        m_bubbleWidget->setMaximumWidth(bubbleWidth);
        m_bubbleWidget->setMinimumHeight(bubbleHeight);
        m_bubbleWidget->setMaximumHeight(bubbleHeight);
        
        updateGeometry();
        
        QWidget* parent = this->parentWidget();
        while (parent) {
            QListWidget* listWidget = qobject_cast<QListWidget*>(parent);
            if (listWidget) {
                for (int i = 0; i < listWidget->count(); ++i) {
                    QListWidgetItem* item = listWidget->item(i);
                    if (item && listWidget->itemWidget(item) == this) {
                        item->setSizeHint(sizeHint());
                        listWidget->updateGeometry();
                        QScrollBar *scrollBar = listWidget->verticalScrollBar();
                        if (scrollBar) {
                            scrollBar->setValue(scrollBar->maximum());
                        }
                        break;
                    }
                }
                break;
            }
            parent = parent->parentWidget();
        }
    }
}

void MessageWidget::setMarkdownContent(const QString &markdown)
{
    if (m_contentBrowser) {
        m_rawText = markdown.trimmed();
        
        QTextDocument *doc = m_contentBrowser->document();
        doc->setDocumentMargin(0);
        
        m_contentBrowser->setMarkdown(m_rawText);
        
        for (QTextBlock block = doc->begin(); block.isValid(); block = block.next()) {
            QTextCursor cursor(block);
            QTextBlockFormat blockFormat = block.blockFormat();
            blockFormat.setTopMargin(0);
            blockFormat.setBottomMargin(0);
            cursor.setBlockFormat(blockFormat);
        }
        
        const int maxBubbleWidth = 600;
        const int horizontalPadding = 24;
        const int verticalPadding = 16;
        const int maxTextWidth = maxBubbleWidth - horizontalPadding * 2;
        
        doc->setTextWidth(maxTextWidth);
        doc->adjustSize();
        
        int textWidth = qCeil(doc->idealWidth());
        int textHeight = qCeil(doc->size().height());
        
        int contentWidth = qMin(textWidth, maxTextWidth);
        
        if (textWidth > contentWidth) {
            doc->setTextWidth(contentWidth);
            doc->adjustSize();
            textHeight = qCeil(doc->size().height());
        }
        
        int bubbleWidth = contentWidth + horizontalPadding * 2;
        int bubbleHeight = textHeight + verticalPadding * 2;
        
        m_contentBrowser->setMinimumWidth(contentWidth);
        m_contentBrowser->setMaximumWidth(contentWidth);
        m_contentBrowser->setMinimumHeight(textHeight + 10);
        m_contentBrowser->setMaximumHeight(textHeight + 10);
        
        m_bubbleWidget->setMinimumWidth(bubbleWidth);
        m_bubbleWidget->setMaximumWidth(bubbleWidth);
        m_bubbleWidget->setMinimumHeight(bubbleHeight);
        m_bubbleWidget->setMaximumHeight(bubbleHeight);
        
        updateGeometry();
    }
}

QSize MessageWidget::sizeHint() const
{
    if (!m_contentBrowser || !m_headerWidget || !m_bubbleWidget) {
        return QWidget::sizeHint();
    }
    
    int headerHeight = m_headerWidget->sizeHint().height();
    int bubbleHeight = m_bubbleWidget->height();
    int totalHeight = headerHeight + bubbleHeight + 12;
    
    int totalWidth = m_bubbleWidget->width() + 70;
    
    return QSize(totalWidth, totalHeight);
}

void MessageWidget::setVoiceContent(const QString &audioPath, int duration) {
    m_voiceUrl = audioPath;
    m_voiceDuration = duration;
    
    m_contentStack->setCurrentWidget(m_voiceContainer);
    m_voiceContainer->show();
    
    QString btnText = duration > 0 
        ? QString("▶️ 语音消息 %1s").arg(duration) 
        : QString("▶️ 语音消息");
    m_playVoiceBtn->setText(btnText);
    
    m_bubbleWidget->setMinimumWidth(200);
    m_bubbleWidget->setMaximumWidth(300);
    m_bubbleWidget->setMinimumHeight(50);
    m_bubbleWidget->setMaximumHeight(50);
    
    updateGeometry();
}

void MessageWidget::onPlayVoiceClicked() {
    if (!m_mediaPlayer || m_voiceUrl.isEmpty()) {
        return;
    }
    
    qDebug() << "onPlayVoiceClicked - voiceUrl:" << m_voiceUrl;
    
    if (m_mediaPlayer->state() == QMediaPlayer::PlayingState) {
        m_mediaPlayer->stop();
        QString btnText = m_voiceDuration > 0 
            ? QString("▶️ 语音消息 %1s").arg(m_voiceDuration) 
            : QString("▶️ 语音消息");
        m_playVoiceBtn->setText(btnText);
        m_playVoiceBtn->setStyleSheet(
            "QPushButton { background-color: #3b82f6; color: #ffffff; border: none; border-radius: 16px; "
            "padding: 8px 16px; font-size: 14px; min-width: 120px; }"
            "QPushButton:hover { background-color: #2563eb; }"
            "QPushButton:pressed { background-color: #1d4ed8; }"
        );
    } else {
        QUrl mediaUrl;
        if (m_voiceUrl.startsWith("http://") || m_voiceUrl.startsWith("https://")) {
            mediaUrl = QUrl(m_voiceUrl);
            qDebug() << "Playing from HTTP URL:" << mediaUrl.toString();
        } else if (m_voiceUrl.startsWith("/")) {
            mediaUrl = QUrl::fromLocalFile(m_voiceUrl);
            qDebug() << "Playing from local file:" << mediaUrl.toString();
        } else {
            mediaUrl = QUrl::fromLocalFile(m_voiceUrl);
            qDebug() << "Playing as local path:" << mediaUrl.toString();
        }
        
        m_mediaPlayer->setMedia(mediaUrl);
        m_mediaPlayer->play();
        
        QString btnText = m_voiceDuration > 0 
            ? QString("🔊 播放中 %1s").arg(m_voiceDuration) 
            : QString("🔊 播放中");
        m_playVoiceBtn->setText(btnText);
        m_playVoiceBtn->setStyleSheet(
            "QPushButton { background-color: #ef4444; color: #ffffff; border: none; border-radius: 16px; "
            "padding: 8px 16px; font-size: 14px; min-width: 120px; }"
            "QPushButton:hover { background-color: #dc2626; }"
        );
    }
}

void MessageWidget::onMediaStateChanged(QMediaPlayer::State state) {
    if (state == QMediaPlayer::StoppedState) {
        QString btnText = m_voiceDuration > 0 
            ? QString("▶️ 语音消息 %1s").arg(m_voiceDuration) 
            : QString("▶️ 语音消息");
        m_playVoiceBtn->setText(btnText);
    }
}

void MessageWidget::paintEvent(QPaintEvent *event)
{
    Q_UNUSED(event)
    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing, true);
    painter.fillRect(rect(), Qt::transparent);
}
