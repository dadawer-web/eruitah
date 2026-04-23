#include "codingagentdialog.h"
#include <QSettings>
#include <QCoreApplication>

CodingAgentDialog::CodingAgentDialog(QWidget *parent) : QDialog(parent) {
    setupUI();
}

CodingAgentDialog::~CodingAgentDialog() {
}

void CodingAgentDialog::setupUI() {
    setWindowTitle("Eruitah 编程 Agent");
    resize(1200, 800);
    
    QVBoxLayout *mainLayout = new QVBoxLayout(this);
    mainLayout->setContentsMargins(0, 0, 0, 0);
    mainLayout->setSpacing(0);
    
    m_statusLabel = new QLabel("正在加载 Agent 服务...", this);
    m_statusLabel->setStyleSheet(
        "QLabel {"
        "  background-color: #2d2d2d;"
        "  color: #4ec9b0;"
        "  padding: 8px 16px;"
        "  font-weight: bold;"
        "  font-size: 13px;"
        "}"
    );
    mainLayout->addWidget(m_statusLabel);
    
    m_webView = new QWebEngineView(this);
    m_webView->setStyleSheet("background-color: #1e1e1e;");
    mainLayout->addWidget(m_webView, 1);
    
    QSettings settings;
    QString sandboxUrl = settings.value("sandbox/url", "").toString();
    
    if (sandboxUrl.isEmpty()) {
        QString hostEnv = qEnvironmentVariable("ERUITAH_SANDBOX_HOST", "");
        if (!hostEnv.isEmpty()) {
            sandboxUrl = QString("http://%1/ide").arg(hostEnv);
        } else {
            sandboxUrl = "http://127.0.0.1:8001/ide";
        }
    }
    
    if (!sandboxUrl.contains("/ide")) {
        if (sandboxUrl.endsWith("/")) {
            sandboxUrl.chop(1);
        }
        sandboxUrl += "/ide";
    }
    
    qDebug() << "Loading Eruitah sandbox from:" << sandboxUrl;
    m_webView->load(QUrl(sandboxUrl));
}
