#ifndef CAREERADVICEPOPUP_H
#define CAREERADVICEPOPUP_H

#include <QWidget>
#include <QLabel>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QGraphicsOpacityEffect>
#include <QPropertyAnimation>
#include <QTimer>
#include <QPainter>
#include <QPainterPath>
#include <QGuiApplication>
#include <QScreen>

class CareerAdvicePopup : public QWidget {
    Q_OBJECT

public:
    CareerAdvicePopup(const QString &skills, const QString &resumeHighlight,
                       const QString &learningAdvice, QWidget *parent = nullptr)
        : QWidget(parent, Qt::FramelessWindowHint | Qt::Tool | Qt::WindowStaysOnTopHint) {
        setAttribute(Qt::WA_TranslucentBackground);
        setAttribute(Qt::WA_DeleteOnClose);
        setFixedSize(380, 260);

        QGraphicsOpacityEffect *opacityEffect = new QGraphicsOpacityEffect(this);
        opacityEffect->setOpacity(0.0);
        setGraphicsEffect(opacityEffect);

        QWidget *container = new QWidget(this);
        container->setObjectName("popupContainer");
        container->setGeometry(0, 0, 380, 260);

        QVBoxLayout *mainLayout = new QVBoxLayout(container);
        mainLayout->setContentsMargins(20, 18, 20, 18);
        mainLayout->setSpacing(10);

        QHBoxLayout *headerLayout = new QHBoxLayout();
        headerLayout->setSpacing(8);

        QLabel *iconLabel = new QLabel("⚡");
        iconLabel->setStyleSheet("font-size: 22px; background: transparent;");
        headerLayout->addWidget(iconLabel);

        QLabel *titleLabel = new QLabel("技能树已更新");
        titleLabel->setObjectName("popupTitle");
        headerLayout->addWidget(titleLabel);
        headerLayout->addStretch();

        mainLayout->addLayout(headerLayout);

        QFrame *divider = new QFrame();
        divider->setFrameShape(QFrame::HLine);
        divider->setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 transparent, stop:0.2 #00ff88, stop:0.8 #00ff88, stop:1 transparent); max-height: 1px;");
        mainLayout->addWidget(divider);

        if (!skills.isEmpty()) {
            QLabel *skillsLabel = new QLabel("🛠 " + skills);
            skillsLabel->setObjectName("popupSkills");
            skillsLabel->setWordWrap(true);
            mainLayout->addWidget(skillsLabel);
        }

        if (!resumeHighlight.isEmpty()) {
            QLabel *resumeLabel = new QLabel("📋 " + resumeHighlight);
            resumeLabel->setObjectName("popupResume");
            resumeLabel->setWordWrap(true);
            mainLayout->addWidget(resumeLabel);
        }

        if (!learningAdvice.isEmpty()) {
            QLabel *adviceLabel = new QLabel("💡 " + learningAdvice);
            adviceLabel->setObjectName("popupAdvice");
            adviceLabel->setWordWrap(true);
            mainLayout->addWidget(adviceLabel);
        }

        mainLayout->addStretch();

        container->setStyleSheet(R"(
            #popupContainer {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a1a2e, stop:0.5 #16213e, stop:1 #0f3460);
                border: 1px solid #00ff88;
                border-radius: 12px;
            }
            #popupTitle {
                color: #00ff88;
                font-size: 18px;
                font-weight: bold;
                background: transparent;
            }
            #popupSkills {
                color: #64ffda;
                font-size: 12px;
                padding: 4px 8px;
                background: rgba(0, 255, 136, 15);
                border-radius: 6px;
                border: 1px solid rgba(0, 255, 136, 40);
            }
            #popupResume {
                color: #e0e0e0;
                font-size: 12px;
                padding: 4px 8px;
                background: rgba(255, 255, 255, 8);
                border-radius: 6px;
            }
            #popupAdvice {
                color: #ffd54f;
                font-size: 12px;
                padding: 4px 8px;
                background: rgba(255, 213, 79, 10);
                border-radius: 6px;
                border: 1px solid rgba(255, 213, 79, 30);
            }
        )");

        QPropertyAnimation *fadeIn = new QPropertyAnimation(opacityEffect, "opacity");
        fadeIn->setDuration(400);
        fadeIn->setStartValue(0.0);
        fadeIn->setEndValue(1.0);
        fadeIn->start(QAbstractAnimation::DeleteWhenStopped);

        QTimer::singleShot(5000, this, [this, opacityEffect]() {
            QPropertyAnimation *fadeOut = new QPropertyAnimation(opacityEffect, "opacity");
            fadeOut->setDuration(600);
            fadeOut->setStartValue(1.0);
            fadeOut->setEndValue(0.0);
            connect(fadeOut, &QPropertyAnimation::finished, this, &QWidget::close);
            fadeOut->start(QAbstractAnimation::DeleteWhenStopped);
        });
    }

    void showAtBottomRight() {
        QRect screenRect = QGuiApplication::primaryScreen()->availableGeometry();
        int x = screenRect.right() - width() - 20;
        int y = screenRect.bottom() - height() - 20;
        move(x, y);
        show();
    }

protected:
    void paintEvent(QPaintEvent *) override {
        QPainter painter(this);
        painter.setRenderHint(QPainter::Antialiasing);
        QPainterPath path;
        path.addRoundedRect(rect(), 12, 12);
        painter.setClipPath(path);
        painter.fillRect(rect(), Qt::transparent);
    }
};

#endif // CAREERADVICEPOPUP_H
