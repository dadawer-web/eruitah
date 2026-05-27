#ifndef CAREER_HISTORY_H
#define CAREER_HISTORY_H

#include <QObject>
#include <QJsonObject>
#include <QJsonArray>
#include <QJsonDocument>
#include <QFile>
#include <QDir>
#include <QDateTime>
#include <QMutex>
#include <QMutexLocker>

class CareerHistoryManager : public QObject {
    Q_OBJECT

public:
    static CareerHistoryManager& instance();

    void appendRecord(const QJsonObject& record);
    void deleteRecord(int index);
    void clearAllRecords();
    QJsonArray getAllRecords();

signals:
    void careerDataUpdated();

private:
    CareerHistoryManager(QObject* parent = nullptr);
    ~CareerHistoryManager() override;
    CareerHistoryManager(const CareerHistoryManager&) = delete;
    CareerHistoryManager& operator=(const CareerHistoryManager&) = delete;

    QString getFilePath() const;
    QJsonArray readFromFile() const;
    bool writeToFile(const QJsonArray& records) const;
};

#endif // CAREER_HISTORY_H
