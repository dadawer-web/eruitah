#ifndef CODINGAGENTDIALOG_H
#define CODINGAGENTDIALOG_H

#include <QDialog>
#include <QWebEngineView>
#include <QVBoxLayout>
#include <QLabel>

class CodingAgentDialog : public QDialog {
    Q_OBJECT

public:
    explicit CodingAgentDialog(QWidget *parent = nullptr);
    ~CodingAgentDialog();

private:
    void setupUI();

    QWebEngineView *m_webView;
    QLabel *m_statusLabel;
};

#endif
