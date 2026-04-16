#ifndef KNOWLEDGEGRAPHDIALOG_H
#define KNOWLEDGEGRAPHDIALOG_H

#include <QDialog>
#include <QWebEngineView>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QPushButton>
#include <QLabel>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QTimer>
#include <QJsonObject>

class KnowledgeGraphDialog : public QDialog {
    Q_OBJECT

public:
    explicit KnowledgeGraphDialog(int userId, QWidget *parent = nullptr);
    ~KnowledgeGraphDialog();

private slots:
    void onRefreshClicked();
    void onReviewClicked();
    void onClearCacheClicked();
    void onTreeDataReceived(QNetworkReply *reply);
    void onTreeStatsReceived(QNetworkReply *reply);
    void onGraphDataReceived(QNetworkReply *reply);
    void onReviewDataReceived(QNetworkReply *reply);

private:
    void setupUI();
    void loadTreeData();
    void loadTreeStats();
    void loadReviewData();
    void loadSubTree(const QString &parentName, int depth = 3);

    int m_userId;
    QWebEngineView *m_webView;
    QPushButton *m_refreshBtn;
    QPushButton *m_reviewBtn;
    QPushButton *m_clearCacheBtn;
    QLabel *m_statusLabel;
    QNetworkAccessManager *m_networkManager;
    QString m_reviewText;
    QJsonObject m_treeStats;
};

#endif
