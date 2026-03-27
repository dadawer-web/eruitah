#pragma once

// 跨平台网络头文件处理 - 注意：先包含Windows网络头文件，再包含Qt头文件，避免byte类型歧义
#ifdef _WIN32
    #include <winsock2.h>
    #include <ws2tcpip.h>
    // 防止Windows头文件中的byte类型与Qt冲突
    #undef byte
#endif

#include <QWidget>
#include <QLabel>
#include <QHBoxLayout>
#include <QDateTime>

class MessageWidget : public QWidget {
    Q_OBJECT
public:
    // isSender: true表示"我"发的(右边)，false表示别人发的(左边)
    explicit MessageWidget(bool isSender, const QString &text, const QString &avatarPath, const QString &timeStr, QWidget *parent = nullptr);
    
    // 追加文本内容（用于流式消息）
    void appendText(const QString &text);
    
    // 重写 sizeHint 以正确计算大小
    QSize sizeHint() const override;
    
    QLabel *lblAvatar;  // 头像
    QLabel *lblContent; // 气泡文字
    QLabel *lblTime;    // 时间
    
private:
    bool m_isSender;
};