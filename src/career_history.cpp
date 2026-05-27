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

void CareerHistoryManager::appendRecord(const QJsonObject& record)
{
    static QMutex mutex;
    QMutexLocker locker(&mutex);

    QJsonArray records = readFromFile();

    QString newHighlight = record.value("resume_highlight").toString();
    if (newHighlight.isEmpty()) {
        newHighlight = record.value("resumeHighlight").toString();
    }

    bool replaced = false;
    if (!newHighlight.isEmpty()) {
        for (int i = 0; i < records.size(); ++i) {
            QJsonObject existing = records[i].toObject();
            QString existingHighlight = existing.value("resume_highlight").toString();
            if (existingHighlight.isEmpty()) {
                existingHighlight = existing.value("resumeHighlight").toString();
            }
            if (!existingHighlight.isEmpty() && existingHighlight.trimmed() == newHighlight.trimmed()) {
                QJsonObject merged = existing;
                if (record.contains("skills")) {
                    merged["skills"] = record.value("skills");
                }
                if (record.contains("timestamp")) {
                    merged["timestamp"] = record.value("timestamp");
                } else {
                    merged["timestamp"] = QDateTime::currentDateTime().toString(Qt::ISODate);
                }
                if (record.contains("learningAdvice") || record.contains("next_suggestion")) {
                    merged["learningAdvice"] = record.value("learningAdvice").toString().isEmpty()
                        ? record.value("next_suggestion").toString()
                        : record.value("learningAdvice").toString();
                }
                if (record.contains("resumeHighlight") && !record.value("resumeHighlight").toString().isEmpty()) {
                    merged["resumeHighlight"] = record.value("resumeHighlight");
                }
                if (record.contains("resume_highlight") && !record.value("resume_highlight").toString().isEmpty()) {
                    merged["resume_highlight"] = record.value("resume_highlight");
                }
                records.removeAt(i);
                records.prepend(merged);
                replaced = true;
                qDebug() << "[CareerHistory] Refreshed existing record at index" << i
                         << "with new skills/timestamp, highlight=" << newHighlight.left(40);
                break;
            }
        }
    }

    if (!replaced) {
        records.prepend(record);
    }

    const int MAX_RECORDS = 50;
    while (records.size() > MAX_RECORDS) {
        records.removeLast();
    }

    if (writeToFile(records)) {
        qDebug() << "[CareerHistory] Appended: total=" << records.size()
                 << "replaced=" << replaced;
        emit careerDataUpdated();
    }
}

void CareerHistoryManager::deleteRecord(int index)
{
    static QMutex mutex;
    QMutexLocker locker(&mutex);

    QJsonArray records = readFromFile();

    if (index < 0 || index >= records.size()) {
        qWarning() << "[CareerHistory] deleteRecord: invalid index" << index;
        return;
    }

    records.removeAt(index);

    if (writeToFile(records)) {
        qDebug() << "[CareerHistory] Deleted index" << index << ", remaining=" << records.size();
        emit careerDataUpdated();
    }
}

void CareerHistoryManager::clearAllRecords()
{
    static QMutex mutex;
    QMutexLocker locker(&mutex);

    QJsonArray empty;
    if (writeToFile(empty)) {
        qDebug() << "[CareerHistory] All records cleared";
        emit careerDataUpdated();
    }
}

QJsonArray CareerHistoryManager::getAllRecords()
{
    static QMutex mutex;
    QMutexLocker locker(&mutex);
    return readFromFile();
}
