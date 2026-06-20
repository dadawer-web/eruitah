#include "messagebubble.h"

MessageBubble::MessageBubble(QWidget *parent)
    : QWidget(nullptr)  // 绝对不要传 parent，保持自由身
{
    // 独立置顶窗口，无边框，背景透明
    setWindowFlags(Qt::Tool | Qt::FramelessWindowHint | Qt::WindowStaysOnTopHint);
    setAttribute(Qt::WA_TranslucentBackground);
    setStyleSheet("background: transparent; border: none;");

    // 内部 QLabel：白底黑字圆角
    m_label = new QLabel(this);
    m_label->setAlignment(Qt::AlignCenter);
    m_label->setWordWrap(true);
    m_label->setMaximumWidth(280);
    m_label->setStyleSheet(
        "QLabel {"
        "  background-color: rgba(255, 255, 255, 240);"
        "  color: #333333;"
        "  border-radius: 12px;"
        "  padding: 10px 15px;"
        "  font-weight: bold;"
        "  font-size: 14px;"
        "  border: 1px solid #e0e0e0;"
        "}"
    );

    m_layout = new QVBoxLayout(this);
    m_layout->setContentsMargins(0, 0, 0, 0);
    m_layout->addWidget(m_label);

    // 8 秒自动隐藏
    m_autoHideTimer = new QTimer(this);
    m_autoHideTimer->setSingleShot(true);
    connect(m_autoHideTimer, &QTimer::timeout, this, &QWidget::hide);

    hide();  // 初始隐藏
}

void MessageBubble::showMessage(const QString &text, const QPoint &petTopLeft) {
    m_autoHideTimer->stop();
    m_label->setText(text);
    // 先让 QLabel 自适应文字大小，再让窗口跟随布局收缩
    m_label->adjustSize();
    adjustSize();
    updatePosition(petTopLeft);
    show();
    raise();  // 确保置顶
    m_autoHideTimer->start(8000);
}

void MessageBubble::updatePosition(const QPoint &petTopLeft) {
    // 气泡水平居中，贴在宠物头顶上方 10px
    int bubbleX = petTopLeft.x() + (192 - width()) / 2;
    int bubbleY = petTopLeft.y() - height() - 10;
    move(bubbleX, bubbleY);
}
