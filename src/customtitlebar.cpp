#include "customtitlebar.h"
#include <QMouseEvent>
#include <QPainter>
#include <QMainWindow>
#include <QApplication>

CustomTitleBar::CustomTitleBar(const QString &title, QWidget *parent)
    : QWidget(parent)
    , m_titleLabel(nullptr)
    , m_minimizeButton(nullptr)
    , m_maximizeButton(nullptr)
    , m_closeButton(nullptr)
    , m_canMaximize(true)
    , m_isDragging(false)
{
    setupUI();
    setTitle(title);
    applyStyles();
    
    setFixedHeight(40);
    setCursor(Qt::SizeAllCursor);
    setMouseTracking(true);
    setAttribute(Qt::WA_StyledBackground, true);
    setFocusPolicy(Qt::NoFocus);
    setAttribute(Qt::WA_NoMousePropagation, false);
}

void CustomTitleBar::setupUI()
{
    QHBoxLayout *layout = new QHBoxLayout(this);
    layout->setContentsMargins(12, 0, 0, 0);
    layout->setSpacing(0);
    
    m_titleLabel = new QLabel(this);
    m_titleLabel->setAlignment(Qt::AlignLeft | Qt::AlignVCenter);
    m_titleLabel->setText("Application");
    m_titleLabel->setAttribute(Qt::WA_TransparentForMouseEvents, true);
    
    layout->addWidget(m_titleLabel);
    layout->addStretch();
    
    m_minimizeButton = new QPushButton(this);
    m_minimizeButton->setFixedSize(46, 32);
    m_minimizeButton->setText("─");
    m_minimizeButton->setToolTip("Minimize");
    m_minimizeButton->setCursor(Qt::ArrowCursor);
    
    m_maximizeButton = new QPushButton(this);
    m_maximizeButton->setFixedSize(46, 32);
    m_maximizeButton->setText("□");
    m_maximizeButton->setToolTip("Maximize");
    m_maximizeButton->setCursor(Qt::ArrowCursor);
    
    m_closeButton = new QPushButton(this);
    m_closeButton->setFixedSize(46, 32);
    m_closeButton->setText("✕");
    m_closeButton->setToolTip("Close");
    m_closeButton->setCursor(Qt::ArrowCursor);
    
    layout->addWidget(m_minimizeButton);
    layout->addWidget(m_maximizeButton);
    layout->addWidget(m_closeButton);
    
    connect(m_minimizeButton, &QPushButton::clicked, this, &CustomTitleBar::minimizeClicked);
    connect(m_maximizeButton, &QPushButton::clicked, this, &CustomTitleBar::maximizeClicked);
    connect(m_closeButton, &QPushButton::clicked, this, &CustomTitleBar::closeClicked);
}

void CustomTitleBar::applyStyles()
{
    QString titleStyle = QString(
        "QLabel {"
        "  color: #ececec;"
        "  font-size: 13px;"
        "  font-weight: 500;"
        "  background: transparent;"
        "  padding: 0 8px;"
        "}"
    );
    m_titleLabel->setStyleSheet(titleStyle);
    
    QString buttonStyle = QString(
        "QPushButton {"
        "  background-color: transparent;"
        "  color: #9ca3af;"
        "  border: none;"
        "  font-size: 12px;"
        "  border-radius: 0;"
        "  padding: 0;"
        "}"
        "QPushButton:hover {"
        "  background-color: #3b3b3b;"
        "  color: #ececec;"
        "}"
    );
    
    m_minimizeButton->setStyleSheet(buttonStyle);
    m_maximizeButton->setStyleSheet(buttonStyle);
    
    QString closeButtonStyle = QString(
        "QPushButton {"
        "  background-color: transparent;"
        "  color: #9ca3af;"
        "  border: none;"
        "  font-size: 12px;"
        "  border-radius: 0;"
        "  padding: 0;"
        "}"
        "QPushButton:hover {"
        "  background-color: #e81123;"
        "  color: #ffffff;"
        "}"
    );
    m_closeButton->setStyleSheet(closeButtonStyle);
}

void CustomTitleBar::setTitle(const QString &title)
{
    if (m_titleLabel) {
        m_titleLabel->setText(title);
    }
}

void CustomTitleBar::setCanMaximize(bool can)
{
    m_canMaximize = can;
    if (m_maximizeButton) {
        m_maximizeButton->setVisible(can);
    }
}

void CustomTitleBar::mousePressEvent(QMouseEvent *event)
{
    if (event->button() == Qt::LeftButton) {
        m_dragPosition = event->globalPos() - window()->pos();
        m_isDragging = true;
        event->accept();
        return;
    }
    QWidget::mousePressEvent(event);
}

void CustomTitleBar::mouseMoveEvent(QMouseEvent *event)
{
    if (m_isDragging && (event->buttons() & Qt::LeftButton)) {
        QPoint newPos = event->globalPos() - m_dragPosition;
        if (window()->isMaximized()) {
            window()->showNormal();
            int titleBarWidth = width();
            m_dragPosition = QPoint(titleBarWidth / 2, 20);
            newPos = event->globalPos() - m_dragPosition;
        }
        window()->move(newPos);
        event->accept();
        return;
    }
    QWidget::mouseMoveEvent(event);
}

void CustomTitleBar::mouseReleaseEvent(QMouseEvent *event)
{
    if (event->button() == Qt::LeftButton) {
        m_isDragging = false;
    }
    QWidget::mouseReleaseEvent(event);
}

void CustomTitleBar::mouseDoubleClickEvent(QMouseEvent *event)
{
    if (m_canMaximize && event->button() == Qt::LeftButton) {
        emit maximizeClicked();
        event->accept();
        return;
    }
    QWidget::mouseDoubleClickEvent(event);
}

void CustomTitleBar::paintEvent(QPaintEvent *event)
{
    Q_UNUSED(event)
    
    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing, false);
    
    painter.fillRect(rect(), QColor("#212121"));
    
    painter.setPen(QPen(QColor("#2f2f2f"), 1));
    painter.drawLine(0, height() - 1, width(), height() - 1);
}
