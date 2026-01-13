#pragma once
#include <QWidget>
#include <QLabel>
#include <QHBoxLayout>
#include <QDateTime>

class MessageWidget : public QWidget {
    Q_OBJECT
public:
    // isSender: true表示“我”发的(右边)，false表示别人发的(左边)
    explicit MessageWidget(bool isSender, const QString &text, const QString &avatarPath, const QString &timeStr, QWidget *parent = nullptr);

private:
    QLabel *lblAvatar;  // 头像
    QLabel *lblContent; // 气泡文字
    QLabel *lblTime;    // 时间
};