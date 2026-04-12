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
#include <QStackedWidget>

class QtMaterialAvatar;
class QWebEngineView;

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
    void setupUI(const QString &avatarPath, const QString &senderName, const QString &timeStr);
    void applyStyles();
    void processAndSetContent(const QString &text);
    bool looksLikeCode(const QString &text);
    QString escapeForMarkdown(const QString &text);
    bool containsImage(const QString &text);
    QString extractAndDisplayImages(const QString &text);
    bool containsMermaid(const QString &text);
    void renderMermaidDiagram(const QString &mermaidCode);
    QString processMermaidInText(const QString &text);
    
    bool m_isSender;
    QString m_senderName;
    QString m_rawText;
    QString m_avatarPath;
    
    QWidget *m_headerWidget;
    QWidget *m_contentContainer;
    QWidget *m_bubbleWidget;
    QtMaterialAvatar *m_avatarLabel;
    QLabel *m_nameLabel;
    QStackedWidget *m_contentStack;
    QTextBrowser *m_contentBrowser;
    QWidget *m_imageContainer;
    QLabel *m_imageLabel;
    QWebEngineView *m_mermaidView;
    QLabel *m_timeLabel;
    
    QList<QLabel*> m_imageLabels;
};
