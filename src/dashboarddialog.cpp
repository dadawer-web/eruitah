#include "dashboarddialog.h"
#include <QMessageBox>
#include <QDebug>
#include <QJsonDocument>
#include <QJsonArray>
#include <QTextEdit>

DashboardDialog::DashboardDialog(int userId, QWidget *parent)
    : QDialog(parent)
    , m_userId(userId)
    , m_networkManager(new QNetworkAccessManager(this))
{
    setupUI();
    
    m_webView->load(QUrl("http://localhost:8081/dashboard.html?userId=" + QString::number(m_userId)));
    
    connect(m_webView, &QWebEngineView::loadFinished, this, [this](bool success) {
        if (success) {
            loadDashboardData();
        } else {
            m_statusLabel->setText(QString::fromUtf8("❌ 页面加载失败"));
        }
    });
    
    connect(m_networkManager, &QNetworkAccessManager::finished, this, [this](QNetworkReply *reply) {
        QUrl url = reply->url();
        QString path = url.path();
        
        if (path.contains("/report")) {
            onReportDataReceived(reply);
        } else {
            onDashboardDataReceived(reply);
        }
        reply->deleteLater();
    });
}

DashboardDialog::~DashboardDialog()
{
}

void DashboardDialog::setupUI()
{
    setWindowTitle(QString::fromUtf8("📊 408考情大屏"));
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
    )");

    QVBoxLayout *mainLayout = new QVBoxLayout(this);
    mainLayout->setContentsMargins(15, 15, 15, 15);
    mainLayout->setSpacing(10);

    QHBoxLayout *headerLayout = new QHBoxLayout;

    QLabel *titleLabel = new QLabel(QString::fromUtf8("📊 408考情大屏"));
    titleLabel->setStyleSheet("font-size: 22px; font-weight: bold; color: #00f2fe;");
    headerLayout->addWidget(titleLabel);

    headerLayout->addStretch();

    m_reportBtn = new QPushButton(QString::fromUtf8("📋 生成周报"));
    m_reportBtn->setStyleSheet("background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00f2fe, stop:1 #7edad2); color: #0b0f1a; font-weight: bold;");
    m_refreshBtn = new QPushButton(QString::fromUtf8("🔄 刷新"));
    m_refreshBtn->setStyleSheet("background-color: #6c757d;");
    
    headerLayout->addWidget(m_reportBtn);
    headerLayout->addWidget(m_refreshBtn);

    mainLayout->addLayout(headerLayout);

    m_statusLabel = new QLabel(QString::fromUtf8("⏳ 正在加载考情数据..."));
    m_statusLabel->setStyleSheet("font-size: 12px; color: #8392A5; padding: 4px;");
    mainLayout->addWidget(m_statusLabel);

    m_webView = new QWebEngineView;
    m_webView->setStyleSheet("QWebEngineView { border: 2px solid rgba(0, 242, 254, 0.2); border-radius: 8px; }");
    mainLayout->addWidget(m_webView);

    connect(m_refreshBtn, &QPushButton::clicked, this, &DashboardDialog::onRefreshClicked);
    connect(m_reportBtn, &QPushButton::clicked, this, &DashboardDialog::onWeeklyReportClicked);
}

void DashboardDialog::loadDashboardData()
{
    QString url = QString("http://localhost:8081/api/analysis/dashboard/%1").arg(m_userId);
    m_networkManager->get(QNetworkRequest(QUrl(url)));
    m_statusLabel->setText(QString::fromUtf8("⏳ 正在加载考情数据..."));
}

void DashboardDialog::onDashboardDataReceived(QNetworkReply *reply)
{
    if (reply->error() != QNetworkReply::NoError) {
        m_statusLabel->setText(QString::fromUtf8("❌ 加载失败: ") + reply->errorString());
        return;
    }

    QByteArray data = reply->readAll();
    QJsonDocument doc = QJsonDocument::fromJson(data);
    
    if (doc.isObject()) {
        m_dashboardData = doc.object();
        
        QJsonArray radarArray = m_dashboardData["radar"].toArray();
        QJsonArray lineArray = m_dashboardData["line"].toArray();
        
        QString radarJson = QString::fromUtf8(QJsonDocument(radarArray).toJson(QJsonDocument::Compact));
        QString lineJson = QString::fromUtf8(QJsonDocument(lineArray).toJson(QJsonDocument::Compact));
        
        QString jsCode = QString("updateDashboardData(%1, %2);")
            .arg(radarJson)
            .arg(lineJson);
        
        m_webView->page()->runJavaScript(jsCode);
        m_statusLabel->setText(QString::fromUtf8("✅ 考情数据加载成功"));
    }
}

void DashboardDialog::onRefreshClicked()
{
    m_webView->reload();
}

void DashboardDialog::onWeeklyReportClicked()
{
    m_reportBtn->setEnabled(false);
    m_reportBtn->setText(QString::fromUtf8("⏳ 生成中..."));
    m_statusLabel->setText(QString::fromUtf8("⏳ AI正在生成周报..."));
    
    generateWeeklyReport();
}

void DashboardDialog::generateWeeklyReport()
{
    QString urlStr = QString("http://localhost:8081/api/analysis/dashboard/%1/report").arg(m_userId);
    QUrl requestUrl(urlStr);
    QNetworkRequest request(requestUrl);
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");
    
    m_networkManager->post(request, QByteArray());
}

void DashboardDialog::onReportDataReceived(QNetworkReply *reply)
{
    m_reportBtn->setEnabled(true);
    m_reportBtn->setText(QString::fromUtf8("📋 生成周报"));
    
    if (reply->error() != QNetworkReply::NoError) {
        m_statusLabel->setText(QString::fromUtf8("❌ 周报生成失败: ") + reply->errorString());
        QMessageBox::warning(this, QString::fromUtf8("周报生成失败"), reply->errorString());
        return;
    }

    QByteArray data = reply->readAll();
    QJsonDocument doc = QJsonDocument::fromJson(data);
    
    if (doc.isObject()) {
        QJsonObject obj = doc.object();
        QString report = obj["report"].toString();
        
        if (!report.isEmpty()) {
            m_statusLabel->setText(QString::fromUtf8("✅ 周报生成成功"));
            
            QDialog *reportDialog = new QDialog(this);
            reportDialog->setWindowTitle(QString::fromUtf8("📅 408 AI 学习诊断周报"));
            reportDialog->setMinimumSize(600, 500);
            reportDialog->setStyleSheet(R"(
                QDialog {
                    background-color: #131a28;
                }
                QLabel {
                    color: #e0e6ed;
                }
                QPushButton {
                    background-color: #4a4e69;
                    color: white;
                    border: none;
                    padding: 8px 16px;
                    border-radius: 6px;
                }
                QPushButton:hover {
                    background-color: #5c6378;
                }
                QTextEdit {
                    background-color: #1a2332;
                    color: #e0e6ed;
                    border: 1px solid rgba(0, 242, 254, 0.2);
                    border-radius: 6px;
                    padding: 10px;
                    font-size: 14px;
                }
            )");
            
            QVBoxLayout *layout = new QVBoxLayout(reportDialog);
            
            QTextEdit *reportText = new QTextEdit;
            reportText->setReadOnly(true);
            reportText->setMarkdown(report);
            layout->addWidget(reportText);
            
            QPushButton *closeBtn = new QPushButton(QString::fromUtf8("关闭"));
            connect(closeBtn, &QPushButton::clicked, reportDialog, &QDialog::accept);
            layout->addWidget(closeBtn);
            
            reportDialog->exec();
            reportDialog->deleteLater();
        } else {
            m_statusLabel->setText(QString::fromUtf8("❌ 周报内容为空"));
        }
    }
}
