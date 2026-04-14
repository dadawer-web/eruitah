#include "farmplotitem.h"
#include <QFont>
#include <QFontMetrics>

FarmPlotItem::FarmPlotItem(int plotId, QGraphicsItem *parent)
    : QGraphicsObject(parent)
    , m_plotId(plotId)
    , m_state(EMPTY)
    , m_ownerUserId(-1)
    , m_answererId(-1)
    , m_hovered(false)
{
    setAcceptHoverEvents(true);
    setCursor(Qt::PointingHandCursor);
}

QRectF FarmPlotItem::boundingRect() const
{
    return QRectF(0, 0, 140, 140);
}

void FarmPlotItem::paint(QPainter *painter, const QStyleOptionGraphicsItem *, QWidget *)
{
    painter->setRenderHint(QPainter::Antialiasing);

    QRectF rect = boundingRect().adjusted(4, 4, -4, -4);

    QColor bgColor = stateBackgroundColor();
    QColor borderColor = stateBorderColor();

    if (m_hovered) {
        bgColor = bgColor.lighter(120);
        borderColor = borderColor.lighter(130);
    }

    painter->setPen(QPen(borderColor, 2.5));
    painter->setBrush(bgColor);
    painter->drawRoundedRect(rect, 12, 12);

    QString emoji = stateEmoji();
    QFont emojiFont;
    emojiFont.setPointSize(28);
    painter->setFont(emojiFont);
    painter->setPen(Qt::black);
    painter->drawText(rect.adjusted(0, 5, 0, -50), Qt::AlignCenter, emoji);

    QFont textFont;
    textFont.setPointSize(8);
    painter->setFont(textFont);

    if (m_state == EMPTY) {
        painter->setPen(QColor("#888888"));
        painter->drawText(rect.adjusted(0, 50, 0, 0), Qt::AlignHCenter | Qt::AlignTop, "空地");
    } else if (m_state == GROWING) {
        painter->setPen(QColor("#2d5016"));
        QString displayQ = m_question;
        if (displayQ.length() > 12) {
            displayQ = displayQ.left(11) + "...";
        }
        painter->drawText(rect.adjusted(6, 48, -6, 0), Qt::AlignHCenter | Qt::AlignTop | Qt::TextWordWrap, displayQ);

        if (!m_subjectTag.isEmpty()) {
            QFont tagFont;
            tagFont.setPointSize(6);
            painter->setFont(tagFont);
            painter->setPen(Qt::white);
            QRectF tagRect(rect.left() + 8, rect.bottom() - 22, 40, 16);
            painter->setBrush(QColor("#4CAF50"));
            painter->setPen(Qt::NoPen);
            painter->drawRoundedRect(tagRect, 4, 4);
            painter->setPen(Qt::white);
            painter->drawText(tagRect, Qt::AlignCenter, m_subjectTag);
        }
    } else if (m_state == RIPE) {
        painter->setPen(QColor("#b8860b"));
        QString displayQ = m_question;
        if (displayQ.length() > 12) {
            displayQ = displayQ.left(11) + "...";
        }
        painter->drawText(rect.adjusted(6, 48, -6, 0), Qt::AlignHCenter | Qt::AlignTop | Qt::TextWordWrap, displayQ);

        QFont ripeFont;
        ripeFont.setPointSize(7);
        ripeFont.setBold(true);
        painter->setFont(ripeFont);
        painter->setPen(QColor("#ff6600"));
        painter->drawText(rect.adjusted(0, -5, 0, 0), Qt::AlignHCenter | Qt::AlignBottom, "可收菜!");
    } else if (m_state == HARVESTED) {
        painter->setPen(QColor("#888888"));
        QFont harvestedFont;
        harvestedFont.setPointSize(7);
        painter->setFont(harvestedFont);
        painter->drawText(rect.adjusted(0, 50, 0, 0), Qt::AlignHCenter | Qt::AlignTop, "已收割");
    }
}

void FarmPlotItem::setState(PlotState state)
{
    if (m_state != state) {
        m_state = state;
        update();
    }
}

void FarmPlotItem::setQuestion(const QString &question)
{
    m_question = question;
    update();
}

void FarmPlotItem::setOwnerInfo(int userId, const QString &name)
{
    m_ownerUserId = userId;
    m_ownerName = name;
    update();
}

void FarmPlotItem::setAnswererId(int id)
{
    m_answererId = id;
}

void FarmPlotItem::setSubjectTag(const QString &tag)
{
    m_subjectTag = tag;
    update();
}

void FarmPlotItem::mousePressEvent(QGraphicsSceneMouseEvent *)
{
    emit plotClicked(m_plotId, static_cast<int>(m_state));
}

void FarmPlotItem::hoverEnterEvent(QGraphicsSceneHoverEvent *)
{
    m_hovered = true;
    update();
}

void FarmPlotItem::hoverLeaveEvent(QGraphicsSceneHoverEvent *)
{
    m_hovered = false;
    update();
}

QColor FarmPlotItem::stateBackgroundColor() const
{
    switch (m_state) {
    case EMPTY:     return QColor("#3a2a1a");
    case GROWING:   return QColor("#1a3a0a");
    case RIPE:      return QColor("#3a3a0a");
    case HARVESTED: return QColor("#2a2a2a");
    }
    return QColor("#3a2a1a");
}

QColor FarmPlotItem::stateBorderColor() const
{
    switch (m_state) {
    case EMPTY:     return QColor("#5a4a3a");
    case GROWING:   return QColor("#4a8a2a");
    case RIPE:      return QColor("#daa520");
    case HARVESTED: return QColor("#555555");
    }
    return QColor("#5a4a3a");
}

QString FarmPlotItem::stateEmoji() const
{
    switch (m_state) {
    case EMPTY:     return QString::fromUtf8("\xF0\x9F\x92\x80");
    case GROWING:   return QString::fromUtf8("\xF0\x9F\x8C\xB1");
    case RIPE:      return QString::fromUtf8("\xF0\x9F\xA5\xAC");
    case HARVESTED: return QString::fromUtf8("\xF0\x9F\x92\xA8");
    }
    return QString::fromUtf8("\xF0\x9F\x92\x80");
}
