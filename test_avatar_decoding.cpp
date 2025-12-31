#include <QCoreApplication>
#include <QByteArray>
#include <QDebug>
#include <QImage>
#include <QFile>

int main(int argc, char *argv[])
{
    QCoreApplication a(argc, argv);
    
    // 测试Base64解码
    QString base64Data = "LzlqLzRBQVFTa1pKUmdBQkFRRUFTQUJJQUFELzJ3QkRBQVVEQkFRRUF3VUVCQVFGQlFVR0J3d0lCd2NIQnc4TEN3a01FUThTRWhF";
    QByteArray decodedData = QByteArray::fromBase64(base64Data.toUtf8());
    
    qDebug() << "Base64 data:" << base64Data;
    qDebug() << "Decoded data length:" << decodedData.length();
    qDebug() << "Decoded data (raw):" << decodedData.left(50);
    qDebug() << "Decoded data (hex):" << decodedData.left(50).toHex();
    
    // 测试加载图像
    QImage image;
    bool success = image.loadFromData(decodedData);
    qDebug() << "Image load success:" << success;
    
    // 保存解码后的数据到文件
    QFile file("/home/xmy/code/test_avatar.jpg");
    if (file.open(QIODevice::WriteOnly)) {
        qint64 bytesWritten = file.write(decodedData);
        file.close();
        qDebug() << "Wrote" << bytesWritten << "bytes to test_avatar.jpg";
        
        // 尝试从文件加载图像
        QImage fileImage;
        success = fileImage.load("/home/xmy/code/test_avatar.jpg");
        qDebug() << "Image load from file success:" << success;
    }
    
    return a.exec();
}