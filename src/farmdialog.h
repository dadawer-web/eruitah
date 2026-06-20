#ifndef FARMDIALOG_H
#define FARMDIALOG_H

#include <QDialog>
#include <QGraphicsScene>
#include <QGraphicsView>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QLabel>
#include <QPushButton>
#include <QInputDialog>
#include <QMessageBox>
#include <QLineEdit>
#include <QTextEdit>
#include <QScrollArea>
#include <QComboBox>
#include <QMap>
#include <QShowEvent>
#include "farmplotitem.h"

class ChatClient;

class FarmDialog : public QDialog {
    Q_OBJECT

public:
    FarmDialog(int userId, const QString &userName, ChatClient *client, QWidget *parent = nullptr);
    ~FarmDialog();

    void updatePlotFromServer(int plotId, int state, const QString &question,
                              int ownerUserId = -1, const QString &ownerName = "",
                              const QString &subjectTag = "");
    void updateUserStats(int coins, int exp);
    void handlePlantResponse(bool success, int plotId, const QString &message);
    void handleAnswerResponse(bool success, int plotId, const QString &feedback, int score, bool canHarvest);
    void handlePlotHarvested(int plotId, int ownerId);
    void handleFarmBroadcast(const QString &message);

protected:
    void showEvent(QShowEvent *event) override;

private slots:
    void onPlotClicked(int plotId, int state);
    void onRefreshFarm();
    void onVisitFarm();
    void onMyFarm();
    void onFarmLogClicked();
    void onFarmLogReceived(const QJsonArray& logs);
    void onFarmLogDeleted(int logId, bool success, const QString &message);

private:
    void setupUI();
    void requestFarmState();
    void refreshPlotsFromData();

    int m_userId;
    QString m_userName;
    ChatClient *m_chatClient;

    QGraphicsScene *m_scene;
    QGraphicsView *m_view;
    QLabel *m_coinsLabel;
    QLabel *m_expLabel;
    QLabel *m_titleLabel;
    QPushButton *m_refreshBtn;
    QPushButton *m_visitBtn;
    QPushButton *m_myFarmBtn;
    QPushButton *m_logBtn;
    QLabel *m_broadcastLabel;

    QMap<int, FarmPlotItem *> m_plots;

    int m_currentVisitUserId;
    QString m_currentVisitUserName;

    struct PlotData {
        int state = 0;
        QString question;
        int ownerUserId = -1;
        QString ownerName;
        QString subjectTag;
        int answererId = -1;
    };
    QMap<int, PlotData> m_plotData;

    int m_coins;
    int m_exp;

    QDialog *m_currentLogDialog = nullptr;
    QString m_currentSubject;
};

#endif
