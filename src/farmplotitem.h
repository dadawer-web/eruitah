#ifndef FARMPLOTITEM_H
#define FARMPLOTITEM_H

#include <QGraphicsObject>
#include <QPainter>
#include <QGraphicsSceneMouseEvent>
#include <QCursor>

class FarmPlotItem : public QGraphicsObject {
    Q_OBJECT

public:
    enum PlotState { EMPTY, GROWING, RIPE, HARVESTED };

    explicit FarmPlotItem(int plotId, QGraphicsItem *parent = nullptr);

    QRectF boundingRect() const override;
    void paint(QPainter *painter, const QStyleOptionGraphicsItem *option, QWidget *widget) override;

    int plotId() const { return m_plotId; }
    PlotState state() const { return m_state; }
    QString question() const { return m_question; }
    int ownerUserId() const { return m_ownerUserId; }
    QString ownerName() const { return m_ownerName; }
    int answererId() const { return m_answererId; }

    void setState(PlotState state);
    void setQuestion(const QString &question);
    void setOwnerInfo(int userId, const QString &name);
    void setAnswererId(int id);
    void setSubjectTag(const QString &tag);

signals:
    void plotClicked(int plotId, int state);

protected:
    void mousePressEvent(QGraphicsSceneMouseEvent *event) override;
    void hoverEnterEvent(QGraphicsSceneHoverEvent *event) override;
    void hoverLeaveEvent(QGraphicsSceneHoverEvent *event) override;

private:
    int m_plotId;
    PlotState m_state;
    QString m_question;
    int m_ownerUserId;
    QString m_ownerName;
    int m_answererId;
    QString m_subjectTag;
    bool m_hovered;

    QColor stateBackgroundColor() const;
    QColor stateBorderColor() const;
    QString stateEmoji() const;
};

#endif
