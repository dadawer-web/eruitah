#include <QCoreApplication>
#include <QDebug>
#include <QByteArray>
#include <QImage>
#include <QPixmap>
#include <QFile>

// Test function for avatar decoding
void testAvatarDecoding() {
    qDebug() << "=== Testing Avatar Decoding ===";
    
    // Sample Base64 encoded PNG image (1x1 red pixel)
    QString sampleBase64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==";
    
    qDebug() << "Sample Base64 length:" << sampleBase64.length();
    qDebug() << "Sample Base64 data:" << sampleBase64;
    
    // Decode Base64
    QByteArray decodedData = QByteArray::fromBase64(sampleBase64.toUtf8());
    qDebug() << "Decoded data length:" << decodedData.length();
    
    // Check first few bytes
    if (decodedData.size() >= 4) {
        qDebug() << "First 4 bytes:" << QString::asprintf("%02X %02X %02X %02X", 
                                                         (unsigned char)decodedData[0],
                                                         (unsigned char)decodedData[1],
                                                         (unsigned char)decodedData[2],
                                                         (unsigned char)decodedData[3]);
    }
    
    // Try loading with QImage
    QImage image;
    bool success = image.loadFromData(decodedData);
    qDebug() << "QImage load success:" << success;
    if (success) {
        qDebug() << "Image size:" << image.size();
        qDebug() << "Image format:" << image.format();
    }
    
    // Try loading with QPixmap
    QPixmap pixmap;
    success = pixmap.loadFromData(decodedData);
    qDebug() << "QPixmap load success:" << success;
    if (success) {
        qDebug() << "Pixmap size:" << pixmap.size();
    }
    
    // Try loading with specific formats
    success = image.loadFromData(decodedData, "PNG");
    qDebug() << "QImage PNG load success:" << success;
    
    success = image.loadFromData(decodedData, "JPEG");
    qDebug() << "QImage JPEG load success:" << success;
    
    success = image.loadFromData(decodedData, "BMP");
    qDebug() << "QImage BMP load success:" << success;
    
    qDebug() << "=== Test Complete ===";
}

int main(int argc, char *argv[]) {
    QCoreApplication a(argc, argv);
    
    // Test avatar decoding
    testAvatarDecoding();
    
    return 0;
}