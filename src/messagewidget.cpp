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
    , m_headerWidget(nullptr)
    , m_contentContainer(nullptr)
    , m_bubbleWidget(nullptr)
    , m_avatarLabel(nullptr)
    , m_nameLabel(nullptr)
    , m_contentBrowser(nullptr)
    , m_timeLabel(nullptr)
{
    setupUI(text, avatarPath, senderName, timeStr);
    applyStyles();
}

void MessageWidget::setupUI(const QString &text, const QString &avatarPath, 
                            const QString &senderName, const QString &timeStr)
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
    m_nameLabel->setStyleSheet("color: #9ca3af; font-size: 12px; font-weight: 500; background: transparent;");
    
    m_timeLabel = new QLabel(this);
    m_timeLabel->setText(timeStr.isEmpty() 
        ? QDateTime::currentDateTime().toString("hh:mm") 
        : timeStr);
    m_timeLabel->setStyleSheet("color: #6b7280; font-size: 11px; background: transparent;");
    
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
    bubbleLayout->setContentsMargins(24, 16, 24, 16);
    bubbleLayout->setSpacing(0);
    
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
    m_contentBrowser->setTextInteractionFlags(Qt::TextBrowserInteraction | Qt::TextSelectableByMouse);
    m_contentBrowser->setMinimumWidth(60);
    m_contentBrowser->setMaximumWidth(600);
    
    processAndSetContent(text);
    
    bubbleLayout->addWidget(m_contentBrowser);
    
    m_contentContainer = new QWidget(this);
    m_contentContainer->setStyleSheet("background: transparent;");
    QVBoxLayout *bodyLayout = new QVBoxLayout(m_contentContainer);
    bodyLayout->setContentsMargins(0, 0, 0, 0);
    bodyLayout->setSpacing(1);
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
        "QTextBrowser { background-color: transparent; color: #f1f5f9; font-size: 15px; border: none; padding: 0; margin: 0; }"
        "QTextBrowser::selection { background-color: #3b82f6; color: #ffffff; }"
        "QTextBrowser viewport { background-color: transparent; padding: 0; margin: 0; }"
    );
    if (m_contentBrowser) {
        m_contentBrowser->setStyleSheet(browserStyle);
    }
}

QByteArray MessageWidget::imageDataFromPixmap(const QPixmap &pixmap)
{
    QByteArray imageData;
    QBuffer buffer(&imageData);
    buffer.open(QIODevice::WriteOnly);
    pixmap.save(&buffer, "PNG");
    buffer.close();
    return imageData;
}

int MessageWidget::calculateDocumentHeight(QTextDocument *doc, int textWidth)
{
    doc->setTextWidth(textWidth);
    
    // 使用 documentLayout 获取渲染后的实际尺寸
    QAbstractTextDocumentLayout *layout = doc->documentLayout();
    QSizeF docSize = layout->documentSize();
    
    // 返回向上取整的高度，并添加更多的安全边距
    // 长文本可能需要更多的空间
    int blockCount = doc->blockCount();
    int extraPadding = qMax(16, blockCount * 2);  // 每个段落额外 2px
    
    return qCeil(docSize.height()) + extraPadding + 16;
}

void MessageWidget::processAndSetContent(const QString &text)
{
    QString processedText = text;
    
    if (text.startsWith("data:image/") || text.startsWith("[EMOJI_DATA:") || text.startsWith("[IMAGE]")) {
        QByteArray imageData;
        
        if (text.startsWith("data:image/")) {
            int commaPos = text.indexOf(',');
            if (commaPos != -1) {
                imageData = QByteArray::fromBase64(text.mid(commaPos + 1).toUtf8());
            }
        } else if (text.startsWith("[EMOJI_DATA:")) {
            int startPos = text.indexOf(':') + 1;
            int endPos = text.lastIndexOf(']');
            if (startPos != -1 && endPos != -1) {
                imageData = QByteArray::fromBase64(text.mid(startPos, endPos - startPos).toUtf8());
            }
        } else if (text.startsWith("[IMAGE]")) {
            int commaPos = text.indexOf(',');
            if (commaPos != -1) {
                imageData = QByteArray::fromBase64(text.mid(commaPos + 1).toUtf8());
            }
        }
        
        if (!imageData.isEmpty()) {
            QImage image;
            if (image.loadFromData(imageData)) {
                QString base64 = QString(imageData.toBase64());
                QString imageType = text.contains("png", Qt::CaseInsensitive) ? "png" : "jpeg";
                processedText = QString("![image](data:image/%1;base64,%2)").arg(imageType).arg(base64);
            } else {
                processedText = "[Image load failed]";
            }
        }
    } else if (text.startsWith("image:")) {
        QString imagePath = text.mid(6);
        QPixmap pixmap;
        if (pixmap.load(imagePath)) {
            QString base64 = QString(imageDataFromPixmap(pixmap).toBase64());
            processedText = QString("![image](data:image/png;base64,%1)").arg(base64);
        } else {
            processedText = "[Image load failed]";
        }
    }
    
    processedText = processedText.trimmed();
    
    QTextDocument *doc = m_contentBrowser->document();
    doc->setDocumentMargin(0);
    
    m_contentBrowser->setMarkdown(processedText);
    m_rawText = processedText;
    
    const int maxBubbleWidth = 600;
    const int minBubbleWidth = 200;
    const int horizontalPadding = 48;
    const int maxTextWidth = maxBubbleWidth - horizontalPadding;
    
    int docHeight = calculateDocumentHeight(doc, maxTextWidth);
    
    qreal idealWidth = doc->idealWidth();
    int actualTextWidth = qMin(qCeil(idealWidth), maxTextWidth);
    int bubbleWidth = qBound(minBubbleWidth, actualTextWidth + horizontalPadding, maxBubbleWidth);
    int contentWidth = bubbleWidth - horizontalPadding;
    
    if (contentWidth < maxTextWidth) {
        docHeight = calculateDocumentHeight(doc, contentWidth);
    }
    
    m_contentBrowser->setMinimumWidth(contentWidth);
    m_contentBrowser->setMaximumWidth(contentWidth);
    m_contentBrowser->setMinimumHeight(docHeight);
    // 不限制最大高度，让内容自动扩展
    m_contentBrowser->setMaximumHeight(16777215);  // QWIDGETSIZE_MAX
    
    m_bubbleWidget->setMinimumWidth(bubbleWidth);
    m_bubbleWidget->setMaximumWidth(bubbleWidth);
    
    m_contentBrowser->updateGeometry();
    m_bubbleWidget->updateGeometry();
    updateGeometry();
}

void MessageWidget::appendText(const QString &text)
{
    if (m_contentBrowser) {
        m_rawText += text;
        
        QTextDocument *doc = m_contentBrowser->document();
        doc->setDocumentMargin(0);
        
        m_contentBrowser->setMarkdown(m_rawText);
        
        const int maxBubbleWidth = 600;
        const int minBubbleWidth = 200;
        const int horizontalPadding = 48;
        const int maxTextWidth = maxBubbleWidth - horizontalPadding;
        
        int docHeight = calculateDocumentHeight(doc, maxTextWidth);
        qreal idealWidth = doc->idealWidth();
        int actualTextWidth = qMin(qCeil(idealWidth), maxTextWidth);
        int bubbleWidth = qBound(minBubbleWidth, actualTextWidth + horizontalPadding, maxBubbleWidth);
        int contentWidth = bubbleWidth - horizontalPadding;
        
        if (contentWidth < maxTextWidth) {
            docHeight = calculateDocumentHeight(doc, contentWidth);
        }
        
        m_contentBrowser->setMinimumWidth(contentWidth);
        m_contentBrowser->setMaximumWidth(contentWidth);
        m_contentBrowser->setMinimumHeight(docHeight);
        m_contentBrowser->setMaximumHeight(16777215);  // 不限制最大高度
        
        m_bubbleWidget->setMinimumWidth(bubbleWidth);
        m_bubbleWidget->setMaximumWidth(bubbleWidth);
        
        updateGeometry();
        
        // 查找父级 QListWidget 并更新大小
        QWidget* parent = this->parentWidget();
        while (parent) {
            QListWidget* listWidget = qobject_cast<QListWidget*>(parent);
            if (listWidget) {
                for (int i = 0; i < listWidget->count(); ++i) {
                    QListWidgetItem* item = listWidget->item(i);
                    if (item && listWidget->itemWidget(item) == this) {
                        item->setSizeHint(sizeHint());
                        listWidget->updateGeometry();
                        // 滚动到底部
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
        
        const int maxBubbleWidth = 600;
        const int minBubbleWidth = 200;
        const int horizontalPadding = 48;
        const int maxTextWidth = maxBubbleWidth - horizontalPadding;
        
        int docHeight = calculateDocumentHeight(doc, maxTextWidth);
        
        qreal idealWidth = doc->idealWidth();
        int actualTextWidth = qMin(qCeil(idealWidth), maxTextWidth);
        int bubbleWidth = qBound(minBubbleWidth, actualTextWidth + horizontalPadding, maxBubbleWidth);
        int contentWidth = bubbleWidth - horizontalPadding;
        
        if (contentWidth < maxTextWidth) {
            docHeight = calculateDocumentHeight(doc, contentWidth);
        }
        
        m_contentBrowser->setMinimumWidth(contentWidth);
        m_contentBrowser->setMaximumWidth(contentWidth);
        m_contentBrowser->setMinimumHeight(docHeight);
        m_contentBrowser->setMaximumHeight(16777215);  // 不限制最大高度
        
        m_bubbleWidget->setMinimumWidth(bubbleWidth);
        m_bubbleWidget->setMaximumWidth(bubbleWidth);
        
        updateGeometry();
    }
}

QSize MessageWidget::sizeHint() const
{
    if (!m_contentBrowser || !m_headerWidget) {
        return QWidget::sizeHint();
    }
    
    int headerHeight = m_headerWidget->sizeHint().height();
    
    // 使用文档的实际高度
    QTextDocument *doc = m_contentBrowser->document();
    int docHeight = qCeil(doc->size().height());
    
    int bubbleHeight = docHeight + 32;  // 上下边距各 16px
    int totalHeight = headerHeight + bubbleHeight + 8;
    
    return QSize(width() > 0 ? width() : 800, totalHeight);
}

void MessageWidget::paintEvent(QPaintEvent *event)
{
    Q_UNUSED(event)
    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing, true);
    painter.fillRect(rect(), Qt::transparent);
}
