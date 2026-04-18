#ifndef DASHBOARDDIALOG_H
#define DASHBOARDDIALOG_H

#include <QDialog>
#include <QWebEngineView>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QPushButton>
#include <QLabel>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QJsonObject>

class DashboardDialog : public QDialog {
    Q_OBJECT

public:
    explicit DashboardDialog(int userId, QWidget *parent = nullptr);
    ~DashboardDialog();

private slots:
    void onRefreshClicked();
    void onWeeklyReportClicked();
    void onDashboardDataReceived(QNetworkReply *reply);
    void onReportDataReceived(QNetworkReply *reply);

private:
    void setupUI();
    void loadDashboardData();
    void generateWeeklyReport();

    int m_userId;
    QWebEngineView *m_webView;
    QPushButton *m_refreshBtn;
    QPushButton *m_reportBtn;
    QLabel *m_statusLabel;
    QNetworkAccessManager *m_networkManager;
    QJsonObject m_dashboardData;
};

#endif
