#include "codingagentdialog.h"
#include <QSettings>
#include <QCoreApplication>
#include <QWebEngineProfile>
#include <QWebEngineSettings>

CodingAgentDialog::CodingAgentDialog(int userId, QWidget *parent) : QDialog(parent), m_userId(userId) {
    setupUI();
}

CodingAgentDialog::~CodingAgentDialog() {
}

QString CodingAgentDialog::resolveSandboxUrl() {
    QSettings settings;
    QString url = settings.value("agent/vue_url", "").toString();

    if (!url.isEmpty()) {
        if (m_userId > 0) {
            QString sep = url.contains('?') ? "&" : "?";
            url += sep + QString("user_id=%1").arg(m_userId);
        }
        return url;
    }

    QString hostEnv = qEnvironmentVariable("ERUITAH_SANDBOX_HOST", "");
    if (!hostEnv.isEmpty()) {
        QString base = QString("http://%1/ide").arg(hostEnv);
        if (m_userId > 0) {
            base += QString("?user_id=%1").arg(m_userId);
        }
        return base;
    }

    QString base = "http://127.0.0.1:8001/ide";
    if (m_userId > 0) {
        base += QString("?user_id=%1").arg(m_userId);
    }
    return base;
}

void CodingAgentDialog::setupUI() {
    setWindowTitle("Eruitah AI Coding Agent");
    resize(1280, 860);
    setWindowFlags(windowFlags() | Qt::WindowMaximizeButtonHint);

    QVBoxLayout *mainLayout = new QVBoxLayout(this);
    mainLayout->setContentsMargins(0, 0, 0, 0);
    mainLayout->setSpacing(0);

    m_statusLabel = new QLabel("Eruitah AI Coding Agent", this);
    m_statusLabel->setStyleSheet(
        "QLabel {"
        "  background-color: #1a1a2e;"
        "  color: #00ff88;"
        "  padding: 6px 16px;"
        "  font-weight: bold;"
        "  font-size: 13px;"
        "  border-bottom: 1px solid #16213e;"
        "}"
    );
    mainLayout->addWidget(m_statusLabel);

    m_progressBar = new QProgressBar(this);
    m_progressBar->setRange(0, 100);
    m_progressBar->setValue(0);
    m_progressBar->setMaximumHeight(3);
    m_progressBar->setTextVisible(false);
    m_progressBar->setStyleSheet(
        "QProgressBar {"
        "  background-color: #1a1a2e;"
        "  border: none;"
        "}"
        "QProgressBar::chunk {"
        "  background-color: #00ff88;"
        "}"
    );
    mainLayout->addWidget(m_progressBar);

    m_stackedWidget = new QStackedWidget(this);

    m_webView = new QWebEngineView(this);
    m_webView->setStyleSheet("background-color: #0a0a0a;");

    QWebEnginePage *page = m_webView->page();
    QWebEngineSettings *settings = page->settings();
    settings->setAttribute(QWebEngineSettings::JavascriptEnabled, true);
    settings->setAttribute(QWebEngineSettings::LocalContentCanAccessRemoteUrls, true);
    settings->setAttribute(QWebEngineSettings::LocalContentCanAccessFileUrls, true);
    settings->setAttribute(QWebEngineSettings::JavascriptCanOpenWindows, true);
    settings->setAttribute(QWebEngineSettings::JavascriptCanAccessClipboard, true);

    m_stackedWidget->addWidget(m_webView);

    m_errorWidget = new QWidget(this);
    m_errorWidget->setStyleSheet("background-color: #0a0a0a;");
    QVBoxLayout *errorLayout = new QVBoxLayout(m_errorWidget);
    errorLayout->setAlignment(Qt::AlignCenter);

    m_errorLabel = new QLabel("无法连接到 Eruitah Agent 服务", this);
    m_errorLabel->setStyleSheet(
        "QLabel {"
        "  color: #ff6b6b;"
        "  font-size: 16px;"
        "  font-weight: bold;"
        "  background: transparent;"
        "}"
    );
    m_errorLabel->setAlignment(Qt::AlignCenter);
    errorLayout->addWidget(m_errorLabel);

    QLabel *hintLabel = new QLabel(
        "请确保 Eruitah 沙盒服务已启动:\n"
        "  cd eruitah-sandbox && python main.py\n\n"
        "默认地址: http://127.0.0.1:8001/ide",
        this
    );
    hintLabel->setStyleSheet(
        "QLabel {"
        "  color: #737373;"
        "  font-size: 13px;"
        "  background: transparent;"
        "}"
    );
    hintLabel->setAlignment(Qt::AlignCenter);
    errorLayout->addWidget(hintLabel);

    m_retryButton = new QPushButton("重新连接", this);
    m_retryButton->setStyleSheet(
        "QPushButton {"
        "  background-color: #00ff88;"
        "  color: #0a0a0a;"
        "  border: none;"
        "  padding: 10px 32px;"
        "  border-radius: 6px;"
        "  font-size: 14px;"
        "  font-weight: bold;"
        "}"
        "QPushButton:hover {"
        "  background-color: #00cc6a;"
        "}"
    );
    m_retryButton->setCursor(Qt::PointingHandCursor);
    errorLayout->addWidget(m_retryButton, 0, Qt::AlignCenter);

    m_stackedWidget->addWidget(m_errorWidget);

    mainLayout->addWidget(m_stackedWidget, 1);

    connect(m_webView, &QWebEngineView::loadStarted, this, &CodingAgentDialog::onLoadStarted);
    connect(m_webView, &QWebEngineView::loadProgress, this, &CodingAgentDialog::onLoadProgress);
    connect(m_webView, &QWebEngineView::loadFinished, this, &CodingAgentDialog::onLoadFinished);
    connect(m_retryButton, &QPushButton::clicked, this, &CodingAgentDialog::onRetryLoad);

    m_currentUrl = resolveSandboxUrl();
    qDebug() << "Loading Eruitah Agent from:" << m_currentUrl;
    m_statusLabel->setText("正在连接 Eruitah Agent 服务...");
    m_webView->load(QUrl(m_currentUrl));
}

void CodingAgentDialog::onLoadStarted() {
    m_progressBar->setValue(0);
    m_progressBar->setVisible(true);
    m_statusLabel->setText("正在加载页面...");
}

void CodingAgentDialog::onLoadProgress(int progress) {
    m_progressBar->setValue(progress);
    if (progress < 100) {
        m_statusLabel->setText(QString("正在加载... %1%").arg(progress));
    }
}

void CodingAgentDialog::onLoadFinished(bool success) {
    m_progressBar->setValue(100);

    if (success) {
        m_statusLabel->setText("Eruitah AI Coding Agent — 已连接");
        m_stackedWidget->setCurrentWidget(m_webView);
        m_progressBar->setVisible(false);
    } else {
        m_statusLabel->setText("连接失败");
        m_errorLabel->setText(QString("无法连接到: %1").arg(m_currentUrl));
        m_stackedWidget->setCurrentWidget(m_errorWidget);
    }
}

void CodingAgentDialog::onRetryLoad() {
    m_currentUrl = resolveSandboxUrl();
    m_statusLabel->setText("正在重新连接...");
    m_stackedWidget->setCurrentWidget(m_webView);
    m_progressBar->setVisible(true);
    m_progressBar->setValue(0);
    m_webView->load(QUrl(m_currentUrl));
}
