#include "messagewidget.h"
#include <QGraphicsDropShadowEffect>
#include <QPixmap>
#include <QPainter>
#include <QBrush>
#include <QPen>
#include <QPainterPath>
#include <QDebug>

// 跨平台网络头文件处理 - 注意：先包含Windows网络头文件，再包含Qt头文件，避免byte类型歧义
#ifdef _WIN32
    #include <winsock2.h>
    #include <ws2tcpip.h>
    // 防止Windows头文件中的byte类型与Qt冲突
    #undef byte
#endif

MessageWidget::MessageWidget(bool isSender, const QString &text, const QString &avatarPath, const QString &timeStr, QWidget *parent)
    : QWidget(parent)
{
    // 1. 初始化控件
    lblAvatar = new QLabel(this);
    lblAvatar->setFixedSize(40, 40);
    
    // 设置头像
    QPixmap avatarPixmap;
    if (!avatarPixmap.load(avatarPath)) {
        // 如果头像加载失败，创建默认头像
        QPixmap defaultAvatar(40, 40);
        defaultAvatar.fill(Qt::lightGray);
        
        QPainter painter(&defaultAvatar);
        painter.setRenderHint(QPainter::Antialiasing, true);
        
        // 绘制圆形背景
        QBrush brush(QColor(100, 149, 237)); //  CornflowerBlue
        painter.setBrush(brush);
        painter.setPen(Qt::NoPen);
        painter.drawEllipse(0, 0, 40, 40);
        
        // 绘制默认文字
        QFont font("Arial", 14, QFont::Bold);
        painter.setFont(font);
        painter.setPen(QColor(Qt::white));
        painter.drawText(defaultAvatar.rect(), Qt::AlignCenter, "U");
        
        lblAvatar->setPixmap(defaultAvatar);
    } else {
        // 头像加载成功，设置圆形头像
        QPixmap circularAvatar(40, 40);
        circularAvatar.fill(Qt::transparent);
        
        QPainter painter(&circularAvatar);
        painter.setRenderHint(QPainter::Antialiasing, true);
        
        // 绘制圆形路径作为遮罩
        QPainterPath path;
        path.addEllipse(0, 0, 40, 40);
        painter.setClipPath(path);
        
        // 绘制头像
        QPixmap scaledAvatar = avatarPixmap.scaled(40, 40, Qt::KeepAspectRatioByExpanding, Qt::SmoothTransformation);
        painter.drawPixmap(0, 0, scaledAvatar);
        
        // 绘制边框
        painter.setClipping(false);
        QPen pen(QColor(100, 149, 237), 2);
        painter.setPen(pen);
        painter.drawEllipse(0, 0, 39, 39);
        
        lblAvatar->setPixmap(circularAvatar);
    }
    
    lblContent = new QLabel(this);
    lblContent->setWordWrap(true); // 允许换行
    lblContent->setMaximumWidth(300); // 气泡最大宽度
    lblContent->setTextInteractionFlags(Qt::TextSelectableByMouse); // 允许复制文字
    
    // 检查消息是否包含图片数据
    if (text.startsWith("data:image/")) {
        // 是Data URL格式的图片
        qDebug() << "MessageWidget: Received image message, processing...";
        
        // 提取Base64数据
        int commaPos = text.indexOf(',');
        if (commaPos != -1) {
            QString base64Data = text.mid(commaPos + 1);
            QByteArray decodedData = QByteArray::fromBase64(base64Data.toUtf8());
            
            // 检查是否需要再次解码
            if (decodedData.size() >= 4 && decodedData[0] == '/' && decodedData[1] == '9' && decodedData[2] == 'j' && decodedData[3] == '/') {
                qDebug() << "MessageWidget: Image data is double Base64 encoded, decoding again...";
                decodedData = QByteArray::fromBase64(decodedData);
            }
            
            // 加载图片
            QImage image;
            if (image.loadFromData(decodedData)) {
                // 图片加载成功，调整大小
                QImage scaledImage = image.scaled(200, 150, Qt::KeepAspectRatio, Qt::SmoothTransformation);
                QPixmap pixmap = QPixmap::fromImage(scaledImage);
                
                // 显示图片
                lblContent->setPixmap(pixmap);
                lblContent->setAlignment(Qt::AlignCenter);
                lblContent->setStyleSheet(""); // 清除文本样式
            } else {
                // 图片加载失败，显示错误信息
                lblContent->setText("图片加载失败");
            }
        }
    } else if (text.startsWith("image:")) {
        // 是图片路径
        QString imagePath = text.mid(6); // 移除"image:"前缀
        QPixmap pixmap;
        if (pixmap.load(imagePath)) {
            // 图片加载成功，调整大小
            QPixmap scaledPixmap = pixmap.scaled(200, 150, Qt::KeepAspectRatio, Qt::SmoothTransformation);
            lblContent->setPixmap(scaledPixmap);
            lblContent->setAlignment(Qt::AlignCenter);
            lblContent->setStyleSheet(""); // 清除文本样式
        } else {
            // 图片加载失败，显示错误信息
            lblContent->setText("图片加载失败");
        }
    } else if (text.startsWith("[EMOJI_DATA:")) {
        // 是表情包数据
        qDebug() << "MessageWidget: Received emoji message, processing...";
        
        // 提取Base64数据
        int startPos = text.indexOf(':') + 1;
        int endPos = text.lastIndexOf(']');
        if (startPos != -1 && endPos != -1) {
            QString base64Data = text.mid(startPos, endPos - startPos);
            QByteArray decodedData = QByteArray::fromBase64(base64Data.toUtf8());
            
            // 检查是否需要再次解码
            if (decodedData.size() >= 4 && decodedData[0] == '/' && decodedData[1] == '9' && decodedData[2] == 'j' && decodedData[3] == '/') {
                qDebug() << "MessageWidget: Emoji data is double Base64 encoded, decoding again...";
                decodedData = QByteArray::fromBase64(decodedData);
            }
            
            // 加载图片
            QImage image;
            if (image.loadFromData(decodedData)) {
                // 图片加载成功，调整大小（表情包通常较小）
                QImage scaledImage = image.scaled(64, 64, Qt::KeepAspectRatio, Qt::SmoothTransformation);
                QPixmap pixmap = QPixmap::fromImage(scaledImage);
                
                // 显示图片
                lblContent->setPixmap(pixmap);
                lblContent->setAlignment(Qt::AlignCenter);
                lblContent->setStyleSheet(""); // 清除文本样式
            } else {
                // 图片加载失败，显示错误信息
                lblContent->setText("表情包加载失败");
            }
        }
    } else if (text.startsWith("[IMAGE]")) {
        // 是图片消息
        qDebug() << "MessageWidget: Received image message, processing...";
        
        // 提取图片类型和Base64数据
        int commaPos = text.indexOf(',');
        if (commaPos != -1) {
            QString imageType = text.mid(7, commaPos - 7); // 提取图片类型
            QString base64Data = text.mid(commaPos + 1);  // 提取Base64数据
            QByteArray decodedData = QByteArray::fromBase64(base64Data.toUtf8());
            
            // 检查是否需要再次解码
            if (decodedData.size() >= 4 && decodedData[0] == '/' && decodedData[1] == '9' && decodedData[2] == 'j' && decodedData[3] == '/') {
                qDebug() << "MessageWidget: Image data is double Base64 encoded, decoding again...";
                decodedData = QByteArray::fromBase64(decodedData);
            }
            
            // 加载图片
            QImage image;
            if (image.loadFromData(decodedData)) {
                // 图片加载成功，调整大小
                QImage scaledImage = image.scaled(200, 150, Qt::KeepAspectRatio, Qt::SmoothTransformation);
                QPixmap pixmap = QPixmap::fromImage(scaledImage);
                
                // 显示图片
                lblContent->setPixmap(pixmap);
                lblContent->setAlignment(Qt::AlignCenter);
                lblContent->setStyleSheet(""); // 清除文本样式
            } else {
                // 图片加载失败，显示错误信息
                lblContent->setText("图片加载失败");
            }
        }
    } else {
        // 是文本消息，直接显示
        lblContent->setText(text);
    }
    
    // 2. 设置气泡样式 (利用QSS设置背景色和尖角)
    if (isSender) {
        // 只有当是文本消息时才设置气泡样式
        if (lblContent->text() != "" && lblContent->pixmap(Qt::ReturnByValue).isNull()) {
            lblContent->setStyleSheet("background-color: #00bfff; color: white; border-radius: 10px; padding: 10px;");
        }
    } else {
        // 只有当是文本消息时才设置气泡样式
        if (lblContent->text() != "" && lblContent->pixmap(Qt::ReturnByValue).isNull()) {
            lblContent->setStyleSheet("background-color: #ffffff; color: black; border-radius: 10px; padding: 10px; border: 1px solid #e0e0e0;");
        }
    }
    
    // 3. 添加时间标签
    lblTime = new QLabel(timeStr, this);
    lblTime->setStyleSheet("font-size: 10px; color: #999;");
    
    // 4. 布局管理
    QVBoxLayout *messageLayout = new QVBoxLayout();
    messageLayout->setContentsMargins(0, 0, 0, 0);
    messageLayout->setSpacing(5);
    
    if (isSender) {
        messageLayout->addWidget(lblTime, 0, Qt::AlignRight);
        messageLayout->addWidget(lblContent, 0, Qt::AlignRight);
    } else {
        messageLayout->addWidget(lblTime, 0, Qt::AlignLeft);
        messageLayout->addWidget(lblContent, 0, Qt::AlignLeft);
    }
    
    QHBoxLayout *mainLayout = new QHBoxLayout(this);
    mainLayout->setContentsMargins(10, 5, 10, 5); // 气泡间的上下间距
    
    if (isSender) {
        // 我发的： 弹簧 + 消息布局 + 头像
        mainLayout->addStretch();
        mainLayout->addLayout(messageLayout);
        mainLayout->addWidget(lblAvatar);
    } else {
        // 别人发的： 头像 + 消息布局 + 弹簧
        mainLayout->addWidget(lblAvatar);
        mainLayout->addLayout(messageLayout);
        mainLayout->addStretch();
    }
}