#ifndef REALTIMEVOICEDIALOG_H
#define REALTIMEVOICEDIALOG_H

#include <QDialog>
#include <QWebSocket>
#include <QAudioInput>
#include <QAudioOutput>
#include <QIODevice>
#include <QTimer>
#include <QLabel>
#include <QPushButton>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QBuffer>
#include <QByteArray>
#include <QQueue>
#include <QElapsedTimer>

class RealtimeVoiceDialog : public QDialog
{
    Q_OBJECT

public:
    explicit RealtimeVoiceDialog(int userId, int botId, QWidget *parent = nullptr);
    ~RealtimeVoiceDialog();

    void startSession();
    void stopSession();

protected:
    void closeEvent(QCloseEvent *event) override;

signals:
    void sessionEnded();

private slots:
    void onConnected();
    void onDisconnected();
    void onTextMessageReceived(const QString &message);
    void onBinaryMessageReceived(const QByteArray &message);
    void onError(QAbstractSocket::SocketError error);
    
    void onAudioDataReady();
    void onAudioStateChanged(QAudio::State state);
    
    void processAudioOutput();
    void checkVad();
    void updateUi();

private:
    void setupUi();
    void connectWebSocket();
    void disconnectWebSocket();
    void startAudioCapture();
    void stopAudioCapture();
    void startAudioPlayback();
    void stopAudioPlayback();
    void sendJsonMessage(const QString &type, const QVariantMap &data);
    double calculateRms(const QByteArray &audioData);
    
    int m_userId;
    int m_botId;
    QString m_botName;
    
    QWebSocket *m_webSocket;
    QString m_webSocketUrl;
    bool m_isConnected;
    bool m_isSessionActive;
    
    QAudioInput *m_audioInput;
    QIODevice *m_audioInputDevice;
    QAudioFormat m_inputFormat;
    
    QAudioOutput *m_audioOutput;
    QIODevice *m_audioOutputDevice;
    QAudioFormat m_outputFormat;
    QQueue<QByteArray> m_audioOutputQueue;
    QByteArray m_audioOutputBuffer;
    
    QTimer *m_vadTimer;
    QTimer *m_uiUpdateTimer;
    QElapsedTimer m_lastVoiceTime;
    
    double m_noiseThreshold;
    int m_silenceCount;
    int m_voiceCount;
    bool m_isSpeaking;
    bool m_isAiSpeaking;
    
    QLabel *m_statusLabel;
    QLabel *m_userTranscriptLabel;
    QLabel *m_aiResponseLabel;
    QPushButton *m_endButton;
    
    QString m_currentUserText;
    QString m_currentAiText;
};

#endif // REALTIMEVOICEDIALOG_H
