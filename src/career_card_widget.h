#ifndef CAREER_CARD_WIDGET_H
#define CAREER_CARD_WIDGET_H

#include <QWidget>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QPushButton>
#include <QLabel>
#include <QTextBrowser>
#include <QJsonObject>
#include <QJsonArray>
#include <QJsonValue>
#include <QFrame>

class CareerCardWidget : public QWidget {
    Q_OBJECT

public:
    explicit CareerCardWidget(const QJsonObject &record, int index, QWidget *parent = nullptr)
        : QWidget(parent), m_record(record), m_index(index)
    {
        setObjectName("careerCard");

        QVBoxLayout *cardLayout = new QVBoxLayout(this);
        cardLayout->setContentsMargins(14, 12, 14, 12);
        cardLayout->setSpacing(8);

        QString timestamp = record.value("timestamp").toString("未知时间");
        QString category = record.value("category").toString("职业档案");

        QHBoxLayout *topRow = new QHBoxLayout;
        topRow->setSpacing(8);

        QLabel *dotLabel = new QLabel("●");
        dotLabel->setStyleSheet("color: #38BDF8; font-size: 8px;");
        dotLabel->setFixedSize(10, 10);
        topRow->addWidget(dotLabel);

        QLabel *timeLabel = new QLabel(timestamp);
        timeLabel->setStyleSheet("color: #64748B; font-size: 11px; font-family: 'Consolas', monospace;");
        topRow->addWidget(timeLabel);

        topRow->addStretch();

        QLabel *catLabel = new QLabel(category);
        catLabel->setStyleSheet(
            "color: #38BDF8; font-size: 10px; font-weight: bold;"
            "background: rgba(56, 189, 248, 12);"
            "border: 1px solid rgba(56, 189, 248, 30);"
            "border-radius: 6px; padding: 2px 10px;"
        );
        topRow->addWidget(catLabel);

        QPushButton *btnDelete = new QPushButton("🗑️");
        btnDelete->setObjectName("btnDeleteCard");
        btnDelete->setFixedSize(28, 28);
        btnDelete->setToolTip("删除本条记录");
        btnDelete->setStyleSheet(
            "#btnDeleteCard {"
            "  background: transparent; color: #64748B;"
            "  border: 1px solid #1E293B; border-radius: 14px;"
            "  font-size: 12px;"
            "}"
            "#btnDeleteCard:hover {"
            "  background: #EF4444; color: white; border-color: #EF4444;"
            "}"
        );
        connect(btnDelete, &QPushButton::clicked, this, &CareerCardWidget::onDeleteClicked);
        topRow->addWidget(btnDelete);

        cardLayout->addLayout(topRow);

        QString resumeHighlight = record.value("resume_highlight").toString();
        if (resumeHighlight.isEmpty()) {
            resumeHighlight = record.value("resumeHighlight").toString();
        }
        if (!resumeHighlight.isEmpty()) {
            QLabel *resumeHeader = new QLabel("📝 简历亮点");
            resumeHeader->setStyleSheet("color: #38BDF8; font-size: 12px; font-weight: bold; letter-spacing: 0.5px;");
            cardLayout->addWidget(resumeHeader);

            QTextBrowser *resumeContent = new QTextBrowser;
            resumeContent->setReadOnly(true);
            resumeContent->setOpenExternalLinks(true);
            resumeContent->setFrameShape(QFrame::NoFrame);
            resumeContent->setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
            resumeContent->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
            resumeContent->setOpenLinks(false);
            resumeContent->setMarkdown(resumeHighlight);
            resumeContent->setStyleSheet(
                "QTextBrowser {"
                "  color: #E2E8F0; font-size: 12px; line-height: 1.7;"
                "  background: rgba(56, 189, 248, 6);"
                "  border-left: 2px solid #38BDF8;"
                "  border-radius: 0 8px 8px 0; padding: 10px 12px;"
                "}"
                "QTextBrowser h2 { color: #38BDF8; font-size: 14px; font-weight: bold; margin-top: 4px; }"
                "QTextBrowser strong { color: #818CF8; }"
            );
            int textHeight = resumeHighlight.count('\n') * 24 + 60;
            resumeContent->setFixedHeight(qMin(qMax(textHeight, 60), 300));
            cardLayout->addWidget(resumeContent);
        }

        QString nextSuggestion = record.value("next_suggestion").toString();
        if (nextSuggestion.isEmpty()) {
            nextSuggestion = record.value("learningAdvice").toString();
        }
        if (!nextSuggestion.isEmpty()) {
            QLabel *adviceHeader = new QLabel("🎯 进阶建议");
            adviceHeader->setStyleSheet("color: #FBBF24; font-size: 12px; font-weight: bold; letter-spacing: 0.5px;");
            cardLayout->addWidget(adviceHeader);

            QTextBrowser *adviceContent = new QTextBrowser;
            adviceContent->setReadOnly(true);
            adviceContent->setOpenExternalLinks(true);
            adviceContent->setFrameShape(QFrame::NoFrame);
            adviceContent->setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
            adviceContent->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
            adviceContent->setOpenLinks(false);
            adviceContent->setMarkdown(nextSuggestion);
            adviceContent->setStyleSheet(
                "QTextBrowser {"
                "  color: #CBD5E1; font-size: 12px; line-height: 1.7;"
                "  background: rgba(251, 191, 36, 6);"
                "  border-left: 2px solid #FBBF24;"
                "  border-radius: 0 8px 8px 0; padding: 10px 12px;"
                "}"
            );
            int adviceHeight = nextSuggestion.count('\n') * 24 + 50;
            adviceContent->setFixedHeight(qMin(qMax(adviceHeight, 40), 200));
            cardLayout->addWidget(adviceContent);
        }

        QJsonValue skillsVal = record.value("skills");
        QString skillsStr;
        if (skillsVal.isArray()) {
            QStringList parts;
            for (const QJsonValue &v : skillsVal.toArray()) {
                parts << v.toString();
            }
            skillsStr = parts.join(", ");
        } else {
            skillsStr = skillsVal.toString();
        }
        if (!skillsStr.isEmpty()) {
            QLabel *skillsLabel = new QLabel("🛠 " + skillsStr);
            skillsLabel->setWordWrap(true);
            skillsLabel->setStyleSheet(
                "color: #38BDF8; font-size: 10px; font-family: 'Consolas', monospace;"
                "background: rgba(56, 189, 248, 8);"
                "border: 1px solid rgba(56, 189, 248, 20);"
                "border-radius: 8px; padding: 4px 12px;"
            );
            cardLayout->addWidget(skillsLabel);
        }

        QString borderAccent = (index % 2 == 0) ? "rgba(56, 189, 248, 35)" : "rgba(129, 140, 248, 35)";
        setStyleSheet(QString(
            "#careerCard {"
            "   background: rgba(15, 23, 42, 80);"
            "   border: 1px solid %1;"
            "   border-radius: 10px;"
            "}"
        ).arg(borderAccent));
    }

    int index() const { return m_index; }
    QJsonObject record() const { return m_record; }

    void setIndex(int idx) { m_index = idx; }

signals:
    void deleteRequested(int index, const QString &highlightText);

private slots:
    void onDeleteClicked() {
        QString highlight = m_record.value("resume_highlight").toString();
        if (highlight.isEmpty()) {
            highlight = m_record.value("resumeHighlight").toString();
        }
        emit deleteRequested(m_index, highlight);
    }

private:
    QJsonObject m_record;
    int m_index;
};

#endif // CAREER_CARD_WIDGET_H
