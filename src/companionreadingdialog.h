#ifndef COMPANIONREADINGDIALOG_H
#define COMPANIONREADINGDIALOG_H

#include <QDialog>
#include <QTextBrowser>
#include <QPushButton>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QLabel>
#include <QWebEngineView>
#include <QWebEngineUrlRequestInterceptor>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QJsonObject>
#include <QJsonDocument>
#include <QGraphicsDropShadowEffect>
#include <QTimer>
#include <QCursor>
#include <QProgressBar>
#include <QFile>

class Live2DUrlInterceptor : public QWebEngineUrlRequestInterceptor {
    Q_OBJECT
public:
    explicit Live2DUrlInterceptor(const QString &baseDir, QObject *parent = nullptr);
    void interceptRequest(QWebEngineUrlRequestInfo &info) override;

private:
    QString m_baseDir;
};

class CompanionReadingDialog : public QDialog {
    Q_OBJECT

public:
    explicit CompanionReadingDialog(int userId, QWidget *parent = nullptr);
    ~CompanionReadingDialog();

private slots:
    void onSelectionChanged();
    void onExplainButtonClicked();
    void onCompanionReadReply(QNetworkReply *reply);
    void onUploadFileClicked();
    void onPdfParseReply(QNetworkReply *reply);
    void onFileUploadProgress(qint64 bytesSent, qint64 bytesTotal);
    void onAudioDownloadFinished(QNetworkReply *reply);

protected:
    bool eventFilter(QObject *watched, QEvent *event) override;

private:
    void setupUI();
    void loadDefaultContent();
    void showExplainButton(const QPoint &globalPos);
    void hideExplainButton();
    void sendCompanionReadRequest(const QString &selectedText);
    void playAvatarAudio(const QString &localAudioPath, const QString &text);
    void playAvatarAudioBase64(const QByteArray &audioData, const QString &mimeType, const QString &text);
    void downloadAndPlayAudio(const QString &audioUrl, const QString &text);
    void deployLive2DAssets();
    void loadMarkdownFile(const QString &filePath);
    void loadPdfFile(const QString &filePath);
    QString markdownToHtml(const QString &markdown);
    void updateWindowTitle();

    int m_userId;

    QTextBrowser *m_ebookBrowser;
    QPushButton *m_explainBtn;
    QPushButton *m_uploadBtn;
    QWebEngineView *m_avatarView;
    QLabel *m_statusLabel;
    QLabel *m_fileLabel;
    QProgressBar *m_progressBar;
    QNetworkAccessManager *m_networkManager;
    QNetworkAccessManager *m_fileUploadManager;
    QNetworkAccessManager *m_audioDownloadManager;
    Live2DUrlInterceptor *m_urlInterceptor;

    QString m_selectedText;
    bool m_explainBtnVisible;
    QString m_assetDir;
    QString m_currentFilePath;
    QString m_currentFileName;
    QString m_pendingExplanationText;
    QFile *m_currentAudioFile;
    QNetworkReply *m_currentAudioReply;
};

#endif
