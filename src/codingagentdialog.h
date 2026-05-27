#ifndef CODINGAGENTDIALOG_H
#define CODINGAGENTDIALOG_H

#include <QDialog>
#include <QWebEngineView>
#include <QWebEnginePage>
#include <QVBoxLayout>
#include <QLabel>
#include <QProgressBar>
#include <QPushButton>
#include <QStackedWidget>

class CodingAgentDialog : public QDialog {
    Q_OBJECT

public:
    explicit CodingAgentDialog(int userId = 0, QWidget *parent = nullptr);
    ~CodingAgentDialog();

private slots:
    void onLoadStarted();
    void onLoadProgress(int progress);
    void onLoadFinished(bool success);
    void onRetryLoad();

private:
    void setupUI();
    QString resolveSandboxUrl();

    int m_userId;
    QWebEngineView *m_webView;
    QLabel *m_statusLabel;
    QProgressBar *m_progressBar;
    QStackedWidget *m_stackedWidget;
    QWidget *m_errorWidget;
    QLabel *m_errorLabel;
    QPushButton *m_retryButton;
    QString m_currentUrl;
};

#endif
