#pragma once

#ifdef _WIN32
    #include <winsock2.h>
    #include <ws2tcpip.h>
    #undef byte
#endif

#include <QWidget>
#include <QLabel>
#include <QTextBrowser>
#include <QHBoxLayout>
#include <QVBoxLayout>
#include <QDateTime>
#include <QPixmap>

class QtMaterialAvatar;

class MessageWidget : public QWidget {
    Q_OBJECT

public:
    explicit MessageWidget(bool isSender, const QString &text, const QString &avatarPath, 
                           const QString &senderName, const QString &timeStr, 
                           QWidget *parent = nullptr);
    
    void appendText(const QString &text);
    void setMarkdownContent(const QString &markdown);
    QSize sizeHint() const override;
    
    QtMaterialAvatar* avatarLabel() const { return m_avatarLabel; }
    QLabel* nameLabel() const { return m_nameLabel; }
    QTextBrowser* contentBrowser() const { return m_contentBrowser; }
    QLabel* timeLabel() const { return m_timeLabel; }
    
    bool isSender() const { return m_isSender; }

protected:
    void paintEvent(QPaintEvent *event) override;

private:
    void setupUI(const QString &text, const QString &avatarPath, 
                 const QString &senderName, const QString &timeStr);
    void applyStyles();
    void processAndSetContent(const QString &text);
    int calculateDocumentHeight(QTextDocument *doc, int textWidth);
    QByteArray imageDataFromPixmap(const QPixmap &pixmap);
    
    bool m_isSender;
    QString m_senderName;
    QString m_rawText;
    
    QWidget *m_headerWidget;
    QWidget *m_contentContainer;
    QWidget *m_bubbleWidget;
    QtMaterialAvatar *m_avatarLabel;
    QLabel *m_nameLabel;
    QTextBrowser *m_contentBrowser;
    QLabel *m_timeLabel;
};
