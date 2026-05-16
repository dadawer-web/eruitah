#include "realtimevoicedialog.h"
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QDebug>
#include <QCoreApplication>
#include <QtMath>

RealtimeVoiceDialog::RealtimeVoiceDialog(int userId, int botId, QWidget *parent)
    : QDialog(parent)
    , m_userId(userId)
    , m_botId(botId)
    , m_ttsProvider("xiaomi")
    , m_ttsVoice("冰糖")
    , m_webSocket(nullptr)
    , m_webSocketUrl("ws://localhost:8081/api/voice/stream")
    , m_isConnected(false)
    , m_isSessionActive(false)
    , m_audioInput(nullptr)
    , m_audioInputDevice(nullptr)
    , m_audioOutput(nullptr)
    , m_audioOutputDevice(nullptr)
    , m_vadTimer(nullptr)
    , m_uiUpdateTimer(nullptr)
    , m_noiseThreshold(500.0)
    , m_silenceCount(0)
    , m_voiceCount(0)
    , m_isSpeaking(false)
    , m_isAiSpeaking(false)
{
    m_botName = (botId == 10009) ? "心理委员" : "AI助手";
    
    m_inputFormat.setSampleRate(16000);
    m_inputFormat.setChannelCount(1);
    m_inputFormat.setSampleSize(16);
    m_inputFormat.setCodec("audio/pcm");
    m_inputFormat.setByteOrder(QAudioFormat::LittleEndian);
    m_inputFormat.setSampleType(QAudioFormat::SignedInt);
    
    m_outputFormat.setSampleRate(24000);
    m_outputFormat.setChannelCount(1);
    m_outputFormat.setSampleSize(16);
    m_outputFormat.setCodec("audio/pcm");
    m_outputFormat.setByteOrder(QAudioFormat::LittleEndian);
    m_outputFormat.setSampleType(QAudioFormat::SignedInt);
    
    setupUi();
    
    m_vadTimer = new QTimer(this);
    connect(m_vadTimer, &QTimer::timeout, this, &RealtimeVoiceDialog::checkVad);
    
    m_uiUpdateTimer = new QTimer(this);
    connect(m_uiUpdateTimer, &QTimer::timeout, this, &RealtimeVoiceDialog::updateUi);
}

RealtimeVoiceDialog::~RealtimeVoiceDialog()
{
    stopSession();
    qDebug() << "RealtimeVoiceDialog 析构函数";
}

void RealtimeVoiceDialog::closeEvent(QCloseEvent *event)
{
    qDebug() << "实时语音对话框关闭";
    stopSession();
    QDialog::closeEvent(event);
}

void RealtimeVoiceDialog::setupUi()
{
    setWindowTitle(QString("实时语音通话 - %1").arg(m_botName));
    setMinimumSize(400, 300);
    
    QVBoxLayout *mainLayout = new QVBoxLayout(this);
    mainLayout->setSpacing(15);
    mainLayout->setContentsMargins(20, 20, 20, 20);
    
    m_statusLabel = new QLabel("正在连接...");
    m_statusLabel->setAlignment(Qt::AlignCenter);
    m_statusLabel->setStyleSheet("font-size: 16px; font-weight: bold; color: #333;");
    mainLayout->addWidget(m_statusLabel);
    
    m_userTranscriptLabel = new QLabel("你的话：");
    m_userTranscriptLabel->setWordWrap(true);
    m_userTranscriptLabel->setStyleSheet("font-size: 14px; color: #666; background: #f0f0f0; padding: 10px; border-radius: 8px;");
    mainLayout->addWidget(m_userTranscriptLabel);
    
    m_aiResponseLabel = new QLabel(QString("%1：").arg(m_botName));
    m_aiResponseLabel->setWordWrap(true);
    m_aiResponseLabel->setStyleSheet("font-size: 14px; color: #333; background: #e3f2fd; padding: 10px; border-radius: 8px;");
    mainLayout->addWidget(m_aiResponseLabel);
    
    m_endButton = new QPushButton("结束通话");
    m_endButton->setStyleSheet("QPushButton { padding: 10px 20px; font-size: 14px; border-radius: 5px; background: #f44336; color: white; }");
    connect(m_endButton, &QPushButton::clicked, this, &QDialog::reject);
    mainLayout->addWidget(m_endButton);
    
    setLayout(mainLayout);
}

void RealtimeVoiceDialog::startSession()
{
    connectWebSocket();
    m_uiUpdateTimer->start(100);
}

void RealtimeVoiceDialog::stopSession()
{
    qDebug() << "停止实时语音会话... m_isSessionActive =" << m_isSessionActive;
    
    if (!m_isSessionActive) {
        qDebug() << "会话已停止，跳过";
        return;
    }
    
    m_isSessionActive = false;
    
    if (m_uiUpdateTimer) {
        m_uiUpdateTimer->stop();
    }
    if (m_vadTimer) {
        m_vadTimer->stop();
    }
    
    stopAudioCapture();
    stopAudioPlayback();
    
    if (m_webSocket) {
        if (m_isConnected) {
            sendJsonMessage("stop", QVariantMap());
        }
        m_webSocket->close();
        delete m_webSocket;
        m_webSocket = nullptr;
    }
    m_isConnected = false;
    
    qDebug() << "实时语音会话已停止";
}

void RealtimeVoiceDialog::connectWebSocket()
{
    m_webSocket = new QWebSocket();
    
    connect(m_webSocket, &QWebSocket::connected, this, &RealtimeVoiceDialog::onConnected);
    connect(m_webSocket, &QWebSocket::disconnected, this, &RealtimeVoiceDialog::onDisconnected);
    connect(m_webSocket, &QWebSocket::textMessageReceived, this, &RealtimeVoiceDialog::onTextMessageReceived);
    connect(m_webSocket, &QWebSocket::binaryMessageReceived, this, &RealtimeVoiceDialog::onBinaryMessageReceived);
    connect(m_webSocket, QOverload<QAbstractSocket::SocketError>::of(&QWebSocket::error), this, &RealtimeVoiceDialog::onError);
    
    m_webSocket->open(QUrl(m_webSocketUrl));
}

void RealtimeVoiceDialog::disconnectWebSocket()
{
    if (m_webSocket) {
        m_webSocket->close();
        delete m_webSocket;
        m_webSocket = nullptr;
    }
    m_isConnected = false;
}

void RealtimeVoiceDialog::startAudioCapture()
{
    if (m_audioInput) {
        stopAudioCapture();
    }
    
    QAudioDeviceInfo inputDevice = QAudioDeviceInfo::defaultInputDevice();
    if (!inputDevice.isFormatSupported(m_inputFormat)) {
        qWarning() << "Default input format not supported, trying nearest";
        m_inputFormat = inputDevice.nearestFormat(m_inputFormat);
    }
    
    m_audioInput = new QAudioInput(m_inputFormat, nullptr);
    m_audioInput->setBufferSize(6400);
    
    m_audioInputDevice = m_audioInput->start();
    connect(m_audioInputDevice, &QIODevice::readyRead, this, &RealtimeVoiceDialog::onAudioDataReady);
    
    if (m_vadTimer) {
        m_vadTimer->start(50);
    }
    
    qDebug() << "Audio capture started, sample rate:" << m_inputFormat.sampleRate();
}

void RealtimeVoiceDialog::stopAudioCapture()
{
    if (!m_audioInput && !m_audioInputDevice) {
        return;
    }
    
    if (m_vadTimer) {
        m_vadTimer->stop();
    }
    
    if (m_audioInputDevice) {
        disconnect(m_audioInputDevice, &QIODevice::readyRead, this, &RealtimeVoiceDialog::onAudioDataReady);
        m_audioInputDevice = nullptr;
    }
    
    if (m_audioInput) {
        m_audioInput->stop();
        m_audioInput->reset();
        delete m_audioInput;
        m_audioInput = nullptr;
    }
    
    qDebug() << "Audio capture stopped";
}

void RealtimeVoiceDialog::startAudioPlayback()
{
    if (m_audioOutput) {
        stopAudioPlayback();
    }
    
    QAudioDeviceInfo outputDevice = QAudioDeviceInfo::defaultOutputDevice();
    if (!outputDevice.isFormatSupported(m_outputFormat)) {
        qWarning() << "Default output format not supported, trying nearest";
        m_outputFormat = outputDevice.nearestFormat(m_outputFormat);
    }
    
    m_audioOutput = new QAudioOutput(m_outputFormat, nullptr);
    m_audioOutput->setBufferSize(8192);
    
    m_audioOutputDevice = m_audioOutput->start();
    
    qDebug() << "Audio playback started, sample rate:" << m_outputFormat.sampleRate();
}

void RealtimeVoiceDialog::stopAudioPlayback()
{
    if (!m_audioOutput && !m_audioOutputDevice && m_audioOutputBuffer.isEmpty()) {
        return;
    }
    
    if (m_audioOutput) {
        m_audioOutput->stop();
        m_audioOutput->reset();
        delete m_audioOutput;
        m_audioOutput = nullptr;
    }
    m_audioOutputDevice = nullptr;
    
    m_audioOutputQueue.clear();
    m_audioOutputBuffer.clear();
    m_isAiSpeaking = false;
    
    qDebug() << "Audio playback stopped";
}

void RealtimeVoiceDialog::onConnected()
{
    m_isConnected = true;
    m_statusLabel->setText("已连接，正在启动会话...");
    qDebug() << "WebSocket connected";

    QVariantMap startData;
    startData["userId"] = m_userId;
    startData["botId"] = m_botId;

    QVariantMap asrConfig;
    asrConfig["provider"] = "alibaba";
    asrConfig["model"] = "paraformer-realtime-v2";
    startData["asr_config"] = asrConfig;

    QVariantMap ttsConfig;
    ttsConfig["provider"] = m_ttsProvider.isEmpty() ? "alibaba" : m_ttsProvider;
    ttsConfig["voice"] = m_ttsVoice.isEmpty() ? "Cherry" : m_ttsVoice;
    startData["tts_config"] = ttsConfig;

    sendJsonMessage("start", startData);
}

void RealtimeVoiceDialog::onDisconnected()
{
    m_isConnected = false;
    m_statusLabel->setText("连接已断开");
    stopAudioCapture();
    stopAudioPlayback();
    qDebug() << "WebSocket disconnected";
}

void RealtimeVoiceDialog::onTextMessageReceived(const QString &message)
{
    QJsonDocument doc = QJsonDocument::fromJson(message.toUtf8());
    if (doc.isNull() || !doc.isObject()) return;
    
    QJsonObject json = doc.object();
    QString type = json["type"].toString();
    
    if (type == "connected") {
        qDebug() << "Server confirmed connection";
    }
    else if (type == "session_started") {
        m_isSessionActive = true;
        m_statusLabel->setText(QString("正在与 %1 通话中...").arg(m_botName));
        startAudioCapture();
        startAudioPlayback();
    }
    else if (type == "asr_result") {
        QString text = json["text"].toString();
        bool isEnd = json["isEnd"].toBool();
        
        if (isEnd) {
            m_currentUserText = text;
            m_userTranscriptLabel->setText(QString("你：%1").arg(text));
        } else {
            m_userTranscriptLabel->setText(QString("你（正在说）：%1").arg(text));
        }
    }
    else if (type == "llm_start") {
        m_currentAiText.clear();
        m_aiResponseLabel->setText(QString("%1：正在思考...").arg(m_botName));
    }
    else if (type == "llm_chunk") {
        QString chunk = json["text"].toString();
        m_currentAiText += chunk;
        m_aiResponseLabel->setText(QString("%1：%2").arg(m_botName, m_currentAiText));
    }
    else if (type == "llm_end") {
        m_aiResponseLabel->setText(QString("%1：%2").arg(m_botName, m_currentAiText));
    }
    else if (type == "session_stopped") {
        m_statusLabel->setText("会话已结束");
        stopAudioCapture();
        stopAudioPlayback();
    }
    else if (type == "error") {
        QString errorMsg = json["message"].toString();
        m_statusLabel->setText(QString("错误：%1").arg(errorMsg));
        qWarning() << "Server error:" << errorMsg;
    }
}

void RealtimeVoiceDialog::onBinaryMessageReceived(const QByteArray &message)
{
    if (m_audioOutputDevice) {
        m_audioOutputQueue.enqueue(message);
        processAudioOutput();
        m_isAiSpeaking = true;
    }
}

void RealtimeVoiceDialog::onError(QAbstractSocket::SocketError error)
{
    Q_UNUSED(error);
    m_statusLabel->setText(QString("连接错误：%1").arg(m_webSocket->errorString()));
    qWarning() << "WebSocket error:" << m_webSocket->errorString();
}

void RealtimeVoiceDialog::onAudioDataReady()
{
    if (!m_audioInputDevice || !m_webSocket || !m_isConnected) return;
    
    QByteArray audioData = m_audioInputDevice->readAll();
    if (audioData.isEmpty()) return;
    
    if (m_webSocket->isValid()) {
        m_webSocket->sendBinaryMessage(audioData);
    }
}

void RealtimeVoiceDialog::onAudioStateChanged(QAudio::State state)
{
    qDebug() << "Audio state changed:" << state;
}

void RealtimeVoiceDialog::processAudioOutput()
{
    if (!m_audioOutputDevice) return;
    
    while (!m_audioOutputQueue.isEmpty()) {
        QByteArray chunk = m_audioOutputQueue.dequeue();
        m_audioOutputBuffer.append(chunk);
    }
    
    if (!m_audioOutputBuffer.isEmpty()) {
        int bytesWritten = m_audioOutputDevice->write(m_audioOutputBuffer);
        if (bytesWritten > 0) {
            m_audioOutputBuffer.remove(0, bytesWritten);
        }
    }
}

void RealtimeVoiceDialog::checkVad()
{
    if (!m_audioInput || !m_audioInputDevice) return;
    
    QByteArray audioData = m_audioInputDevice->peek(3200);
    if (audioData.size() < 3200) return;
    
    double rms = calculateRms(audioData);
    
    bool isVoice = rms > m_noiseThreshold;
    
    if (isVoice) {
        m_voiceCount++;
        m_silenceCount = 0;
        m_lastVoiceTime.start();
        
        if (m_voiceCount > 3 && !m_isSpeaking) {
            m_isSpeaking = true;
        }
    } else {
        m_silenceCount++;
        m_voiceCount = 0;
        
        if (m_silenceCount > 20 && m_isSpeaking) {
            m_isSpeaking = false;
        }
    }
}

void RealtimeVoiceDialog::updateUi()
{
    if (m_isSpeaking) {
        m_statusLabel->setText(QString("正在与 %1 通话中... (你在说话)").arg(m_botName));
    } else {
        m_statusLabel->setText(QString("正在与 %1 通话中...").arg(m_botName));
    }
}

void RealtimeVoiceDialog::sendJsonMessage(const QString &type, const QVariantMap &data)
{
    if (!m_webSocket || !m_isConnected) return;
    
    QJsonObject json;
    json["action"] = type;
    for (auto it = data.begin(); it != data.end(); ++it) {
        json[it.key()] = QJsonValue::fromVariant(it.value());
    }
    
    QJsonDocument doc(json);
    m_webSocket->sendTextMessage(doc.toJson(QJsonDocument::Compact));
}

double RealtimeVoiceDialog::calculateRms(const QByteArray &audioData)
{
    if (audioData.size() < 2) return 0.0;
    
    const qint16 *samples = reinterpret_cast<const qint16 *>(audioData.constData());
    int sampleCount = audioData.size() / 2;
    
    double sum = 0.0;
    for (int i = 0; i < sampleCount; ++i) {
        double sample = static_cast<double>(samples[i]);
        sum += sample * sample;
    }
    
    return qSqrt(sum / sampleCount);
}
