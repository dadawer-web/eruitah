#include "chatwindow.h"
#include "messagewidget.h"
#include "farmdialog.h"
#include "knowledgegraphdialog.h"
#include "realtimevoicedialog.h"
#include "dashboarddialog.h"
#include "companionreadingdialog.h"
#include <QDebug>
#include <QDateTime>
#include <QDesktopServices>
#include <QInputDialog>
#include <QCloseEvent>
#include <QMouseEvent>
#include <QWindow>
#include <QMenu>
#include <QAction>
#include <QMessageBox>
#include <QToolBar>
#include <QStatusBar>
#include <QTimer>
#include <QFileDialog>
#include <QFileInfo>
#include <QCoreApplication>
#include <QApplication>
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
#include <QAudioEncoderSettings>
#include <QVideoEncoderSettings>

// Material 组件头文件
#include "qtmaterialtextfield.h"
#include "qtmaterialflatbutton.h"
#include "qtmaterialraisedbutton.h"
#include "qtmaterialiconbutton.h"
#include "qtmaterialscrollbar.h"
#include "qtmaterialavatar.h"
#include "lib/qtmaterialtheme.h"

// 跨平台网络头文件处理 - 注意：先包含Windows网络头文件，再包含Qt头文件，避免byte类型歧义
#ifdef _WIN32
    #include <winsock2.h>
    #include <ws2tcpip.h>
    #include <windows.h>
    // 防止Windows头文件中的byte类型与Qt冲突
    #undef byte
#endif

// 用于在线程间传递处理结果
struct ImageProcessResult {
    bool success;          // 是否成功
    QString message;       // 失败时的错误信息 / 成功时的JSON消息
    QString displayPath;   // 用于在本地列表显示的图片路径
    QPixmap displayPixmap; // 用于显示的图片对象(可选，防止再次加载)
    QString timeStr;       // 发送时间
};

// 定义一个结构体用于在线程间传递单个表情的解码结果
struct EmojiLoadResult {
    int id;                // 表情ID
    QImage image;          // 解码后的图片（子线程只能用QImage，不能用QPixmap）
    QByteArray rawData;    // 原始图片数据（用于发送）
};

ChatWindow::ChatWindow(int userId, const QString &userName, ChatClient *client, QWidget *parent) : QMainWindow(parent), userId(userId), userName(userName), m_titleBar(nullptr), chatClient(client), loginHandled(false), friendListLoaded(false), offlineMessagesProcessed(false), isLoggingOut(false), m_farmDialog(nullptr), m_realtimeVoiceDialog(nullptr), m_companionReadingDialog(nullptr) {
    setWindowFlags(Qt::FramelessWindowHint);
    setAttribute(Qt::WA_TranslucentBackground, false);
    
    setWindowTitle(QString(QStringLiteral("AI Chat - %1")).arg(userName));
    setObjectName("chatWindow");
    setMinimumSize(900, 650);
    resize(1100, 750);

    // 应用全局现代化样式表
    QString modernStyle = loadModernStylesheet();
    setStyleSheet(modernStyle);
    
    // 设置全局字体（无衬线字体 + 抗锯齿）
    QFont modernFont;
    modernFont.setStyleStrategy(QFont::PreferAntialias);
    modernFont.setStyleHint(QFont::SansSerif);
    #ifdef _WIN32
        modernFont.setFamily("Microsoft YaHei");
    #elif defined(Q_OS_MAC)
        modernFont.setFamily("Helvetica Neue");
    #else
        modernFont.setFamily("Segoe UI");
    #endif
    modernFont.setPointSize(14);
    QApplication::setFont(modernFont);
    
    QWidget *centralContainer = new QWidget(this);
    QVBoxLayout *containerLayout = new QVBoxLayout(centralContainer);
    containerLayout->setContentsMargins(0, 0, 0, 0);
    containerLayout->setSpacing(0);
    
    m_titleBar = new CustomTitleBar(windowTitle(), this);
    containerLayout->addWidget(m_titleBar);
    
    connect(m_titleBar, &CustomTitleBar::minimizeClicked, this, &QMainWindow::showMinimized);
    connect(m_titleBar, &CustomTitleBar::maximizeClicked, this, [this]() {
        if (isMaximized()) {
            showNormal();
        } else {
            showMaximized();
        }
    });
    connect(m_titleBar, &CustomTitleBar::closeClicked, this, &QMainWindow::close);
    
    QWidget *mainContent = new QWidget(this);
    containerLayout->addWidget(mainContent, 1);
    
    setCentralWidget(centralContainer);

    if (client) {
        chatClient = client;
        chatClient->setParent(this);
    } else {
        chatClient = new ChatClient(this);
    }
    isLoadingEmojis = false;
    currentEmojiDialog = nullptr;
    
    ragNetworkManager = new QNetworkAccessManager(this);
    connect(ragNetworkManager, &QNetworkAccessManager::finished, this, &ChatWindow::onRagUploadFinished);
    
    m_audioRecorder = new QAudioRecorder(this);
    m_audioFilePath = QDir::tempPath() + "/chat_record_temp.wav";
    
    qDebug() << "=== Audio Recorder Initialization ===";
    qDebug() << "Available audio inputs:" << m_audioRecorder->audioInputs();
    qDebug() << "Default audio input:" << m_audioRecorder->defaultAudioInput();
    qDebug() << "Supported containers:" << m_audioRecorder->supportedContainers();
    qDebug() << "Supported audio codecs:" << m_audioRecorder->supportedAudioCodecs();
    
    QString audioInput = m_audioRecorder->defaultAudioInput();
    if (audioInput.isEmpty()) {
        QStringList inputs = m_audioRecorder->audioInputs();
        if (!inputs.isEmpty()) {
            audioInput = inputs.first();
            qDebug() << "Using first available audio input:" << audioInput;
        } else {
            qDebug() << "ERROR: No audio input devices available!";
        }
    }
    
    if (!audioInput.isEmpty()) {
        m_audioRecorder->setAudioInput(audioInput);
        qDebug() << "Audio input set to:" << audioInput;
    }
    
    QAudioEncoderSettings audioSettings;
    audioSettings.setQuality(QMultimedia::HighQuality);
    audioSettings.setChannelCount(1);
    audioSettings.setSampleRate(16000);
    
    QString container = "audio/x-wav";
    QStringList containers = m_audioRecorder->supportedContainers();
    if (containers.contains("audio/x-wav")) {
        container = "audio/x-wav";
    } else if (containers.contains("wav")) {
        container = "wav";
    } else if (!containers.isEmpty()) {
        container = containers.first();
    }
    qDebug() << "Using container format:" << container;
    
    m_audioRecorder->setEncodingSettings(audioSettings, QVideoEncoderSettings(), container);
    
    QUrl outputUrl = QUrl::fromLocalFile(m_audioFilePath);
    m_audioRecorder->setOutputLocation(outputUrl);
    qDebug() << "Output location set to:" << outputUrl.toString();
    qDebug() << "Actual output location:" << m_audioRecorder->outputLocation().toString();
    
    m_voiceBtn = nullptr;
    m_voiceRecordStartTime = 0;
    m_pendingVoiceDuration = 0;
    m_pendingVoiceToId = -1;
    m_voiceUploadManager = new QNetworkAccessManager(this);
    connect(m_voiceUploadManager, &QNetworkAccessManager::finished, this, &ChatWindow::onVoiceUploadFinished);
    connect(m_audioRecorder, &QAudioRecorder::stateChanged, this, &ChatWindow::onAudioRecorderStateChanged);
    connect(m_audioRecorder, QOverload<QMediaRecorder::Error>::of(&QAudioRecorder::error), this, [this](QMediaRecorder::Error error) {
        qDebug() << "Audio recorder error:" << error << "-" << m_audioRecorder->errorString();
    });
    
    contactTreeWidget = new QTreeWidget;
    contactTreeWidget->setContextMenuPolicy(Qt::CustomContextMenu);
    contactTreeWidget->setContentsMargins(0, 0, 0, 0);
    contactTreeWidget->setFrameShape(QFrame::NoFrame); // 去除3D边框
    contactTreeWidget->setStyleSheet(
        "QTreeWidget { background-color: #1e1e1e; border: none; border-right: 1px solid #2f2f2f; outline: none; color: #CCCCCC; }"
        "QTreeWidget::item { height: 48px; padding: 4px 12px; border: none; border-radius: 8px; margin: 2px 8px; color: #CCCCCC; }"
        "QTreeWidget::item:hover { background-color: #2a2a2a; }"
        "QTreeWidget::item:selected { background-color: #2d3748; color: #60a5fa; outline: none; }"
        "QTreeWidget::item:selected:!active { background-color: #2d3748; }"
        "QTreeWidget::branch { background-color: transparent; border: none; }"
        "QHeaderView::section { background-color: #1e1e1e; border: none; border-bottom: 1px solid #2f2f2f; padding: 8px; color: #9ca3af; font-weight: 500; }"
    );
    connect(contactTreeWidget, &QTreeWidget::itemClicked, this, &ChatWindow::onContactSelected);
    connect(contactTreeWidget, &QTreeWidget::customContextMenuRequested, this, &ChatWindow::showContextMenu);
    
    contactTreeWidget->setColumnCount(3);
    QStringList headers;
    headers << "头像" << "联系人" << "状态";
    contactTreeWidget->setHeaderLabels(headers);
    
    // 设置联系人树字体
    QFont treeFont = contactTreeWidget->font();
    treeFont.setPointSize(14);
    #ifdef _WIN32
    treeFont.setFamily("Microsoft YaHei");
    #else
    treeFont.setFamily("Segoe UI");
    #endif
    contactTreeWidget->setFont(treeFont);
    
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
    chatTabWidget->setStyleSheet("QTabWidget { background-color: #2b2b2b; border: none; } QTabWidget::pane { background-color: #2b2b2b; border: none; }");
    connect(chatTabWidget, &QTabWidget::tabCloseRequested, chatTabWidget, &QTabWidget::removeTab);

    // 创建主分割器
    mainSplitter = new QSplitter(Qt::Horizontal);
    mainSplitter->addWidget(contactTreeWidget);
    mainSplitter->addWidget(chatTabWidget);
    mainSplitter->setSizes({250, 550});
    mainSplitter->setHandleWidth(1);
    mainSplitter->setStyleSheet("QSplitter { background-color: #2b2b2b; } QSplitter::handle { background-color: #3a3a3a; }");

    // 设置状态栏
    statusBarLabel = new QLabel(QString("已登录: %1").arg(userName));
    statusBar()->addWidget(statusBarLabel);

    // 创建顶部用户信息和头像区域
    QWidget *topBar = new QWidget;
    QHBoxLayout *topLayout = new QHBoxLayout(topBar);
    topLayout->setContentsMargins(15, 10, 15, 10);
    topLayout->setSpacing(15);
    
    // 用户头像 - 使用 QtMaterialAvatar
    QChar firstChar = userName.isEmpty() ? 'U' : userName[0];
    avatarLabel = new QtMaterialAvatar(firstChar.toUpper(), this);
    avatarLabel->setSize(50);
    avatarLabel->setBackgroundColor(QColor(52, 152, 219));
    avatarLabel->setTextColor(QColor(255, 255, 255));
    
    // 连接信号槽
    connect(chatClient, &ChatClient::connected, this, &ChatWindow::onConnected);
    connect(chatClient, &ChatClient::disconnected, this, &ChatWindow::onDisconnected);
    connect(chatClient, &ChatClient::messageReceived, this, &ChatWindow::onReceiveMessage);
    connect(chatClient, &ChatClient::groupMessageReceived, this, &ChatWindow::onReceiveGroupMessage);
    connect(chatClient, &ChatClient::voiceMessageReceived, this, &ChatWindow::onReceiveVoiceMessage);
    connect(chatClient, &ChatClient::friendListUpdated, this, &ChatWindow::onFriendListUpdated);
    connect(chatClient, &ChatClient::groupListUpdated, this, &ChatWindow::onGroupListUpdated);
    connect(chatClient, &ChatClient::addFriendResponse, this, &ChatWindow::onAddFriendResponse);
    connect(chatClient, &ChatClient::addGroupResponse, this, &ChatWindow::onAddGroupResponse);
    connect(chatClient, &ChatClient::createGroupResponse, this, &ChatWindow::onCreateGroupResponse);
    connect(chatClient, &ChatClient::inviteGroupResponse, this, &ChatWindow::onInviteGroupResponse);
    connect(chatClient, &ChatClient::interviewGroupCreated, this, &ChatWindow::onInterviewGroupCreated);

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
                QImage image = pixmap.toImage();
                avatarLabel->setImage(image);
                avatarLabel->setBackgroundColor(QColor(52, 152, 219));
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
                avatarLabel->setLetter(firstChar.toUpper());
                avatarLabel->setBackgroundColor(QColor(52, 152, 219));
                avatarLabel->setTextColor(QColor(255, 255, 255));
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
            avatarLabel->setLetter(firstChar.toUpper());
            avatarLabel->setBackgroundColor(QColor(52, 152, 219));
            avatarLabel->setTextColor(QColor(255, 255, 255));
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
                
                // 使用QtMaterialAvatar的setImage方法
                QImage image = pixmap.toImage();
                avatarLabel->setImage(image);
                avatarLabel->setBackgroundColor(QColor(52, 152, 219));
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
                avatarLabel->setLetter(firstChar.toUpper());
                avatarLabel->setBackgroundColor(QColor(52, 152, 219));
                avatarLabel->setTextColor(QColor(255, 255, 255));
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
            avatarLabel->setLetter(firstChar.toUpper());
            avatarLabel->setBackgroundColor(QColor(52, 152, 219));
            avatarLabel->setTextColor(QColor(255, 255, 255));
        }
    });
    
    // 连接好友状态更新信号
    connect(chatClient, &ChatClient::friendStateUpdated, this, &ChatWindow::onFriendStateUpdated);

    connect(chatClient, &ChatClient::farmPlantResponse, this, &ChatWindow::onFarmPlantResponse);
    connect(chatClient, &ChatClient::farmAnswerResponse, this, &ChatWindow::onFarmAnswerResponse);
    connect(chatClient, &ChatClient::farmQueryResponse, this, &ChatWindow::onFarmQueryResponse);
    connect(chatClient, &ChatClient::farmHarvestResponse, this, &ChatWindow::onFarmHarvestResponse);
    connect(chatClient, &ChatClient::farmPlotHarvested, this, &ChatWindow::onFarmPlotHarvested);
    connect(chatClient, &ChatClient::farmBroadcastReceived, this, &ChatWindow::onFarmBroadcastReceived);
    connect(chatClient, &ChatClient::careerAdviceReceived, this, &ChatWindow::onCareerAdviceReceived);

    m_farmDialog = nullptr;
    m_realtimeVoiceDialog = nullptr;
    m_realtimeVoiceBtn = nullptr;

    connect(chatClient, &ChatClient::fileTransferRequestReceived, this, &ChatWindow::onFileTransferRequestReceived);
    connect(chatClient, &ChatClient::fileTransferAccepted, this, &ChatWindow::onFileTransferAccepted);
    connect(chatClient, &ChatClient::fileTransferDataReceived, this, &ChatWindow::onFileTransferDataReceived);
    connect(chatClient, &ChatClient::fileTransferCompleteReceived, this, &ChatWindow::onFileTransferCompleteReceived);
    connect(chatClient, &ChatClient::fileTransferError, this, &ChatWindow::onFileTransferError);
    
    // 用户信息
    QVBoxLayout *userInfoLayout = new QVBoxLayout;
    userInfoLayout->setSpacing(5);
    QLabel *userNameLabel = new QLabel(userName);
    QFont userNameFont = userNameLabel->font();
    userNameFont.setPointSize(16);
    userNameFont.setBold(true);
    #ifdef _WIN32
    userNameFont.setFamily("Microsoft YaHei");
    #else
    userNameFont.setFamily("Arial");
    #endif
    userNameLabel->setFont(userNameFont);
    userNameLabel->setStyleSheet(
        "font-size: 16px; "
        "font-weight: bold; "
        "color: #2c3e50; "
        "font-family: 'Microsoft YaHei', Arial, sans-serif;"
    );
    QLabel *userIdLabel = new QLabel(QString("ID: %1").arg(userId));
    QFont userIdFont = userIdLabel->font();
    userIdFont.setPointSize(12);
    #ifdef _WIN32
    userIdFont.setFamily("Microsoft YaHei");
    #else
    userIdFont.setFamily("Arial");
    #endif
    userIdLabel->setFont(userIdFont);
    userIdLabel->setStyleSheet(
        "font-size: 12px; "
        "color: #666; "
        "font-family: 'Microsoft YaHei', Arial, sans-serif;"
    );
    userInfoLayout->addWidget(userNameLabel);
    userInfoLayout->addWidget(userIdLabel);
    userInfoLayout->addStretch();
    
    // 修改头像按钮
    changeAvatarButton = new QPushButton("修改头像");
    QFont buttonFont = changeAvatarButton->font();
    buttonFont.setPointSize(12);
    #ifdef _WIN32
    buttonFont.setFamily("Microsoft YaHei");
    #else
    buttonFont.setFamily("Arial");
    #endif
    changeAvatarButton->setFont(buttonFont);
    changeAvatarButton->setStyleSheet(
        "height: 32px; "
        "background-color: white; "
        "color: #3498db; "
        "border: 1px solid #3498db; "
        "border-radius: 16px; "
        "font-size: 12px; "
        "font-family: 'Microsoft YaHei', Arial, sans-serif;"
    );
    
    topLayout->addWidget(avatarLabel);
    topLayout->addLayout(userInfoLayout);
    topLayout->addStretch();
    topLayout->addWidget(changeAvatarButton);
    
    // 创建工具栏（使用 QWidget 而非 QToolBar，避免布局问题）
    QWidget *toolBarWidget = new QWidget;
    toolBarWidget->setFixedHeight(44);
    toolBarWidget->setStyleSheet("background-color: #2a2a2a; border: none; border-bottom: 1px solid #3a3a3a;");
    QHBoxLayout *toolbarLayout = new QHBoxLayout(toolBarWidget);
    toolbarLayout->setContentsMargins(10, 0, 10, 0);
    toolbarLayout->setSpacing(4);
    
    QFont toolbarFont = toolBarWidget->font();
    toolbarFont.setPointSize(13);
    #ifdef _WIN32
    toolbarFont.setFamily("Microsoft YaHei");
    #else
    toolbarFont.setFamily("Arial");
    #endif
    
    QPushButton *addFriendBtn = new QPushButton("添加好友", toolBarWidget);
    QPushButton *createGroupBtn = new QPushButton("创建群组", toolBarWidget);
    QPushButton *joinGroupBtn = new QPushButton("加入群组", toolBarWidget);
    QPushButton *inviteGroupBtn = new QPushButton("邀请进群", toolBarWidget);
    QPushButton *interviewBtn = new QPushButton("🔥 开启模拟面试", toolBarWidget);
    QPushButton *farmBtn = new QPushButton("🌱 408农场", toolBarWidget);
    QPushButton *knowledgeGraphBtn = new QPushButton("🧠 知识图谱", toolBarWidget);
    QPushButton *dashboardBtn = new QPushButton("📊 考情大屏", toolBarWidget);
    QPushButton *companionReadBtn = new QPushButton("📖 AI伴学", toolBarWidget);
    QPushButton *codingAgentBtn = new QPushButton("💻 编程 Agent", toolBarWidget);
    QPushButton *careerBtn = new QPushButton("🎓 职业档案", toolBarWidget);
    QPushButton *aiDocsBtn = new QPushButton("📄 AI文档与课件", toolBarWidget);
    QPushButton *logoutBtn = new QPushButton("注销", toolBarWidget);
    
    QString btnStyle = "QPushButton { background-color: transparent; border: none; color: #9ca3af; font-size: 13px; padding: 6px 12px; border-radius: 4px; } QPushButton:hover { background-color: #3a3a3a; color: #ececec; } QPushButton:pressed { background-color: #404040; }";
    QString interviewBtnStyle = "QPushButton { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ef4444, stop:1 #f97316); border: none; color: white; font-size: 13px; padding: 6px 12px; border-radius: 4px; font-weight: bold; } QPushButton:hover { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #dc2626, stop:1 #ea580c); } QPushButton:pressed { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #b91c1c, stop:1 #c2410c); }";
    QString farmBtnStyle = "QPushButton { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #22c55e, stop:1 #16a34a); border: none; color: white; font-size: 13px; padding: 6px 12px; border-radius: 4px; font-weight: bold; } QPushButton:hover { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #16a34a, stop:1 #15803d); } QPushButton:pressed { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #15803d, stop:1 #166534); }";
    QString knowledgeGraphBtnStyle = "QPushButton { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8b5cf6, stop:1 #6366f1); border: none; color: white; font-size: 13px; padding: 6px 12px; border-radius: 4px; font-weight: bold; } QPushButton:hover { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7c3aed, stop:1 #4f46e5); } QPushButton:pressed { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6d28d9, stop:1 #4338ca); }";
    QString dashboardBtnStyle = "QPushButton { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00f2fe, stop:1 #7edad2); border: none; color: #0b0f1a; font-size: 13px; padding: 6px 12px; border-radius: 4px; font-weight: bold; } QPushButton:hover { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00d4e0, stop:1 #6bc4b8); } QPushButton:pressed { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00b6c2, stop:1 #59b0a0); }";
    QString companionReadBtnStyle = "QPushButton { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7c3aed, stop:1 #a855f7); border: none; color: white; font-size: 13px; padding: 6px 12px; border-radius: 4px; font-weight: bold; } QPushButton:hover { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6d28d9, stop:1 #9333ea); } QPushButton:pressed { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #5b21b6, stop:1 #7e22ce); }";
    QString codingAgentBtnStyle = "QPushButton { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #007acc, stop:1 #0098ff); border: none; color: white; font-size: 13px; padding: 6px 12px; border-radius: 4px; font-weight: bold; } QPushButton:hover { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #005a9e, stop:1 #0078d4); } QPushButton:pressed { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #004578, stop:1 #0066b3); }";
    QString careerBtnStyle = "QPushButton { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #059669, stop:1 #10b981); border: none; color: white; font-size: 13px; padding: 6px 12px; border-radius: 4px; font-weight: bold; } QPushButton:hover { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #047857, stop:1 #059669); } QPushButton:pressed { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #065f46, stop:1 #047857); }";
    QString aiDocsBtnStyle = "QPushButton { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ea580c, stop:1 #f59e0b); border: none; color: white; font-size: 13px; padding: 6px 12px; border-radius: 4px; font-weight: bold; } QPushButton:hover { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #c2410c, stop:1 #d97706); } QPushButton:pressed { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #9a3412, stop:1 #b45309); }";
    addFriendBtn->setStyleSheet(btnStyle);
    createGroupBtn->setStyleSheet(btnStyle);
    joinGroupBtn->setStyleSheet(btnStyle);
    inviteGroupBtn->setStyleSheet(btnStyle);
    interviewBtn->setStyleSheet(interviewBtnStyle);
    farmBtn->setStyleSheet(farmBtnStyle);
    knowledgeGraphBtn->setStyleSheet(knowledgeGraphBtnStyle);
    dashboardBtn->setStyleSheet(dashboardBtnStyle);
    companionReadBtn->setStyleSheet(companionReadBtnStyle);
    codingAgentBtn->setStyleSheet(codingAgentBtnStyle);
    careerBtn->setStyleSheet(careerBtnStyle);
    aiDocsBtn->setStyleSheet(aiDocsBtnStyle);
    logoutBtn->setStyleSheet(btnStyle);
    
    addFriendBtn->setFont(toolbarFont);
    createGroupBtn->setFont(toolbarFont);
    joinGroupBtn->setFont(toolbarFont);
    inviteGroupBtn->setFont(toolbarFont);
    interviewBtn->setFont(toolbarFont);
    farmBtn->setFont(toolbarFont);
    knowledgeGraphBtn->setFont(toolbarFont);
    dashboardBtn->setFont(toolbarFont);
    companionReadBtn->setFont(toolbarFont);
    codingAgentBtn->setFont(toolbarFont);
    careerBtn->setFont(toolbarFont);
    aiDocsBtn->setFont(toolbarFont);
    logoutBtn->setFont(toolbarFont);
    
    toolbarLayout->addWidget(addFriendBtn);
    toolbarLayout->addWidget(createGroupBtn);
    toolbarLayout->addWidget(joinGroupBtn);
    toolbarLayout->addWidget(inviteGroupBtn);
    toolbarLayout->addWidget(interviewBtn);
    toolbarLayout->addWidget(farmBtn);
    toolbarLayout->addWidget(knowledgeGraphBtn);
    toolbarLayout->addWidget(dashboardBtn);
    toolbarLayout->addWidget(companionReadBtn);
    toolbarLayout->addWidget(codingAgentBtn);
    toolbarLayout->addWidget(careerBtn);
    toolbarLayout->addWidget(aiDocsBtn);
    toolbarLayout->addSpacing(8);
    toolbarLayout->addWidget(new QLabel("|", toolBarWidget));
    toolbarLayout->addSpacing(8);
    toolbarLayout->addWidget(logoutBtn);
    toolbarLayout->addStretch();

    connect(addFriendBtn, &QPushButton::clicked, this, &ChatWindow::onAddFriend);
    connect(createGroupBtn, &QPushButton::clicked, this, &ChatWindow::onCreateGroup);
    connect(joinGroupBtn, &QPushButton::clicked, this, &ChatWindow::onJoinGroup);
    connect(inviteGroupBtn, &QPushButton::clicked, this, &ChatWindow::onInviteToGroup);
    connect(interviewBtn, &QPushButton::clicked, this, &ChatWindow::onCreateInterviewGroup);
    connect(farmBtn, &QPushButton::clicked, this, &ChatWindow::onOpenFarm);
    connect(knowledgeGraphBtn, &QPushButton::clicked, this, &ChatWindow::onOpenKnowledgeGraph);
    connect(dashboardBtn, &QPushButton::clicked, this, &ChatWindow::onOpenDashboard);
    connect(companionReadBtn, &QPushButton::clicked, this, &ChatWindow::onOpenCompanionReading);
    connect(codingAgentBtn, &QPushButton::clicked, this, &ChatWindow::onOpenCodingAgent);
    connect(careerBtn, &QPushButton::clicked, this, &ChatWindow::onOpenCareerDashboard);
    connect(aiDocsBtn, &QPushButton::clicked, this, &ChatWindow::onOpenAiDocs);
    connect(logoutBtn, &QPushButton::clicked, this, &ChatWindow::onLogout);
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
            QImage image(filePath);
            if (!image.isNull()) {
                avatarLabel->setImage(image);
            }
        }
    });

    QVBoxLayout *contentLayout = new QVBoxLayout(mainContent);
    contentLayout->setContentsMargins(0, 0, 0, 0);
    contentLayout->setSpacing(0);
    
    contentLayout->addWidget(topBar);
    contentLayout->addWidget(toolBarWidget);
    contentLayout->addWidget(mainSplitter, 1);
    
    qDebug() << "ChatWindow initialized for userId:" << userId;

    // 初始化添加好友对话框
    addFriendDialog = new QDialog(this);
    addFriendDialog->setWindowTitle("添加好友");
    addFriendDialog->setFixedSize(320, 160);
    addFriendDialog->setStyleSheet(
        "QDialog { background-color: #2a2a2a; border: 2px solid #3a3a3a; border-radius: 12px; }"
        "QLabel { color: #ececec; font-size: 14px; }"
        "QLineEdit { background-color: #3a3a3a; border: none; border-radius: 6px; padding: 8px 12px; color: #ececec; }"
        "QPushButton { background-color: #3b82f6; color: white; border: none; border-radius: 6px; padding: 8px 16px; min-width: 60px; }"
        "QPushButton:hover { background-color: #2563eb; }"
    );
    
    QVBoxLayout *addFriendLayout = new QVBoxLayout(addFriendDialog);
    addFriendLayout->setContentsMargins(20, 20, 20, 20);
    addFriendLayout->setSpacing(12);
    
    QLabel *addFriendIdLabel = new QLabel("好友ID:", addFriendDialog);
    QFont labelFont = addFriendIdLabel->font();
    labelFont.setPointSize(14);
    #ifdef _WIN32
    labelFont.setFamily("Microsoft YaHei");
    #else
    labelFont.setFamily("Arial");
    #endif
    addFriendLayout->addWidget(addFriendIdLabel);
    addFriendIdEdit = new QLineEdit(addFriendDialog);
    addFriendIdEdit->setPlaceholderText("请输入好友ID");
    addFriendLayout->addWidget(addFriendIdEdit);
    
    QHBoxLayout *addFriendButtonLayout = new QHBoxLayout;
    addFriendButtonLayout->setSpacing(10);
    
    QPushButton *addFriendOkButton = new QPushButton("确定", addFriendDialog);
    QPushButton *addFriendCancelButton = new QPushButton("取消", addFriendDialog);
    
    addFriendButtonLayout->addWidget(addFriendOkButton);
    addFriendButtonLayout->addWidget(addFriendCancelButton);
    addFriendLayout->addLayout(addFriendButtonLayout);
    
    connect(addFriendOkButton, &QPushButton::clicked, this, &ChatWindow::onAddFriendConfirmed);
    connect(addFriendCancelButton, &QPushButton::clicked, addFriendDialog, &QDialog::close);
    
    // 处理存储的离线消息 - 移到构造函数末尾，确保所有UI元素都已初始化
    chatClient->processStoredOfflineMessages();

    // 初始化创建群组对话框
    createGroupDialog = new QDialog(this);
    createGroupDialog->setWindowTitle("创建群组");
    createGroupDialog->setFixedSize(400, 250);
    createGroupDialog->setStyleSheet(
        "QDialog { background-color: #2a2a2a; border: 2px solid #3a3a3a; border-radius: 12px; }"
        "QLabel { color: #ececec; font-size: 14px; }"
        "QLineEdit { background-color: #3a3a3a; border: none; border-radius: 6px; padding: 10px 12px; color: #ececec; min-height: 28px; font-size: 13px; }"
        "QPushButton { background-color: #3b82f6; color: white; border: none; border-radius: 6px; padding: 10px 20px; min-width: 80px; min-height: 32px; font-size: 14px; }"
        "QPushButton:hover { background-color: #2563eb; }"
    );
    
    QVBoxLayout *createGroupLayout = new QVBoxLayout(createGroupDialog);
    createGroupLayout->setContentsMargins(20, 20, 20, 20);
    createGroupLayout->setSpacing(12);
    
    QLabel *groupNameLabel = new QLabel("群组名称:", createGroupDialog);
    createGroupLayout->addWidget(groupNameLabel);
    groupNameEdit = new QLineEdit(createGroupDialog);
    groupNameEdit->setPlaceholderText("请输入群组名称");
    createGroupLayout->addWidget(groupNameEdit);
    QLabel *groupDescLabel = new QLabel("群组描述:");
    createGroupLayout->addWidget(groupDescLabel);
    groupDescEdit = new QLineEdit(createGroupDialog);
    groupDescEdit->setPlaceholderText("请输入群组描述");
    createGroupLayout->addWidget(groupDescEdit);
    
    QHBoxLayout *createGroupButtonLayout = new QHBoxLayout;
    createGroupButtonLayout->setSpacing(10);
    
    QPushButton *createGroupOkButton = new QPushButton("确定", createGroupDialog);
    QPushButton *createGroupCancelButton = new QPushButton("取消", createGroupDialog);
    
    createGroupButtonLayout->addWidget(createGroupOkButton);
    createGroupButtonLayout->addWidget(createGroupCancelButton);
    createGroupLayout->addLayout(createGroupButtonLayout);
    
    connect(createGroupOkButton, &QPushButton::clicked, this, &ChatWindow::onCreateGroupConfirmed);
    connect(createGroupCancelButton, &QPushButton::clicked, createGroupDialog, &QDialog::close);

    // 初始化加入群组对话框
    joinGroupDialog = new QDialog(this);
    joinGroupDialog->setWindowTitle("加入群组");
    joinGroupDialog->setFixedSize(320, 160);
    joinGroupDialog->setStyleSheet(
        "QDialog { background-color: #2a2a2a; border: 2px solid #3a3a3a; border-radius: 12px; }"
        "QLabel { color: #ececec; font-size: 14px; }"
        "QLineEdit { background-color: #3a3a3a; border: none; border-radius: 6px; padding: 8px 12px; color: #ececec; }"
        "QPushButton { background-color: #3b82f6; color: white; border: none; border-radius: 6px; padding: 8px 16px; min-width: 60px; }"
        "QPushButton:hover { background-color: #2563eb; }"
    );
    
    QVBoxLayout *joinGroupLayout = new QVBoxLayout(joinGroupDialog);
    joinGroupLayout->setContentsMargins(20, 20, 20, 20);
    joinGroupLayout->setSpacing(12);
    
    QLabel *joinGroupIdLabel = new QLabel("群组ID:", joinGroupDialog);
    joinGroupLayout->addWidget(joinGroupIdLabel);
    joinGroupIdEdit = new QLineEdit(joinGroupDialog);
    joinGroupIdEdit->setPlaceholderText("请输入群组ID");
    joinGroupLayout->addWidget(joinGroupIdEdit);
    
    QHBoxLayout *joinGroupButtonLayout = new QHBoxLayout;
    joinGroupButtonLayout->setSpacing(10);
    
    QPushButton *joinGroupOkButton = new QPushButton("确定", joinGroupDialog);
    QPushButton *joinGroupCancelButton = new QPushButton("取消", joinGroupDialog);
    
    joinGroupButtonLayout->addWidget(joinGroupOkButton);
    joinGroupButtonLayout->addWidget(joinGroupCancelButton);
    joinGroupLayout->addLayout(joinGroupButtonLayout);
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

QString ChatWindow::getMyAvatarPath() {
    QString myAvatarPath = ":/icons/user.png";
    
    if (currentUserAvatarData.isEmpty()) {
        return myAvatarPath;
    }
    
    QString cleanBase64 = currentUserAvatarData.trimmed();
    
    if (cleanBase64.startsWith("data:image/")) {
        int commaPos = cleanBase64.indexOf(',');
        if (commaPos != -1) {
            cleanBase64 = cleanBase64.mid(commaPos + 1);
        }
    }
    
    QByteArray decodedData = QByteArray::fromBase64(cleanBase64.toUtf8());
    
    if (decodedData.isEmpty()) {
        return myAvatarPath;
    }
    
    if (decodedData.size() >= 4 && decodedData[0] == '/' && decodedData[1] == '9' && decodedData[2] == 'j' && decodedData[3] == '/') {
        decodedData = QByteArray::fromBase64(decodedData);
    }
    
    QImage avatarImage;
    bool loadSuccess = avatarImage.loadFromData(decodedData);
    
    if (!loadSuccess) {
        loadSuccess = avatarImage.loadFromData(decodedData, "PNG");
    }
    if (!loadSuccess) {
        loadSuccess = avatarImage.loadFromData(decodedData, "JPEG");
    }
    if (!loadSuccess) {
        loadSuccess = avatarImage.loadFromData(decodedData, "BMP");
    }
    
    if (loadSuccess) {
        QPixmap avatarPixmap = QPixmap::fromImage(avatarImage);
        QString tempAvatarPath = QCoreApplication::applicationDirPath() + "/temp_avatar_current.png";
        if (avatarPixmap.save(tempAvatarPath)) {
            myAvatarPath = tempAvatarPath;
        }
    }
    
    return myAvatarPath;
}

QString ChatWindow::getFriendAvatarPath(int friendId) {
    QString avatarPath = ":/icons/user.png";
    
    if (!friendMap.contains(friendId)) {
        qDebug() << "getFriendAvatarPath: friendId" << friendId << "not in friendMap";
        return avatarPath;
    }
    
    User friendUser = friendMap[friendId];
    std::string avatarStdStr = friendUser.getAvatar();
    
    if (avatarStdStr.empty()) {
        qDebug() << "getFriendAvatarPath: friendId" << friendId << "has empty avatar";
        return avatarPath;
    }
    
    QString avatarDataStr = QString::fromStdString(avatarStdStr);
    qDebug() << "getFriendAvatarPath: friendId" << friendId << "avatar data length:" << avatarDataStr.length();
    
    QString cleanBase64 = avatarDataStr.trimmed();
    
    if (cleanBase64.startsWith("data:image/")) {
        int commaPos = cleanBase64.indexOf(',');
        if (commaPos != -1) {
            cleanBase64 = cleanBase64.mid(commaPos + 1);
        }
    }
    
    QByteArray decodedData = QByteArray::fromBase64(cleanBase64.toUtf8());
    
    if (decodedData.isEmpty()) {
        qDebug() << "getFriendAvatarPath: decoded data is empty";
        return avatarPath;
    }
    
    if (decodedData.size() >= 4 && decodedData[0] == '/' && decodedData[1] == '9' && decodedData[2] == 'j' && decodedData[3] == '/') {
        decodedData = QByteArray::fromBase64(decodedData);
    }
    
    QImage avatarImage;
    bool loadSuccess = avatarImage.loadFromData(decodedData);
    
    if (!loadSuccess) {
        loadSuccess = avatarImage.loadFromData(decodedData, "PNG");
    }
    if (!loadSuccess) {
        loadSuccess = avatarImage.loadFromData(decodedData, "JPEG");
    }
    if (!loadSuccess) {
        loadSuccess = avatarImage.loadFromData(decodedData, "BMP");
    }
    
    if (loadSuccess) {
        QPixmap avatarPixmap = QPixmap::fromImage(avatarImage);
        QString tempAvatarPath = QDir::tempPath() + QString("/avatar_%1.png").arg(friendId);
        if (avatarPixmap.save(tempAvatarPath)) {
            avatarPath = tempAvatarPath;
            qDebug() << "getFriendAvatarPath: saved avatar to" << tempAvatarPath;
        }
    } else {
        qDebug() << "getFriendAvatarPath: failed to load image from decoded data";
    }
    
    return avatarPath;
}

QListWidgetItem* ChatWindow::addMessageToChatList(QListWidget *listWidget, bool isSender, const QString &message, const QString &avatarPath, const QString &timeStr, const QString &senderName) {
    QListWidgetItem *item = new QListWidgetItem(listWidget);
    
    QString finalSenderName;
    if (!senderName.isEmpty()) {
        finalSenderName = senderName;
    } else if (isSender) {
        finalSenderName = this->userName;
    } else {
        finalSenderName = "User";
    }
    
    MessageWidget *messageWidget = new MessageWidget(isSender, message, avatarPath, finalSenderName, timeStr);
    
    item->setSizeHint(messageWidget->sizeHint());
    
    listWidget->setItemWidget(item, messageWidget);
    
    listWidget->updateGeometry();
    listWidget->repaint();
    
    QScrollBar *scrollBar = listWidget->verticalScrollBar();
    if (scrollBar) {
        scrollBar->setValue(scrollBar->maximum());
        
        QTimer::singleShot(10, listWidget, [this, listWidget]() {
            scrollChatToBottom(listWidget);
        });
    }
    
    return item;
}

QListWidgetItem* ChatWindow::addVoiceMessageToChatList(QListWidget *listWidget, bool isSender, const QString &voiceUrl, int duration, const QString &avatarPath, const QString &timeStr, const QString &senderName) {
    QListWidgetItem *item = new QListWidgetItem(listWidget);
    
    QString finalSenderName;
    if (!senderName.isEmpty()) {
        finalSenderName = senderName;
    } else if (isSender) {
        finalSenderName = this->userName;
    } else {
        finalSenderName = "User";
    }
    
    QString displayText = QString("[语音消息 %1秒]").arg(duration);
    MessageWidget *messageWidget = new MessageWidget(isSender, displayText, avatarPath, finalSenderName, timeStr);
    messageWidget->setVoiceContent(voiceUrl, duration);
    
    item->setSizeHint(messageWidget->sizeHint());
    
    listWidget->setItemWidget(item, messageWidget);
    
    listWidget->updateGeometry();
    listWidget->repaint();
    
    QScrollBar *scrollBar = listWidget->verticalScrollBar();
    if (scrollBar) {
        scrollBar->setValue(scrollBar->maximum());
        
        QTimer::singleShot(10, listWidget, [this, listWidget]() {
            scrollChatToBottom(listWidget);
        });
    }
    
    return item;
}

void ChatWindow::onSendMessage()
{
    QWidget *currentWidget = chatTabWidget->currentWidget();
    if (!currentWidget)
        return;
    
    if (!chatComponents.contains(currentWidget) || !inputTextFields.contains(currentWidget))
        return;
    
    ChatComponents components = chatComponents[currentWidget];
    QListWidget *chatListWidget = components.chatListWidget;
    QtMaterialTextField *inputEdit = inputTextFields[currentWidget];
    
    QString message = inputEdit->text().trimmed();
    if (message.isEmpty())
        return;
    
    int chatId = currentWidget->property("chatId").toInt();
    bool isGroup = currentWidget->property("isGroup").toBool();

    QString timeStr = QDateTime::currentDateTime().toString("hh:mm:ss");
    QString myAvatarPath = getMyAvatarPath();
    
    qDebug() << "ChatWindow: onSendMessage - avatarPath:" << myAvatarPath;
    addMessageToChatList(chatListWidget, true, message, myAvatarPath, timeStr);
    inputEdit->clear();

    if (isGroup) {
        chatClient->sendGroupMessage(chatId, message);
    } else {
        chatClient->sendMessage(chatId, message);
    }
}

QListWidget* ChatWindow::findChatListWidgetForUser(int userId) {
    // 遍历所有的聊天窗口，找到对应用户的chatListWidget
    for (int i = 0; i < chatTabWidget->count(); ++i) {
        QWidget* widget = chatTabWidget->widget(i);
        if (widget && widget->property("chatId").toInt() == userId &&
            !widget->property("isGroup").toBool()) {
            if (chatComponents.contains(widget)) {
                return chatComponents[widget].chatListWidget;
            }
        }
    }
    
    // 如果找不到，自动创建一个新的聊天窗口
    qDebug() << "ChatWindow: Creating new chat widget for user" << userId;
    createChatWidget(userId, QString("User %1").arg(userId), false);
    
    // 再次查找
    for (int i = 0; i < chatTabWidget->count(); ++i) {
        QWidget* widget = chatTabWidget->widget(i);
        if (widget && widget->property("chatId").toInt() == userId &&
            !widget->property("isGroup").toBool()) {
            if (chatComponents.contains(widget)) {
                return chatComponents[widget].chatListWidget;
            }
        }
    }
    
    return nullptr;
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

    QWidget *chatWidget = new QWidget;
    chatWidget->setStyleSheet("background-color: #2b2b2b;");
    
    QVBoxLayout *mainLayout = new QVBoxLayout;
    mainLayout->setContentsMargins(0, 0, 0, 0);
    mainLayout->setSpacing(0);
    
    BottomPaddingListWidget *chatListWidget = new BottomPaddingListWidget;
    chatListWidget->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    chatListWidget->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    chatListWidget->setFocusPolicy(Qt::NoFocus);
    chatListWidget->setSelectionMode(QAbstractItemView::NoSelection);
    chatListWidget->setFrameShape(QFrame::NoFrame);
    chatListWidget->setWordWrap(true);
    chatListWidget->setResizeMode(QListWidget::Adjust);
    chatListWidget->setUniformItemSizes(false);
    chatListWidget->setVerticalScrollMode(QAbstractItemView::ScrollPerPixel);
    chatListWidget->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    chatListWidget->setStyleSheet(
        "QListWidget { background-color: #2b2b2b; border: none; outline: none; }"
        "QListWidget::item { background-color: transparent; border: none; outline: none; margin-bottom: 8px; }"
        "QListWidget::item:selected { background-color: transparent; }"
        "QListWidget::item:hover { background-color: transparent; }"
        "QScrollBar:vertical { background-color: transparent; width: 8px; }"
        "QScrollBar::handle:vertical { background-color: #404040; border-radius: 4px; min-height: 32px; }"
    );
    
    QWidget *memberWidget = nullptr;
    QListWidget *memberListWidget = nullptr;
    QVBoxLayout *memberLayout = nullptr;
    
    if (isGroup) {
        memberWidget = new QWidget;
        memberWidget->setStyleSheet("background-color: #212121; border-left: 1px solid #2f2f2f;");
        memberLayout = new QVBoxLayout;
        memberLayout->setContentsMargins(10, 10, 10, 10);
        memberLayout->setSpacing(10);
        
        QLabel *memberTitle = new QLabel("Group Members");
        memberTitle->setStyleSheet("font-weight: bold; font-size: 14px; color: #9ca3af;");
        memberLayout->addWidget(memberTitle);
        
        memberListWidget = new QListWidget;
        memberListWidget->setStyleSheet(
            "QListWidget { background-color: #2f2f2f; border: 1px solid #404040; border-radius: 6px; color: #ececec; }"
            "QListWidget::item { height: 30px; padding: 5px 10px; border-bottom: 1px solid #404040; color: #ececec; }"
            "QListWidget::item:last-child { border-bottom: none; }"
        );
        memberLayout->addWidget(memberListWidget);

        QtMaterialFlatButton *inviteBtn = new QtMaterialFlatButton("Invite +");
        inviteBtn->setMinimumHeight(32);
        inviteBtn->setRole(Material::Default);
        inviteBtn->setForegroundColor(QColor("#3b82f6"));
        inviteBtn->setBackgroundColor(QColor("#1a2a3a"));
        inviteBtn->setOverlayColor(QColor("#2a4a6a"));
        inviteBtn->setRippleStyle(Material::CenteredRipple);
        inviteBtn->setCornerRadius(6);
        inviteBtn->setFontSize(12);
        inviteBtn->setProperty("groupId", chatId);
        connect(inviteBtn, &QtMaterialFlatButton::clicked, this, &ChatWindow::onInviteToGroup);
        memberLayout->addWidget(inviteBtn);

        memberWidget->setLayout(memberLayout);
        memberWidget->setFixedWidth(180);
    }
    
    if (isGroup && memberWidget) {
        QSplitter *chatSplitter = new QSplitter(Qt::Horizontal);
        chatSplitter->addWidget(chatListWidget);
        chatSplitter->addWidget(memberWidget);
        chatSplitter->setSizes({450, 180});
        chatSplitter->setHandleWidth(1);
        mainLayout->addWidget(chatSplitter, 1);
    } else {
        mainLayout->addWidget(chatListWidget, 1);
    }
    
    QFrame *separator = new QFrame;
    separator->setFrameShape(QFrame::HLine);
    separator->setFrameShadow(QFrame::Plain);
    separator->setStyleSheet("background-color: #3a3a3a; border: none;");
    separator->setFixedHeight(1);
    mainLayout->addWidget(separator);
    
    QWidget *inputWidget = new QWidget;
    inputWidget->setStyleSheet("background-color: #333333; border: none; border-top: 1px solid #EAEAEA; border-radius: 0;");
    QVBoxLayout *inputLayout = new QVBoxLayout;
    inputLayout->setContentsMargins(16, 12, 16, 12);
    inputLayout->setSpacing(12);
    
    QtMaterialTextField *inputEdit = new QtMaterialTextField;
    inputEdit->setMinimumHeight(56);
    inputEdit->setMinimumWidth(300);
    inputEdit->setPlaceholderText("Type a message...");
    inputEdit->setTextColor(QColor("#FFFFFF"));
    inputEdit->setLabelColor(QColor("#9ca3af"));
    inputEdit->setInkColor(QColor("#3b82f6"));
    inputEdit->setInputLineColor(QColor("#4a4a4a"));
    inputEdit->setShowInputLine(true);
    inputEdit->setShowLabel(false);
    inputLayout->addWidget(inputEdit);
    
    QHBoxLayout *buttonLayout = new QHBoxLayout;
    buttonLayout->setContentsMargins(0, 0, 0, 0);
    buttonLayout->setSpacing(10);
    buttonLayout->setAlignment(Qt::AlignRight);
    
    // 发送按钮使用 QtMaterialRaisedButton（主要操作按钮）
    QtMaterialRaisedButton *sendButton = new QtMaterialRaisedButton("Send");
    sendButton->setMinimumHeight(40);
    sendButton->setFixedWidth(100);
    sendButton->setForegroundColor(QColor("#ffffff"));
    sendButton->setBackgroundColor(QColor("#3b82f6"));
    sendButton->setOverlayColor(QColor("#2563eb"));
    sendButton->setRippleStyle(Material::CenteredRipple);
    sendButton->setCornerRadius(8);
    sendButton->setFontSize(14);
    sendButton->setHaloVisible(true);
    
    // 其他次要按钮使用 QtMaterialFlatButton
    QtMaterialFlatButton *sendFileButton = new QtMaterialFlatButton("File");
    sendFileButton->setMinimumHeight(40);
    sendFileButton->setFixedWidth(80);
    sendFileButton->setRole(Material::Default);
    sendFileButton->setForegroundColor(QColor("#9ca3af"));
    sendFileButton->setBackgroundColor(QColor("#2a2a2a"));
    sendFileButton->setOverlayColor(QColor("#3a3a3a"));
    sendFileButton->setRippleStyle(Material::CenteredRipple);
    sendFileButton->setCornerRadius(8);
    sendFileButton->setFontSize(14);
    
    QtMaterialFlatButton *sendImageButton = new QtMaterialFlatButton("Image");
    sendImageButton->setMinimumHeight(40);
    sendImageButton->setFixedWidth(80);
    sendImageButton->setRole(Material::Default);
    sendImageButton->setForegroundColor(QColor("#9ca3af"));
    sendImageButton->setBackgroundColor(QColor("#2a2a2a"));
    sendImageButton->setOverlayColor(QColor("#3a3a3a"));
    sendImageButton->setRippleStyle(Material::CenteredRipple);
    sendImageButton->setCornerRadius(8);
    sendImageButton->setFontSize(14);
    
    QtMaterialFlatButton *sendEmojiButton = new QtMaterialFlatButton("Emoji");
    sendEmojiButton->setMinimumHeight(40);
    sendEmojiButton->setFixedWidth(80);
    sendEmojiButton->setRole(Material::Default);
    sendEmojiButton->setForegroundColor(QColor("#9ca3af"));
    sendEmojiButton->setBackgroundColor(QColor("#2a2a2a"));
    sendEmojiButton->setOverlayColor(QColor("#3a3a3a"));
    sendEmojiButton->setRippleStyle(Material::CenteredRipple);
    sendEmojiButton->setCornerRadius(8);
    sendEmojiButton->setFontSize(14);
    
    QtMaterialFlatButton *uploadKnowledgeButton = new QtMaterialFlatButton("📚 Knowledge");
    uploadKnowledgeButton->setMinimumHeight(40);
    uploadKnowledgeButton->setFixedWidth(130);
    uploadKnowledgeButton->setRole(Material::Default);
    uploadKnowledgeButton->setForegroundColor(QColor("#34d399"));
    uploadKnowledgeButton->setBackgroundColor(QColor("#1a3a2a"));
    uploadKnowledgeButton->setOverlayColor(QColor("#2a5a3a"));
    uploadKnowledgeButton->setRippleStyle(Material::CenteredRipple);
    uploadKnowledgeButton->setCornerRadius(8);
    uploadKnowledgeButton->setFontSize(13);
    
    m_voiceBtn = new QPushButton("🎤 按住说话", this);
    m_voiceBtn->setMinimumHeight(40);
    m_voiceBtn->setFixedWidth(120);
    m_voiceBtn->setStyleSheet(
        "QPushButton { background-color: #2a2a2a; color: #9ca3af; border: none; border-radius: 8px; font-size: 14px; }"
        "QPushButton:hover { background-color: #3a3a3a; }"
    );
    connect(m_voiceBtn, &QPushButton::pressed, this, &ChatWindow::onVoiceBtnPressed);
    connect(m_voiceBtn, &QPushButton::released, this, &ChatWindow::onVoiceBtnReleased);
    
    buttonLayout->addWidget(sendButton);
    buttonLayout->addWidget(m_voiceBtn);
    buttonLayout->addWidget(sendEmojiButton);
    buttonLayout->addWidget(sendImageButton);
    buttonLayout->addWidget(sendFileButton);
    buttonLayout->addWidget(uploadKnowledgeButton);
    
    if (chatId == 10009) {
        m_realtimeVoiceBtn = new QPushButton("📞 实时通话", this);
        m_realtimeVoiceBtn->setMinimumHeight(40);
        m_realtimeVoiceBtn->setFixedWidth(120);
        m_realtimeVoiceBtn->setStyleSheet(
            "QPushButton { background-color: #1a73e8; color: white; border: none; border-radius: 8px; font-size: 14px; }"
            "QPushButton:hover { background-color: #1557b0; }"
        );
        connect(m_realtimeVoiceBtn, &QPushButton::clicked, this, &ChatWindow::onRealtimeVoiceCall);
        buttonLayout->addWidget(m_realtimeVoiceBtn);
    }
    
    connect(sendEmojiButton, &QtMaterialFlatButton::clicked, this, &ChatWindow::onSendEmoji);
    
    inputLayout->addLayout(buttonLayout);
    
    inputWidget->setLayout(inputLayout);
    
    mainLayout->addWidget(inputWidget);
    
    chatWidget->setLayout(mainLayout);
    
    chatWidget->setProperty("chatId", chatId);
    chatWidget->setProperty("isGroup", isGroup);
    
    QtMaterialScrollBar *verticalScrollBar = new QtMaterialScrollBar;
    verticalScrollBar->setCanvasColor(QColor("#1a1a1a"));
    verticalScrollBar->setBackgroundColor(QColor("#2f2f2f"));
    verticalScrollBar->setSliderColor(QColor("#4a4a4a"));
    chatListWidget->setVerticalScrollBar(verticalScrollBar);
    
    chatComponents[chatWidget] = {chatListWidget, verticalScrollBar, memberListWidget};
    
    connect(sendButton, &QtMaterialRaisedButton::clicked, this, &ChatWindow::onSendMessage);
    connect(inputEdit, &QtMaterialTextField::returnPressed, this, &ChatWindow::onSendMessage);
    connect(sendImageButton, &QtMaterialFlatButton::clicked, this, &ChatWindow::onSendImage);
    connect(sendFileButton, &QtMaterialFlatButton::clicked, this, &ChatWindow::onSendFile);
    connect(uploadKnowledgeButton, &QtMaterialFlatButton::clicked, this, &ChatWindow::onUploadKnowledgeDoc);
    
    inputTextFields[chatWidget] = inputEdit;
    
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
    if (!item || !item->parent()) return;

    bool isGroup = (item->parent()->text(1) == "群组");
    int chatId = item->data(1, Qt::UserRole).toInt();
    QString chatName = item->text(1);

    QString key = generateChatKey(chatId, isGroup);
    unreadMessageCounts.remove(key);

    createChatWidget(chatId, chatName, isGroup);

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
    qDebug() << "ChatWindow: onReceiveMessage - Received message from" << fromId << ":" << message;
    
    // 检查是否是流式消息（包含特殊标记）
    bool isStreamChunk = message.startsWith("[STREAM_CHUNK]:");
    QString actualMessage = isStreamChunk ? message.mid(15) : message;
    
    bool isStreamEnd = actualMessage == "[STREAM_END]";
    bool isStreamClear = actualMessage == "[STREAM_CLEAR]";
    bool isStreamThinking = actualMessage.startsWith("[STREAM_THINKING]:");
    QString thinkingHint;
    if (isStreamThinking) {
        thinkingHint = actualMessage.mid(18);
    }
    
    if (isStreamClear) {
        qDebug() << "ChatWindow: Stream clear received, resetting message content for user" << fromId;
        QList<QListWidgetItem*> items = streamMessageItems.value(fromId);
        if (!items.isEmpty()) {
            QListWidgetItem* lastItem = items.last();
            QListWidget* chatListWidget = findChatListWidgetForUser(fromId);
            if (chatListWidget && lastItem) {
                MessageWidget* messageWidget = qobject_cast<MessageWidget*>(chatListWidget->itemWidget(lastItem));
                if (messageWidget) {
                    messageWidget->setMarkdownContent("");
                    lastItem->setSizeHint(messageWidget->sizeHint());
                    chatListWidget->updateGeometry();
                }
            }
        }
        return;
    }
    
    if (isStreamEnd) {
        qDebug() << "ChatWindow: Stream message ended, clearing stream message items for user" << fromId;
        if (streamMessageItems.contains(fromId)) {
            streamMessageItems.remove(fromId);
        }
        if (thinkingIndicatorItems.contains(fromId)) {
            QListWidgetItem* thinkingItem = thinkingIndicatorItems.take(fromId);
            QListWidget* chatListWidget = findChatListWidgetForUser(fromId);
            if (chatListWidget) {
                int row = chatListWidget->row(thinkingItem);
                if (row >= 0) {
                    chatListWidget->takeItem(row);
                    delete thinkingItem;
                }
            }
        }
        return;
    }
    
    if (isStreamThinking) {
        QListWidget* chatListWidget = findChatListWidgetForUser(fromId);
        if (chatListWidget) {
            if (thinkingIndicatorItems.contains(fromId)) {
                QListWidgetItem* thinkingItem = thinkingIndicatorItems.value(fromId);
                MessageWidget* thinkingWidget = qobject_cast<MessageWidget*>(chatListWidget->itemWidget(thinkingItem));
                if (thinkingWidget) {
                    thinkingWidget->setMarkdownContent(thinkingHint.isEmpty() ? "🤔 AI正在思考..." : thinkingHint);
                    thinkingItem->setSizeHint(thinkingWidget->sizeHint());
                    chatListWidget->updateGeometry();
                    scrollChatToBottom(chatListWidget);
                }
            } else {
                QListWidgetItem* thinkingItem = new QListWidgetItem();
                chatListWidget->addItem(thinkingItem);
                
                QString senderName = fromName.isEmpty() ? "AI Assistant" : fromName;
                QString displayText = thinkingHint.isEmpty() ? "🤔 AI正在思考..." : thinkingHint;
                MessageWidget* thinkingWidget = new MessageWidget(false, displayText, "", senderName, timestamp, this);
                thinkingItem->setSizeHint(thinkingWidget->sizeHint());
                chatListWidget->setItemWidget(thinkingItem, thinkingWidget);
                
                thinkingIndicatorItems.insert(fromId, thinkingItem);
                scrollChatToBottom(chatListWidget);
            }
        }
        return;
    }
    
    // 如果是流式消息，累积到现有消息项中
    if (isStreamChunk) {
        qDebug() << "ChatWindow: Processing stream message for user" << fromId;
        
        // 需要先找到对应的chatListWidget
        QListWidget* chatListWidget = findChatListWidgetForUser(fromId);
        qDebug() << "ChatWindow: findChatListWidgetForUser returned:" << (chatListWidget ? "valid" : "nullptr");
        
        if (chatListWidget) {
            // 使用 value() 方法避免自动插入空列表
            QList<QListWidgetItem*> items = streamMessageItems.value(fromId);
            qDebug() << "ChatWindow: chatListWidget is valid, streamMessageItems contains:" << streamMessageItems.contains(fromId) 
                     << ", items count:" << items.size();

            // 如果该用户还没有流式消息项
            if (items.isEmpty()) {
                // 检查是否有"正在思考"提示，如果没有则创建
                if (!thinkingIndicatorItems.contains(fromId)) {
                    qDebug() << "ChatWindow: Creating 'AI is thinking...' indicator for user" << fromId;
                    
                    // 创建"正在思考"提示项
                    QListWidgetItem* thinkingItem = new QListWidgetItem();
                    chatListWidget->addItem(thinkingItem);
                    
                    QString senderName = fromName.isEmpty() ? "AI Assistant" : fromName;
                    MessageWidget* thinkingWidget = new MessageWidget(false, "🤔 AI正在思考...", "", senderName, timestamp, this);
                    thinkingItem->setSizeHint(thinkingWidget->sizeHint());
                    chatListWidget->setItemWidget(thinkingItem, thinkingWidget);
                    
                    // 存储思考提示项
                    thinkingIndicatorItems.insert(fromId, thinkingItem);
                    
                    qDebug() << "ChatWindow: Thinking indicator created, chatListWidget->count():" << chatListWidget->count();
                    
                    scrollChatToBottom(chatListWidget);
                }
                
                // 只有当有实际内容时才创建消息项
                if (!actualMessage.isEmpty() && actualMessage != " " && actualMessage != "\n") {
                    qDebug() << "ChatWindow: First content received, removing thinking indicator and creating message item";
                    
                    // 移除思考提示
                    if (thinkingIndicatorItems.contains(fromId)) {
                        QListWidgetItem* thinkingItem = thinkingIndicatorItems.take(fromId);
                        int row = chatListWidget->row(thinkingItem);
                        if (row >= 0) {
                            chatListWidget->takeItem(row);
                            delete thinkingItem;
                        }
                    }
                    
                    // 创建实际消息项
                    QListWidgetItem* item = new QListWidgetItem();
                    chatListWidget->addItem(item);
                    
                    QString senderName = fromName.isEmpty() ? "AI Assistant" : fromName;
                    MessageWidget* messageWidget = new MessageWidget(false, actualMessage, "", senderName, timestamp, this);
                    item->setSizeHint(messageWidget->sizeHint());
                    chatListWidget->setItemWidget(item, messageWidget);
                    
                    // 添加到流式消息项列表
                    items.append(item);
                    streamMessageItems.insert(fromId, items);
                    
                    qDebug() << "ChatWindow: Message item created, chatListWidget->count():" << chatListWidget->count();
                    
                    scrollChatToBottom(chatListWidget);
                }
            } else {
                // 确保思考提示已移除
                if (thinkingIndicatorItems.contains(fromId)) {
                    QListWidgetItem* thinkingItem = thinkingIndicatorItems.take(fromId);
                    int row = chatListWidget->row(thinkingItem);
                    if (row >= 0) {
                        chatListWidget->takeItem(row);
                        delete thinkingItem;
                    }
                }
                
                // 获取最后一个消息项并追加内容
                QListWidgetItem* lastItem = items.last();
                if (lastItem) {
                    MessageWidget* messageWidget = qobject_cast<MessageWidget*>(chatListWidget->itemWidget(lastItem));
                    if (messageWidget) {
                        messageWidget->appendText(actualMessage);
                        lastItem->setSizeHint(messageWidget->sizeHint());
                        
                        // 强制更新chatListWidget的布局
                        chatListWidget->updateGeometry();
                        chatListWidget->repaint();
                        
                        scrollChatToBottom(chatListWidget);
                        
                        qDebug() << "ChatWindow: Stream chunk accumulated:" << actualMessage.length() << "chars";
                    } else {
                        qDebug() << "ChatWindow: ERROR - messageWidget is nullptr!";
                    }
                }
            }
        } else {
            qDebug() << "ChatWindow: ERROR - chatListWidget is nullptr, cannot display stream message!";
        }
        return;
    }
    
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
        addMessageToChatList(chatListWidget, false, message, senderAvatarPath, timeStr, fromName);
        
        // 如果是AI Bot的消息，添加到流式消息映射中以便后续累积
        if (fromId == 100) {
            QListWidgetItem* lastItem = chatListWidget->item(chatListWidget->count() - 1);
            if (lastItem) {
                streamMessageItems[fromId].append(lastItem);
                qDebug() << "ChatWindow: Added AI Bot message to stream tracking";
            }
        }
        
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
        addMessageToChatList(chatListWidget, false, message, senderAvatarPath, timeStr, userName);
        
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

void ChatWindow::onReceiveVoiceMessage(qint64 fromId, const QString &voiceUrl, int duration, const QString &fromName, const QString &timestamp) {
    qDebug() << "Received voice message from" << fromId << "(" << fromName << "):" << voiceUrl << "duration:" << duration;
    
    QString senderName = fromName.isEmpty() ? QString("用户 %1").arg(fromId) : fromName;
    
    QListWidget *chatListWidget = nullptr;
    QWidget *chatWidget = nullptr;
    
    for (int i = 0; i < chatTabWidget->count(); ++i) {
        if (chatTabWidget->widget(i)->property("chatId").toLongLong() == fromId &&
            chatTabWidget->widget(i)->property("isGroup").toBool() == false) {
            chatWidget = chatTabWidget->widget(i);
            if (chatComponents.contains(chatWidget)) {
                chatListWidget = chatComponents[chatWidget].chatListWidget;
            }
            break;
        }
    }
    
    if (!chatListWidget) {
        createChatWidget(fromId, senderName, false);
        
        for (int i = 0; i < chatTabWidget->count(); ++i) {
            if (chatTabWidget->widget(i)->property("chatId").toLongLong() == fromId &&
                chatTabWidget->widget(i)->property("isGroup").toBool() == false) {
                chatWidget = chatTabWidget->widget(i);
                if (chatComponents.contains(chatWidget)) {
                    chatListWidget = chatComponents[chatWidget].chatListWidget;
                }
                break;
            }
        }
    }
    
    if (chatListWidget) {
        QString timeStr = timestamp.isEmpty() ? 
            QDateTime::currentDateTime().toString("hh:mm") : timestamp;
        
        QString senderAvatarPath = getFriendAvatarPath(fromId);
        
        qDebug() << "onReceiveVoiceMessage: fromId=" << fromId << ", senderAvatarPath=" << senderAvatarPath;
        
        addVoiceMessageToChatList(chatListWidget, false, voiceUrl, duration, senderAvatarPath, timeStr, senderName);
        scrollChatToBottom(chatListWidget);
        
        if (chatTabWidget->currentWidget() != chatWidget) {
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
        
        // 检查当前用户是否是群组创建者
        QString userStatus = "群组成员";
        if (groupMap.contains(group.getId())) {
            const vector<GroupUser>& members = groupMap[group.getId()].getUsers();
            for (const GroupUser& member : members) {
                if (member.getId() == userId && member.getRole() == "creator") {
                    userStatus = "群主";
                    break;
                } else if (member.getId() == userId && member.getRole() == "admin") {
                    userStatus = "管理员";
                    break;
                }
            }
        }
        
        item->setText(2, userStatus);
        qDebug() << "[CRITICAL] Added group:" << groupName << "with user status:" << userStatus;
        
        qDebug() << "[CRITICAL] Added group to UI list:" << groupName;
    }
    
    // 展开群组节点
    groupRoot->setExpanded(true);
    
    // 刷新UI
    contactTreeWidget->update();
    contactTreeWidget->repaint();
    qDebug() << "[CRITICAL] Group list UI updated, expanded and repainted";

    // 更新已打开的群聊Tab中的成员列表
    for (int i = 0; i < chatTabWidget->count(); ++i) {
        QWidget *tabWidget = chatTabWidget->widget(i);
        if (tabWidget && tabWidget->property("isGroup").toBool()) {
            int groupId = tabWidget->property("chatId").toInt();
            if (groupMap.contains(groupId)) {
                auto it = chatComponents.find(tabWidget);
                if (it != chatComponents.end() && it->memberListWidget) {
                    QListWidget *memberList = it->memberListWidget;
                    memberList->clear();
                    
                    const vector<GroupUser>& members = groupMap[groupId].getUsers();
                    for (const GroupUser& member : members) {
                        QString memberName = QString::fromStdString(member.getName());
                        QString memberRole = QString::fromStdString(member.getRole());
                        QString display = memberName;
                        if (memberRole == "creator") {
                            display += " (群主)";
                        } else if (memberRole == "admin") {
                            display += " (管理员)";
                        }
                        memberList->addItem(display);
                    }
                    qDebug() << "Updated member list for group" << groupId << "with" << members.size() << "members";
                }
            }
        }
    }
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
        chatClient->requestGroupList(userId);
    } else {
        QMessageBox::warning(this, "失败", message);
    }
}

void ChatWindow::onInviteToGroup() {
    QtMaterialFlatButton *btn = qobject_cast<QtMaterialFlatButton*>(sender());
    int groupId = -1;

    if (btn) {
        groupId = btn->property("groupId").toInt();
    }

    if (groupId <= 0) {
        bool ok;
        QString groupIdStr = QInputDialog::getText(this, "邀请进群", "请输入要邀请加入的群ID：", QLineEdit::Normal, "", &ok);
        if (!ok || groupIdStr.isEmpty()) return;
        groupId = groupIdStr.toInt(&ok);
        if (!ok || groupId <= 0) {
            QMessageBox::warning(this, "警告", "请输入有效的群ID");
            return;
        }
    }

    bool ok2;
    int targetId = QInputDialog::getInt(this, "邀请加入群聊",
        "请输入要拉入群聊的用户ID（如 AI 导师 10001）：", 0, 1, 999999, 1, &ok2);

    if (ok2 && targetId > 0) {
        chatClient->inviteToGroup(userId, groupId, targetId);
    }
}

void ChatWindow::onInviteGroupResponse(bool success, const QString &message) {
    if (success) {
        QMessageBox::information(this, "成功", "邀请进群成功！");
        chatClient->requestGroupList(userId);
    } else {
        QMessageBox::warning(this, "失败", message);
    }
}

void ChatWindow::onCreateGroupResponse(bool success, const QString &message) {
    if (success) {
        QMessageBox::information(this, "成功", "创建群组成功！");
        chatClient->requestGroupList(userId);
    } else {
        QMessageBox::warning(this, "失败", message);
    }
}

void ChatWindow::onCreateInterviewGroup() {
    chatClient->createInterviewGroup(userId);
}

void ChatWindow::onInterviewGroupCreated(bool success, int groupId, const QString &groupName, const QString &message) {
    if (success) {
        QMessageBox::information(this, "模拟面试", 
            QString("已为您分配专属复试房间「%1」！\n请在群聊列表中查看并开始面试。").arg(groupName));
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
    
    if (item->parent() && item->parent()->text(0) == "群组") {
        int groupId = item->data(1, Qt::UserRole).toInt();
        QAction *inviteAction = menu->addAction("邀请进群");
        connect(inviteAction, &QAction::triggered, this, [this, groupId]() {
            bool ok;
            int targetId = QInputDialog::getInt(this, "邀请加入群聊",
                "请输入要拉入群聊的用户ID（如 AI 导师 10001）：", 0, 1, 999999, 1, &ok);
            if (ok && targetId > 0) {
                chatClient->inviteToGroup(userId, groupId, targetId);
            }
        });
    }
    
    menu->popup(contactTreeWidget->viewport()->mapToGlobal(pos));
}

void ChatWindow::onVoiceBtnPressed() {
    qDebug() << "onVoiceBtnPressed called, current recorder state:" << m_audioRecorder->state();
    qDebug() << "Audio input:" << m_audioRecorder->audioInput();
    qDebug() << "Output location:" << m_audioRecorder->outputLocation().toString();
    
    if (m_audioRecorder->state() == QAudioRecorder::StoppedState) {
        m_voiceBtn->setText("松开 发送");
        m_voiceBtn->setStyleSheet(
            "QPushButton { background-color: #4a4a4a; color: #ffffff; border: none; border-radius: 8px; font-size: 14px; }"
            "QPushButton:hover { background-color: #5a5a5a; }"
        );
        m_voiceRecordStartTime = QDateTime::currentMSecsSinceEpoch();
        m_audioRecorder->record();
        qDebug() << "Called record(), new state:" << m_audioRecorder->state();
        
        if (m_audioRecorder->error() != QMediaRecorder::NoError) {
            qDebug() << "Recorder error:" << m_audioRecorder->errorString();
        }
    } else {
        qDebug() << "Recorder not in StoppedState, current state:" << m_audioRecorder->state();
    }
}

void ChatWindow::onVoiceBtnReleased() {
    qDebug() << "onVoiceBtnReleased called, current recorder state:" << m_audioRecorder->state();
    
    if (m_audioRecorder->state() == QAudioRecorder::RecordingState) {
        qDebug() << "Stopping recorder...";
        m_audioRecorder->stop();
        qDebug() << "After stop(), recorder state:" << m_audioRecorder->state();
    } else {
        qDebug() << "Recorder not in RecordingState, might have failed to start";
    }
    
    m_voiceBtn->setText("🎤 按住说话");
    m_voiceBtn->setStyleSheet(
        "QPushButton { background-color: #2a2a2a; color: #9ca3af; border: none; border-radius: 8px; font-size: 14px; }"
        "QPushButton:hover { background-color: #3a3a3a; }"
    );
    
    qint64 duration = (QDateTime::currentMSecsSinceEpoch() - m_voiceRecordStartTime) / 1000;
    if (duration < 1) {
        qDebug() << "Voice message too short, ignored";
        m_pendingVoiceDuration = 0;
        m_pendingVoiceToId = -1;
        return;
    }
    
    m_pendingVoiceDuration = duration;
    
    QWidget *currentWidget = chatTabWidget->currentWidget();
    if (!currentWidget) {
        qDebug() << "No active chat window";
        m_pendingVoiceDuration = 0;
        m_pendingVoiceToId = -1;
        return;
    }
    
    int toId = currentWidget->property("chatId").toInt();
    bool isGroup = currentWidget->property("isGroup").toBool();
    
    if (isGroup) {
        qDebug() << "Voice message to group not supported yet";
        m_pendingVoiceDuration = 0;
        m_pendingVoiceToId = -1;
        return;
    }
    
    m_pendingVoiceToId = toId;
    qDebug() << "Voice recording stopped, waiting for file to be saved. Duration:" << duration << "s, toId:" << toId;
    
    QTimer::singleShot(200, this, &ChatWindow::uploadVoiceFile);
}

void ChatWindow::onAudioRecorderStateChanged(QAudioRecorder::State state) {
    qDebug() << "Audio recorder state changed to:" << state;
}

void ChatWindow::uploadVoiceFile() {
    if (m_pendingVoiceDuration <= 0 || m_pendingVoiceToId <= 0) {
        qDebug() << "Invalid pending voice data, skipping upload. duration:" << m_pendingVoiceDuration << "toId:" << m_pendingVoiceToId;
        return;
    }
    
    qint64 duration = m_pendingVoiceDuration;
    int toId = m_pendingVoiceToId;
    
    m_pendingVoiceDuration = 0;
    m_pendingVoiceToId = -1;
    
    QFile *audioFile = new QFile(m_audioFilePath);
    if (!audioFile->exists()) {
        qDebug() << "Audio file does not exist:" << m_audioFilePath;
        delete audioFile;
        return;
    }
    
    if (!audioFile->open(QIODevice::ReadOnly)) {
        qDebug() << "Failed to open audio file:" << m_audioFilePath;
        delete audioFile;
        return;
    }
    
    qDebug() << "Audio file opened successfully, size:" << audioFile->size() << "bytes";
    
    QHttpMultiPart *multiPart = new QHttpMultiPart(QHttpMultiPart::FormDataType);
    
    QHttpPart audioPart;
    audioPart.setHeader(QNetworkRequest::ContentTypeHeader, QVariant("audio/wav"));
    audioPart.setHeader(QNetworkRequest::ContentDispositionHeader, 
        QVariant("form-data; name=\"audio\"; filename=\"voice.wav\""));
    audioPart.setBodyDevice(audioFile);
    audioFile->setParent(multiPart);
    
    multiPart->append(audioPart);
    
    QHttpPart userIdPart;
    userIdPart.setHeader(QNetworkRequest::ContentDispositionHeader, QVariant("form-data; name=\"userId\""));
    userIdPart.setBody(QString::number(userId).toUtf8());
    multiPart->append(userIdPart);
    
    QHttpPart toIdPart;
    toIdPart.setHeader(QNetworkRequest::ContentDispositionHeader, QVariant("form-data; name=\"toId\""));
    toIdPart.setBody(QString::number(toId).toUtf8());
    multiPart->append(toIdPart);
    
    QHttpPart durationPart;
    durationPart.setHeader(QNetworkRequest::ContentDispositionHeader, QVariant("form-data; name=\"duration\""));
    durationPart.setBody(QString::number(duration).toUtf8());
    multiPart->append(durationPart);
    
    QNetworkRequest request(QUrl("http://127.0.0.1:8081/api/voice/upload"));
    QNetworkReply *reply = m_voiceUploadManager->post(request, multiPart);
    multiPart->setParent(reply);
    
    reply->setProperty("toId", toId);
    reply->setProperty("duration", QVariant::fromValue(duration));
    
    qDebug() << "Uploading voice file to server, toId:" << toId << ", duration:" << duration;
}

void ChatWindow::onVoiceUploadFinished(QNetworkReply *reply) {
    reply->deleteLater();
    
    if (reply->error() != QNetworkReply::NoError) {
        qDebug() << "Voice upload failed:" << reply->errorString();
        return;
    }
    
    QByteArray responseData = reply->readAll();
    QJsonDocument doc = QJsonDocument::fromJson(responseData);
    QJsonObject json = doc.object();
    
    if (json.value("success").toBool()) {
        QString voiceUrl = json.value("url").toString();
        int toId = reply->property("toId").toInt();
        int duration = reply->property("duration").toInt();
        
        qDebug() << "Voice uploaded successfully, URL:" << voiceUrl;
        
        chatClient->sendVoiceMessage(toId, voiceUrl, duration);
        
        QWidget *currentWidget = chatTabWidget->currentWidget();
        if (currentWidget && chatComponents.contains(currentWidget)) {
            QListWidget *chatListWidget = chatComponents[currentWidget].chatListWidget;
            QString timeStr = QDateTime::currentDateTime().toString("hh:mm");
            QString myAvatarPath = getMyAvatarPath();
            
            qDebug() << "Voice message - userName:" << userName << ", avatarPath:" << myAvatarPath;
            
            addVoiceMessageToChatList(chatListWidget, true, voiceUrl, duration, myAvatarPath, timeStr, userName);
            scrollChatToBottom(chatListWidget);
        }
    } else {
        qDebug() << "Voice upload failed:" << json.value("message").toString();
    }
}

void ChatWindow::onOpenFarm()
{
    if (!m_farmDialog) {
        m_farmDialog = new FarmDialog(userId, userName, chatClient, this);
    }
    m_farmDialog->exec();
}

void ChatWindow::onOpenKnowledgeGraph()
{
    KnowledgeGraphDialog *dialog = new KnowledgeGraphDialog(userId, this);
    dialog->setAttribute(Qt::WA_DeleteOnClose);
    dialog->exec();
}

void ChatWindow::onOpenDashboard()
{
    DashboardDialog *dialog = new DashboardDialog(userId, this);
    dialog->setAttribute(Qt::WA_DeleteOnClose);
    dialog->exec();
}

void ChatWindow::onOpenCompanionReading()
{
    if (!m_companionReadingDialog) {
        m_companionReadingDialog = new CompanionReadingDialog(userId, this);
    }
    m_companionReadingDialog->exec();
}

void ChatWindow::onOpenCodingAgent()
{
    QString hostEnv = qEnvironmentVariable("ERUITAH_SANDBOX_HOST", "");
    QString url;
    if (!hostEnv.isEmpty()) {
        url = QString("http://%1/ide?user_id=%2").arg(hostEnv).arg(userId);
    } else {
        url = QString("http://127.0.0.1:8001/ide?user_id=%1").arg(userId);
    }

    bool success = QDesktopServices::openUrl(QUrl(url));
    if (!success) {
        qDebug() << "Failed to open browser for URL:" << url;
    }
}

void ChatWindow::onOpenCareerDashboard()
{
    CareerDashboardDialog *dialog = new CareerDashboardDialog(userId, this);
    dialog->setAttribute(Qt::WA_DeleteOnClose);
    dialog->exec();
}

void ChatWindow::onOpenAiDocs()
{
    QString hostEnv = qEnvironmentVariable("BUTCANTHIC_HOST", "");
    QString url;
    if (!hostEnv.isEmpty()) {
        url = QString("http://%1/?userId=%2&authFrom=qt_client").arg(hostEnv).arg(userId);
    } else {
        url = QString("http://127.0.0.1:8002/?userId=%1&authFrom=qt_client").arg(userId);
    }

    bool success = QDesktopServices::openUrl(QUrl(url));
    if (!success) {
        QMessageBox::warning(this, QString::fromUtf8("打开失败"),
                             QString::fromUtf8("无法打开浏览器，请手动访问：\n%1").arg(url));
    }
}

void ChatWindow::onFarmPlantResponse(bool success, int plotId, const QString &message)
{
    if (m_farmDialog) {
        m_farmDialog->handlePlantResponse(success, plotId, message);
    }
}

void ChatWindow::onFarmAnswerResponse(bool success, int plotId, const QString &feedback, int score, bool canHarvest)
{
    if (m_farmDialog) {
        m_farmDialog->handleAnswerResponse(success, plotId, feedback, score, canHarvest);
    }
}

void ChatWindow::onFarmQueryResponse(const QJsonArray &plots, int coins, int exp)
{
    if (m_farmDialog) {
        m_farmDialog->updateUserStats(coins, exp);
        for (const QJsonValue &val : plots) {
            QJsonObject obj = val.toObject();
            m_farmDialog->updatePlotFromServer(
                obj["plotid"].toInt(),
                obj["state"].toInt(),
                obj["question"].toString(),
                obj["ownerid"].toInt(),
                obj["ownername"].toString(),
                obj["subject"].toString()
            );
        }
    }
}

void ChatWindow::onFarmHarvestResponse(bool success, int plotId, const QString &message, int coins)
{
    if (m_farmDialog) {
        m_farmDialog->handleFarmBroadcast(
            success ? QString("收菜成功！地块%1，%2 金币+%3").arg(plotId).arg(message).arg(coins)
                    : QString("收菜失败！地块%1，%2").arg(plotId).arg(message)
        );
    }
}

void ChatWindow::onFarmPlotHarvested(int plotId, int ownerId)
{
    if (m_farmDialog) {
        m_farmDialog->handlePlotHarvested(plotId, ownerId);
    }
}

void ChatWindow::onFarmBroadcastReceived(const QString &message)
{
    if (m_farmDialog) {
        m_farmDialog->handleFarmBroadcast(message);
    }
}

void ChatWindow::onCareerAdviceReceived(const QString &skills, const QString &resumeHighlight, const QString &learningAdvice)
{
    QJsonArray skillsArr;
    QStringList parts = skills.split(",", Qt::SkipEmptyParts);
    for (const QString &p : parts) {
        QString trimmed = p.trimmed();
        if (!trimmed.isEmpty()) {
            skillsArr.append(trimmed);
        }
    }

    QJsonObject record;
    record["skills"] = skillsArr;
    record["resume_highlight"] = resumeHighlight;
    record["next_suggestion"] = learningAdvice;
    record["category"] = QString::fromUtf8("职业档案");
    record["timestamp"] = QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm");
    CareerHistoryManager::instance().appendRecord(record);

    CareerAdvicePopup *popup = new CareerAdvicePopup(skills, resumeHighlight, learningAdvice);
    popup->showAtBottomRight();

    QPushButton *careerBtn = findChild<QPushButton*>();
    QList<QPushButton*> buttons = findChildren<QPushButton*>();
    for (auto *btn : buttons) {
        if (btn->text().contains("职业档案")) {
            btn->setStyleSheet(
                "QPushButton { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #dc2626, stop:1 #ef4444);"
                "  border: 2px solid #fbbf24; color: white; font-size: 13px; padding: 6px 12px;"
                "  border-radius: 4px; font-weight: bold; }"
                "QPushButton:hover { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #b91c1c, stop:1 #dc2626); }"
            );
            QTimer::singleShot(8000, this, [btn]() {
                btn->setStyleSheet(
                    "QPushButton { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #059669, stop:1 #10b981);"
                    "  border: none; color: white; font-size: 13px; padding: 6px 12px;"
                    "  border-radius: 4px; font-weight: bold; }"
                    "QPushButton:hover { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #047857, stop:1 #059669); }"
                    "QPushButton:pressed { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #065f46, stop:1 #047857); }"
                );
            });
            break;
        }
    }
}

void ChatWindow::closeEvent(QCloseEvent *event) {
    if (isLoggingOut) {
        event->accept();
        return;
    }
    
    if (QMessageBox::question(this, "Confirm Exit", "Are you sure you want to exit?") == QMessageBox::Yes) {
        chatClient->logout(userId);
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
// 发送图片 - 多线程优化版
void ChatWindow::onSendImage() {
    // 1. [主线程] 获取当前聊天状态
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
    
    // 2. [主线程] 选择文件
    QString imagePath = QFileDialog::getOpenFileName(
        this, "选择要发送的图片", "",
        "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif);;所有文件 (*.*)"
    );
    
    if (imagePath.isEmpty()) return;

    // 3. [主线程] 准备数据传入子线程 (防止线程竞争，复制一份数据)
    // 注意：不能在子线程里操作 chatTabWidget 或访问成员变量，必须拷贝一份
    QString myAvatarData = this->currentUserAvatarData;
    QString appDirPath = QCoreApplication::applicationDirPath(); // 路径也不能在子线程获取
    
    // 显示一个“处理中”的状态
    statusBarLabel->setText("正在处理图片...");

    // 4. [启动子线程] 使用 QtConcurrent 执行耗时操作
    QFutureWatcher<ImageProcessResult> *watcher = new QFutureWatcher<ImageProcessResult>(this);
    
    QFuture<ImageProcessResult> future = QtConcurrent::run([=]() -> ImageProcessResult {
        ImageProcessResult result;
        result.success = false;
        result.timeStr = QDateTime::currentDateTime().toString("hh:mm:ss");

        // --- 以下是耗时的图片处理逻辑 (都在子线程跑) ---
        
        QFile imageFile(imagePath);
        if (!imageFile.open(QIODevice::ReadOnly)) {
            result.message = "无法打开图片文件";
            return result;
        }
        QByteArray imageData = imageFile.readAll();
        imageFile.close();

        // 加载图片
        QImage image;
        if (!image.loadFromData(imageData)) {
            result.message = "图片加载失败或格式不支持";
            return result;
        }

        // 图片缩放 (耗时!)
        if (image.width() > 300 || image.height() > 300) {
            image = image.scaled(300, 300, Qt::KeepAspectRatio, Qt::SmoothTransformation);
        }

        // 压缩转 PNG (耗时!)
        QByteArray compressedData;
        QBuffer buffer(&compressedData);
        buffer.open(QIODevice::WriteOnly);
        
        // 将所有格式统一转换为PNG格式，确保HTML支持
        QString saveFormat = "PNG";
        bool saveSuccess = image.save(&buffer, saveFormat.toLatin1());
        buffer.close();
        
        if (!saveSuccess || compressedData.isEmpty()) {
            result.message = "图片压缩失败";
            return result;
        }

        // 构造发送消息 (Base64编码 耗时!)
        QString imageType = "png";
        
        // 直接生成Base64数据，避免不必要的QString复制
        QByteArray base64Data = compressedData.toBase64();
        
        // 进一步优化：将Base64编码后的大小限制为1MB，确保JSON能被服务器处理
        const qint64 MAX_BASE64_SIZE = 1024 * 1024; // 1MB
        
        // 如果Base64编码后大小超过1MB，尝试进一步压缩
        if (base64Data.size() > MAX_BASE64_SIZE) {
            // 尝试将质量降低到50%，进一步压缩
            QByteArray moreCompressedData;
            QBuffer moreCompressedBuffer(&moreCompressedData);
            moreCompressedBuffer.open(QIODevice::WriteOnly);
            
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
            QByteArray moreCompressedBase64 = moreCompressedData.toBase64();
            
            // 如果仍然超过大小限制，拒绝发送
            if (moreCompressedBase64.size() > MAX_BASE64_SIZE) {
                result.message = "图片过大，无法发送";
                result.success = false;
                return result;
            }
            
            // 使用更压缩的图片
            base64Data = moreCompressedBase64;
            compressedData = moreCompressedData;
        }
        
        // 构造图片消息格式: [IMAGE]imageType,base64data
        QString imageMessage = QString("[IMAGE]%1,%2").arg(imageType).arg(QString::fromLatin1(base64Data));
        result.message = imageMessage; // 这里存的是要发送的协议字符串
        
        // --- 处理头像 --- 
        QString myAvatarPath = ":/icons/user.png";
        if (!myAvatarData.isEmpty()) {
            // 头像数据存在，尝试解码
            QByteArray base64Bytes = myAvatarData.toUtf8();
            QString cleanBase64 = myAvatarData.trimmed();
            QByteArray decodedData = QByteArray::fromBase64(cleanBase64.toUtf8());
            
            if (!decodedData.isEmpty()) {
                // 检查是否仍然是Base64编码的数据
                if (decodedData.size() >= 4 && decodedData[0] == '/' && decodedData[1] == '9' && decodedData[2] == 'j' && decodedData[3] == '/') {
                    QByteArray doubleDecoded = QByteArray::fromBase64(decodedData);
                    if (!doubleDecoded.isEmpty()) {
                        decodedData = doubleDecoded;
                    }
                }
                
                // 尝试检测图片格式或使用常见格式
                QPixmap avatarPixmap;
                bool loadSuccess = false;
                loadSuccess = avatarPixmap.loadFromData(decodedData);
                if (!loadSuccess) {
                    loadSuccess = avatarPixmap.loadFromData(decodedData, "PNG");
                }
                if (!loadSuccess) {
                    loadSuccess = avatarPixmap.loadFromData(decodedData, "JPEG");
                }
                if (!loadSuccess) {
                    loadSuccess = avatarPixmap.loadFromData(decodedData, "BMP");
                }
                
                // 如果所有格式都尝试失败，使用默认头像
                if (loadSuccess && !avatarPixmap.isNull()) {
                    // 头像加载成功，保存到临时文件
                    QString tempAvatarPath = appDirPath + "/temp_avatar_current.png";
                    if (avatarPixmap.save(tempAvatarPath)) {
                        myAvatarPath = tempAvatarPath;
                    }
                }
            }
        }
        
        // 保存临时发送图用于本地显示
        QString tempSendPath = appDirPath + "/temp_sending_" + QString::number(QDateTime::currentMSecsSinceEpoch()) + ".png";
        if (image.save(tempSendPath)) {
            result.displayPath = tempSendPath;
        }
        
        result.success = true;
        return result;
    });
    
    // 5. [主线程] 监听结果
    connect(watcher, &QFutureWatcher<ImageProcessResult>::finished, this, [=]() {
        // 获取处理结果
        ImageProcessResult result = watcher->result();
        
        // 恢复状态栏
        statusBarLabel->setText("就绪");
        
        // 处理结果
        if (!result.success) {
            QMessageBox::warning(this, "发送失败", result.message);
        } else {
            // 查找对应的 chatListWidget
            // 注意：因为是异步的，需要再次确认当前窗口还是不是那个窗口，或者从 map 里找
            // 为了安全，我们重新获取一次
            if (chatComponents.contains(currentWidget)) {
                QListWidget *chatListWidget = chatComponents[currentWidget].chatListWidget;
                
                // 处理头像路径 (如果没有在子线程生成，就用默认的)
                QString finalAvatarPath = ":/icons/user.png"; // 默认头像
                if (!currentUserAvatarData.isEmpty()) {
                    // 头像数据存在，使用它
                    QString tempAvatarPath = QCoreApplication::applicationDirPath() + "/temp_avatar_current.png";
                    QFile avatarFile(tempAvatarPath);
                    if (avatarFile.exists()) {
                        finalAvatarPath = tempAvatarPath;
                    }
                }
                
                // 添加消息到聊天列表
                addMessageToChatList(chatListWidget, true, result.message, finalAvatarPath, result.timeStr);
                
                // 发送网络消息 (IO操作，非阻塞)
                if (isGroup) {
                    chatClient->sendGroupMessage(chatId, result.message);
                } else {
                    chatClient->sendMessage(chatId, result.message);
                }
            }
        }
        
        // 清理资源
        watcher->deleteLater();
    });
    
    // 启动任务
    watcher->setFuture(future);
}

// 发送表情包
void ChatWindow::onSendEmoji() {
    // 检查当前是否有选中的好友
    QWidget *currentWidget = chatTabWidget->currentWidget();
    if (!currentWidget) {
        QMessageBox::warning(this, "警告", "请先选择一个好友进行聊天");
        return;
    }

    // 如果已经有表情缓存，直接显示，不等待网络
    if (!emojiIconCache.isEmpty()) {
        showEmojiDialog();
        // 可以在后台静默更新，不阻塞用户
        // chatClient->requestEmojiList(userId); // 注释掉自动更新，减少网络请求
        return;
    }
    
    // 只有第一次为空时，才显示"加载中"并等待网络
    isLoadingEmojis = true;
    chatClient->requestEmojiList(userId);
    statusBarLabel->setText("正在加载表情包...");
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
        if (emojiIconCache.contains(emojiId)) {
            // 直接从缓存取图标，不进行 loadFromData
            emojiBtn->setIcon(emojiIconCache[emojiId]);
            emojiBtn->setIconSize(QSize(50, 50));
            qDebug() << "Successfully loaded cached icon for emoji:" << emojiId;
        } else {
            // 只有缓存里没有时，才临时解码（兜底策略）
            QPixmap pixmap;
            if (pixmap.loadFromData(imageBytes)) {
                QPixmap scaledPixmap = pixmap.scaled(50, 50, Qt::KeepAspectRatio, Qt::SmoothTransformation);
                emojiBtn->setIcon(QIcon(scaledPixmap));
                emojiBtn->setIconSize(QSize(50, 50));
                // 顺便补入缓存
                emojiIconCache[emojiId] = QIcon(scaledPixmap);
                qDebug() << "Successfully loaded and cached image for emoji:" << emojiId;
            } else {
                qDebug() << "Failed to load image for emoji:" << emojiId;
                // 如果图片加载失败，显示表情ID
                emojiBtn->setText(QString::number(emojiId));
            }
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
    qDebug() << "Received emoji list update with" << emojis.size() << "items";
    
    // 如果列表为空，直接结束
    if (emojis.isEmpty()) {
        statusBarLabel->setText("暂无表情包");
        if (isLoadingEmojis) {
            isLoadingEmojis = false;
            showEmojiDialog(); // 还是显示空对话框给用户看
        }
        return;
    }

    statusBarLabel->setText("正在后台解压表情包...");

    // 1. 启动子线程进行 Base64 解码和图片加载
    QFutureWatcher<QList<EmojiLoadResult>> *watcher = new QFutureWatcher<QList<EmojiLoadResult>>(this);

    QFuture<QList<EmojiLoadResult>> future = QtConcurrent::run([emojis]() -> QList<EmojiLoadResult> {
        QList<EmojiLoadResult> results;
        
        for (const QJsonObject &emojiObj : emojis) {
            if (emojiObj.contains("id") && emojiObj.contains("imageData")) {
                int emojiId = emojiObj["id"].toInt();
                QString imageData = emojiObj["imageData"].toString();
                
                // --- 耗时操作开始 (解码 Base64) ---
                QByteArray imageBytes = QByteArray::fromBase64(imageData.toLatin1());
                
                if (!imageBytes.isEmpty()) {
                    // --- 耗时操作 (加载图片) ---
                    QImage img;
                    // loadFromData 很慢，必须在子线程做
                    if (img.loadFromData(imageBytes)) {
                        // 顺便在这里做缩放，进一步减轻主线程负担
                        if (img.width() > 60 || img.height() > 60) {
                            img = img.scaled(60, 60, Qt::KeepAspectRatio, Qt::SmoothTransformation);
                        }
                        
                        EmojiLoadResult res;
                        res.id = emojiId;
                        res.image = img;
                        res.rawData = imageBytes;
                        results.append(res);
                    }
                }
            }
        }
        return results;
    });

    // 2. 监听子线程完成 (回到主线程)
    connect(watcher, &QFutureWatcher<QList<EmojiLoadResult>>::finished, this, [=]() {
        QList<EmojiLoadResult> results = watcher->result();
        
        qDebug() << "Background decoding finished, updating UI for" << results.size() << "emojis";
        
        // 清空旧数据，因为这是全量更新
        emojiList.clear();
        emojiIconCache.clear();
        
        // 快速更新到内存
        for (const EmojiLoadResult &res : results) {
            // 存原始数据 (用于发送)
            emojiList[res.id] = res.rawData;
            
            // 存图标缓存 (UI显示用) - 这里 QPixmap::fromImage 非常快
            emojiIconCache[res.id] = QIcon(QPixmap::fromImage(res.image));
        }

        statusBarLabel->setText("表情包加载完成");
        
        // 如果是用户点击触发的加载，现在数据好了，自动弹窗
        if (isLoadingEmojis) {
            isLoadingEmojis = false;
            showEmojiDialog();
        }
        
        watcher->deleteLater();
    });

    // 开始监控
    watcher->setFuture(future);
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
#ifdef _WIN32
        ::Sleep(5); // 使用全局命名空间的Sleep
#else
        QThread::msleep(5); // Linux平台使用QThread::msleep
#endif
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

// RAG知识库文档上传
void ChatWindow::onUploadKnowledgeDoc() {
    QString filePath = QFileDialog::getOpenFileName(
        this,
        "选择知识库文档",
        QString(),
        "文档文件 (*.txt *.pdf);;文本文件 (*.txt);;PDF文件 (*.pdf)"
    );

    if (filePath.isEmpty()) {
        return;
    }

    QFileInfo fileInfo(filePath);
    QString fileName = fileInfo.fileName();

    QFile *file = new QFile(filePath);
    if (!file->open(QIODevice::ReadOnly)) {
        QMessageBox::warning(this, "上传失败", "无法打开文件: " + fileName);
        delete file;
        return;
    }

    statusBarLabel->setText("正在向量化并上传知识库文档...");

    QHttpMultiPart *multiPart = new QHttpMultiPart(QHttpMultiPart::FormDataType);

    QHttpPart filePart;
    filePart.setHeader(
        QNetworkRequest::ContentDispositionHeader,
        QVariant(QString("form-data; name=\"file\"; filename=\"%1\"").arg(fileName))
    );
    filePart.setBodyDevice(file);
    file->setParent(multiPart);

    multiPart->append(filePart);

    QNetworkRequest request(QUrl("http://localhost:8081/api/rag/upload"));
    QNetworkReply *reply = ragNetworkManager->post(request, multiPart);
    multiPart->setParent(reply);

    reply->setProperty("fileName", fileName);
}

void ChatWindow::onRagUploadFinished(QNetworkReply *reply) {
    QString fileName = reply->property("fileName").toString();

    if (reply->error() == QNetworkReply::NoError) {
        QByteArray responseData = reply->readAll();
        qDebug() << "RAG upload response:" << responseData;

        statusBarLabel->setText("知识库文档上传成功: " + fileName);

        QMessageBox::information(
            this,
            "知识库更新成功",
            QString("文档 \"%1\" 已成功上传并索引到知识库！\n\n服务器响应: %2")
                .arg(fileName)
                .arg(QString::fromUtf8(responseData))
        );
    } else {
        QString errorMsg = reply->errorString();
        qDebug() << "RAG upload error:" << errorMsg;

        statusBarLabel->setText("知识库文档上传失败: " + fileName);

        QMessageBox::warning(
            this,
            "上传失败",
            QString("文档 \"%1\" 上传失败！\n\n错误信息: %2")
                .arg(fileName)
                .arg(errorMsg)
        );
    }

    reply->deleteLater();
}

void ChatWindow::scrollChatToBottom(QListWidget *listWidget)
{
    if (!listWidget) return;
    
    QTimer::singleShot(50, this, [listWidget]() {
        int lastRow = listWidget->count() - 1;
        if (lastRow >= 0) {
            QListWidgetItem *lastItem = listWidget->item(lastRow);
            if (lastItem) {
                listWidget->scrollToItem(lastItem, QAbstractItemView::ScrollHint::PositionAtBottom);
            }
        }
    });
}

// 加载现代化样式表
QString ChatWindow::loadModernStylesheet()
{
    QString style;
    
    // 全局背景与边框
    style += "QMainWindow, QMainWindow > QWidget { background-color: #1a1a1a; border: none; }";
    style += "QWidget { background-color: transparent; border: none; color: #ececec; }";
    
    // 文本控件
    style += "QTextBrowser { background-color: transparent; border: none; border-radius: 0; padding: 0; margin: 0; color: #ececec; selection-background-color: #3b82f6; selection-color: #ffffff; }";
    style += "QTextEdit { background-color: #2a2a2a; border: none; border-radius: 8px; padding: 12px; color: #ececec; selection-background-color: #3b82f6; selection-color: #ffffff; }";
    style += "QLineEdit { background-color: #2a2a2a; border: none; border-radius: 8px; padding: 8px 12px; color: #ececec; selection-background-color: #3b82f6; selection-color: #ffffff; }";
    style += "QLineEdit:focus { border: 1px solid #3b82f6; }";
    
    // 列表控件
    style += "QListWidget { background-color: transparent; border: none; outline: none; padding: 0; margin: 0; }";
    style += "QListWidget::item { background-color: transparent; border: none; padding: 0; margin: 0; }";
    style += "QListWidget::item:selected, QListWidget::item:hover { background-color: transparent; }";
    
    // 树形控件
    style += "QTreeWidget { background-color: #1a1a1a; border: none; border-right: 1px solid #2f2f2f; outline: none; padding: 0; margin: 0; color: #ececec; }";
    style += "QTreeWidget::item { background-color: transparent; border: none; padding: 8px 4px; margin: 0; color: #ececec; }";
    style += "QTreeWidget::item:selected { background-color: #2d3748; color: #60a5fa; }";
    style += "QTreeWidget::item:hover { background-color: #2a2a2a; }";
    style += "QTreeWidget::branch { background-color: transparent; border: none; }";
    
    // 滚动区域
    style += "QScrollArea { background-color: transparent; border: none; }";
    style += "QScrollArea > QWidget > QWidget { background-color: transparent; }";
    
    // 标签页
    style += "QTabWidget::pane { border: none; background-color: transparent; top: -1px; }";
    style += "QTabBar::tab { background-color: transparent; border: none; border-bottom: 2px solid transparent; padding: 12px 20px; margin: 0 4px; color: #9ca3af; font-weight: 500; }";
    style += "QTabBar::tab:selected { color: #60a5fa; border-bottom: 2px solid #3b82f6; }";
    style += "QTabBar::tab:hover { color: #ececec; background-color: rgba(59, 130, 246, 0.1); }";
    
    // 按钮
    style += "QPushButton { background-color: #2a2a2a; border: none; border-radius: 6px; padding: 8px 16px; color: #ececec; font-weight: 500; }";
    style += "QPushButton:hover { background-color: #3a3a3a; }";
    style += "QPushButton:pressed { background-color: #1a1a1a; }";
    style += "QPushButton:disabled { background-color: #1a1a1a; color: #4a4a4a; }";
    
    // 分割器
    style += "QSplitter::handle { background-color: #2f2f2f; border: none; }";
    style += "QSplitter::handle:horizontal { width: 1px; }";
    style += "QSplitter::handle:vertical { height: 1px; }";
    style += "QSplitter::handle:hover { background-color: #3b82f6; }";
    
    // 标签
    style += "QLabel { background-color: transparent; border: none; color: #ececec; }";
    
    // 状态栏
    style += "QStatusBar { background-color: #1a1a1a; border: none; border-top: 1px solid #2f2f2f; color: #9ca3af; }";
    style += "QStatusBar::item { border: none; }";
    
    // 滚动条 - 极简现代风格
    style += "QScrollBar:vertical { background-color: transparent; width: 8px; margin: 0; padding: 0; border: none; }";
    style += "QScrollBar::handle:vertical { background-color: rgba(156, 163, 175, 0.3); min-height: 40px; border-radius: 4px; margin: 2px; }";
    style += "QScrollBar::handle:vertical:hover { background-color: rgba(156, 163, 175, 0.5); }";
    style += "QScrollBar::handle:vertical:pressed { background-color: rgba(59, 130, 246, 0.7); }";
    style += "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; background-color: transparent; border: none; }";
    style += "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background-color: transparent; border: none; }";
    
    style += "QScrollBar:horizontal { background-color: transparent; height: 8px; margin: 0; padding: 0; border: none; }";
    style += "QScrollBar::handle:horizontal { background-color: rgba(156, 163, 175, 0.3); min-width: 40px; border-radius: 4px; margin: 2px; }";
    style += "QScrollBar::handle:horizontal:hover { background-color: rgba(156, 163, 175, 0.5); }";
    style += "QScrollBar::handle:horizontal:pressed { background-color: rgba(59, 130, 246, 0.7); }";
    style += "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; background-color: transparent; border: none; }";
    style += "QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background-color: transparent; border: none; }";
    
    // 菜单
    style += "QMenu { background-color: #2a2a2a; border: 1px solid #2f2f2f; border-radius: 8px; padding: 8px 0; color: #ececec; }";
    style += "QMenu::item { padding: 8px 24px; border-radius: 0; }";
    style += "QMenu::item:selected { background-color: #3b82f6; }";
    style += "QMenu::separator { height: 1px; background-color: #2f2f2f; margin: 4px 8px; }";
    
    // 工具提示
    style += "QToolTip { background-color: #2a2a2a; border: 1px solid #2f2f2f; border-radius: 6px; padding: 6px 10px; color: #ececec; }";
    
    return style;
}

void ChatWindow::onRealtimeVoiceCall()
{
    if (m_realtimeVoiceDialog) {
        if (m_realtimeVoiceDialog->isVisible()) {
            m_realtimeVoiceDialog->raise();
            m_realtimeVoiceDialog->activateWindow();
            return;
        }
        m_realtimeVoiceDialog->deleteLater();
        m_realtimeVoiceDialog = nullptr;
    }
    
    m_realtimeVoiceDialog = new RealtimeVoiceDialog(userId, 10009, this);
    connect(m_realtimeVoiceDialog, &QDialog::finished, this, [this]() {
        if (m_realtimeVoiceDialog) {
            m_realtimeVoiceDialog->deleteLater();
            m_realtimeVoiceDialog = nullptr;
        }
    });
    connect(m_realtimeVoiceDialog, &QObject::destroyed, this, [this]() {
        m_realtimeVoiceDialog = nullptr;
    });
    
    m_realtimeVoiceDialog->show();
    m_realtimeVoiceDialog->startSession();
}

void ChatWindow::onRealtimeVoiceCallEnded()
{
    if (m_realtimeVoiceDialog) {
        m_realtimeVoiceDialog->close();
    }
}

void ChatWindow::mousePressEvent(QMouseEvent *event)
{
    if (event->button() == Qt::LeftButton) {
        QWidget *child = childAt(event->pos());
        if (!child || child == m_titleBar || child == centralWidget()) {
            if (QWindow *w = windowHandle()) {
                w->startSystemMove();
            }
            event->accept();
            return;
        }
    }
    QMainWindow::mousePressEvent(event);
}