#include "chatwindow.h"
#include "messagewidget.h"
#include <QDebug>
#include <QDateTime>
#include <QInputDialog>
#include <QCloseEvent>
#include <QMenu>
#include <QAction>
#include <QMessageBox>
#include <QToolBar>
#include <QStatusBar>
#include <QTimer>
#include <QFileDialog>
#include <QFileInfo>
#include <QCoreApplication>
#include <QThread>
#include <QBuffer>
#include <QImage>
#include <QImageReader>
#include <QPixmap>
#include <QPainter>
#include <QBrush>
#include <QFont>
#include <QPainterPath>
#include <QProcess>

ChatWindow::ChatWindow(int userId, const QString &userName, ChatClient *client, QWidget *parent) : QMainWindow(parent), userId(userId), userName(userName), chatClient(client), loginHandled(false), friendListLoaded(false), offlineMessagesProcessed(false), isLoggingOut(false) {
    // 设置窗口标题
    setWindowTitle(QString("Qt Chat - %1").arg(userName));
    setObjectName("chatWindow");
    setMinimumSize(800, 600);

    // 应用样式表
    QString styleFilePath = QCoreApplication::applicationDirPath() + "/styles.qss";
    QFile styleFile(styleFilePath);
    if (styleFile.open(QIODevice::ReadOnly | QIODevice::Text)) {
        QString styleSheet = styleFile.readAll();
        setStyleSheet(styleSheet);
        styleFile.close();
        qDebug() << "样式表加载成功";
    } else {
        qDebug() << "样式表加载失败，使用默认样式";
        // 如果样式表文件无法加载，使用不包含Qt不支持属性的内联样式
        QString inlineStyle = ""
            "QMainWindow[objectName='chatWindow'] { background-color: #f5f5f5; }" 
            "QTreeWidget { background-color: white; border: none; border-right: 1px solid #eee; }" 
            "QTreeWidget::item { height: 40px; padding: 0 10px; border-radius: 6px; margin: 2px 8px; }" 
            "QTreeWidget::item:hover { background-color: #f0f0f0; }" 
            "QTreeWidget::item:selected { background-color: #e3f2fd; color: #1976d2; }" 
            "QTabWidget::pane { background-color: white; border: none; }" 
            "QTabBar::tab { background-color: #f5f5f5; border: none; border-bottom: 2px solid transparent; padding: 10px 20px; margin-right: 2px; border-radius: 8px 8px 0 0; font-weight: 500; }" 
            "QTabBar::tab:selected { background-color: white; border-bottom-color: #3498db; color: #3498db; }" 
            "QTextBrowser { background-color: #fafafa; border: none; padding: 10px; border-radius: 8px; }" 
            "QLineEdit { height: 40px; border: 1px solid #ddd; border-radius: 8px; padding: 0 12px; font-size: 14px; background-color: white; }" 
            "QLineEdit:focus { border-color: #3498db; }" 
            "QPushButton { height: 40px; border: none; border-radius: 8px; font-size: 14px; font-weight: 500; padding: 0 20px; }" 
            "QPushButton[class='primaryButton'] { background-color: #3498db; color: white; }" 
            "QPushButton[class='primaryButton']:hover { background-color: #2980b9; }" 
            "QPushButton[class='primaryButton']:pressed { background-color: #2471a3; }" 
            "QPushButton[class='secondaryButton'] { background-color: #ecf0f1; color: #333; border: 1px solid #ddd; }" 
            "QPushButton[class='secondaryButton']:hover { background-color: #d5dbdb; }" 
            "QPushButton[class='secondaryButton']:pressed { background-color: #bdc3c7; }" 
            "QSplitter::handle { background-color: #eee; width: 1px; }" 
            "QFrame[class='separator'] { background-color: #eee; height: 1px; margin: 10px 0; }";
        setStyleSheet(inlineStyle);
    }

    // 使用传入的ChatClient实例或创建新实例
    if (client) {
        chatClient = client;
        // 确保ChatClient不会被销毁
        chatClient->setParent(this);
    } else {
        chatClient = new ChatClient(this);
    }
    // 初始化表情包相关成员变量
    isLoadingEmojis = false;
    currentEmojiDialog = nullptr;
    
    // 初始化左侧联系人树
    contactTreeWidget = new QTreeWidget;
    contactTreeWidget->setContextMenuPolicy(Qt::CustomContextMenu);
    connect(contactTreeWidget, &QTreeWidget::itemClicked, this, &ChatWindow::onContactSelected);
    connect(contactTreeWidget, &QTreeWidget::customContextMenuRequested, this, &ChatWindow::showContextMenu);
    
    // 设置联系人树列数和表头
    contactTreeWidget->setColumnCount(3);
    QStringList headers;
    headers << "头像" << "联系人" << "状态";
    contactTreeWidget->setHeaderLabels(headers);
    
    // 设置列宽
    contactTreeWidget->setColumnWidth(0, 70); // 增加头像列宽度到70
    contactTreeWidget->setColumnWidth(1, 150); // 联系人列宽度
    contactTreeWidget->setColumnWidth(2, 50); // 状态列宽度
    contactTreeWidget->setIndentation(0); // 去除缩进

    // 创建好友和群组节点
    friendRoot = new QTreeWidgetItem(contactTreeWidget);
    friendRoot->setText(1, "好友"); // 在联系人列显示标题
    friendRoot->setExpanded(true);
    friendRoot->setFirstColumnSpanned(true); // 好友根节点跨列
    
    groupRoot = new QTreeWidgetItem(contactTreeWidget);
    groupRoot->setText(1, "群组"); // 在联系人列显示标题
    groupRoot->setExpanded(true);
    groupRoot->setFirstColumnSpanned(true); // 群组根节点跨列

    // 初始化聊天标签页
    chatTabWidget = new QTabWidget;
    chatTabWidget->setTabsClosable(true);
    connect(chatTabWidget, &QTabWidget::tabCloseRequested, chatTabWidget, &QTabWidget::removeTab);

    // 创建主分割器
    mainSplitter = new QSplitter(Qt::Horizontal);
    mainSplitter->addWidget(contactTreeWidget);
    mainSplitter->addWidget(chatTabWidget);
    mainSplitter->setSizes({250, 550});
    mainSplitter->setHandleWidth(1);

    // 设置状态栏
    statusBarLabel = new QLabel(QString("已登录: %1").arg(userName));
    statusBar()->addWidget(statusBarLabel);

    // 创建顶部用户信息和头像区域
    QWidget *topBar = new QWidget;
    QHBoxLayout *topLayout = new QHBoxLayout(topBar);
    topLayout->setContentsMargins(15, 10, 15, 10);
    topLayout->setSpacing(15);
    
    // 用户头像
    avatarLabel = new QLabel;
    avatarLabel->setFixedSize(50, 50); // 调整头像大小为50x50
    avatarLabel->setStyleSheet(
        "border: 2px solid #3498db; "
        "border-radius: 25px; "
        "background-color: #f0f0f0;"
    );
    avatarLabel->setAlignment(Qt::AlignCenter);
    
    // 初始显示用户名首字母
    QChar firstChar = userName.isEmpty() ? 'U' : userName[0];
    avatarLabel->setText(firstChar.toUpper());
    avatarLabel->setStyleSheet(avatarLabel->styleSheet() + 
        "font-size: 20px; "
        "font-weight: bold; "
        "color: #3498db;"
    );
    
    // 连接信号槽
    connect(chatClient, &ChatClient::connected, this, &ChatWindow::onConnected);
    connect(chatClient, &ChatClient::disconnected, this, &ChatWindow::onDisconnected);
    connect(chatClient, &ChatClient::messageReceived, this, &ChatWindow::onReceiveMessage);
    connect(chatClient, &ChatClient::groupMessageReceived, this, &ChatWindow::onReceiveGroupMessage);
    connect(chatClient, &ChatClient::friendListUpdated, this, &ChatWindow::onFriendListUpdated);
    connect(chatClient, &ChatClient::groupListUpdated, this, &ChatWindow::onGroupListUpdated);
    connect(chatClient, &ChatClient::addFriendResponse, this, &ChatWindow::onAddFriendResponse);
    connect(chatClient, &ChatClient::addGroupResponse, this, &ChatWindow::onAddGroupResponse);
    connect(chatClient, &ChatClient::createGroupResponse, this, &ChatWindow::onCreateGroupResponse);

    connect(chatClient, &ChatClient::emojiListUpdated, this, &ChatWindow::onEmojiListUpdated);
    connect(chatClient, &ChatClient::avatarUpdated, this, [this](const QString &avatarData) {
        // 更新当前用户头像（统一使用数据库处理）
        qDebug() << "Updating user avatar from database, data length:" << avatarData.length();
        currentUserAvatarData = avatarData; // 存储当前用户头像数据
        if (!avatarData.isEmpty()) {
            QPixmap pixmap;
            QByteArray decodedData;
            bool loadSuccess = false;
            
            // 直接处理Base64编码数据（统一从数据库获取）
            qDebug() << "ChatWindow: Avatar is Base64 data from database, trying to decode...";
            
            // 检查是Data URL还是纯Base64编码数据
            if (avatarData.startsWith("data:image/")) {
                // Data URL格式：data:image/png;base64,...
                qDebug() << "ChatWindow: Avatar is Data URL, extracting Base64 data...";
                int commaPos = avatarData.indexOf(',');
                if (commaPos != -1) {
                    QString base64Data = avatarData.mid(commaPos + 1);
                    qDebug() << "ChatWindow: Extracted Base64 data length:" << base64Data.length();
                    // 使用标准Base64解码
                    decodedData = QByteArray::fromBase64(base64Data.toUtf8());
                    qDebug() << "ChatWindow: Decoded data length:" << decodedData.length();
                    
                    // 尝试检测图片格式或使用常见格式
                    loadSuccess = pixmap.loadFromData(decodedData);
                    if (!loadSuccess) {
                        // 如果自动检测失败，尝试常见的图片格式
                        qDebug() << "ChatWindow: Auto-detect failed, trying PNG...";
                        loadSuccess = pixmap.loadFromData(decodedData, "PNG");
                    }
                    if (!loadSuccess) {
                        qDebug() << "ChatWindow: PNG failed, trying JPEG...";
                        loadSuccess = pixmap.loadFromData(decodedData, "JPEG");
                    }
                    if (!loadSuccess) {
                        qDebug() << "ChatWindow: JPEG failed, trying BMP...";
                        loadSuccess = pixmap.loadFromData(decodedData, "BMP");
                    }
                }
            } else {
                // 纯Base64编码数据
                qDebug() << "ChatWindow: Avatar is pure Base64, decoding directly...";
                // 使用标准Base64解码
                decodedData = QByteArray::fromBase64(avatarData.toUtf8());
                qDebug() << "ChatWindow: Decoded data length:" << decodedData.length();
                
                // 尝试检测图片格式或使用常见格式
                loadSuccess = pixmap.loadFromData(decodedData);
                if (!loadSuccess) {
                    // 如果自动检测失败，尝试常见的图片格式
                    qDebug() << "ChatWindow: Auto-detect failed, trying PNG...";
                    loadSuccess = pixmap.loadFromData(decodedData, "PNG");
                }
                if (!loadSuccess) {
                    qDebug() << "ChatWindow: PNG failed, trying JPEG...";
                    loadSuccess = pixmap.loadFromData(decodedData, "JPEG");
                }
                if (!loadSuccess) {
                    qDebug() << "ChatWindow: JPEG failed, trying BMP...";
                    loadSuccess = pixmap.loadFromData(decodedData, "BMP");
                }
            }
            
            qDebug() << "ChatWindow: Avatar load success:" << loadSuccess << "Pixmap is null:" << pixmap.isNull();
            
            // 如果所有格式都尝试失败，记录错误并使用默认头像
            if (!loadSuccess || pixmap.isNull()) {
                qDebug() << "ChatWindow: Failed to load avatar image from database, all formats failed, using default avatar";
                return;
            }
            
            if (!pixmap.isNull()) {
                // 头像图片加载成功
                // 创建一个正方形的QPixmap，确保宽高相等
                QSize avatarSize = avatarLabel->size();
                int side = qMin(avatarSize.width(), avatarSize.height());
                
                // 缩放图片，保持宽高比，确保图片完全覆盖正方形区域
                QPixmap scaledPixmap = pixmap.scaled(
                    side, side, 
                    Qt::KeepAspectRatioByExpanding, 
                    Qt::SmoothTransformation
                );
                
                // 创建一个带有圆形遮罩的QPixmap
                QPixmap circularPixmap(side, side);
                circularPixmap.fill(Qt::transparent);
                
                QPainter painter(&circularPixmap);
                painter.setRenderHint(QPainter::Antialiasing, true);
                painter.setRenderHint(QPainter::SmoothPixmapTransform, true);
                
                // 绘制圆形路径作为遮罩
                QPainterPath path;
                path.addEllipse(0, 0, side, side);
                painter.setClipPath(path);
                
                // 在圆形遮罩内绘制图片，居中显示
                painter.drawPixmap(
                    (side - scaledPixmap.width()) / 2, 
                    (side - scaledPixmap.height()) / 2, 
                    scaledPixmap
                );
                
                // 绘制边框
                painter.setClipping(false);
                QPen pen(QColor(52, 152, 219), 2);
                painter.setPen(pen);
                painter.drawEllipse(0, 0, side, side);
                
                avatarLabel->setPixmap(circularPixmap);
                avatarLabel->setStyleSheet(
                    "border-radius: 25px; "
                    "background-color: transparent;"
                );
                qDebug() << "Avatar updated successfully from database";
            } else {
                // 头像图片加载失败，显示默认头像
                qDebug() << "Failed to load avatar image from database, showing default avatar";
                // 显示用户名首字母
                QChar firstChar;
                if (this->userName.isEmpty()) {
                    firstChar = QChar('U');
                } else {
                    firstChar = this->userName[0];
                }
                QPixmap defaultPixmap(avatarLabel->size());
                defaultPixmap.fill(Qt::transparent);
                
                QPainter painter(&defaultPixmap);
                painter.setRenderHint(QPainter::Antialiasing, true);
                
                // 绘制蓝色圆形背景
                QBrush brush(QColor(52, 152, 219)); // #3498db
                painter.setBrush(brush);
                painter.setPen(Qt::NoPen);
                painter.drawEllipse(0, 0, avatarLabel->width(), avatarLabel->height());
                
                // 绘制白色文字
                QFont font("Arial", 20, QFont::Bold);
                painter.setFont(font);
                painter.setPen(QColor(Qt::white));
                painter.drawText(defaultPixmap.rect(), Qt::AlignCenter, firstChar.toUpper());
                
                avatarLabel->setPixmap(defaultPixmap);
                avatarLabel->setStyleSheet(
                    "border: 2px solid #3498db; "
                    "border-radius: 25px;"
                );
            }
        } else {
            // 头像数据为空，显示默认头像
            qDebug() << "Avatar data is empty, showing default avatar";
            // 显示用户名首字母
            QChar firstChar;
            if (this->userName.isEmpty()) {
                firstChar = QChar('U');
            } else {
                firstChar = this->userName[0];
            }
            QPixmap defaultPixmap(avatarLabel->size());
            defaultPixmap.fill(Qt::transparent);
            
            QPainter painter(&defaultPixmap);
            painter.setRenderHint(QPainter::Antialiasing, true);
            
            // 绘制蓝色圆形背景
            QBrush brush(QColor(52, 152, 219)); // #3498db
            painter.setBrush(brush);
            painter.setPen(Qt::NoPen);
            painter.drawEllipse(0, 0, avatarLabel->width(), avatarLabel->height());
            
            // 绘制白色文字
            QFont font("Arial", 20, QFont::Bold);
            painter.setFont(font);
            painter.setPen(QColor(Qt::white));
            painter.drawText(defaultPixmap.rect(), Qt::AlignCenter, firstChar.toUpper());
            
            avatarLabel->setPixmap(defaultPixmap);
            avatarLabel->setStyleSheet(
                "border: 2px solid #3498db; "
                "border-radius: 25px;"
            );
        }
    });
    
    // 延迟检查并应用当前用户头像（解决第二次登录时头像不显示的问题）
    // 使用QTimer延迟执行，确保ChatClient::processMessage方法已经处理完LOGIN_MSG_ACK消息
    QTimer::singleShot(100, this, [this]() {
        QString currentAvatar = chatClient->getCurrentUserAvatar();
        qDebug() << "ChatWindow: Checking stored avatar data after delay, length:" << currentAvatar.length();
        
        // 直接输出头像数据的前50个字符，查看数据格式
        if (!currentAvatar.isEmpty()) {
            qDebug() << "ChatWindow: Avatar data preview:" << currentAvatar.left(50) << (currentAvatar.length() > 50 ? "..." : "");
        }
        
        if (!currentAvatar.isEmpty()) {
            // 直接设置头像，不依赖信号机制
            QPixmap pixmap;
            QByteArray decodedData;
            bool loadSuccess = false;
            
            // 直接处理Base64编码数据（统一从数据库获取）
            qDebug() << "ChatWindow: Avatar is Base64 data from database, trying to decode...";
            
            // 检查是Data URL还是纯Base64编码数据
            if (currentAvatar.startsWith("data:image/")) {
                // Data URL格式：data:image/png;base64,...
                qDebug() << "ChatWindow: Avatar is Data URL, extracting Base64 data...";
                int commaPos = currentAvatar.indexOf(',');
                if (commaPos != -1) {
                    QString base64Data = currentAvatar.mid(commaPos + 1);
                    qDebug() << "ChatWindow: Extracted Base64 data length:" << base64Data.length();
                    decodedData = QByteArray::fromBase64(base64Data.toUtf8());
                    qDebug() << "ChatWindow: Decoded data length:" << decodedData.length();
                    loadSuccess = pixmap.loadFromData(decodedData);
                } else {
                    qDebug() << "ChatWindow: Invalid Data URL format, no comma found";
                }
            } else {
                // 尝试解码Base64数据
                decodedData = QByteArray::fromBase64(currentAvatar.toUtf8());
                qDebug() << "ChatWindow: Decoded data length:" << decodedData.length();
                
                // 检查解码后的data是否是ASCII文本且看起来像Base64编码
                bool isBase64Text = true;
                for (char c : decodedData) {
                    if (!isalnum(c) && c != '+' && c != '/' && c != '=' && !isspace(c)) {
                        isBase64Text = false;
                        break;
                    }
                }
                
                if (isBase64Text && decodedData.length() > 0 && decodedData.length() % 4 == 0) {
                    qDebug() << "ChatWindow: Detected double Base64 encoding, decoding again...";
                    QByteArray doubleDecoded = QByteArray::fromBase64(decodedData);
                    qDebug() << "ChatWindow: Double decoded data length:" << doubleDecoded.length();
                    qDebug() << "ChatWindow: Double decoded data header:" << doubleDecoded.left(20).toHex();
                    
                    // 使用再次解码后的数据
                    decodedData = doubleDecoded;
                }
                
                // 查看解码后的数据前20个字节，了解数据格式
                QByteArray dataHeader = decodedData.left(20);
                qDebug() << "ChatWindow: Decoded data header:" << dataHeader.toHex();
                
                // 检测图片格式
                QString detectedFormat = "unknown";
                if (dataHeader.startsWith("/9j/")) {
                    detectedFormat = "JPEG"; // JPEG文件的典型开头
                    qDebug() << "ChatWindow: Detected JPEG format from header";
                } else if (dataHeader.startsWith("\x89PNG\r\n\x1a\n")) {
                    detectedFormat = "PNG"; // PNG文件的典型开头
                    qDebug() << "ChatWindow: Detected PNG format from header";
                } else if (dataHeader.startsWith("BM")) {
                    detectedFormat = "BMP"; // BMP文件的典型开头
                    qDebug() << "ChatWindow: Detected BMP format from header";
                }
                
                // 使用QImage直接加载数据，尝试明确指定JPEG格式
                QImage image;
                loadSuccess = image.loadFromData(decodedData, "JPEG");
                qDebug() << "ChatWindow: Loaded image with QImage::loadFromData(JPEG), success:" << loadSuccess;
                
                if (!loadSuccess) {
                    // 尝试自动检测格式
                    loadSuccess = image.loadFromData(decodedData);
                    qDebug() << "ChatWindow: Loaded image with QImage::loadFromData(auto), success:" << loadSuccess;
                }
                
                if (loadSuccess) {
                    // 将QImage转换为QPixmap
                    pixmap = QPixmap::fromImage(image);
                    qDebug() << "ChatWindow: Converted QImage to QPixmap, success:" << !pixmap.isNull();
                } else {
                    // QImage加载失败，尝试将数据保存到文件并使用外部工具检查
                    QString tempFileName = QCoreApplication::applicationDirPath() + "/temp_avatar.jpg";
                    QFile tempFile(tempFileName);
                    if (tempFile.open(QIODevice::WriteOnly)) {
                        qint64 bytesWritten = tempFile.write(decodedData);
                        tempFile.close();
                        qDebug() << "ChatWindow: Saved decoded avatar data to" << tempFileName << "bytes written:" << bytesWritten;
                        
                        // 尝试使用QImage从临时文件加载，明确指定JPEG格式
                        QImage fileImage;
                        loadSuccess = fileImage.load(tempFileName, "JPEG");
                        qDebug() << "ChatWindow: Loaded avatar from temp file with QImage(JPEG), success:" << loadSuccess;
                        
                        if (!loadSuccess) {
                            // 尝试自动检测格式
                            loadSuccess = fileImage.load(tempFileName);
                            qDebug() << "ChatWindow: Loaded avatar from temp file with QImage(auto), success:" << loadSuccess;
                        }
                        
                        if (loadSuccess) {
                            pixmap = QPixmap::fromImage(fileImage);
                            qDebug() << "ChatWindow: Converted temp file QImage to QPixmap, success:" << !pixmap.isNull();
                            QFile::remove(tempFileName);
                            qDebug() << "ChatWindow: Removed temp avatar file";
                        } else {
                            // 保存原始数据用于手动分析
                            QString rawTempFileName = QCoreApplication::applicationDirPath() + "/temp_avatar_raw.dat";
                            QFile rawTempFile(rawTempFileName);
                            if (rawTempFile.open(QIODevice::WriteOnly)) {
                                rawTempFile.write(decodedData);
                                rawTempFile.close();
                                qDebug() << "ChatWindow: Saved raw avatar data to" << rawTempFileName << "for manual analysis";
                            }
                            
                            // 检查文件是否可被外部工具打开
                            QProcess process;
                            process.start("file", QStringList() << tempFileName);
                            process.waitForFinished();
                            QString fileType = process.readAllStandardOutput();
                            qDebug() << "ChatWindow: External file command output:" << fileType;
                            
                            // 检查文件是否可被外部工具识别为JPEG
                            QProcess identifyProcess;
                            identifyProcess.start("identify", QStringList() << tempFileName);
                            identifyProcess.waitForFinished();
                            QString identifyOutput = identifyProcess.readAllStandardOutput();
                            QString identifyError = identifyProcess.readAllStandardError();
                            qDebug() << "ChatWindow: External identify command output:" << identifyOutput;
                            qDebug() << "ChatWindow: External identify command error:" << identifyError;
                            
                            // 输出更多调试信息
                            qDebug() << "ChatWindow: Image data length:" << decodedData.length();
                            qDebug() << "ChatWindow: Image data first 100 bytes:" << decodedData.left(100);
                            qDebug() << "ChatWindow: Image data last 100 bytes:" << decodedData.right(100);
                        }
                    } else {
                        qDebug() << "ChatWindow: Failed to create temp avatar file";
                    }
                }
                
                // 移除冗余的内存加载尝试，因为已经在前面的代码中处理了所有内存加载情况
                // 如果到这里loadSuccess仍然为false，说明所有方法都失败了
                if (!loadSuccess) {
                    qDebug() << "ChatWindow: All avatar loading methods failed, using default avatar";
                }
            }
            
            qDebug() << "ChatWindow: Avatar load success:" << loadSuccess;
            
            if (loadSuccess && !pixmap.isNull()) {
                // 头像图片加载成功
                qDebug() << "ChatWindow: Avatar image loaded successfully, size:" << pixmap.size();
                
                // 创建一个正方形的QPixmap，确保宽高相等
                QSize avatarSize = avatarLabel->size();
                int side = qMin(avatarSize.width(), avatarSize.height());
                qDebug() << "ChatWindow: Avatar label size:" << avatarSize << "side:" << side;
                
                // 缩放图片，保持宽高比，确保图片完全覆盖正方形区域
                QPixmap scaledPixmap = pixmap.scaled(
                    side, side, 
                    Qt::KeepAspectRatioByExpanding, 
                    Qt::SmoothTransformation
                );
                
                // 创建一个带有圆形遮罩的QPixmap
                QPixmap circularPixmap(side, side);
                circularPixmap.fill(Qt::transparent);
                
                QPainter painter(&circularPixmap);
                painter.setRenderHint(QPainter::Antialiasing, true);
                painter.setRenderHint(QPainter::SmoothPixmapTransform, true);
                
                // 绘制圆形路径作为遮罩
                QPainterPath path;
                path.addEllipse(0, 0, side, side);
                painter.setClipPath(path);
                
                // 在圆形遮罩内绘制图片，居中显示
                painter.drawPixmap(
                    (side - scaledPixmap.width()) / 2, 
                    (side - scaledPixmap.height()) / 2, 
                    scaledPixmap
                );
                
                // 绘制边框
                painter.setClipping(false);
                QPen pen(QColor(52, 152, 219), 2);
                painter.setPen(pen);
                painter.drawEllipse(0, 0, side, side);
                
                avatarLabel->setPixmap(circularPixmap);
                avatarLabel->setStyleSheet(
                    "border-radius: 25px; "
                    "background-color: transparent;"
                );
                qDebug() << "ChatWindow: Avatar updated successfully after delay";
            } else {
                // 头像图片加载失败，显示默认头像
                qDebug() << "ChatWindow: Failed to load avatar image after delay, using default avatar";
                // 显示用户名首字母
                QChar firstChar;
                if (this->userName.isEmpty()) {
                    firstChar = QChar('U');
                } else {
                    firstChar = this->userName[0];
                }
                QPixmap defaultPixmap(avatarLabel->size());
                defaultPixmap.fill(Qt::transparent);
                
                QPainter painter(&defaultPixmap);
                painter.setRenderHint(QPainter::Antialiasing, true);
                
                // 绘制蓝色圆形背景
                QBrush brush(QColor(52, 152, 219)); // #3498db
                painter.setBrush(brush);
                painter.setPen(Qt::NoPen);
                painter.drawEllipse(0, 0, avatarLabel->width(), avatarLabel->height());
                
                // 绘制白色文字
                QFont font("Arial", 20, QFont::Bold);
                painter.setFont(font);
                painter.setPen(QColor(Qt::white));
                painter.drawText(defaultPixmap.rect(), Qt::AlignCenter, firstChar.toUpper());
                
                avatarLabel->setPixmap(defaultPixmap);
                avatarLabel->setStyleSheet(
                    "border: 2px solid #3498db; "
                    "border-radius: 25px;"
                );
            }
        } else {
            qDebug() << "ChatWindow: No stored avatar data found after delay, showing default avatar";
            // 显示用户名首字母
            QChar firstChar;
            if (this->userName.isEmpty()) {
                firstChar = QChar('U');
            } else {
                firstChar = this->userName[0];
            }
            QPixmap defaultPixmap(avatarLabel->size());
            defaultPixmap.fill(Qt::transparent);
            
            QPainter painter(&defaultPixmap);
            painter.setRenderHint(QPainter::Antialiasing, true);
            
            // 绘制蓝色圆形背景
            QBrush brush(QColor(52, 152, 219)); // #3498db
            painter.setBrush(brush);
            painter.setPen(Qt::NoPen);
            painter.drawEllipse(0, 0, avatarLabel->width(), avatarLabel->height());
            
            // 绘制白色文字
            QFont font("Arial", 20, QFont::Bold);
            painter.setFont(font);
            painter.setPen(QColor(Qt::white));
            painter.drawText(defaultPixmap.rect(), Qt::AlignCenter, firstChar.toUpper());
            
            avatarLabel->setPixmap(defaultPixmap);
            avatarLabel->setStyleSheet(
                "border: 2px solid #3498db; "
                "border-radius: 25px;"
            );
        }
    });
    
    // 连接好友状态更新信号
    connect(chatClient, &ChatClient::friendStateUpdated, this, &ChatWindow::onFriendStateUpdated);

    connect(chatClient, &ChatClient::fileTransferRequestReceived, this, &ChatWindow::onFileTransferRequestReceived);
    connect(chatClient, &ChatClient::fileTransferAccepted, this, &ChatWindow::onFileTransferAccepted);
    connect(chatClient, &ChatClient::fileTransferDataReceived, this, &ChatWindow::onFileTransferDataReceived);
    connect(chatClient, &ChatClient::fileTransferCompleteReceived, this, &ChatWindow::onFileTransferCompleteReceived);
    connect(chatClient, &ChatClient::fileTransferError, this, &ChatWindow::onFileTransferError);
    
    // 用户信息
    QVBoxLayout *userInfoLayout = new QVBoxLayout;
    userInfoLayout->setSpacing(5);
    QLabel *userNameLabel = new QLabel(userName);
    userNameLabel->setStyleSheet(
        "font-size: 16px; "
        "font-weight: bold; "
        "color: #2c3e50;"
    );
    QLabel *userIdLabel = new QLabel(QString("ID: %1").arg(userId));
    userIdLabel->setStyleSheet(
        "font-size: 12px; "
        "color: #666;"
    );
    userInfoLayout->addWidget(userNameLabel);
    userInfoLayout->addWidget(userIdLabel);
    userInfoLayout->addStretch();
    
    // 修改头像按钮
    changeAvatarButton = new QPushButton("修改头像");
    changeAvatarButton->setStyleSheet(
        "height: 32px; "
        "background-color: white; "
        "color: #3498db; "
        "border: 1px solid #3498db; "
        "border-radius: 16px; "
        "font-size: 12px;"
    );
    
    topLayout->addWidget(avatarLabel);
    topLayout->addLayout(userInfoLayout);
    topLayout->addStretch();
    topLayout->addWidget(changeAvatarButton);
    
    // 创建工具栏
    QToolBar *toolBar = addToolBar("工具栏");
    toolBar->setMovable(false);
    toolBar->setFloatable(false);
    
    QAction *addFriendAction = toolBar->addAction(QIcon(), "添加好友");
    QAction *createGroupAction = toolBar->addAction(QIcon(), "创建群组");
    QAction *joinGroupAction = toolBar->addAction(QIcon(), "加入群组");
    toolBar->addSeparator();
    //QAction *sendFileAction = toolBar->addAction(QIcon(), "发送文件");
    //toolBar->addSeparator();
    QAction *logoutAction = toolBar->addAction(QIcon(), "注销");

    connect(addFriendAction, &QAction::triggered, this, &ChatWindow::onAddFriend);
    connect(createGroupAction, &QAction::triggered, this, &ChatWindow::onCreateGroup);
    connect(joinGroupAction, &QAction::triggered, this, &ChatWindow::onJoinGroup);
    //connect(sendFileAction, &QAction::triggered, this, &ChatWindow::onSendFile);
    connect(logoutAction, &QAction::triggered, this, &ChatWindow::onLogout);
    connect(changeAvatarButton, &QPushButton::clicked, this, [this, userId]() {
        // 打开文件选择对话框
        QString filePath = QFileDialog::getOpenFileName(
            this, 
            "选择头像", 
            ".", 
            "图像文件 (*.png *.jpg *.jpeg)"
        );
        if (!filePath.isEmpty()) {
            // 上传头像
            chatClient->updateAvatar(userId, filePath);
            
            // 本地预览头像
            QPixmap pixmap(filePath);
            QPixmap scaledPixmap = pixmap.scaled(
                avatarLabel->size(), 
                Qt::KeepAspectRatio, 
                Qt::SmoothTransformation
            );
            avatarLabel->setPixmap(scaledPixmap);
            avatarLabel->setStyleSheet(
                "border: 2px solid #3498db; "
                "border-radius: 30px; "
                "background-color: #f0f0f0;"
            );
        }
    });

    // 创建主布局，将顶部栏和主分割器垂直排列
    QVBoxLayout *mainLayout = new QVBoxLayout;
    mainLayout->setContentsMargins(0, 0, 0, 0);
    mainLayout->setSpacing(0);
    
    // 创建一个主窗口部件来容纳布局
    QWidget *centralWidget = new QWidget;
    centralWidget->setLayout(mainLayout);
    
    // 将顶部栏和主分割器添加到主布局
    mainLayout->addWidget(topBar);
    mainLayout->addWidget(mainSplitter, 1); // 设置拉伸因子为1，使分割器占据剩余空间
    
    setCentralWidget(centralWidget);
    
    // 列表请求移至登录成功后执行，确保在正确的时机获取数据
    qDebug() << "ChatWindow initialized for userId:" << userId;

    // 初始化添加好友对话框
    addFriendDialog = new QDialog(this);
    addFriendDialog->setWindowTitle("添加好友");
    addFriendDialog->setFixedSize(320, 180);
    
    QVBoxLayout *addFriendLayout = new QVBoxLayout;
    addFriendLayout->setContentsMargins(20, 20, 20, 20);
    addFriendLayout->setSpacing(15);
    
    QLabel *addFriendTitle = new QLabel("添加好友");
    QFont font = addFriendTitle->font();
    font.setPointSize(16);
    font.setBold(true);
    addFriendTitle->setFont(font);
    addFriendTitle->setAlignment(Qt::AlignCenter);
    
    addFriendLayout->addWidget(addFriendTitle);
    addFriendLayout->addWidget(new QLabel("好友ID:"));
    addFriendIdEdit = new QLineEdit;
    addFriendLayout->addWidget(addFriendIdEdit);
    
    QHBoxLayout *addFriendButtonLayout = new QHBoxLayout;
    addFriendButtonLayout->setSpacing(10);
    
    QPushButton *addFriendOkButton = new QPushButton("确定");
    addFriendOkButton->setProperty("class", "primaryButton");
    
    QPushButton *addFriendCancelButton = new QPushButton("取消");
    addFriendCancelButton->setProperty("class", "secondaryButton");
    
    addFriendButtonLayout->addWidget(addFriendOkButton);
    addFriendButtonLayout->addWidget(addFriendCancelButton);
    addFriendLayout->addLayout(addFriendButtonLayout);
    
    addFriendDialog->setLayout(addFriendLayout);
    connect(addFriendOkButton, &QPushButton::clicked, this, &ChatWindow::onAddFriendConfirmed);
    connect(addFriendCancelButton, &QPushButton::clicked, addFriendDialog, &QDialog::close);
    
    // 处理存储的离线消息 - 移到构造函数末尾，确保所有UI元素都已初始化
    chatClient->processStoredOfflineMessages();

    // 初始化创建群组对话框
    createGroupDialog = new QDialog(this);
    createGroupDialog->setWindowTitle("创建群组");
    createGroupDialog->setFixedSize(350, 220);
    
    QVBoxLayout *createGroupLayout = new QVBoxLayout;
    createGroupLayout->setContentsMargins(20, 20, 20, 20);
    createGroupLayout->setSpacing(15);
    
    QLabel *createGroupTitle = new QLabel("创建群组");
    createGroupTitle->setFont(font);
    createGroupTitle->setAlignment(Qt::AlignCenter);
    
    createGroupLayout->addWidget(createGroupTitle);
    createGroupLayout->addWidget(new QLabel("群组名称:"));
    groupNameEdit = new QLineEdit;
    createGroupLayout->addWidget(groupNameEdit);
    createGroupLayout->addWidget(new QLabel("群组描述:"));
    groupDescEdit = new QLineEdit;
    createGroupLayout->addWidget(groupDescEdit);
    
    QHBoxLayout *createGroupButtonLayout = new QHBoxLayout;
    createGroupButtonLayout->setSpacing(10);
    
    QPushButton *createGroupOkButton = new QPushButton("确定");
    createGroupOkButton->setProperty("class", "primaryButton");
    
    QPushButton *createGroupCancelButton = new QPushButton("取消");
    createGroupCancelButton->setProperty("class", "secondaryButton");
    
    createGroupButtonLayout->addWidget(createGroupOkButton);
    createGroupButtonLayout->addWidget(createGroupCancelButton);
    createGroupLayout->addLayout(createGroupButtonLayout);
    
    createGroupDialog->setLayout(createGroupLayout);
    connect(createGroupOkButton, &QPushButton::clicked, this, &ChatWindow::onCreateGroupConfirmed);
    connect(createGroupCancelButton, &QPushButton::clicked, createGroupDialog, &QDialog::close);

    // 初始化加入群组对话框
    joinGroupDialog = new QDialog(this);
    joinGroupDialog->setWindowTitle("加入群组");
    joinGroupDialog->setFixedSize(320, 180);
    
    QVBoxLayout *joinGroupLayout = new QVBoxLayout;
    joinGroupLayout->setContentsMargins(20, 20, 20, 20);
    joinGroupLayout->setSpacing(15);
    
    QLabel *joinGroupTitle = new QLabel("加入群组");
    joinGroupTitle->setFont(font);
    joinGroupTitle->setAlignment(Qt::AlignCenter);
    
    joinGroupLayout->addWidget(joinGroupTitle);
    joinGroupLayout->addWidget(new QLabel("群组ID:"));
    joinGroupIdEdit = new QLineEdit;
    joinGroupLayout->addWidget(joinGroupIdEdit);
    
    QHBoxLayout *joinGroupButtonLayout = new QHBoxLayout;
    joinGroupButtonLayout->setSpacing(10);
    
    QPushButton *joinGroupOkButton = new QPushButton("确定");
    joinGroupOkButton->setProperty("class", "primaryButton");
    
    QPushButton *joinGroupCancelButton = new QPushButton("取消");
    joinGroupCancelButton->setProperty("class", "secondaryButton");
    
    joinGroupButtonLayout->addWidget(joinGroupOkButton);
    joinGroupButtonLayout->addWidget(joinGroupCancelButton);
    joinGroupLayout->addLayout(joinGroupButtonLayout);
    joinGroupDialog->setLayout(joinGroupLayout);
    connect(joinGroupOkButton, &QPushButton::clicked, this, &ChatWindow::onJoinGroupConfirmed);
    connect(joinGroupCancelButton, &QPushButton::clicked, joinGroupDialog, &QDialog::close);

    // 立即请求好友列表和群组列表，确保UI能够正确显示
    qDebug() << "[CRITICAL] ChatWindow constructor: Directly requesting friend and group lists for userId:" << userId;
    // 首先发送好友列表请求
    chatClient->requestFriendList(userId);
    // 立即发送群组列表请求，不需要延迟
    chatClient->requestGroupList(userId);
    // 再次发送群组列表请求，确保能收到响应
    QTimer::singleShot(100, this, [this, userId]() {
        chatClient->requestGroupList(userId);
    });
    
}

ChatWindow::~ChatWindow() {
}

// 生成聊天键
QString ChatWindow::generateChatKey(int chatId, bool isGroup) {
    return QString("%1_%2").arg(chatId).arg(isGroup ? "group" : "friend");
}

// 更新标签页文本，显示小红点
void ChatWindow::updateTabText(int chatId, bool isGroup, const QString &chatName) {
    QString key = generateChatKey(chatId, isGroup);
    int unreadCount = unreadMessageCounts.value(key, 0);
    
    // 查找对应的标签页
    for (int i = 0; i < chatTabWidget->count(); ++i) {
        QWidget *widget = chatTabWidget->widget(i);
        if (widget->property("chatId").toInt() == chatId &&
            widget->property("isGroup").toBool() == isGroup) {
            // 根据未读消息数量更新标签页文本
            if (unreadCount > 0) {
                chatTabWidget->setTabText(i, QString("%1 %2").arg(chatName).arg(QString("<span style='background-color: #ff4444; color: white; border-radius: 8px; padding: 2px 6px; font-size: 10px;'>%3</span>").arg(unreadCount)));
            } else {
                chatTabWidget->setTabText(i, chatName);
            }
            break;
        }
    }
}

// 添加消息到聊天列表，使用聊天气泡
void ChatWindow::addMessageToChatList(QListWidget *listWidget, bool isSender, const QString &message, const QString &avatarPath, const QString &timeStr) {
    // 创建QListWidgetItem
    QListWidgetItem *item = new QListWidgetItem(listWidget);
    
    // 创建MessageWidget
    MessageWidget *messageWidget = new MessageWidget(isSender, message, avatarPath, timeStr);
    
    // 设置Item的大小提示
    item->setSizeHint(messageWidget->sizeHint());
    
    // 将控件放入列表
    listWidget->setItemWidget(item, messageWidget);
    
    // 强制更新布局和大小
    listWidget->updateGeometry();
    listWidget->repaint();
    
    // 确保列表有足够的高度
    QScrollBar *scrollBar = listWidget->verticalScrollBar();
    if (scrollBar) {
        // 先滚动到底部
        scrollBar->setValue(scrollBar->maximum());
        
        // 再次确保滚动到底部（双重保险）
        QTimer::singleShot(10, listWidget, [listWidget]() {
            listWidget->scrollToBottom();
        });
    }
}

void ChatWindow::onSendMessage() {
    // 获取当前聊天窗口的相关组件
    QWidget *currentWidget = chatTabWidget->currentWidget();
    if (!currentWidget) return;

    // 从映射中获取聊天组件
    if (!chatComponents.contains(currentWidget) || !inputLineEdits.contains(currentWidget)) return;
    
    ChatComponents components = chatComponents[currentWidget];
    QListWidget *chatListWidget = components.chatListWidget;
    QLineEdit *inputEdit = inputLineEdits[currentWidget];
    
    QString message = inputEdit->text().trimmed();
    if (message.isEmpty()) return;

    // 获取标签页的用户数据（好友ID或群组ID）
    int chatId = currentWidget->property("chatId").toInt();
    bool isGroup = currentWidget->property("isGroup").toBool();

    // 显示自己发送的消息 - 使用聊天气泡
            QString timeStr = QDateTime::currentDateTime().toString("hh:mm:ss");
            // 使用自己的头像
            QString myAvatarPath = ":/icons/user.png"; // 默认头像
            // 尝试从当前用户头像数据中获取
            qDebug() << "ChatWindow: onSendMessage - currentUserAvatarData length:" << currentUserAvatarData.length();
            if (!currentUserAvatarData.isEmpty()) {
                // 头像数据存在，使用它
                qDebug() << "ChatWindow: onSendMessage - Avatar data exists, processing...";
                
                // 检查Base64数据的有效性
                QByteArray base64Bytes = currentUserAvatarData.toUtf8();
                qDebug() << "ChatWindow: onSendMessage - Base64 data length:" << base64Bytes.length();
                qDebug() << "ChatWindow: onSendMessage - Base64 data preview:" << currentUserAvatarData.left(50) << "...";
                
                // 移除可能的空白字符
                QString cleanBase64 = currentUserAvatarData.trimmed();
                qDebug() << "ChatWindow: onSendMessage - Clean Base64 length:" << cleanBase64.length();
                
                // 尝试解码
                    QByteArray decodedData = QByteArray::fromBase64(cleanBase64.toUtf8());
                    qDebug() << "ChatWindow: onSendMessage - Decoded data length:" << decodedData.length();
                    
                    // 检查解码后的数据是否为空
                    if (decodedData.isEmpty()) {
                        qDebug() << "ChatWindow: onSendMessage - Decoded data is empty!";
                    } else {
                        // 检查解码后的数据的前几个字节，了解文件格式
                        if (decodedData.size() >= 4) {
                            qDebug() << "ChatWindow: onSendMessage - First 4 bytes of decoded data:" 
                                     << QString::asprintf("%02X %02X %02X %02X", 
                                                         (unsigned char)decodedData[0],
                                                         (unsigned char)decodedData[1],
                                                         (unsigned char)decodedData[2],
                                                         (unsigned char)decodedData[3]);
                            
                            // 检查是否仍然是Base64编码的数据
                            // 常见的Base64编码JPEG开头是 "/9j/"
                            if (decodedData.size() >= 4 && decodedData[0] == '/' && decodedData[1] == '9' && decodedData[2] == 'j' && decodedData[3] == '/') {
                                qDebug() << "ChatWindow: onSendMessage - Decoded data is still Base64 encoded, decoding again...";
                                // 再次解码
                                QByteArray redecodedData = QByteArray::fromBase64(decodedData);
                                qDebug() << "ChatWindow: onSendMessage - Redecoded data length:" << redecodedData.length();
                                
                                // 检查再次解码后的数据
                                if (redecodedData.size() >= 4) {
                                    qDebug() << "ChatWindow: onSendMessage - First 4 bytes of redecode data:" 
                                             << QString::asprintf("%02X %02X %02X %02X", 
                                                                 (unsigned char)redecodedData[0],
                                                                 (unsigned char)redecodedData[1],
                                                                 (unsigned char)redecodedData[2],
                                                                 (unsigned char)redecodedData[3]);
                                }
                                
                                decodedData = redecodedData;
                            }
                        }
                    
                    // 尝试使用QImage加载，可能更宽松
                    QImage avatarImage;
                    bool loadSuccess = false;
                    
                    // 尝试自动检测格式
                    loadSuccess = avatarImage.loadFromData(decodedData);
                    qDebug() << "ChatWindow: onSendMessage - QImage auto-detect success:" << loadSuccess;
                    
                    if (!loadSuccess) {
                        // 尝试常见的图片格式
                        loadSuccess = avatarImage.loadFromData(decodedData, "PNG");
                        qDebug() << "ChatWindow: onSendMessage - QImage PNG success:" << loadSuccess;
                        
                        if (!loadSuccess) {
                            loadSuccess = avatarImage.loadFromData(decodedData, "JPEG");
                            qDebug() << "ChatWindow: onSendMessage - QImage JPEG success:" << loadSuccess;
                            
                            if (!loadSuccess) {
                                loadSuccess = avatarImage.loadFromData(decodedData, "BMP");
                                qDebug() << "ChatWindow: onSendMessage - QImage BMP success:" << loadSuccess;
                            }
                        }
                    }
                    
                    if (loadSuccess) {
                        qDebug() << "ChatWindow: onSendMessage - Image loaded successfully, size:" << avatarImage.size();
                        // 转换QImage为QPixmap
                        QPixmap avatarPixmap = QPixmap::fromImage(avatarImage);
                        // 保存到临时文件
                        QString tempAvatarPath = QCoreApplication::applicationDirPath() + "/temp_avatar_current.png";
                        qDebug() << "ChatWindow: onSendMessage - Saving avatar to:" << tempAvatarPath;
                        if (avatarPixmap.save(tempAvatarPath)) {
                            myAvatarPath = tempAvatarPath;
                            qDebug() << "ChatWindow: onSendMessage - Avatar saved successfully";
                        } else {
                            qDebug() << "ChatWindow: onSendMessage - Failed to save avatar to temp file";
                        }
                    } else {
                        qDebug() << "ChatWindow: onSendMessage - Failed to load avatar from data";
                        // 保存解码后的数据到文件以便分析
                        QString tempFileName = QCoreApplication::applicationDirPath() + "/temp_avatar_debug.bin";
                        QFile tempFile(tempFileName);
                        if (tempFile.open(QIODevice::WriteOnly)) {
                            qint64 bytesWritten = tempFile.write(decodedData);
                            tempFile.close();
                            qDebug() << "ChatWindow: onSendMessage - Saved decoded avatar data to" << tempFileName << "bytes written:" << bytesWritten;
                        }
                        
                        // 尝试保存为JPEG文件并加载
                        QString tempJpegFileName = QCoreApplication::applicationDirPath() + "/temp_avatar_debug.jpg";
                        QFile tempJpegFile(tempJpegFileName);
                        if (tempJpegFile.open(QIODevice::WriteOnly)) {
                            qint64 bytesWritten = tempJpegFile.write(decodedData);
                            tempJpegFile.close();
                            qDebug() << "ChatWindow: onSendMessage - Saved decoded avatar data to" << tempJpegFileName << "bytes written:" << bytesWritten;
                            
                            // 尝试从文件加载
                            QImage fileImage;
                            bool fileLoadSuccess = fileImage.load(tempJpegFileName);
                            qDebug() << "ChatWindow: onSendMessage - Loaded from JPEG file, success:" << fileLoadSuccess;
                            
                            if (fileLoadSuccess) {
                                qDebug() << "ChatWindow: onSendMessage - Image size from file:" << fileImage.size();
                                // 转换为QPixmap
                                QPixmap avatarPixmap = QPixmap::fromImage(fileImage);
                                // 保存到临时文件
                                QString tempAvatarPath = QCoreApplication::applicationDirPath() + "/temp_avatar_current.png";
                                if (avatarPixmap.save(tempAvatarPath)) {
                                    myAvatarPath = tempAvatarPath;
                                    qDebug() << "ChatWindow: onSendMessage - Avatar saved successfully from file";
                                }
                            }
                        }
                    }
                }
            } else {
                qDebug() << "ChatWindow: onSendMessage - No avatar data available, using default";
            }
            qDebug() << "ChatWindow: onSendMessage - Final avatar path:" << myAvatarPath;
            addMessageToChatList(chatListWidget, true, message, myAvatarPath, timeStr);
            inputEdit->clear();

    // 发送消息
    if (isGroup) {
        chatClient->sendGroupMessage(chatId, message);
    } else {
        chatClient->sendMessage(chatId, message);
    }
}

void ChatWindow::createChatWidget(int chatId, const QString &chatName, bool isGroup) {
    // 检查是否已经打开了该聊天窗口
    for (int i = 0; i < chatTabWidget->count(); ++i) {
        if (chatTabWidget->widget(i)->property("chatId").toInt() == chatId &&
            chatTabWidget->widget(i)->property("isGroup").toBool() == isGroup) {
            // 已经存在该聊天窗口，直接切换到它
            chatTabWidget->setCurrentIndex(i);
            return;
        }
    }

    // 创建新的聊天窗口
    QWidget *chatWidget = new QWidget;
    chatWidget->setStyleSheet("background-color: white;");
    
    // 使用QVBoxLayout作为主布局
    QVBoxLayout *mainLayout = new QVBoxLayout;
    mainLayout->setContentsMargins(0, 0, 0, 0);
    mainLayout->setSpacing(0);
    
    // 聊天记录区域 - 使用QListWidget替代QTextEdit，以便使用聊天气泡
    QListWidget *chatListWidget = new QListWidget;
    chatListWidget->setMinimumHeight(200); // 减小最小高度，使窗口可以更小
    chatListWidget->setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOn);
    chatListWidget->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    chatListWidget->setFocusPolicy(Qt::NoFocus); // 禁用焦点
    chatListWidget->setSelectionMode(QAbstractItemView::NoSelection); // 禁用选择
    chatListWidget->setStyleSheet("border: none; background-color: #fafafa;"
                                 "QListWidget { outline: none; }"
                                 "QListWidget::item { outline: none; border: none; }"
                                 "QListWidget::item:selected { background-color: transparent; outline: none; border: none; }"
                                 "QListWidget::item:selected:!active { background-color: transparent; outline: none; border: none; }"
                                 "QListWidget::item:selected:active { background-color: transparent; outline: none; border: none; }"
                                 "QListWidget::item:hover { background-color: transparent; outline: none; border: none; }"
                                 "QListWidget::item:disabled { background-color: transparent; outline: none; border: none; }");
    
    // 创建群组成员列表（仅群组聊天显示）
    QWidget *memberWidget = nullptr;
    QListWidget *memberListWidget = nullptr;
    QVBoxLayout *memberLayout = nullptr;
    
    if (isGroup) {
        // 创建成员列表部件
        memberWidget = new QWidget;
        memberWidget->setStyleSheet("background-color: #f8f9fa; border-left: 1px solid #eee;");
        memberLayout = new QVBoxLayout;
        memberLayout->setContentsMargins(10, 10, 10, 10);
        memberLayout->setSpacing(10);
        
        // 成员列表标题
        QLabel *memberTitle = new QLabel("群组成员");
        memberTitle->setStyleSheet("font-weight: bold; font-size: 14px; color: #333;");
        memberLayout->addWidget(memberTitle);
        
        // 成员列表
        memberListWidget = new QListWidget;
        memberListWidget->setStyleSheet(
            "background-color: white; border: 1px solid #ddd; border-radius: 6px;"
            "QListWidget::item { height: 30px; padding: 5px 10px; border-bottom: 1px solid #f0f0f0; }"
            "QListWidget::item:last-child { border-bottom: none; }"
        );
        memberLayout->addWidget(memberListWidget);
        
        memberWidget->setLayout(memberLayout);
        memberWidget->setFixedWidth(180);
    }
    
    // 如果是群组聊天，使用分割器布局，包含聊天记录和成员列表
    if (isGroup && memberWidget) {
        QSplitter *chatSplitter = new QSplitter(Qt::Horizontal);
        chatSplitter->addWidget(chatListWidget);
        chatSplitter->addWidget(memberWidget);
        chatSplitter->setSizes({450, 180}); // 设置初始大小
        chatSplitter->setHandleWidth(1);
        mainLayout->addWidget(chatSplitter);
    } else {
        // 普通聊天，仅显示聊天记录
        mainLayout->addWidget(chatListWidget);
    }
    
    // 分隔线
    QFrame *separator = new QFrame;
    separator->setFrameShape(QFrame::HLine);
    separator->setFrameShadow(QFrame::Sunken);
    separator->setStyleSheet("background-color: #eee;");
    mainLayout->addWidget(separator);
    
    // 输入区域
    QWidget *inputWidget = new QWidget;
    inputWidget->setStyleSheet("background-color: white;");
    QVBoxLayout *inputLayout = new QVBoxLayout;
    inputLayout->setContentsMargins(10, 10, 10, 10);
    inputLayout->setSpacing(10);
    
    // 输入框
    QLineEdit *inputEdit = new QLineEdit;
    inputEdit->setMinimumHeight(40);
    inputEdit->setStyleSheet("border: 1px solid #ddd; border-radius: 8px; padding: 0 12px;");
    inputLayout->addWidget(inputEdit);
    
    // 按钮区域
    QHBoxLayout *buttonLayout = new QHBoxLayout;
    buttonLayout->setContentsMargins(0, 0, 0, 0);
    buttonLayout->setSpacing(10);
    buttonLayout->setAlignment(Qt::AlignRight);
    
    // 创建发送按钮
    QPushButton *sendButton = new QPushButton("发送");
    sendButton->setMinimumHeight(40);
    sendButton->setFixedWidth(100);
    sendButton->setStyleSheet(
        "QPushButton { background-color: #3498db; color: white; border: none; border-radius: 8px; font-size: 14px; font-weight: 500; }"
        "QPushButton:hover { background-color: #2980b9; }"
        "QPushButton:pressed { background-color: #2471a3; }"
    );
    
    // 创建发送文件按钮
    QPushButton *sendFileButton = new QPushButton("发送文件");
    sendFileButton->setMinimumHeight(40);
    sendFileButton->setFixedWidth(100);
    sendFileButton->setStyleSheet(
        "QPushButton { background-color: #ecf0f1; color: #333; border: 1px solid #ddd; border-radius: 8px; font-size: 14px; font-weight: 500; }"
        "QPushButton:hover { background-color: #d5dbdb; }"
        "QPushButton:pressed { background-color: #bdc3c7; }"
    );
    
    // 创建发送图片按钮
    QPushButton *sendImageButton = new QPushButton("发送图片");
    sendImageButton->setMinimumHeight(40);
    sendImageButton->setFixedWidth(100);
    sendImageButton->setStyleSheet(
        "QPushButton { background-color: #ecf0f1; color: #333; border: 1px solid #ddd; border-radius: 8px; font-size: 14px; font-weight: 500; }"
        "QPushButton:hover { background-color: #d5dbdb; }"
        "QPushButton:pressed { background-color: #bdc3c7; }"
    );
    
    // 创建表情包按钮
    QPushButton *sendEmojiButton = new QPushButton("表情包");
    sendEmojiButton->setMinimumHeight(40);
    sendEmojiButton->setFixedWidth(80);
    sendEmojiButton->setStyleSheet(
        "QPushButton { background-color: #ecf0f1; color: #333; border: 1px solid #ddd; border-radius: 8px; font-size: 14px; font-weight: 500; }"
        "QPushButton:hover { background-color: #d5dbdb; }"
        "QPushButton:pressed { background-color: #bdc3c7; }"
    );
    
    // 添加按钮到布局
    buttonLayout->addWidget(sendButton);
    buttonLayout->addWidget(sendEmojiButton);
    buttonLayout->addWidget(sendImageButton);
    buttonLayout->addWidget(sendFileButton);
    
    // 连接表情包按钮信号
    connect(sendEmojiButton, &QPushButton::clicked, this, &ChatWindow::onSendEmoji);
    
    // 将按钮布局添加到输入布局
    inputLayout->addLayout(buttonLayout);
    
    // 将输入布局添加到输入部件
    inputWidget->setLayout(inputLayout);
    
    // 将输入部件添加到主布局
    mainLayout->addWidget(inputWidget);
    
    // 将主布局设置到聊天部件
    chatWidget->setLayout(mainLayout);
    
    // 设置属性
    chatWidget->setProperty("chatId", chatId);
    chatWidget->setProperty("isGroup", isGroup);
    
    // 存储聊天组件的映射关系
    chatComponents[chatWidget] = {chatListWidget, memberListWidget};
    
    // 连接信号
    connect(sendButton, &QPushButton::clicked, this, &ChatWindow::onSendMessage);
    connect(inputEdit, &QLineEdit::returnPressed, this, &ChatWindow::onSendMessage);
    connect(sendImageButton, &QPushButton::clicked, this, &ChatWindow::onSendImage);
    connect(sendFileButton, &QPushButton::clicked, this, &ChatWindow::onSendFile);
    
    // 存储输入框的映射关系
    inputLineEdits[chatWidget] = inputEdit;
    
    // 添加到标签页
    chatTabWidget->addTab(chatWidget, chatName);
    chatTabWidget->setCurrentWidget(chatWidget);
    
    // 更新标签页文本，可能包含未读消息小红点
    updateTabText(chatId, isGroup, chatName);
    
    // 如果是群组聊天，加载并显示群组成员
    if (isGroup) {
        // 从groupMap中获取真实群组成员列表
        memberListWidget->addItem("群组成员加载中...");
        
        QTimer::singleShot(50, this, [this, memberListWidget, chatId]() {
            memberListWidget->clear();
            
            // 检查groupMap中是否有该群组的信息
            if (groupMap.contains(chatId)) {
                // 获取群组信息
                Group group = groupMap.value(chatId);
                const vector<GroupUser>& members = group.getUsers();
                
                // 添加真实成员名字
                for (const GroupUser& member : members) {
                    QString memberName = QString::fromStdString(member.getName());
                    QString memberRole = QString::fromStdString(member.getRole());
                    
                    // 格式化成员显示，包含角色信息
                    QString memberDisplay = memberName;
                    if (memberRole == "creator") {
                        memberDisplay += " (群主)";
                    } else if (memberRole == "admin") {
                        memberDisplay += " (管理员)";
                    }
                    
                    memberListWidget->addItem(memberDisplay);
                }
                
                if (members.empty()) {
                    memberListWidget->addItem("暂无成员");
                }
            } else {
                // 如果没有找到群组信息，显示提示
                memberListWidget->addItem("无法获取群组成员信息");
                
                // 可以考虑重新请求群组列表
                qDebug() << "Group information not found in groupMap, requesting group list again";
                chatClient->requestGroupList(userId);
            }
        });
    }
}

void ChatWindow::onContactSelected() {
    QTreeWidgetItem *item = contactTreeWidget->currentItem();
    if (!item || !item->parent()) return; // 忽略根节点

    bool isGroup = (item->parent()->text(1) == "群组");
    int chatId = item->data(1, Qt::UserRole).toInt();
    QString chatName = item->text(1);

    // 首先修复所有现有窗口
    for (int i = 0; i < chatTabWidget->count(); ++i) {
        QWidget *existingWidget = chatTabWidget->widget(i);
        
        // 检查现有窗口是否有发送按钮，如果没有则修复
        QVBoxLayout *chatLayout = qobject_cast<QVBoxLayout*>(existingWidget->layout());
        if (chatLayout) {
            QWidget *inputWidget = chatLayout->itemAt(2)->widget();
            if (inputWidget) {
                QVBoxLayout *inputLayout = qobject_cast<QVBoxLayout*>(inputWidget->layout());
                if (inputLayout) {
                    // 查找按钮布局
                    QHBoxLayout *buttonLayout = nullptr;
                    for (int j = 0; j < inputLayout->count(); ++j) {
                        QLayout *layout = inputLayout->itemAt(j)->layout();
                        if (layout) {
                            buttonLayout = qobject_cast<QHBoxLayout*>(layout);
                            if (buttonLayout) {
                                break;
                            }
                        }
                    }
                    
                    if (buttonLayout) {
                        // 检查是否有各种按钮
                        bool hasSendButton = false;
                        bool hasSendEmojiButton = false;
                        bool hasSendImageButton = false;
                        bool hasSendFileButton = false;
                        
                        // 遍历按钮布局中的所有控件
                        for (int j = 0; j < buttonLayout->count(); ++j) {
                            QWidget *widget = buttonLayout->itemAt(j)->widget();
                            if (QPushButton *button = qobject_cast<QPushButton*>(widget)) {
                                if (button->text() == "发送") {
                                    hasSendButton = true;
                                } else if (button->text() == "表情包") {
                                    hasSendEmojiButton = true;
                                } else if (button->text() == "发送图片") {
                                    hasSendImageButton = true;
                                } else if (button->text() == "发送文件") {
                                    hasSendFileButton = true;
                                }
                            }
                        }
                        
                        // 如果缺少发送按钮，添加它
                        if (!hasSendButton) {
                            QPushButton *sendButton = new QPushButton("发送");
                            sendButton->setMinimumHeight(40);
                            sendButton->setFixedWidth(100);
                            sendButton->setStyleSheet(
                                "QPushButton { background-color: #3498db; color: white; border: none; border-radius: 8px; font-size: 14px; font-weight: 500; }"
                                "QPushButton:hover { background-color: #2980b9; }"
                                "QPushButton:pressed { background-color: #2471a3; }"
                            );
                            buttonLayout->insertWidget(0, sendButton);
                            connect(sendButton, &QPushButton::clicked, this, &ChatWindow::onSendMessage);
                        }
                        
                        // 如果缺少表情包按钮，添加它
                        if (!hasSendEmojiButton) {
                            QPushButton *sendEmojiButton = new QPushButton("表情包");
                            sendEmojiButton->setMinimumHeight(40);
                            sendEmojiButton->setFixedWidth(80);
                            sendEmojiButton->setStyleSheet(
                                "QPushButton { background-color: #ecf0f1; color: #333; border: 1px solid #ddd; border-radius: 8px; font-size: 14px; font-weight: 500; }"
                                "QPushButton:hover { background-color: #d5dbdb; }"
                                "QPushButton:pressed { background-color: #bdc3c7; }"
                            );
                            buttonLayout->insertWidget(1, sendEmojiButton);
                            connect(sendEmojiButton, &QPushButton::clicked, this, &ChatWindow::onSendEmoji);
                        }
                        
                        // 如果缺少发送图片按钮，添加它
                        if (!hasSendImageButton) {
                            QPushButton *sendImageButton = new QPushButton("发送图片");
                            sendImageButton->setMinimumHeight(40);
                            sendImageButton->setFixedWidth(100);
                            sendImageButton->setStyleSheet(
                                "QPushButton { background-color: #ecf0f1; color: #333; border: 1px solid #ddd; border-radius: 8px; font-size: 14px; font-weight: 500; }"
                                "QPushButton:hover { background-color: #d5dbdb; }"
                                "QPushButton:pressed { background-color: #bdc3c7; }"
                            );
                            buttonLayout->insertWidget(2, sendImageButton);
                            connect(sendImageButton, &QPushButton::clicked, this, &ChatWindow::onSendImage);
                        }
                        
                        // 如果缺少发送文件按钮，添加它
                        if (!hasSendFileButton) {
                            QPushButton *sendFileButton = new QPushButton("发送文件");
                            sendFileButton->setMinimumHeight(40);
                            sendFileButton->setFixedWidth(100);
                            sendFileButton->setStyleSheet(
                                "QPushButton { background-color: #ecf0f1; color: #333; border: 1px solid #ddd; border-radius: 8px; font-size: 14px; font-weight: 500; }"
                                "QPushButton:hover { background-color: #d5dbdb; }"
                                "QPushButton:pressed { background-color: #bdc3c7; }"
                            );
                            buttonLayout->insertWidget(3, sendFileButton);
                            connect(sendFileButton, &QPushButton::clicked, this, &ChatWindow::onSendFile);
                        }
                    }
                }
            }
        }
    }
    
    // 清除未读计数
    QString key = generateChatKey(chatId, isGroup);
    unreadMessageCounts.remove(key);
    
    // 然后创建或切换到目标聊天窗口
    createChatWidget(chatId, chatName, isGroup);
    
    // 更新标签页文本，清除小红点
    updateTabText(chatId, isGroup, chatName);
}

void ChatWindow::onAddFriend() {
    addFriendDialog->show();
}

void ChatWindow::onAddFriendConfirmed() {
    QString idStr = addFriendIdEdit->text();
    bool ok;
    int friendId = idStr.toInt(&ok);
    
    if (!ok || friendId <= 0) {
        QMessageBox::warning(this, "警告", "请输入有效的好友ID");
        return;
    }
    
    chatClient->addFriend(userId, friendId);
    addFriendDialog->close();
    addFriendIdEdit->clear();
}

void ChatWindow::onCreateGroup() {
    createGroupDialog->show();
}

void ChatWindow::onCreateGroupConfirmed() {
    QString groupName = groupNameEdit->text();
    QString groupDesc = groupDescEdit->text();
    
    if (groupName.isEmpty()) {
        QMessageBox::warning(this, "警告", "请输入群组名称");
        return;
    }
    
    chatClient->createGroup(userId, groupName, groupDesc);
    createGroupDialog->close();
    groupNameEdit->clear();
    groupDescEdit->clear();
}

void ChatWindow::onJoinGroup() {
    joinGroupDialog->show();
}

void ChatWindow::onJoinGroupConfirmed() {
    QString idStr = joinGroupIdEdit->text();
    bool ok;
    int groupId = idStr.toInt(&ok);
    
    if (!ok || groupId <= 0) {
        QMessageBox::warning(this, "警告", "请输入有效的群组ID");
        return;
    }
    
    chatClient->joinGroup(userId, groupId);
    joinGroupDialog->close();
    joinGroupIdEdit->clear();
}
void ChatWindow::onReceiveMessage(int fromId, const QString &message, const QString &fromName, bool isGroup, int groupId, const QString &timestamp) {
    // 检查好友列表是否已加载
    if (!friendListLoaded && !isGroup) {
        qDebug() << "ChatWindow: onReceiveMessage - Friend list not loaded yet, storing message from" << fromId;
        // 存储未处理的消息
        PendingMessage pendingMsg;
        pendingMsg.fromId = fromId;
        pendingMsg.message = message;
        pendingMsg.fromName = fromName;
        pendingMsg.isGroup = isGroup;
        pendingMsg.groupId = groupId;
        pendingMsg.timestamp = timestamp;
        pendingMessages.append(pendingMsg);
        qDebug() << "ChatWindow: onReceiveMessage - Stored pending message, queue size:" << pendingMessages.size();
        return;
    }

    QString chatName;
    int chatId;    
    if (isGroup) {
        chatId = groupId;
        if (groupMap.contains(groupId)) {
            chatName = QString::fromStdString(groupMap[groupId].getName());
        }
    } else {
        chatId = fromId;
        // 使用信号中提供的发送者名称，否则从friendMap获取，最后使用默认名称
        if (!fromName.isEmpty()) {
            chatName = fromName;
        } else if (friendMap.contains(fromId)) {
            chatName = QString::fromStdString(friendMap[fromId].getName());
        } else {
            chatName = QString("用户 %1").arg(fromId);
        }
    }

    // 查找或创建对应的聊天窗口
    QListWidget *chatListWidget = nullptr;
    QWidget *chatWidget = nullptr;
    
    // 查找是否已存在聊天窗口
    for (int i = 0; i < chatTabWidget->count(); ++i) {
        if (chatTabWidget->widget(i)->property("chatId").toInt() == chatId &&
            chatTabWidget->widget(i)->property("isGroup").toBool() == isGroup) {
            chatWidget = chatTabWidget->widget(i);
            // 从chatComponents映射中获取chatListWidget
            if (chatComponents.contains(chatWidget)) {
                chatListWidget = chatComponents[chatWidget].chatListWidget;
            }
            break;
        }
    }

    // 如果聊天窗口不存在，创建一个新的
    if (!chatListWidget) {
        createChatWidget(chatId, chatName, isGroup);
        
        // 查找刚创建的聊天窗口
        for (int i = 0; i < chatTabWidget->count(); ++i) {
            if (chatTabWidget->widget(i)->property("chatId").toInt() == chatId &&
                chatTabWidget->widget(i)->property("isGroup").toBool() == isGroup) {
                chatWidget = chatTabWidget->widget(i);
                // 从chatComponents映射中获取chatListWidget
                if (chatComponents.contains(chatWidget)) {
                    chatListWidget = chatComponents[chatWidget].chatListWidget;
                }
                break;
            }
        }
    }

    // 显示接收到的消息
    if (chatListWidget) {
        QString timeStr;
        // 如果有时间戳，使用它，否则使用当前时间
        qDebug() << "[DEBUG] Received timestamp:" << timestamp << "isEmpty:" << timestamp.isEmpty();
        if (!timestamp.isEmpty()) {
            // 将服务器返回的UTC时间转换为本地时间显示
            qDebug() << "[DEBUG] Original timestamp:" << timestamp;
            
            // 解析服务器返回的UTC时间（格式: YYYYMMDD HH:MM:SS.mmmmmm）
            // 先尝试使用完整格式解析
            QString timeOnly = timestamp;
            QString dateOnly = timestamp;
            int spacePos = timestamp.indexOf(' ');
            if (spacePos != -1) {
                dateOnly = timestamp.left(spacePos);
                timeOnly = timestamp.mid(spacePos + 1);
            }
            
            // 去掉毫秒部分
            int dotPos = timeOnly.indexOf('.');
            if (dotPos != -1) {
                timeOnly = timeOnly.left(dotPos);
            }
            
            // 拼接成新的时间字符串（YYYYMMDD HH:MM:SS）
            QString datetimeStr = dateOnly + " " + timeOnly;
            
            // 使用简化格式解析
            QDateTime utcDateTime = QDateTime::fromString(datetimeStr, "yyyyMMdd HH:mm:ss");
            
            qDebug() << "[DEBUG] Original timestamp:" << timestamp;
            qDebug() << "[DEBUG] Date only:" << dateOnly;
            qDebug() << "[DEBUG] Time only:" << timeOnly;
            qDebug() << "[DEBUG] DateTime string:" << datetimeStr;
            qDebug() << "[DEBUG] Parsed datetime:" << utcDateTime << "isValid:" << utcDateTime.isValid();
            
            if (utcDateTime.isValid()) {
                // 设置为UTC时区
                utcDateTime.setTimeSpec(Qt::UTC);
                
                // 转换为本地时间
                QDateTime localDateTime = utcDateTime.toLocalTime();
                
                // 提取时间部分（HH:MM:SS）
                timeStr = localDateTime.toString("hh:mm:ss");
                
                qDebug() << "[DEBUG] UTC time:" << utcDateTime;
                qDebug() << "[DEBUG] Local time:" << localDateTime;
                qDebug() << "[DEBUG] Using local timestamp:" << timeStr;
            } else {
                // 如果解析失败，直接使用提取的时间部分
                timeStr = timeOnly;
                qDebug() << "[DEBUG] Failed to parse timestamp, using extracted time:" << timeStr;
            }
        } else {
            timeStr = QDateTime::currentDateTime().toString("hh:mm:ss");
            qDebug() << "[DEBUG] No timestamp, using current time:" << timeStr;
        }
        
        // 显示接收到的消息 - 使用聊天气泡
        // 获取发送者的头像
        QString senderAvatarPath = ":/icons/user.png"; // 默认头像
        if (friendMap.contains(fromId)) {
            User senderUser = friendMap[fromId];
            string avatarBase64 = senderUser.getAvatar();
            if (!avatarBase64.empty()) {
                // 头像数据存在，使用它
                QString avatarDataStr = QString::fromStdString(avatarBase64);
                QByteArray decodedData;
                QPixmap avatarPixmap;
                bool loadSuccess = false;
                
                // 检查是Data URL还是纯Base64编码数据
                if (avatarDataStr.startsWith("data:image/")) {
                    // Data URL格式：data:image/png;base64,...
                    int commaPos = avatarDataStr.indexOf(',');
                    if (commaPos != -1) {
                        QString base64Data = avatarDataStr.mid(commaPos + 1);
                        decodedData = QByteArray::fromBase64(base64Data.toUtf8());
                        
                        // 检查是否需要再次解码
                        if (decodedData.size() >= 4 && decodedData[0] == '/' && decodedData[1] == '9' && decodedData[2] == 'j' && decodedData[3] == '/') {
                            qDebug() << "ChatWindow: onReceiveMessage - Friend avatar data is double Base64 encoded, decoding again...";
                            decodedData = QByteArray::fromBase64(decodedData);
                        }
                        
                        // 尝试检测图片格式或使用常见格式
                        loadSuccess = avatarPixmap.loadFromData(decodedData);
                        if (!loadSuccess) {
                            // 如果自动检测失败，尝试常见的图片格式
                            loadSuccess = avatarPixmap.loadFromData(decodedData, "PNG");
                        }
                        if (!loadSuccess) {
                            loadSuccess = avatarPixmap.loadFromData(decodedData, "JPEG");
                        }
                        if (!loadSuccess) {
                            loadSuccess = avatarPixmap.loadFromData(decodedData, "BMP");
                        }
                    }
                } else {
                    // 纯Base64编码数据
                    decodedData = QByteArray::fromBase64(avatarDataStr.toUtf8());
                    
                    // 检查是否需要再次解码
                    if (decodedData.size() >= 4 && decodedData[0] == '/' && decodedData[1] == '9' && decodedData[2] == 'j' && decodedData[3] == '/') {
                        qDebug() << "ChatWindow: onReceiveMessage - Friend avatar data is double Base64 encoded, decoding again...";
                        decodedData = QByteArray::fromBase64(decodedData);
                    }
                    
                    // 尝试检测图片格式或使用常见格式
                    loadSuccess = avatarPixmap.loadFromData(decodedData);
                    if (!loadSuccess) {
                        // 如果自动检测失败，尝试常见的图片格式
                        loadSuccess = avatarPixmap.loadFromData(decodedData, "PNG");
                    }
                    if (!loadSuccess) {
                        loadSuccess = avatarPixmap.loadFromData(decodedData, "JPEG");
                    }
                    if (!loadSuccess) {
                        loadSuccess = avatarPixmap.loadFromData(decodedData, "BMP");
                    }
                }
                
                if (loadSuccess) {
                    // 头像加载成功，保存到临时文件
                    QString tempAvatarPath = QCoreApplication::applicationDirPath() + "/temp_avatar_" + QString::number(fromId) + ".png";
                    if (avatarPixmap.save(tempAvatarPath)) {
                        senderAvatarPath = tempAvatarPath;
                    }
                }
            }
        }
        addMessageToChatList(chatListWidget, false, message, senderAvatarPath, timeStr);
        
        // 检查消息是否在当前聊天窗口中显示，如果不是则增加未读计数
        if (chatTabWidget->currentWidget() != chatWidget) {
            QString key = generateChatKey(chatId, isGroup);
            int count = unreadMessageCounts.value(key, 0);
            unreadMessageCounts[key] = count + 1;
            updateTabText(chatId, isGroup, chatName);
        } else {
            // 如果是当前窗口，直接显示
            for (int i = 0; i < chatTabWidget->count(); ++i) {
                if (chatTabWidget->widget(i) == chatWidget) {
                    chatTabWidget->setCurrentIndex(i);
                    break;
                }
            }
        }
    }
}

void ChatWindow::onReceiveGroupMessage(int groupId, int fromId, const QString &userName, const QString &message, const QString &timestamp) {
    QString groupName;
    if (groupMap.contains(groupId)) {
        groupName = QString::fromStdString(groupMap[groupId].getName());
    } else {
        groupName = QString("群组 %1").arg(groupId);
    }

    // 查找或创建对应的群聊窗口
    QListWidget *chatListWidget = nullptr;
    QWidget *chatWidget = nullptr;
    
    // 查找是否已存在聊天窗口
    for (int i = 0; i < chatTabWidget->count(); ++i) {
        if (chatTabWidget->widget(i)->property("chatId").toInt() == groupId &&
            chatTabWidget->widget(i)->property("isGroup").toBool() == true) {
            chatWidget = chatTabWidget->widget(i);
            // 从chatComponents映射中获取chatListWidget
            if (chatComponents.contains(chatWidget)) {
                chatListWidget = chatComponents[chatWidget].chatListWidget;
            }
            break;
        }
    }

    // 如果聊天窗口不存在，创建一个新的
    if (!chatListWidget) {
        createChatWidget(groupId, groupName, true);
        
        // 查找刚创建的聊天窗口
        for (int i = 0; i < chatTabWidget->count(); ++i) {
            if (chatTabWidget->widget(i)->property("chatId").toInt() == groupId &&
                chatTabWidget->widget(i)->property("isGroup").toBool() == true) {
                chatWidget = chatTabWidget->widget(i);
                // 从chatComponents映射中获取chatListWidget
                if (chatComponents.contains(chatWidget)) {
                    chatListWidget = chatComponents[chatWidget].chatListWidget;
                }
                break;
            }
        }
    }

    // 显示群消息
    if (chatListWidget) {
        QString timeStr;
        // 如果有时间戳，使用它，否则使用当前时间
        qDebug() << "[DEBUG] Group message received timestamp:" << timestamp << "isEmpty:" << timestamp.isEmpty();
        if (!timestamp.isEmpty()) {
            // 将服务器返回的UTC时间转换为本地时间显示
            qDebug() << "[DEBUG] Group message original timestamp:" << timestamp;
            
            // 解析服务器返回的UTC时间（格式: YYYYMMDD HH:MM:SS.mmmmmm）
            // 先尝试使用完整格式解析
            QString timeOnly = timestamp;
            QString dateOnly = timestamp;
            int spacePos = timestamp.indexOf(' ');
            if (spacePos != -1) {
                dateOnly = timestamp.left(spacePos);
                timeOnly = timestamp.mid(spacePos + 1);
            }
            
            // 去掉毫秒部分
            int dotPos = timeOnly.indexOf('.');
            if (dotPos != -1) {
                timeOnly = timeOnly.left(dotPos);
            }
            
            // 拼接成新的时间字符串（YYYYMMDD HH:MM:SS）
            QString datetimeStr = dateOnly + " " + timeOnly;
            
            // 使用简化格式解析
            QDateTime utcDateTime = QDateTime::fromString(datetimeStr, "yyyyMMdd HH:mm:ss");
            
            qDebug() << "[DEBUG] Group message original timestamp:" << timestamp;
            qDebug() << "[DEBUG] Group message date only:" << dateOnly;
            qDebug() << "[DEBUG] Group message time only:" << timeOnly;
            qDebug() << "[DEBUG] Group message datetime string:" << datetimeStr;
            qDebug() << "[DEBUG] Group message parsed datetime:" << utcDateTime << "isValid:" << utcDateTime.isValid();
            
            if (utcDateTime.isValid()) {
                // 设置为UTC时区
                utcDateTime.setTimeSpec(Qt::UTC);
                
                // 转换为本地时间
                QDateTime localDateTime = utcDateTime.toLocalTime();
                
                // 提取时间部分（HH:MM:SS）
                timeStr = localDateTime.toString("hh:mm:ss");
                
                qDebug() << "[DEBUG] Group message UTC time:" << utcDateTime;
                qDebug() << "[DEBUG] Group message local time:" << localDateTime;
                qDebug() << "[DEBUG] Group message using local timestamp:" << timeStr;
            } else {
                // 如果解析失败，直接使用提取的时间部分
                timeStr = timeOnly;
                qDebug() << "[DEBUG] Group message failed to parse timestamp, using extracted time:" << timeStr;
            }
        } else {
            timeStr = QDateTime::currentDateTime().toString("hh:mm:ss");
            qDebug() << "[DEBUG] Group message no timestamp, using current time:" << timeStr;
        }
        
        // 显示接收到的消息 - 使用聊天气泡
        // 获取发送者的头像
        QString senderAvatarPath = ":/icons/user.png"; // 默认头像
        if (friendMap.contains(fromId)) {
            User senderUser = friendMap[fromId];
            string avatarBase64 = senderUser.getAvatar();
            if (!avatarBase64.empty()) {
                // 头像数据存在，使用它
                QString avatarDataStr = QString::fromStdString(avatarBase64);
                QByteArray decodedData;
                QPixmap avatarPixmap;
                bool loadSuccess = false;
                
                // 检查是Data URL还是纯Base64编码数据
                if (avatarDataStr.startsWith("data:image/")) {
                    // Data URL格式：data:image/png;base64,...
                    int commaPos = avatarDataStr.indexOf(',');
                    if (commaPos != -1) {
                        QString base64Data = avatarDataStr.mid(commaPos + 1);
                        decodedData = QByteArray::fromBase64(base64Data.toUtf8());
                        
                        // 尝试检测图片格式或使用常见格式
                        loadSuccess = avatarPixmap.loadFromData(decodedData);
                        if (!loadSuccess) {
                            // 如果自动检测失败，尝试常见的图片格式
                            loadSuccess = avatarPixmap.loadFromData(decodedData, "PNG");
                        }
                        if (!loadSuccess) {
                            loadSuccess = avatarPixmap.loadFromData(decodedData, "JPEG");
                        }
                        if (!loadSuccess) {
                            loadSuccess = avatarPixmap.loadFromData(decodedData, "BMP");
                        }
                    }
                } else {
                    // 纯Base64编码数据
                    decodedData = QByteArray::fromBase64(avatarDataStr.toUtf8());
                    
                    // 尝试检测图片格式或使用常见格式
                    loadSuccess = avatarPixmap.loadFromData(decodedData);
                    if (!loadSuccess) {
                        // 如果自动检测失败，尝试常见的图片格式
                        loadSuccess = avatarPixmap.loadFromData(decodedData, "PNG");
                    }
                    if (!loadSuccess) {
                        loadSuccess = avatarPixmap.loadFromData(decodedData, "JPEG");
                    }
                    if (!loadSuccess) {
                        loadSuccess = avatarPixmap.loadFromData(decodedData, "BMP");
                    }
                }
                
                if (loadSuccess) {
                    // 头像加载成功，保存到临时文件
                    QString tempAvatarPath = QCoreApplication::applicationDirPath() + "/temp_avatar_" + QString::number(fromId) + ".png";
                    if (avatarPixmap.save(tempAvatarPath)) {
                        senderAvatarPath = tempAvatarPath;
                    }
                }
            }
        }
        addMessageToChatList(chatListWidget, false, message, senderAvatarPath, timeStr);
        
        // 检查消息是否在当前聊天窗口中显示，如果不是则增加未读计数
        if (chatTabWidget->currentWidget() != chatWidget) {
            QString key = generateChatKey(groupId, true);
            int count = unreadMessageCounts.value(key, 0);
            unreadMessageCounts[key] = count + 1;
            updateTabText(groupId, true, groupName);
        } else {
            // 如果是当前窗口，直接显示
            for (int i = 0; i < chatTabWidget->count(); ++i) {
                if (chatTabWidget->widget(i) == chatWidget) {
                    chatTabWidget->setCurrentIndex(i);
                    break;
                }
            }
        }
    }
}

void ChatWindow::onFriendListUpdated(const QList<User> &friends) {
    qDebug() << "[CRITICAL] Received friend list update, count:" << friends.size();
    
    // 确保contactTreeWidget已初始化
    if (!contactTreeWidget) {
        qDebug() << "[ERROR] contactTreeWidget is null";
        return;
    }
    
    // 打印收到的每个好友信息
    for (const User &user : friends) {
        qDebug() << "[CRITICAL] Friend - ID:" << user.getId() << "Name:" << QString::fromStdString(user.getName());
    }
    
    // 确保friendRoot有效，如果无效则尝试查找或创建
    if (!friendRoot) {
        qDebug() << "[ERROR] friendRoot is null, attempting to find or create";
        // 尝试从contactTreeWidget中查找好友根节点
        for (int i = 0; i < contactTreeWidget->topLevelItemCount(); ++i) {
            QTreeWidgetItem *item = contactTreeWidget->topLevelItem(i);
            if (item->text(1) == "好友") {
                friendRoot = item;
                break;
            }
        }
        
        // 如果仍然没有找到，创建一个新的
        if (!friendRoot) {
            qDebug() << "[DEBUG] Creating new friend root item";
            friendRoot = new QTreeWidgetItem(contactTreeWidget);
            friendRoot->setText(1, "好友"); // 在联系人列显示标题
            friendRoot->setFirstColumnSpanned(true); // 跨列显示
            contactTreeWidget->addTopLevelItem(friendRoot);
        }
    }
    
    // 清空好友列表
    friendRoot->takeChildren();

    // 更新好友数据和列表
    friendMap.clear();
    for (const User &user : friends) {
        friendMap[user.getId()] = user;
        QTreeWidgetItem *item = new QTreeWidgetItem(friendRoot);
        QString friendName = QString::fromStdString(user.getName());
        
        // 设置联系人名称和ID
        item->setText(1, friendName + " (" + QString::number(user.getId()) + ")");
        item->setData(1, Qt::UserRole, user.getId());
        
        // 处理好友头像（统一使用数据库处理）
        string avatarBase64 = user.getAvatar();
        if (!avatarBase64.empty()) {
            // 如果有头像数据
            QPixmap avatarPixmap;
            QByteArray decodedData;
            bool loadSuccess = false;
            
            qDebug() << "ChatWindow: Friend avatar Base64 length:" << avatarBase64.size();
            qDebug() << "ChatWindow: Friend avatar Base64 preview:" << QString::fromStdString(avatarBase64.substr(0, 50));
            
            // 直接将字符串作为Base64编码处理，解码得到二进制数据
            QString base64Str = QString::fromStdString(avatarBase64);
            decodedData = QByteArray::fromBase64(base64Str.toUtf8());
            
            qDebug() << "ChatWindow: Friend avatar decoded length:" << decodedData.size();
            qDebug() << "ChatWindow: Friend avatar decoded header:" << decodedData.left(20).toHex();
            
            // 检查解码后的data是否是ASCII文本且看起来像Base64编码
            bool isBase64Text = true;
            for (char c : decodedData) {
                if (!isalnum(c) && c != '+' && c != '/' && c != '=' && !isspace(c)) {
                    isBase64Text = false;
                    break;
                }
            }
            
            if (isBase64Text && decodedData.length() > 0 && decodedData.length() % 4 == 0) {
                qDebug() << "ChatWindow: Friend avatar detected double Base64 encoding, decoding again...";
                QByteArray doubleDecoded = QByteArray::fromBase64(decodedData);
                qDebug() << "ChatWindow: Friend avatar double decoded length:" << doubleDecoded.length();
                qDebug() << "ChatWindow: Friend avatar double decoded header:" << doubleDecoded.left(20).toHex();
                
                // 使用再次解码后的数据
                decodedData = doubleDecoded;
            }
            
            // 尝试明确指定JPEG格式加载
            loadSuccess = avatarPixmap.loadFromData(decodedData, "JPEG");
            qDebug() << "ChatWindow: Friend avatar load (JPEG):" << loadSuccess;
            
            if (!loadSuccess) {
                // 尝试自动检测格式
                loadSuccess = avatarPixmap.loadFromData(decodedData);
                qDebug() << "ChatWindow: Friend avatar load (auto):" << loadSuccess;
            }
            
            if (loadSuccess && !avatarPixmap.isNull()) {
                // 头像图片加载成功，缩放头像到合适大小
                QPixmap scaledPixmap = avatarPixmap.scaled(
                    50, 50, // 增大头像大小到50x50
                    Qt::KeepAspectRatio, 
                    Qt::SmoothTransformation
                );
                item->setIcon(0, QIcon(scaledPixmap));
                qDebug() << "ChatWindow: Friend avatar loaded successfully, icon set";
            } else {
                // 如果头像加载失败，显示用户名首字母
                QChar firstChar = friendName.isEmpty() ? QChar('U') : friendName[0];
                
                // 创建一个带有首字母的圆形头像
                QPixmap fallbackPixmap(50, 50);
                fallbackPixmap.fill(Qt::transparent);
                
                QPainter painter(&fallbackPixmap);
                painter.setRenderHint(QPainter::Antialiasing, true);
                
                // 绘制蓝色圆形背景
                QBrush brush(QColor(52, 152, 219)); // #3498db
                painter.setBrush(brush);
                painter.setPen(Qt::NoPen);
                painter.drawEllipse(0, 0, 50, 50);
                
                // 绘制白色文字
                QFont font("Arial", 20, QFont::Bold);
                painter.setFont(font);
                painter.setPen(QColor(Qt::white));
                painter.drawText(fallbackPixmap.rect(), Qt::AlignCenter, firstChar.toUpper());
                
                item->setIcon(0, QIcon(fallbackPixmap));
                qDebug() << "ChatWindow: Friend avatar load failed, using fallback";
            }
        } else {
            // 如果没有头像，显示用户名首字母
            QChar firstChar = friendName.isEmpty() ? QChar('U') : friendName[0];
            
            // 创建一个带有首字母的圆形头像
            QPixmap avatarPixmap(50, 50);
            avatarPixmap.fill(Qt::transparent);
            
            QPainter painter(&avatarPixmap);
            painter.setRenderHint(QPainter::Antialiasing, true);
            
            // 绘制蓝色圆形背景
            QBrush brush(QColor(52, 152, 219)); // #3498db
            painter.setBrush(brush);
            painter.setPen(Qt::NoPen);
            painter.drawEllipse(0, 0, 50, 50);
            
            // 绘制白色文字
            QFont font("Arial", 20, QFont::Bold);
            painter.setFont(font);
            painter.setPen(QColor(Qt::white));
            painter.drawText(avatarPixmap.rect(), Qt::AlignCenter, firstChar.toUpper());
            
            item->setIcon(0, QIcon(avatarPixmap));
        }
        
        // 尝试获取并设置在线状态，避免方法不存在的错误
        try {
            QString stateText = QString::fromStdString(user.getState());
            item->setText(2, stateText);
            qDebug() << "[CRITICAL] Added friend with state:" << friendName << "State:" << stateText;
        } catch (...) {
            // 如果getState()方法不存在，忽略状态设置
            qDebug() << "[CRITICAL] Added friend (no state available):" << friendName;
        }
        
        qDebug() << "[CRITICAL] Added friend to UI list:" << friendName;
    }
    
    // 展开好友节点
    friendRoot->setExpanded(true);
    
    // 刷新UI
    contactTreeWidget->update();
    contactTreeWidget->repaint();
    
    // 标记好友列表已加载
    friendListLoaded = true;
    contactTreeWidget->repaint();
    qDebug() << "[CRITICAL] Friend list UI updated, expanded and repainted";
    
    // 处理存储的未处理消息
    if (!pendingMessages.isEmpty()) {
        qDebug() << "ChatWindow: onFriendListUpdated - Processing stored pending messages, count:" << pendingMessages.size();
        // 临时存储消息列表，避免在处理过程中修改原列表
        QList<PendingMessage> messagesToProcess = pendingMessages;
        pendingMessages.clear();
        
        for (const PendingMessage &msg : messagesToProcess) {
            qDebug() << "ChatWindow: onFriendListUpdated - Processing pending message from" << msg.fromId;
            // 重新处理消息，此时friendMap已加载
            onReceiveMessage(msg.fromId, msg.message, msg.fromName, msg.isGroup, msg.groupId, msg.timestamp);
        }
        qDebug() << "ChatWindow: onFriendListUpdated - Finished processing pending messages";
    }
}

void ChatWindow::onGroupListUpdated(const QList<Group> &groups) {
    qDebug() << "[CRITICAL] Received group list update, count:" << groups.size();
    
    // 确保contactTreeWidget已初始化
    if (!contactTreeWidget) {
        qDebug() << "[ERROR] contactTreeWidget is null";
        return;
    }
    
    // 打印收到的每个群组信息
    for (const Group &group : groups) {
        qDebug() << "[CRITICAL] Group - ID:" << group.getId() << "Name:" << QString::fromStdString(group.getName())
                 << "Desc:" << QString::fromStdString(group.getDesc());
    }
    
    // 确保groupRoot有效，如果无效则尝试查找或创建
    if (!groupRoot) {
        qDebug() << "[ERROR] groupRoot is null, attempting to find or create";
        // 尝试从contactTreeWidget中查找群组根节点
        for (int i = 0; i < contactTreeWidget->topLevelItemCount(); ++i) {
            QTreeWidgetItem *item = contactTreeWidget->topLevelItem(i);
            if (item->text(1) == "群组") {
                groupRoot = item;
                break;
            }
        }
        
        // 如果仍然没有找到，创建一个新的
        if (!groupRoot) {
            qDebug() << "[DEBUG] Creating new group root item";
            groupRoot = new QTreeWidgetItem(contactTreeWidget);
            groupRoot->setText(1, "群组"); // 在联系人列显示标题
            groupRoot->setFirstColumnSpanned(true); // 跨列显示
            contactTreeWidget->addTopLevelItem(groupRoot);
        }
    }
    
    // 清空群组列表
    groupRoot->takeChildren();

    // 更新群组数据和列表
    groupMap.clear();
    for (const Group &group : groups) {
        groupMap[group.getId()] = group;
        QTreeWidgetItem *item = new QTreeWidgetItem(groupRoot);
        QString groupName = QString::fromStdString(group.getName());
        
        // 设置群组名称和ID
        item->setText(1, groupName + " (" + QString::number(group.getId()) + ")");
        item->setData(1, Qt::UserRole, group.getId());
        
        // 显示默认群组图标
        // 创建一个带有群组图标的圆形头像
        QPixmap groupPixmap(40, 40);
        groupPixmap.fill(Qt::transparent);
        
        QPainter painter(&groupPixmap);
        painter.setRenderHint(QPainter::Antialiasing, true);
        
        // 绘制蓝色圆形背景
        QBrush brush(QColor(46, 204, 113)); // #2ecc71
        painter.setBrush(brush);
        painter.setPen(Qt::NoPen);
        painter.drawEllipse(0, 0, 40, 40);
        
        // 绘制白色文字 "G" 表示群组
        QFont font("Arial", 16, QFont::Bold);
        painter.setFont(font);
        painter.setPen(QColor(Qt::white));
        painter.drawText(groupPixmap.rect(), Qt::AlignCenter, "G");
        
        item->setIcon(0, QIcon(groupPixmap));
        
        // 不尝试获取群组成员数，避免const和方法不存在的错误
        item->setText(2, "群组成员");
        qDebug() << "[CRITICAL] Added group:" << groupName << "(group member count skipped for compatibility)";
        
        qDebug() << "[CRITICAL] Added group to UI list:" << groupName;
    }
    
    // 展开群组节点
    groupRoot->setExpanded(true);
    
    // 刷新UI
    contactTreeWidget->update();
    contactTreeWidget->repaint();
    qDebug() << "[CRITICAL] Group list UI updated, expanded and repainted";
}

void ChatWindow::onAddFriendResponse(bool success, const QString &message) {
    if (success) {
        QMessageBox::information(this, "成功", "添加好友成功");
        // 重新获取好友列表
        chatClient->requestFriendList(userId);
    } else {
        QMessageBox::warning(this, "失败", message);
    }
}

// 处理好友状态更新
void ChatWindow::onFriendStateUpdated(qint64 userId, const QString &state) {
    qDebug() << "Friend state updated: userId=" << userId << "state=" << state;
    
    // 确保contactTreeWidget和friendRoot已初始化
    if (!contactTreeWidget || !friendRoot) {
        qDebug() << "contactTreeWidget or friendRoot is null, cannot update friend state";
        return;
    }
    
    // 遍历好友列表，查找ID匹配的好友项
    for (int i = 0; i < friendRoot->childCount(); ++i) {
        QTreeWidgetItem *item = friendRoot->child(i);
        if (!item) continue;
        
        // 获取好友ID
        qint64 friendId = item->data(1, Qt::UserRole).toLongLong();
        
        if (friendId == userId) {
            // 更新好友状态
            item->setText(2, state);
            qDebug() << "Updated friend" << friendId << "state to" << state;
            
            // 刷新UI
            contactTreeWidget->update();
            contactTreeWidget->repaint();
            break;
        }
    }
}

void ChatWindow::onAddGroupResponse(bool success, const QString &message) {
    if (success) {
        QMessageBox::information(this, "成功", "加入群组成功！");
        // 重新请求群组列表
        chatClient->requestGroupList(userId);
    } else {
        QMessageBox::warning(this, "失败", message);
    }
}

void ChatWindow::onCreateGroupResponse(bool success, const QString &message) {
    if (success) {
        QMessageBox::information(this, "成功", "创建群组成功！");
        // 重新请求群组列表
        chatClient->requestGroupList(userId);
    } else {
        QMessageBox::warning(this, "失败", message);
    }
}

void ChatWindow::onLoginResponse(bool success, const QString &response) {
    // 首先检查是否已经处理过登录响应，防止重复处理
    if (loginHandled) {
        qDebug() << "[CRITICAL] ChatWindow::onLoginResponse - Already handled login response, ignoring duplicate call";
        return;
    }
    
    // 设置标志为已处理，防止后续重复处理
    loginHandled = true;
    
    qDebug() << "[DEBUG] ChatWindow received login response:" << success;
    qDebug() << "[DEBUG] Response message:" << response;
    
    if (success) {
        // 登录成功后立即请求好友列表和群组列表
        qDebug() << "[DEBUG] Login successful, user ID:" << userId << "Name:" << userName;
        
        // 直接发送请求，不需要定时器延迟，确保及时获取数据
        qDebug() << "[DEBUG] Requesting friend list for user ID:" << userId;
        chatClient->requestFriendList(userId);
        
        qDebug() << "[DEBUG] Requesting group list for user ID:" << userId;
        chatClient->requestGroupList(userId);
        
        // 添加3秒后再次请求，确保即使初始请求失败也能获取到数据
        QTimer::singleShot(3000, this, [this]() {
            qDebug() << "[DEBUG] Retry requesting friend list for user ID:" << userId;
            chatClient->requestFriendList(userId);
        });
        
    }
}

void ChatWindow::onConnected() {
    qDebug() << "ChatWindow connected to server";
    // 可以在这里添加连接成功的处理逻辑
}

void ChatWindow::onDisconnected() {
    qDebug() << "ChatWindow disconnected from server";
    
    // If we're actively logging out, don't show the message box or close the window
    // The logout signal will handle the cleanup and transition to login page
    if (isLoggingOut) {
        qDebug() << "ChatWindow: Disconnection during logout, skipping message box and close";
        return;
    }
    
    // For unexpected disconnections, show message and close
    QMessageBox::warning(this, "连接断开", "与服务器的连接已断开，请重新登录");
    close();
}

void ChatWindow::onLogout() {
    // Mark as logging out to prevent onDisconnected from interfering
    isLoggingOut = true;
    
    qDebug() << "[CRITICAL] ChatWindow::onLogout() started";
    
    // Send logout message to server
    chatClient->logout(userId);
    
    // Emit logout signal to trigger main.cpp cleanup
    qDebug() << "[CRITICAL] Emitting logout signal";
    emit logout();
    
    // Disconnect signals from chatClient to prevent race conditions
    // Only disconnect signals from chatClient, not the logout signal
    disconnect(chatClient, nullptr, this, nullptr);
    
    qDebug() << "[CRITICAL] ChatWindow::onLogout() completed";
    
    // Function returns here, main.cpp will handle the rest
}

void ChatWindow::showContextMenu(const QPoint &pos) {
    QTreeWidgetItem *item = contactTreeWidget->itemAt(pos);
    if (!item) return;

    QMenu *menu = new QMenu(this);
    
    if (item->parent() && item->parent()->text(0) == "好友") {
        QAction *sendMessageAction = menu->addAction("发送消息");
        QAction *sendFileAction = menu->addAction("发送文件");
        connect(sendMessageAction, &QAction::triggered, this, &ChatWindow::onContactSelected);
        connect(sendFileAction, &QAction::triggered, this, [=]() {
            // 先选中该好友，然后触发发送文件
            contactTreeWidget->setCurrentItem(item);
            onSendFile();
        });
    }
    
    if (item->text(0) == "好友") {
        QAction *addFriendAction = menu->addAction("添加好友");
        connect(addFriendAction, &QAction::triggered, this, &ChatWindow::onAddFriend);
    }
    
    if (item->text(0) == "群组") {
        QAction *createGroupAction = menu->addAction("创建群组");
        QAction *joinGroupAction = menu->addAction("加入群组");
        connect(createGroupAction, &QAction::triggered, this, &ChatWindow::onCreateGroup);
        connect(joinGroupAction, &QAction::triggered, this, &ChatWindow::onJoinGroup);
    }
    
    menu->popup(contactTreeWidget->viewport()->mapToGlobal(pos));
}

void ChatWindow::closeEvent(QCloseEvent *event) {
    if (isLoggingOut) {
        // If we're already logging out, just accept the close event
        event->accept();
        return;
    }
    
    if (QMessageBox::question(this, "确认退出", "确定要退出吗？") == QMessageBox::Yes) {
        chatClient->logout(userId);
        // 清理文件传输相关资源
        for (auto it = receivingFiles.begin(); it != receivingFiles.end(); ++it) {
            if (it.value()) {
                it.value()->close();
                delete it.value();
            }
        }
        receivingFiles.clear();
        
        for (auto it = fileProgressDialogs.begin(); it != fileProgressDialogs.end(); ++it) {
            if (it.value()) {
                delete it.value();
            }
        }
        fileProgressDialogs.clear();
        
        event->accept();
    } else {
        event->ignore();
    }
}

// 发送图片
void ChatWindow::onSendImage() {
    // 检查当前是否有选中的好友
    QWidget *currentWidget = chatTabWidget->currentWidget();
    if (!currentWidget) {
        QMessageBox::warning(this, "警告", "请先选择一个好友进行聊天");
        return;
    }
    
    int chatId = currentWidget->property("chatId").toInt();
    bool isGroup = currentWidget->property("isGroup").toBool();
    
    if (isGroup) {
        QMessageBox::warning(this, "警告", "暂不支持向群组发送图片");
        return;
    }
    
    // 选择图片文件，支持更多格式
    QString imagePath = QFileDialog::getOpenFileName(
        this, 
        "选择要发送的图片", 
        "", 
        "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.tif *.webp *.svg *.ppm *.pgm *.pbm *.xpm *.ico);;所有文件 (*.*)"
    );
    
    if (imagePath.isEmpty()) {
        return;
    }
    
    // 读取图片并转换为Base64编码
    QFile imageFile(imagePath);
    if (!imageFile.open(QIODevice::ReadOnly)) {
        QMessageBox::warning(this, "错误", "无法打开图片文件");
        return;
    }
    
    QByteArray imageData = imageFile.readAll();
    imageFile.close();
    
    // 获取图片类型
    QFileInfo fileInfo(imagePath);
    QString imageType = fileInfo.suffix().toLower();
    
    // 优化：对图片进行压缩，减小Base64编码后的大小
    QImage image;
    
    // 确保图片正确加载
    bool loaded = false;
    
    // 简化图片加载逻辑，直接使用QImage.loadFromData
    // 这是最可靠的方式，能处理所有Qt支持的格式
    loaded = image.loadFromData(imageData);
    
    // 检查图片是否加载成功
    if (!loaded || image.isNull()) {
        // 显示支持的图片格式，帮助用户了解支持的格式
        QList<QByteArray> supportedFormats = QImageReader::supportedImageFormats();
        QString supportedFormatsStr;
        for (const QByteArray &format : supportedFormats) {
            supportedFormatsStr += QString(format) + " ";
        }
        
        qDebug() << "[DEBUG] Supported image formats:" << supportedFormatsStr;
        qDebug() << "[DEBUG] Image type:" << imageType;
        qDebug() << "[DEBUG] Image data size:" << imageData.size();
        
        QMessageBox::warning(this, "警告", QString("图片加载失败\n不支持的图片格式或文件损坏: %1\n\n当前系统支持的图片格式: %2").arg(imageType).arg(supportedFormatsStr));
        return;
    }
    
    // 如果图片太大，进行缩放
    if (image.width() > 300 || image.height() > 300) {
        image = image.scaled(300, 300, Qt::KeepAspectRatio, Qt::SmoothTransformation);
    }
    
    // 压缩图片质量，减小文件大小
    QByteArray compressedData;
    QBuffer buffer(&compressedData);
    buffer.open(QIODevice::WriteOnly);
    
    // 将所有格式统一转换为PNG格式，确保HTML支持
    QString saveFormat = "PNG"; // 统一转换为PNG格式
    bool saveSuccess = image.save(&buffer, saveFormat.toLatin1());
    buffer.close();
    
    // 检查图片保存是否成功
    if (!saveSuccess || compressedData.isEmpty()) {
        QMessageBox::warning(this, "警告", "图片压缩失败，请尝试发送其他图片");
        return;
    }
    
    // 更新imageType为实际保存的格式
    imageType = "png";
    
    // 重要：将image对象更新为转换后的PNG图片
    QImage pngImage;
    pngImage.loadFromData(compressedData);
    image = pngImage;
    
    // 检查转换后的PNG图片是否有效
    if (image.isNull()) {
        QMessageBox::warning(this, "警告", "图片格式转换失败，请尝试发送其他图片");
        return;
    }
    
    // 构造图片消息格式: [IMAGE]imageType,base64data
    // 确保使用转换后的png类型
    QString imageMessage = QString("[IMAGE]%1,%2").arg(imageType).arg(QString(compressedData.toBase64()));
    
    // 进一步优化：将Base64编码后的大小限制为1MB，确保JSON能被服务器处理
    const qint64 MAX_BASE64_SIZE = 1024 * 1024; // 1MB
    
    // 如果Base64编码后大小超过1MB，尝试进一步压缩
    if (imageMessage.size() > MAX_BASE64_SIZE) {
        // 尝试将质量降低到50%，进一步压缩
        QByteArray moreCompressedData;
        QBuffer moreCompressedBuffer(&moreCompressedData);
        moreCompressedBuffer.open(QIODevice::WriteOnly);
        
        int lowerQuality = 50;
        
        // 由于已经转换为PNG格式，直接使用PNG压缩逻辑
        // PNG格式不支持质量参数，尝试缩放图片
        QImage scaledImage = image.scaled(
            image.width() * 0.8, 
            image.height() * 0.8, 
            Qt::KeepAspectRatio, 
            Qt::SmoothTransformation
        );
        scaledImage.save(&moreCompressedBuffer, "PNG");
        
        moreCompressedBuffer.close();
        
        // 重新生成Base64编码
        QString moreCompressedImageMessage = QString("[IMAGE]%1,%2").arg(imageType).arg(QString(moreCompressedData.toBase64()));
        
        // 如果仍然超过大小限制，拒绝发送
        if (moreCompressedImageMessage.size() > MAX_BASE64_SIZE) {
            QMessageBox::warning(this, "错误", "图片过大，无法发送");
            return;
        }
        
        // 使用更压缩的图片
        imageMessage = moreCompressedImageMessage;
        compressedData = moreCompressedData;
    }
    
    // 显示自己发送的图片，使用压缩后的图片数据
    QListWidget *chatListWidget = chatComponents[currentWidget].chatListWidget;
    QString timeStr = QDateTime::currentDateTime().toString("hh:mm:ss");

    // 显示自己发送的消息 - 使用聊天气泡
    // 使用自己的头像
    QString myAvatarPath = ":/icons/user.png"; // 默认头像
    // 尝试从当前用户头像数据中获取
    qDebug() << "ChatWindow: onSendImage - currentUserAvatarData length:" << currentUserAvatarData.length();
    if (!currentUserAvatarData.isEmpty()) {
        // 头像数据存在，使用它
        qDebug() << "ChatWindow: onSendImage - Avatar data exists, processing...";
        
        // 检查Base64数据的有效性
        QByteArray base64Bytes = currentUserAvatarData.toUtf8();
        qDebug() << "ChatWindow: onSendImage - Base64 data length:" << base64Bytes.length();
        qDebug() << "ChatWindow: onSendImage - Base64 data preview:" << currentUserAvatarData.left(50) << "...";
        
        // 移除可能的空白字符
        QString cleanBase64 = currentUserAvatarData.trimmed();
        qDebug() << "ChatWindow: onSendImage - Clean Base64 length:" << cleanBase64.length();
        
        // 尝试解码
        QByteArray decodedData = QByteArray::fromBase64(cleanBase64.toUtf8());
        qDebug() << "ChatWindow: onSendImage - Decoded data length:" << decodedData.length();
        
        // 检查解码后的数据是否为空
        if (decodedData.isEmpty()) {
            qDebug() << "ChatWindow: onSendImage - Decoded data is empty!";
        } else {
            // 检查解码后的数据的前几个字节，了解文件格式
            if (decodedData.size() >= 4) {
                qDebug() << "ChatWindow: onSendImage - First 4 bytes of decoded data:" 
                         << QString::asprintf("%02X %02X %02X %02X", 
                                             (unsigned char)decodedData[0],
                                             (unsigned char)decodedData[1],
                                             (unsigned char)decodedData[2],
                                             (unsigned char)decodedData[3]);
                
                // 检查是否仍然是Base64编码的数据
                // 常见的Base64编码JPEG开头是 "/9j/"
                if (decodedData.size() >= 4 && decodedData[0] == '/' && decodedData[1] == '9' && decodedData[2] == 'j' && decodedData[3] == '/') {
                    qDebug() << "ChatWindow: onSendImage - Decoded data is still Base64 encoded, decoding again...";
                    // 再次解码
                    QByteArray doubleDecoded = QByteArray::fromBase64(decodedData);
                    qDebug() << "ChatWindow: onSendImage - Double decoded data length:" << doubleDecoded.length();
                    if (!doubleDecoded.isEmpty()) {
                        decodedData = doubleDecoded;
                    }
                }
            }
            
            // 尝试检测图片格式或使用常见格式
            QPixmap avatarPixmap;
            bool loadSuccess = false;
            loadSuccess = avatarPixmap.loadFromData(decodedData);
            if (!loadSuccess) {
                // 如果自动检测失败，尝试常见的图片格式
                qDebug() << "ChatWindow: onSendImage - Auto-detect failed, trying PNG...";
                loadSuccess = avatarPixmap.loadFromData(decodedData, "PNG");
            }
            if (!loadSuccess) {
                qDebug() << "ChatWindow: onSendImage - PNG failed, trying JPEG...";
                loadSuccess = avatarPixmap.loadFromData(decodedData, "JPEG");
            }
            if (!loadSuccess) {
                qDebug() << "ChatWindow: onSendImage - JPEG failed, trying BMP...";
                loadSuccess = avatarPixmap.loadFromData(decodedData, "BMP");
            }
            
            qDebug() << "ChatWindow: onSendImage - Avatar load success:" << loadSuccess << "Pixmap is null:" << avatarPixmap.isNull();
            
            // 如果所有格式都尝试失败，记录错误并使用默认头像
            if (!loadSuccess || avatarPixmap.isNull()) {
                qDebug() << "ChatWindow: onSendImage - Failed to load avatar from data, using default";
            } else {
                // 头像加载成功，保存到临时文件
                QString tempAvatarPath = QCoreApplication::applicationDirPath() + "/temp_avatar_current.png";
                if (avatarPixmap.save(tempAvatarPath)) {
                    myAvatarPath = tempAvatarPath;
                    qDebug() << "ChatWindow: onSendImage - Avatar saved to temp file:" << tempAvatarPath;
                }
            }
        }
    } else {
        qDebug() << "ChatWindow: onSendImage - No avatar data available, using default";
    }
    qDebug() << "ChatWindow: onSendImage - Final avatar path:" << myAvatarPath;
    addMessageToChatList(chatListWidget, true, imageMessage, myAvatarPath, timeStr);

    // 发送图片消息 - 确保Base64编码数据在JSON中被正确处理
    // 这里不需要特殊处理，因为QJsonDocument::toJson会自动处理特殊字符
    chatClient->sendMessage(chatId, imageMessage);
}

// 发送表情包
void ChatWindow::onSendEmoji() {
    // 检查当前是否有选中的好友
    QWidget *currentWidget = chatTabWidget->currentWidget();
    if (!currentWidget) {
        QMessageBox::warning(this, "警告", "请先选择一个好友进行聊天");
        return;
    }
    
    // 设置加载状态
    isLoadingEmojis = true;
    
    // 请求最新的表情包列表
    chatClient->requestEmojiList(userId);
    
    // 显示加载提示
    statusBarLabel->setText("正在加载表情包...");
    
    // 直接显示表情包对话框，不使用模态加载对话框
    // 表情包对话框会在onEmojiListUpdated中延迟显示
}

// 显示表情包对话框
void ChatWindow::showEmojiDialog() {
    // 检查当前是否有选中的好友
    QWidget *currentWidget = chatTabWidget->currentWidget();
    if (!currentWidget) {
        return;
    }
    
    int chatId = currentWidget->property("chatId").toInt();
    bool isGroup = currentWidget->property("isGroup").toBool();
    
    // 创建表情包选择对话框
    QDialog *emojiDialog = new QDialog(this);
    emojiDialog->setWindowTitle("选择表情包");
    emojiDialog->setFixedSize(400, 300);
    
    QVBoxLayout *mainLayout = new QVBoxLayout;
    mainLayout->setContentsMargins(10, 10, 10, 10);
    mainLayout->setSpacing(10);
    
    // 表情包显示区域
    QWidget *emojiContainer = new QWidget;
    QGridLayout *emojiLayout = new QGridLayout;
    emojiLayout->setContentsMargins(0, 0, 0, 0);
    emojiLayout->setSpacing(5);
    
    // 显示用户上传的图片表情
    qDebug() << "Opening emoji dialog, emojiList size:" << emojiList.size();
    int index = 0;
    for (auto it = emojiList.constBegin(); it != emojiList.constEnd(); ++it) {
        int emojiId = it.key();
        const QByteArray &imageBytes = it.value();
        
        qDebug() << "Processing emoji:" << emojiId << "image size:" << imageBytes.size();
        
        // 创建表情按钮
        QPushButton *emojiBtn = new QPushButton;
        emojiBtn->setFixedSize(60, 60);
        emojiBtn->setStyleSheet(
            "QPushButton { background-color: #f0f0f0; border: 1px solid #ddd; border-radius: 4px; }"
            "QPushButton:hover { background-color: #e0e0e0; }"
            "QPushButton:pressed { background-color: #d0d0d0; }"
        );
        
        // 加载图片到按钮
        QPixmap pixmap;
        if (pixmap.loadFromData(imageBytes)) {
            // 缩放图片以适应按钮大小
            QPixmap scaledPixmap = pixmap.scaled(50, 50, Qt::KeepAspectRatio, Qt::SmoothTransformation);
            emojiBtn->setIcon(QIcon(scaledPixmap));
            emojiBtn->setIconSize(QSize(50, 50));
            qDebug() << "Successfully loaded image for emoji:" << emojiId;
        } else {
            qDebug() << "Failed to load image for emoji:" << emojiId;
            // 如果图片加载失败，显示表情ID
            emojiBtn->setText(QString::number(emojiId));
        }
        
        // 连接表情包按钮信号
connect(emojiBtn, &QPushButton::clicked, this, [=]() {
    // 显示自己发送的表情
    QListWidget *chatListWidget = chatComponents[currentWidget].chatListWidget;
    QString timeStr = QDateTime::currentDateTime().toString("hh:mm:ss");
    
    // 显示自己发送的消息 - 使用聊天气泡
    QString emojiMsg = QString("[EMOJI_DATA:%1]").arg(QString::fromLatin1(emojiList[emojiId].toBase64()));
    // 使用自己的头像
    QString myAvatarPath = ":/icons/user.png"; // 默认头像
    // 尝试从当前用户头像数据中获取
    if (!currentUserAvatarData.isEmpty()) {
        // 头像数据存在，使用它
        QByteArray decodedData;
        QPixmap avatarPixmap;
        bool loadSuccess = false;
        
        // 检查是Data URL还是纯Base64编码数据
        if (currentUserAvatarData.startsWith("data:image/")) {
            // Data URL格式：data:image/png;base64,...
            int commaPos = currentUserAvatarData.indexOf(',');
            if (commaPos != -1) {
                QString base64Data = currentUserAvatarData.mid(commaPos + 1);
                decodedData = QByteArray::fromBase64(base64Data.toUtf8());
                
                // 尝试检测图片格式或使用常见格式
                loadSuccess = avatarPixmap.loadFromData(decodedData);
                if (!loadSuccess) {
                    // 如果自动检测失败，尝试常见的图片格式
                    loadSuccess = avatarPixmap.loadFromData(decodedData, "PNG");
                }
                if (!loadSuccess) {
                    loadSuccess = avatarPixmap.loadFromData(decodedData, "JPEG");
                }
                if (!loadSuccess) {
                    loadSuccess = avatarPixmap.loadFromData(decodedData, "BMP");
                }
            }
        } else {
            // 纯Base64编码数据
            decodedData = QByteArray::fromBase64(currentUserAvatarData.toUtf8());
            
            // 尝试检测图片格式或使用常见格式
            loadSuccess = avatarPixmap.loadFromData(decodedData);
            if (!loadSuccess) {
                // 如果自动检测失败，尝试常见的图片格式
                loadSuccess = avatarPixmap.loadFromData(decodedData, "PNG");
            }
            if (!loadSuccess) {
                loadSuccess = avatarPixmap.loadFromData(decodedData, "JPEG");
            }
            if (!loadSuccess) {
                loadSuccess = avatarPixmap.loadFromData(decodedData, "BMP");
            }
        }
        
        if (loadSuccess) {
            // 头像加载成功，保存到临时文件
            QString tempAvatarPath = QCoreApplication::applicationDirPath() + "/temp_avatar_current.png";
            if (avatarPixmap.save(tempAvatarPath)) {
                myAvatarPath = tempAvatarPath;
            }
        }
    }
    addMessageToChatList(chatListWidget, true, emojiMsg, myAvatarPath, timeStr);
    
    // 发送表情消息 - 直接包含图片数据
    QByteArray imageBytes = emojiList[emojiId];
    QString base64Image = QString::fromLatin1(imageBytes.toBase64());
    QString emojiMsgFull = QString("[EMOJI_DATA:%1]").arg(base64Image);
    if (isGroup) {
        chatClient->sendGroupMessage(chatId, emojiMsgFull);
    } else {
        chatClient->sendMessage(chatId, emojiMsgFull);
    }
    
    // 关闭对话框
    emojiDialog->accept();
});
        
        // 添加到网格布局
        int row = index / 5;
        int col = index % 5;
        emojiLayout->addWidget(emojiBtn, row, col);
        
        index++;
    }
    
    // 如果没有用户上传的表情，显示提示信息
    if (emojiList.isEmpty()) {
        QLabel *noEmojiLabel = new QLabel("暂无表情包，点击下方上传按钮添加");
        noEmojiLabel->setAlignment(Qt::AlignCenter);
        emojiLayout->addWidget(noEmojiLabel, 0, 0, 1, 5);
    }
    
    emojiContainer->setLayout(emojiLayout);
    
    // 添加滚动区域
    QScrollArea *scrollArea = new QScrollArea;
    scrollArea->setWidget(emojiContainer);
    scrollArea->setWidgetResizable(true);
    scrollArea->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    scrollArea->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    
    mainLayout->addWidget(scrollArea);
    
    // 底部按钮
    QHBoxLayout *buttonLayout = new QHBoxLayout;
    buttonLayout->setAlignment(Qt::AlignRight);
    buttonLayout->setSpacing(10);
    
    // 上传表情包按钮
    QPushButton *uploadBtn = new QPushButton("上传表情");
    uploadBtn->setFixedWidth(80);
    connect(uploadBtn, &QPushButton::clicked, this, [=]() {
        // 选择图片文件
        QString imagePath = QFileDialog::getOpenFileName(
            this, 
            "选择表情包图片", 
            "", 
            "图片文件 (*.png *.jpg *.jpeg *.gif *.bmp);;所有文件 (*.*)"
        );
        
        if (!imagePath.isEmpty()) {
            // 读取图片文件
            QFile imageFile(imagePath);
            if (imageFile.open(QIODevice::ReadOnly)) {
                QByteArray imageData = imageFile.readAll();
                imageFile.close();
                
                // 压缩图片大小，限制在100KB以内
                QImage image;
                if (image.loadFromData(imageData)) {
                    // 缩放图片，最大边长不超过200像素
                    if (image.width() > 200 || image.height() > 200) {
                        image = image.scaled(200, 200, Qt::KeepAspectRatio, Qt::SmoothTransformation);
                    }
                    
                    // 保存为PNG格式
                    QByteArray compressedData;
                    QBuffer buffer(&compressedData);
                    buffer.open(QIODevice::WriteOnly);
                    image.save(&buffer, "PNG");
                    buffer.close();
                    
                    // Base64编码
                    QString base64Image = QString::fromLatin1(compressedData.toBase64());
                    
                    // 获取表情名称（使用文件名，不含扩展名）
                    QFileInfo fileInfo(imagePath);
                    QString emojiName = fileInfo.baseName();
                    
                    // 上传表情包到服务器
                    chatClient->uploadEmoji(userId, emojiName, base64Image);
                    
                    QMessageBox::information(this, "成功", "表情包上传请求已发送");
                }
            }
        }
    });
    
    QPushButton *closeBtn = new QPushButton("关闭");
    closeBtn->setFixedWidth(80);
    connect(closeBtn, &QPushButton::clicked, emojiDialog, &QDialog::reject);
    
    buttonLayout->addWidget(uploadBtn);
    buttonLayout->addWidget(closeBtn);
    mainLayout->addLayout(buttonLayout);
    
    emojiDialog->setLayout(mainLayout);
    emojiDialog->exec();
}

// 表情包列表更新
void ChatWindow::onEmojiListUpdated(const QList<QJsonObject> &emojis) {
    // 清空现有表情包列表
    emojiList.clear();
    
    qDebug() << "Received emoji list with" << emojis.size() << "emojis from server";
    
    // 遍历接收到的表情包列表
    for (const QJsonObject &emojiObj : emojis) {
        qDebug() << "Processing emoji object:" << emojiObj;
        
        // 检查是否包含必要字段
        if (emojiObj.contains("id") && emojiObj.contains("imageData")) {
            int emojiId = emojiObj["id"].toInt();
            QString imageData = emojiObj["imageData"].toString();
            
            qDebug() << "Emoji" << emojiId << "imageData size:" << imageData.size();
            
            // 将Base64编码的图片数据转换为QByteArray
            QByteArray imageBytes = QByteArray::fromBase64(imageData.toLatin1());
            
            if (!imageBytes.isEmpty()) {
                // 存储到表情包列表
                emojiList[emojiId] = imageBytes;
                qDebug() << "Added emoji" << emojiId << "to list, image size:" << imageBytes.size();
            } else {
                qDebug() << "Failed to decode image data for emoji" << emojiId;
            }
        } else {
            qDebug() << "Emoji object missing required fields";
        }
    }
    
    qDebug() << "Updated emoji list with" << emojiList.size() << "emojis";
    
    // 清除加载提示
    statusBarLabel->setText("表情包加载完成");
    
    // 暂时注释掉重新渲染聊天窗口的代码，因为我们已经改为使用聊天气泡系统
    /*
    // 重新渲染所有聊天窗口中的表情消息
    for (int i = 0; i < chatTabWidget->count(); ++i) {
        QWidget *chatWidget = chatTabWidget->widget(i);
        if (chatComponents.contains(chatWidget)) {
            QTextEdit *chatEdit = chatComponents[chatWidget].chatEdit;
            
            // 获取当前聊天内容
            QString content = chatEdit->toHtml();
            
            // 替换所有[EMOJI:id]和[表情:id]为图片
            QRegularExpression regex("\\[EMOJI:(\\d+)\\]|\\[表情:(\\d+)\\]");
            QRegularExpressionMatchIterator matchIterator = regex.globalMatch(content);
            
            // 从后往前替换，避免索引偏移
            QString newContent = content;
            int offset = 0;
            QList<QPair<int, int>> matches;
            QList<int> emojiIds;
            
            // 先收集所有匹配项
            while (matchIterator.hasNext()) {
                QRegularExpressionMatch match = matchIterator.next();
                int startPos = match.capturedStart() - offset;
                int endPos = match.capturedEnd() - offset;
                int emojiId = match.captured(1).toInt();
                if (emojiId == 0) {
                    emojiId = match.captured(2).toInt();
                }
                
                matches.append(qMakePair(startPos, endPos));
                emojiIds.append(emojiId);
            }
            
            // 从后往前替换
            for (int j = matches.size() - 1; j >= 0; --j) {
                int startPos = matches[j].first;
                int endPos = matches[j].second;
                int emojiId = emojiIds[j];
                
                if (emojiList.contains(emojiId)) {
                    QByteArray imageBytes = emojiList[emojiId];
                    if (!imageBytes.isEmpty()) {
                        QString base64Image = QString::fromLatin1(imageBytes.toBase64());
                        QString htmlImage = QString("<img src='data:image/png;base64,%1' style='width:80px;height:80px;vertical-align:middle;'>").arg(base64Image);
                        newContent.replace(startPos, endPos - startPos, htmlImage);
                    }
                }
            }
            
            // 更新聊天内容
            if (newContent != content) {
                chatEdit->setHtml(newContent);
            }
        }
    }
    */
    
    // 如果正在加载表情包，显示表情包对话框
    if (isLoadingEmojis) {
        // 重置加载状态
        isLoadingEmojis = false;
        
        // 延迟显示表情包对话框，确保事件循环正常运行
        QTimer::singleShot(100, this, &ChatWindow::showEmojiDialog);
    }
}

// 发送文件
void ChatWindow::onSendFile() {
    // 检查当前是否有选中的好友
    QWidget *currentWidget = chatTabWidget->currentWidget();
    if (!currentWidget) {
        QMessageBox::warning(this, "警告", "请先选择一个好友进行聊天");
        return;
    }
    
    int chatId = currentWidget->property("chatId").toInt();
    bool isGroup = currentWidget->property("isGroup").toBool();
    
    if (isGroup) {
        QMessageBox::warning(this, "警告", "暂不支持向群组发送文件");
        return;
    }
    
    // 选择文件
    QString filename = QFileDialog::getOpenFileName(this, "选择要发送的文件");
    if (filename.isEmpty()) {
        return;
    }
    
    // 获取文件信息
    QFileInfo fileInfo(filename);
    qint64 filesize = fileInfo.size();
    
    QString displayName = fileInfo.fileName();
    
    // 获取对方名称
    QString chatName = getUserNameById(chatId);
    
    // 显示确认对话框
    if (QMessageBox::question(this, "确认发送", 
                      QString("确定要将文件 '%1' (%2 KB) 发送给 %3 吗?")
                      .arg(fileInfo.fileName())
                      .arg(filesize / 1024.0, 0, 'f', 1)
                      .arg(chatName)) != QMessageBox::Yes) {
        return;
    }
    
    // 创建进度对话框
    QProgressDialog *progressDialog = new QProgressDialog(this);
    progressDialog->setWindowTitle("文件传输");
    progressDialog->setLabelText(QString("正在发送 '%1'...").arg(fileInfo.fileName()));
    progressDialog->setRange(0, filesize);
    progressDialog->setCancelButtonText("取消");
    progressDialog->setModal(true);
    
    // 保存文件传输信息
    FileTransferInfo info;
    info.filename = fileInfo.fileName();
    info.filePath = filename; // 保存完整文件路径
    info.filesize = filesize;
    info.senderId = userId;
    info.receiverId = chatId;
    info.isSending = true;
    info.isCompleted = false;
    
    // 生成fileId
    QString fileId = chatClient->generateFileId();
    fileTransferInfo[fileId] = info;
    fileProgressDialogs[fileId] = progressDialog;
    
    // 发送文件传输请求，使用生成的fileId
    chatClient->sendFileRequest(userId, chatId, fileInfo.fileName(), filesize, fileId);
}

// 处理收到的文件传输请求
void ChatWindow::onFileTransferRequestReceived(int fromId, const QString &filename, qint64 filesize, const QString &fileId) {
    QString senderName = getUserNameById(fromId);
    
    // 显示接收确认对话框
    QString message = QString("好友 '%1' 想要发送文件 '%2' (%3 KB)，是否接收？")
                      .arg(senderName)
                      .arg(filename)
                      .arg(filesize / 1024.0, 0, 'f', 1);
    
    int result = QMessageBox::question(this, "接收文件", message, 
                                      QMessageBox::Yes | QMessageBox::No);
    
    if (result == QMessageBox::Yes) {
        // 选择保存位置
        QString savePath = QFileDialog::getSaveFileName(this, "保存文件", filename);
        if (savePath.isEmpty()) {
            chatClient->acceptFileTransfer(userId, fromId, fileId, false);
            return;
        }
        
        // 打开文件准备写入
        QFile *file = new QFile(savePath);
        if (!file->open(QIODevice::WriteOnly)) {
            QMessageBox::warning(this, "错误", "无法打开文件进行写入");
            chatClient->acceptFileTransfer(userId, fromId, fileId, false);
            delete file;
            return;
        }
        
        // 创建进度对话框
        QProgressDialog *progressDialog = new QProgressDialog(this);
        progressDialog->setWindowTitle("文件接收中");
        progressDialog->setLabelText(QString("正在接收 '%1'...").arg(filename));
        progressDialog->setRange(0, filesize);
        progressDialog->setModal(true);
        
        // 记录文件传输信息
        FileTransferInfo info;
        info.filename = filename;
        info.filesize = filesize;
        info.senderId = fromId;
        info.receiverId = userId;
        info.isSending = false;
        info.isCompleted = false;
        
        receivingFiles[fileId] = file;
        receivedFilesSize[fileId] = 0;
        fileTransferInfo[fileId] = info;
        fileProgressDialogs[fileId] = progressDialog;
        
        // 接受文件传输
        chatClient->acceptFileTransfer(userId, fromId, fileId, true);
    } else {
        // 拒绝文件传输
        chatClient->acceptFileTransfer(userId, fromId, fileId, false);
    }
}

// 处理文件传输接受或拒绝的响应
void ChatWindow::onFileTransferAccepted(const QString &fileId, bool accept) {
    if (!fileTransferInfo.contains(fileId)) {
        return;
    }
    
    FileTransferInfo &info = fileTransferInfo[fileId];
    
    if (info.isSending) {
        if (accept) {
            // 对方接受了文件，开始发送文件内容
            sendFileContent(info.receiverId, info.filename, fileId);
        } else {
            // 对方拒绝了文件
            QMessageBox::information(this, "文件发送", "对方拒绝接收文件");
            // 清理进度对话框
            if (fileProgressDialogs.contains(fileId)) {
                delete fileProgressDialogs[fileId];
                fileProgressDialogs.remove(fileId);
            }
            fileTransferInfo.remove(fileId);
        }
    }
}

// 处理接收到的文件数据
void ChatWindow::onFileTransferDataReceived(const QString &fileId, int chunkIndex, const QByteArray &data) {
    if (!receivingFiles.contains(fileId) || !fileTransferInfo.contains(fileId)) {
        return;
    }
    
    QFile *file = receivingFiles[fileId];
    FileTransferInfo &info = fileTransferInfo[fileId];
    
    // 写入数据到文件
    qint64 written = file->write(data);
    if (written < 0) {
        QMessageBox::warning(this, "错误", "文件写入失败");
        chatClient->sendFileTransferComplete(userId, info.senderId, fileId, false);
        // 清理资源
        file->close();
        delete file;
        receivingFiles.remove(fileId);
        if (fileProgressDialogs.contains(fileId)) {
            delete fileProgressDialogs[fileId];
            fileProgressDialogs.remove(fileId);
        }
        fileTransferInfo.remove(fileId);
        return;
    }
    
    // 更新已接收的文件大小
    receivedFilesSize[fileId] += written;
    
    // 更新进度条
    if (fileProgressDialogs.contains(fileId)) {
        fileProgressDialogs[fileId]->setValue(receivedFilesSize[fileId]);
    }
    
    // 检查是否接收完成
    if (receivedFilesSize[fileId] >= info.filesize) {
        // 完成文件传输
        file->close();
        delete file;
        receivingFiles.remove(fileId);
        receivedFilesSize.remove(fileId);
        
        if (fileProgressDialogs.contains(fileId)) {
            fileProgressDialogs[fileId]->close();
            delete fileProgressDialogs[fileId];
            fileProgressDialogs.remove(fileId);
        }
        
        info.isCompleted = true;
        fileTransferInfo[fileId] = info;
        
        QMessageBox::information(this, "成功", QString("文件 '%1' 接收完成").arg(info.filename));
        
        // 通知发送方已完成接收
        chatClient->sendFileTransferComplete(userId, info.senderId, fileId, true);
    }
}

// 处理文件传输完成的通知
void ChatWindow::onFileTransferCompleteReceived(const QString &fileId, bool success) {
    if (!fileTransferInfo.contains(fileId)) {
        return;
    }
    
    FileTransferInfo &info = fileTransferInfo[fileId];
    
    if (info.isSending) {
        // 文件发送方
        if (fileProgressDialogs.contains(fileId)) {
            fileProgressDialogs[fileId]->close();
            delete fileProgressDialogs[fileId];
            fileProgressDialogs.remove(fileId);
        }
        
        if (success) {
            QMessageBox::information(this, "成功", QString("文件 '%1' 发送成功").arg(info.filename));
        } else {
            QMessageBox::information(this, "取消", QString("文件 '%1' 发送已取消").arg(info.filename));
        }
        
        info.isCompleted = true;
        fileTransferInfo.remove(fileId);
    } else {
        // 文件接收方
        if (fileProgressDialogs.contains(fileId)) {
            fileProgressDialogs[fileId]->close();
            delete fileProgressDialogs[fileId];
            fileProgressDialogs.remove(fileId);
        }
        
        if (receivingFiles.contains(fileId)) {
            QFile *file = receivingFiles[fileId];
            file->close();
            delete file;
            receivingFiles.remove(fileId);
        }
        
        if (receivedFilesSize.contains(fileId)) {
            receivedFilesSize.remove(fileId);
        }
        
        if (success) {
            QMessageBox::information(this, "成功", QString("文件 '%1' 接收成功").arg(info.filename));
        } else {
            QMessageBox::information(this, "取消", QString("文件 '%1' 接收已取消（发送方取消）").arg(info.filename));
        }
        
        info.isCompleted = true;
        fileTransferInfo.remove(fileId);
    }
}

// 处理文件传输错误
void ChatWindow::onFileTransferError(const QString &fileId, int errorCode, const QString &errorMsg) {
    if (fileProgressDialogs.contains(fileId)) {
        fileProgressDialogs[fileId]->close();
        delete fileProgressDialogs[fileId];
        fileProgressDialogs.remove(fileId);
    }
    
    if (receivingFiles.contains(fileId)) {
        receivingFiles[fileId]->close();
        delete receivingFiles[fileId];
        receivingFiles.remove(fileId);
        receivedFilesSize.remove(fileId);
    }
    
    if (fileTransferInfo.contains(fileId)) {
        fileTransferInfo.remove(fileId);
    }
    
    QMessageBox::warning(this, "传输错误", QString("文件传输失败: %1 (错误代码: %2)").arg(errorMsg).arg(errorCode));
}

// 发送文件内容
void ChatWindow::sendFileContent(int toId, const QString &filename, const QString &fileId) {
    // 检查文件传输信息是否存在
    if (!fileTransferInfo.contains(fileId)) {
        return;
    }
    
    // 获取保存的文件路径
    QString filePath = fileTransferInfo[fileId].filePath;
    
    if (filePath.isEmpty()) {
        chatClient->sendFileTransferComplete(userId, toId, fileId, false);
        QMessageBox::warning(this, "发送错误", "文件路径无效");
        // 清理资源
        if (fileProgressDialogs.contains(fileId)) {
            delete fileProgressDialogs[fileId];
            fileProgressDialogs.remove(fileId);
        }
        fileTransferInfo.remove(fileId);
        return;
    }
    
    QFile file(filePath);
    if (!file.open(QIODevice::ReadOnly)) {
        QMessageBox::warning(this, "错误", "无法打开文件进行读取: " + file.errorString());
        chatClient->sendFileTransferComplete(userId, toId, fileId, false);
        // 清理资源
        if (fileProgressDialogs.contains(fileId)) {
            delete fileProgressDialogs[fileId];
            fileProgressDialogs.remove(fileId);
        }
        fileTransferInfo.remove(fileId);
        return;
    }
    
    // 分块发送文件内容，增加块大小提高传输速度
    const int chunkSize = 16384; // 从1024字节增加到16384字节
    int chunkIndex = 0;
    qint64 totalRead = 0;
    bool isCancelled = false;
    
    while (!file.atEnd() && !isCancelled) {
        QByteArray chunk = file.read(chunkSize);
        chatClient->sendFileData(userId, toId, fileId, chunkIndex, chunk);
        
        totalRead += chunk.size();
        chunkIndex++;
        
        // 更新进度条
        if (fileProgressDialogs.contains(fileId)) {
            fileProgressDialogs[fileId]->setValue(totalRead);
            
            // 检查是否取消
            if (fileProgressDialogs[fileId]->wasCanceled()) {
                isCancelled = true;
                break;
            }
        }
        
        // 处理事件，确保界面响应
        QCoreApplication::processEvents();
        
        // 减小延迟，提高传输速度
        QThread::msleep(5); // 从50ms减少到5ms
    }
    
    // 如果被取消，发送错误通知
    if (isCancelled) {
        chatClient->sendFileTransferComplete(userId, toId, fileId, false);
        QMessageBox::information(this, "文件传输", "文件传输已取消");
        
        // 清理资源
        if (fileProgressDialogs.contains(fileId)) {
            delete fileProgressDialogs[fileId];
            fileProgressDialogs.remove(fileId);
        }
        fileTransferInfo.remove(fileId);
        return;
    }
    
    file.close();
    
    // 发送完成通知
    chatClient->sendFileTransferComplete(userId, toId, fileId, true);
}

// 处理接收到的文件
void ChatWindow::handleReceivedFile(const QString &fileId, const QString &filename, qint64 filesize) {
    // 此方法已在onFileTransferRequestReceived中实现主要逻辑
    // 这里仅作为备用或扩展
}

// 根据用户ID获取用户名
QString ChatWindow::getUserNameById(int userId) {
    if (friendMap.contains(userId)) {
        return QString::fromStdString(friendMap[userId].getName());
    }
    return QString("用户%1").arg(userId);
}

// 根据群组ID获取群组名称
QString ChatWindow::getGroupNameById(int groupId) {
    if (groupMap.contains(groupId)) {
        return QString::fromStdString(groupMap[groupId].getName());
    }
    return QString("群组%1").arg(groupId);
}