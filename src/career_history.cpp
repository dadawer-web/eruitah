#include "career_history.h"
#include <QStandardPaths>
#include <QCoreApplication>

CareerHistoryManager& CareerHistoryManager::instance()
{
    static CareerHistoryManager inst;
    return inst;
}

CareerHistoryManager::CareerHistoryManager(QObject* parent)
    : QObject(parent)
{
}

CareerHistoryManager::~CareerHistoryManager()
{
}

QString CareerHistoryManager::getFilePath() const
{
    QString dir = QStandardPaths::writableLocation(QStandardPaths::AppDataLocation);
    QDir().mkpath(dir);
    return dir + "/career_history.json";
}

QJsonArray CareerHistoryManager::readFromFile() const
{
    QString path = getFilePath();
    QFile file(path);
    if (!file.exists()) {
        return QJsonArray();
    }
    if (!file.open(QIODevice::ReadOnly)) {
        qWarning() << "[CareerHistory] Failed to read:" << path;
        return QJsonArray();
    }
    QJsonDocument doc = QJsonDocument::fromJson(file.readAll());
    file.close();
    if (!doc.isArray()) {
        qWarning() << "[CareerHistory] Invalid format, resetting";
        return QJsonArray();
    }
    return doc.array();
}

bool CareerHistoryManager::writeToFile(const QJsonArray& records) const
{
    QString path = getFilePath();
    QString tmpPath = path + ".tmp";

    QFile tmpFile(tmpPath);
    if (!tmpFile.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
        qWarning() << "[CareerHistory] Failed to create temp file:" << tmpPath;
        return false;
    }
    QJsonDocument doc(records);
    qint64 written = tmpFile.write(doc.toJson(QJsonDocument::Compact));
    tmpFile.close();

    if (written <= 0) {
        qWarning() << "[CareerHistory] Write failed, aborting";
        QFile::remove(tmpPath);
        return false;
    }

    if (QFile::exists(path)) {
        QFile::remove(path);
    }
    if (!QFile::rename(tmpPath, path)) {
        qWarning() << "[CareerHistory] Rename failed";
        QFile::remove(tmpPath);
        return false;
    }

    return true;
}

void CareerHistoryManager::saveRecord(const QJsonObject& msgData)
{
    static QMutex mutex;
    QMutexLocker locker(&mutex);

    QJsonObject record;
    record["category"] = msgData.value("category").toString(QString::fromUtf8("代码分析"));
    record["skills"] = msgData.value("skills");
    record["resume_highlight"] = msgData.value("resume_highlight").toString(
        msgData.value("resumeHighlight").toString());
    record["next_suggestion"] = msgData.value("next_suggestion").toString(
        msgData.value("learningAdvice").toString());
    record["timestamp"] = QDateTime::currentDateTime().toString("yyyy-MM-dd hh:mm:ss");

    QJsonArray records = readFromFile();
    records.prepend(record);

    const int MAX_RECORDS = 500;
    while (records.size() > MAX_RECORDS) {
        records.removeLast();
    }

    if (writeToFile(records)) {
        qDebug() << "[CareerHistory] Saved record, total:" << records.size();
    }
}

QJsonArray CareerHistoryManager::getAllRecords()
{
    static QMutex mutex;
    QMutexLocker locker(&mutex);
    return readFromFile();
}
