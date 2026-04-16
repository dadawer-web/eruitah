#include "knowledgegraphdialog.h"
#include <QMessageBox>
#include <QDebug>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QUrlQuery>

KnowledgeGraphDialog::KnowledgeGraphDialog(int userId, QWidget *parent)
    : QDialog(parent)
    , m_userId(userId)
    , m_networkManager(new QNetworkAccessManager(this))
{
    setupUI();
    
    m_webView->load(QUrl("qrc:/html/graph.html"));
    
    connect(m_webView, &QWebEngineView::loadFinished, this, [this](bool success) {
        if (success) {
            loadTreeData();
            loadTreeStats();
            loadReviewData();
        } else {
            m_statusLabel->setText(QString::fromUtf8("❌ 页面加载失败"));
        }
    });
    
    connect(m_networkManager, &QNetworkAccessManager::finished, this, [this](QNetworkReply *reply) {
        QUrl url = reply->url();
        QString path = url.path();
        
        if (path.contains("/tree") && !path.contains("/tree-stats")) {
            onTreeDataReceived(reply);
        } else if (path.contains("/tree-stats")) {
            onTreeStatsReceived(reply);
        } else if (path.contains("/review")) {
            onReviewDataReceived(reply);
        } else if (path.contains("/echarts")) {
            onGraphDataReceived(reply);
        }
        reply->deleteLater();
    });
}

KnowledgeGraphDialog::~KnowledgeGraphDialog()
{
}

void KnowledgeGraphDialog::setupUI()
{
    setWindowTitle(QString::fromUtf8("🌳 408认知地图"));
    setMinimumSize(1100, 800);
    setStyleSheet(R"(
        QDialog {
            background-color: #0d1b2a;
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

    QLabel *titleLabel = new QLabel(QString::fromUtf8("🌳 408认知地图"));
    titleLabel->setStyleSheet("font-size: 22px; font-weight: bold; color: #7ec8e3;");
    headerLayout->addWidget(titleLabel);

    headerLayout->addStretch();

    m_reviewBtn = new QPushButton(QString::fromUtf8("📚 复习建议"));
    m_reviewBtn->setStyleSheet("background-color: #2d6a4f;");
    m_refreshBtn = new QPushButton(QString::fromUtf8("🔄 刷新"));
    m_refreshBtn->setStyleSheet("background-color: #6c757d;");
    m_clearCacheBtn = new QPushButton(QString::fromUtf8("🧹 清除缓存"));
    m_clearCacheBtn->setStyleSheet("background-color: #8b5cf6;");
    
    headerLayout->addWidget(m_reviewBtn);
    headerLayout->addWidget(m_refreshBtn);
    headerLayout->addWidget(m_clearCacheBtn);

    mainLayout->addLayout(headerLayout);

    m_statusLabel = new QLabel(QString::fromUtf8("⏳ 正在加载知识树..."));
    m_statusLabel->setStyleSheet("font-size: 12px; color: #aaaaaa; padding: 4px;");
    mainLayout->addWidget(m_statusLabel);

    m_webView = new QWebEngineView;
    m_webView->setStyleSheet("QWebEngineView { border: 2px solid #4a4e69; border-radius: 8px; }");
    mainLayout->addWidget(m_webView);

    connect(m_refreshBtn, &QPushButton::clicked, this, &KnowledgeGraphDialog::onRefreshClicked);
    connect(m_reviewBtn, &QPushButton::clicked, this, &KnowledgeGraphDialog::onReviewClicked);
    connect(m_clearCacheBtn, &QPushButton::clicked, this, &KnowledgeGraphDialog::onClearCacheClicked);
}

void KnowledgeGraphDialog::loadTreeData()
{
    QString url = QString("http://localhost:8081/api/graph/user/%1/tree").arg(m_userId);
    m_networkManager->get(QNetworkRequest(QUrl(url)));
    m_statusLabel->setText(QString::fromUtf8("⏳ 正在加载知识树..."));
}

void KnowledgeGraphDialog::loadTreeStats()
{
    QString url = QString("http://localhost:8081/api/graph/user/%1/tree-stats").arg(m_userId);
    m_networkManager->get(QNetworkRequest(QUrl(url)));
}

void KnowledgeGraphDialog::loadReviewData()
{
    QString url = QString("http://localhost:8081/api/graph/user/%1/review").arg(m_userId);
    m_networkManager->get(QNetworkRequest(QUrl(url)));
}

void KnowledgeGraphDialog::loadSubTree(const QString &parentName, int depth)
{
    QString encodedParent = QUrl::toPercentEncoding(parentName);
    QString url = QString("http://localhost:8081/api/graph/user/%1/tree/%2?depth=%3")
        .arg(m_userId)
        .arg(encodedParent)
        .arg(depth);
    m_networkManager->get(QNetworkRequest(QUrl(url)));
    m_statusLabel->setText(QString::fromUtf8("⏳ 正在加载子树: %1").arg(parentName));
}

void KnowledgeGraphDialog::onTreeDataReceived(QNetworkReply *reply)
{
    if (reply->error() != QNetworkReply::NoError) {
        m_statusLabel->setText(QString::fromUtf8("❌ 加载失败: ") + reply->errorString());
        QString jsCode = "renderEmpty();";
        m_webView->page()->runJavaScript(jsCode);
        return;
    }

    QString jsonString = reply->readAll();
    
    if (jsonString.isEmpty()) {
        QString jsCode = "renderEmpty();";
        m_webView->page()->runJavaScript(jsCode);
        m_statusLabel->setText(QString::fromUtf8("📭 暂无知识图谱数据"));
    } else {
        QString jsCode = QString("renderTree(%1);").arg(jsonString);
        m_webView->page()->runJavaScript(jsCode);
        m_statusLabel->setText(QString::fromUtf8("✅ 知识树加载成功 - 点击节点展开/折叠"));
    }
}

void KnowledgeGraphDialog::onTreeStatsReceived(QNetworkReply *reply)
{
    if (reply->error() != QNetworkReply::NoError) {
        return;
    }

    QByteArray data = reply->readAll();
    QJsonDocument doc = QJsonDocument::fromJson(data);
    if (doc.isObject()) {
        QJsonObject stats = doc.object();
        m_treeStats = stats;
        
        QString jsCode = QString(
            "if (typeof renderTree === 'function') { "
            "  var stats = %1;"
            "  document.getElementById('stats').style.display = 'block';"
            "  document.getElementById('mastered-count').textContent = stats.mastered || 0;"
            "  document.getElementById('familiar-count').textContent = stats.familiar || 0;"
            "  document.getElementById('weak-count').textContent = stats.weak || 0;"
            "  document.getElementById('notstarted-count').textContent = stats.notStarted || 0;"
            "  document.getElementById('avg-mastery').textContent = ((stats.averageMastery || 0) * 100).toFixed(1) + '%';"
            "}"
        ).arg(QString::fromUtf8(data));
        m_webView->page()->runJavaScript(jsCode);
    }
}

void KnowledgeGraphDialog::onGraphDataReceived(QNetworkReply *reply)
{
    if (reply->error() != QNetworkReply::NoError) {
        m_statusLabel->setText(QString::fromUtf8("❌ 加载失败: ") + reply->errorString());
        return;
    }

    QString jsonString = reply->readAll();
    
    if (jsonString.isEmpty() || jsonString == "{\"links\":[],\"nodes\":[]}") {
        QString jsCode = "renderEmpty();";
        m_webView->page()->runJavaScript(jsCode);
        m_statusLabel->setText(QString::fromUtf8("📭 暂无知识图谱数据"));
    } else {
        QString jsCode = QString("renderGraph(%1);").arg(jsonString);
        m_webView->page()->runJavaScript(jsCode);
        m_statusLabel->setText(QString::fromUtf8("✅ 知识图谱加载成功"));
    }
}

void KnowledgeGraphDialog::onReviewDataReceived(QNetworkReply *reply)
{
    if (reply->error() != QNetworkReply::NoError) {
        return;
    }

    QByteArray data = reply->readAll();
    QJsonDocument doc = QJsonDocument::fromJson(data);
    if (doc.isObject()) {
        m_reviewText = doc.object()["recommendation"].toString();
    }
}

void KnowledgeGraphDialog::onRefreshClicked()
{
    loadTreeData();
    loadTreeStats();
    loadReviewData();
}

void KnowledgeGraphDialog::onReviewClicked()
{
    if (m_reviewText.isEmpty()) {
        QMessageBox::information(this, QString::fromUtf8("📚 复习建议"), 
            QString::fromUtf8("暂无复习建议，继续答题积累知识点吧！"));
    } else {
        QMessageBox::information(this, QString::fromUtf8("📚 复习建议"), m_reviewText);
    }
}

void KnowledgeGraphDialog::onClearCacheClicked()
{
    QString url = QString("http://localhost:8081/api/graph/user/%1/mastery-cache").arg(m_userId);
    QNetworkRequest request;
    request.setUrl(QUrl(url));
    request.setAttribute(QNetworkRequest::CustomVerbAttribute, "DELETE");
    m_networkManager->sendCustomRequest(request, "DELETE");
    
    m_statusLabel->setText(QString::fromUtf8("🧹 已清除缓存，正在重新加载..."));
    
    QTimer::singleShot(500, this, [this]() {
        loadTreeData();
        loadTreeStats();
    });
}
