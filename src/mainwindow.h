#ifndef MAINWINDOW_H
#define MAINWINDOW_H

#ifdef _WIN32
    #include <winsock2.h>
    #include <ws2tcpip.h>
    #undef byte
#endif

#include <QMainWindow>
#include <QPushButton>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QWidget>
#include <QLabel>
#include <QLineEdit>
#include <QTextEdit>
#include <QThread>
#include <QMessageBox>
#include "chatserver.h"
#include "loginwindow.h"

class MainWindow : public QMainWindow {
    Q_OBJECT

public:
    MainWindow(QWidget *parent = nullptr);
    ~MainWindow();

private slots:
    void startServer();
    void stopServer();
    void startClient();
    void onServerStarted(bool success);
    void onServerStopped();
    void onClientConnected();
    void handleLoginSuccess(int userId, const QString &userName);
    void onOpenCodingAgent();

private:
    QWidget *centralWidget;
    QVBoxLayout *mainLayout;
    QHBoxLayout *buttonLayout;
    QPushButton *startServerButton;
    QPushButton *stopServerButton;
    QPushButton *startClientButton;
    QPushButton *codingAgentButton;
    QLineEdit *portEdit;
    QLabel *portLabel;
    QTextEdit *logTextEdit;

    ChatServer *server;
    QThread *serverThread;
    bool serverRunning;
    int m_userId = 0;

    LoginWindow *loginWindow;

    void initUI();
    void addLog(const QString &log);
};

#endif // MAINWINDOW_H
