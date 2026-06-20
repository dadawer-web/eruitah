#ifndef MESSAGEBUBBLE_H
#define MESSAGEBUBBLE_H

#include <QWidget>
#include <QLabel>
#include <QVBoxLayout>
#include <QTimer>

/**
 * @brief 桌宠专属消息气泡 — 独立置顶窗口，白底黑字圆角
 *
 * 不依附于 DesktopPetWidget（parent = nullptr），
 * 因此不会被宠物窗口裁剪，也不会被全局 QSS 污染。
 * 拖拽宠物时由 DesktopPetWidget::moveEvent 联动更新位置。
 */
class MessageBubble : public QWidget {
    Q_OBJECT

public:
    explicit MessageBubble(QWidget *parent = nullptr);

    /// 显示消息并定位到宠物头顶上方
    void showMessage(const QString &text, const QPoint &petTopLeft);

    /// 根据宠物位置重新定位气泡
    void updatePosition(const QPoint &petTopLeft);

private:
    QLabel *m_label;
    QVBoxLayout *m_layout;
    QTimer *m_autoHideTimer;  // 8 秒自动隐藏
};

#endif // MESSAGEBUBBLE_H
