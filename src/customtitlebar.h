#pragma once

#include <QWidget>
#include <QLabel>
#include <QPushButton>
#include <QHBoxLayout>
#include <QPoint>

class CustomTitleBar : public QWidget {
    Q_OBJECT

public:
    explicit CustomTitleBar(const QString &title, QWidget *parent = nullptr);
    ~CustomTitleBar() = default;
    
    void setTitle(const QString &title);
    void setCanMaximize(bool can);
    
signals:
    void minimizeClicked();
    void maximizeClicked();
    void closeClicked();

protected:
    void mousePressEvent(QMouseEvent *event) override;
    void mouseMoveEvent(QMouseEvent *event) override;
    void mouseReleaseEvent(QMouseEvent *event) override;
    void mouseDoubleClickEvent(QMouseEvent *event) override;
    void paintEvent(QPaintEvent *event) override;

private:
    void setupUI();
    void applyStyles();
    
    QLabel *m_titleLabel;
    QPushButton *m_minimizeButton;
    QPushButton *m_maximizeButton;
    QPushButton *m_closeButton;
    
    QPoint m_dragPosition;
    bool m_canMaximize;
    bool m_isDragging;
};
