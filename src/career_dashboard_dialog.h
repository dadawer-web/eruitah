#ifndef CAREERDASHBOARDDIALOG_H
#define CAREERDASHBOARDDIALOG_H

#include <QDialog>
#include <QListWidget>
#include <QScrollArea>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QPushButton>
#include <QLabel>
#include <QJsonObject>
#include <QJsonArray>
#include <QSet>
#include "career_history.h"

class CareerDashboardDialog : public QDialog {
    Q_OBJECT

public:
    explicit CareerDashboardDialog(QWidget *parent = nullptr);
    ~CareerDashboardDialog();

protected:
    void mousePressEvent(QMouseEvent *event) override;
    void mouseMoveEvent(QMouseEvent *event) override;

private:
    void setupUI();
    void loadSkillBadges();
    void loadTimeline();
    QWidget* createTimelineCard(const QJsonObject &record, int index);
    QString extractSkills(const QJsonObject &record) const;

private slots:
    void onExportClicked();

private:
    QPoint m_dragPos;
    QListWidget *m_skillList;
    QScrollArea *m_timelineArea;
    QVBoxLayout *m_timelineLayout;
    QPushButton *m_btnExport;
    QPushButton *m_btnClose;
    QJsonArray m_records;
    QSet<QString> m_uniqueSkills;
};

#endif // CAREERDASHBOARDDIALOG_H
