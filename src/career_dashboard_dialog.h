#ifndef CAREERDASHBOARDDIALOG_H
#define CAREERDASHBOARDDIALOG_H

#include <QDialog>
#include <QListWidget>
#include <QScrollArea>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QPushButton>
#include <QLabel>
#include <QTextBrowser>
#include <QJsonObject>
#include <QJsonArray>
#include <QSet>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QWebEngineView>
#include "career_history.h"
#include "career_card_widget.h"

class CareerDashboardDialog : public QDialog {
    Q_OBJECT

public:
    explicit CareerDashboardDialog(int userId = 0, QWidget *parent = nullptr);
    ~CareerDashboardDialog();

protected:
    void mousePressEvent(QMouseEvent *event) override;
    void mouseMoveEvent(QMouseEvent *event) override;

private:
    void setupUI();
    void initData();
    void loadSkillBadges();
    void loadTimeline();
    QString extractSkills(const QJsonObject &record) const;
    void injectRadarChart();
    void applyCareerData(const QString &highlight, const QJsonArray &skills, const QString &advice);

private slots:
    void onExportClicked();
    void onResetClicked();
    void onDeleteCard(int index, const QString &highlightText);
    void onServerDataReceived(QNetworkReply *reply);
    void refreshData();

private:
    int m_userId;
    QPoint m_dragPos;
    QListWidget *m_skillList;
    QScrollArea *m_timelineArea;
    QVBoxLayout *m_timelineLayout;
    QPushButton *m_btnExport;
    QPushButton *m_btnReset;
    QPushButton *m_btnClose;
    QLabel *m_statusLabel;
    QWebEngineView *m_webView;
    QJsonArray m_records;
    QList<CareerCardWidget*> m_cards;
    QSet<QString> m_uniqueSkills;
    QNetworkAccessManager *m_networkManager;

    bool m_isWebViewLoaded = false;
    QString m_pendingChartData;
    QJsonArray m_latestSkills;
    bool m_dataRequestSent = false;
};

#endif // CAREERDASHBOARDDIALOG_H
