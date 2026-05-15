package com.chat.ai.websocket;

import com.alibaba.dashscope.audio.asr.recognition.Recognition;
import com.alibaba.dashscope.audio.asr.recognition.RecognitionParam;
import com.alibaba.dashscope.audio.asr.recognition.RecognitionResult;
import com.alibaba.dashscope.audio.qwen_tts_realtime.*;
import com.alibaba.dashscope.common.ResultCallback;
import com.chat.ai.config.VoiceConfig;
import com.chat.ai.service.AiPersonaRegistry;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.messages.SystemMessage;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.*;
import org.springframework.web.socket.handler.BinaryWebSocketHandler;
import reactor.core.Disposable;
import reactor.core.publisher.Flux;

import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.util.Base64;
import java.util.Map;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.locks.ReentrantLock;

@Slf4j
@Component
public class RealtimeVoiceWebSocketHandler extends BinaryWebSocketHandler {

    private final VoiceConfig voiceConfig;
    private final ChatClient fastChatClient;
    private final ObjectMapper objectMapper;

    private final Map<String, SessionContext> sessions = new ConcurrentHashMap<>();

    private static final int SAMPLE_RATE = 16000;
    private static final int AUDIO_CHUNK_SIZE = 3200;

    public RealtimeVoiceWebSocketHandler(VoiceConfig voiceConfig, ChatClient fastChatClient) {
        this.voiceConfig = voiceConfig;
        this.fastChatClient = fastChatClient;
        this.objectMapper = new ObjectMapper();
    }

    @Override
    public void afterConnectionEstablished(WebSocketSession session) throws Exception {
        String sessionId = session.getId();
        log.info("[实时语音] WebSocket连接建立: sessionId={}", sessionId);

        SessionContext ctx = new SessionContext(sessionId, session);
        sessions.put(sessionId, ctx);

        sendJsonMessage(session, "connected", Map.of("sessionId", sessionId));
    }

    @Override
    protected void handleBinaryMessage(WebSocketSession session, BinaryMessage message) throws Exception {
        String sessionId = session.getId();
        SessionContext ctx = sessions.get(sessionId);

        if (ctx == null || ctx.isInterrupted.get() || ctx.isStopped.get()) {
            return;
        }

        if (!ctx.asrReady.get()) {
            return;
        }

        ByteBuffer payload = message.getPayload();
        byte[] audioData = new byte[payload.remaining()];
        payload.get(audioData);

        if (ctx.recognizer != null && ctx.asrCallback != null) {
            try {
                ByteBuffer audioBuffer = ByteBuffer.wrap(audioData);
                ctx.recognizer.sendAudioFrame(audioBuffer);
            } catch (Exception e) {
                if (e.getMessage() != null && e.getMessage().contains("State invalid")) {
                    log.warn("[实时语音] ASR未就绪，丢弃音频帧");
                } else {
                    log.error("[实时语音] 发送音频帧失败: {}", e.getMessage());
                }
            }
        }
    }

    @Override
    protected void handleTextMessage(WebSocketSession session, TextMessage message) {
        String sessionId = session.getId();
        SessionContext ctx = sessions.get(sessionId);

        if (ctx == null) return;

        try {
            JsonNode jsonNode = objectMapper.readTree(message.getPayload());
            String action = jsonNode.has("action") ? jsonNode.get("action").asText() : "";

            switch (action) {
                case "start":
                    handleStart(ctx, jsonNode);
                    break;
                case "stop":
                    handleStop(ctx);
                    break;
                case "interrupt":
                    handleInterrupt(ctx);
                    break;
            }
        } catch (Exception e) {
            log.error("[实时语音] 处理文本消息失败", e);
        }
    }

    private void handleStart(SessionContext ctx, JsonNode jsonNode) throws Exception {
        int userId = jsonNode.has("userId") ? jsonNode.get("userId").asInt() : 0;
        int botId = jsonNode.has("botId") ? jsonNode.get("botId").asInt() : 10009;

        ctx.userId = userId;
        ctx.botId = botId;
        ctx.botName = AiPersonaRegistry.getBotName(botId);

        log.info("[实时语音] 开始会话: sessionId={}, userId={}, botId={}({})",
            ctx.sessionId, userId, botId, ctx.botName);

        startAsr(ctx);

        sendJsonMessage(ctx.session, "session_started", Map.of(
            "userId", userId,
            "botId", botId,
            "botName", ctx.botName
        ));
    }

    private void startAsr(SessionContext ctx) throws Exception {
        String apiKey = voiceConfig.getAliyun().getApiKey();
        String asrModel = voiceConfig.getAliyun().getAsrModel();

        log.info("[实时语音] 启动ASR: model={}, apiKey前缀={}", asrModel,
            apiKey != null && apiKey.length() > 8 ? apiKey.substring(0, 8) + "..." : "null");

        ctx.recognizer = new Recognition();

        RecognitionParam param = RecognitionParam.builder()
            .model(asrModel)
            .apiKey(apiKey)
            .format("pcm")
            .sampleRate(SAMPLE_RATE)
            .build();

        ctx.asrCallback = new ResultCallback<RecognitionResult>() {
            @Override
            public void onEvent(RecognitionResult result) {
                try {
                    if (ctx.isInterrupted.get() || ctx.isStopped.get()) return;

                    String text = result.getSentence().getText();
                    boolean isEnd = result.isSentenceEnd();

                    if (text != null && !text.isEmpty()) {
                        log.debug("[实时语音] ASR结果: text={}, isEnd={}", text, isEnd);

                        sendJsonMessage(ctx.session, "asr_result", Map.of(
                            "text", text,
                            "isEnd", isEnd
                        ));

                        if (isEnd) {
                            ctx.currentSentence.set(text);
                            processSentence(ctx, text);
                        } else {
                            ctx.partialText.set(text);
                        }
                    }
                } catch (Exception e) {
                    log.error("[实时语音] 处理ASR结果失败", e);
                }
            }

            @Override
            public void onComplete() {
                log.debug("[实时语音] ASR完成");
            }

            @Override
            public void onError(Exception e) {
                log.error("[实时语音] ASR错误", e);
                ctx.asrReady.set(false);
                sendJsonMessage(ctx.session, "error", Map.of(
                    "message", "语音识别服务异常，请重试"
                ));
            }
        };

        try {
            ctx.recognizer.call(param, ctx.asrCallback);
            ctx.asrReady.set(true);
            log.info("[实时语音] ASR启动成功");
        } catch (Exception e) {
            log.error("[实时语音] ASR启动失败", e);
            ctx.asrReady.set(false);
            sendJsonMessage(ctx.session, "error", Map.of(
                "message", "语音识别启动失败: " + e.getMessage()
            ));
        }
    }

    private void processSentence(SessionContext ctx, String text) {
        if (text == null || text.trim().isEmpty() || ctx.isInterrupted.get() || ctx.isStopped.get()) {
            return;
        }

        ctx.executorService.submit(() -> {
            try {
                log.info("[实时语音] 处理句子: {}", text);

                sendJsonMessage(ctx.session, "llm_start", Map.of("text", text));

                SystemMessage systemMessage = AiPersonaRegistry.getPersonaByBotId(ctx.botId);

                Flux<String> responseFlux = fastChatClient.prompt()
                    .system(systemMessage.getContent())
                    .user(text)
                    .stream()
                    .content();

                StringBuilder fullResponse = new StringBuilder();
                StringBuilder buffer = new StringBuilder();
                AtomicBoolean ttsFailed = new AtomicBoolean(false);

                Disposable subscription = responseFlux.subscribe(
                    chunk -> {
                        if (ctx.isInterrupted.get() || ctx.isStopped.get()) return;
                        if (ttsFailed.get()) return;

                        fullResponse.append(chunk);
                        buffer.append(chunk);
                        sendJsonMessage(ctx.session, "llm_chunk", Map.of("text", chunk));

                        if (shouldTriggerTts(buffer.toString())) {
                            String ttsText = buffer.toString();
                            buffer.setLength(0);

                            if (ctx.ttsRef.get() == null && !ttsFailed.get()) {
                                try {
                                    QwenTtsRealtime tts = startTts(ctx);
                                    ctx.ttsRef.set(tts);
                                } catch (Exception e) {
                                    log.error("[实时语音] 启动TTS失败，后续文本将不再发送TTS", e);
                                    ttsFailed.set(true);
                                    return;
                                }
                            }

                            if (ctx.ttsRef.get() != null && !ttsFailed.get()) {
                                try {
                                    ctx.ttsRef.get().appendText(ttsText);
                                } catch (Exception e) {
                                    if (e.getMessage() != null && e.getMessage().contains("already closed")) {
                                        log.error("[实时语音] TTS已关闭，中断后续LLM输出");
                                        ttsFailed.set(true);
                                        ctx.ttsRef.set(null);
                                    } else {
                                        log.error("[实时语音] 发送TTS文本失败", e);
                                        ttsFailed.set(true);
                                    }
                                }
                            }
                        }
                    },
                    error -> {
                        log.error("[实时语音] LLM错误", error);
                        sendJsonMessage(ctx.session, "error", Map.of("message", error.getMessage()));
                    },
                    () -> {
                        if (ctx.isInterrupted.get() || ctx.isStopped.get()) return;

                        if (!ttsFailed.get()) {
                            String remaining = buffer.toString();
                            if (!remaining.isEmpty() && ctx.ttsRef.get() != null) {
                                try {
                                    ctx.ttsRef.get().appendText(remaining);
                                } catch (Exception e) {
                                    log.warn("[实时语音] 发送剩余TTS文本失败: {}", e.getMessage());
                                }
                            }

                            if (ctx.ttsRef.get() != null) {
                                try {
                                    ctx.ttsRef.get().finish();
                                } catch (Exception e) {
                                    log.warn("[实时语音] 结束TTS失败: {}", e.getMessage());
                                }
                            }
                        }

                        ctx.lastResponse = fullResponse.toString();
                        sendJsonMessage(ctx.session, "llm_end", Map.of("fullText", fullResponse.toString()));
                        log.info("[实时语音] LLM完成: {} 字符", fullResponse.length());
                    }
                );

                ctx.currentSubscription.set(subscription);

            } catch (Exception e) {
                log.error("[实时语音] 处理句子失败", e);
            }
        });
    }

    private boolean shouldTriggerTts(String text) {
        if (text.length() >= 10) return true;
        if (text.contains("，") || text.contains("。") || text.contains("！") ||
            text.contains("？") || text.contains("、") || text.contains("；")) {
            return text.length() >= 5;
        }
        return false;
    }

    private QwenTtsRealtime startTts(SessionContext ctx) throws Exception {
        String apiKey = voiceConfig.getAliyun().getApiKey();
        String ttsModel = voiceConfig.getAliyun().getRealtimeTtsModel();
        String voiceName = voiceConfig.getAliyun().getRealtimeTtsVoice();

        log.info("[实时语音] 启动TTS: model={}, voice={}, apiKey前缀={}", ttsModel, voiceName,
            apiKey != null && apiKey.length() > 8 ? apiKey.substring(0, 8) + "..." : "null");

        QwenTtsRealtimeParam param = QwenTtsRealtimeParam.builder()
            .model(ttsModel)
            .url("wss://dashscope.aliyuncs.com/api-ws/v1/realtime")
            .apikey(apiKey)
            .build();

        QwenTtsRealtime tts = new QwenTtsRealtime(param, new QwenTtsRealtimeCallback() {
            @Override
            public void onOpen() {
                log.debug("[实时语音] TTS连接建立");
            }

            @Override
            public void onEvent(com.google.gson.JsonObject message) {
                if (ctx.isInterrupted.get() || ctx.isStopped.get()) return;

                String type = message.get("type").getAsString();
                switch (type) {
                    case "session.created":
                        log.debug("[实时语音] TTS会话创建");
                        break;
                    case "response.audio.delta":
                        String audioB64 = message.get("delta").getAsString();
                        try {
                            sendBinaryMessage(ctx.session, Base64.getDecoder().decode(audioB64));
                        } catch (Exception e) {
                            log.error("[实时语音] 发送音频失败", e);
                        }
                        break;
                    case "response.done":
                        log.debug("[实时语音] TTS响应完成");
                        break;
                    case "session.finished":
                        log.debug("[实时语音] TTS会话结束");
                        break;
                    case "error":
                        log.error("[实时语音] TTS服务端错误: {}", message);
                        ctx.ttsRef.set(null);
                        break;
                }
            }

            @Override
            public void onClose(int code, String reason) {
                log.debug("[实时语音] TTS连接关闭: code={}, reason={}", code, reason);
            }
        });

        tts.connect();

        QwenTtsRealtimeConfig config = QwenTtsRealtimeConfig.builder()
            .voice(voiceName != null ? voiceName : "Cherry")
            .responseFormat(QwenTtsRealtimeAudioFormat.PCM_24000HZ_MONO_16BIT)
            .mode("server_commit")
            .build();
        tts.updateSession(config);

        return tts;
    }

    private void handleStop(SessionContext ctx) throws Exception {
        log.info("[实时语音] 停止会话: sessionId={}", ctx.sessionId);

        ctx.isStopped.set(true);
        ctx.isInterrupted.set(true);
        ctx.asrReady.set(false);

        Disposable subscription = ctx.currentSubscription.get();
        if (subscription != null && !subscription.isDisposed()) {
            subscription.dispose();
        }

        QwenTtsRealtime tts = ctx.ttsRef.get();
        if (tts != null) {
            try {
                tts.finish();
                tts.close();
                ctx.ttsRef.set(null);
                log.info("[实时语音] TTS已关闭");
            } catch (Exception e) {
                log.warn("[实时语音] 关闭TTS失败: {}", e.getMessage());
            }
        }

        if (ctx.recognizer != null) {
            try {
                ctx.recognizer.stop();
                ctx.recognizer.getDuplexApi().close(1000, "stopped");
                ctx.recognizer = null;
            } catch (Exception e) {
                log.warn("[实时语音] 关闭ASR失败: {}", e.getMessage());
            }
        }

        sendJsonMessage(ctx.session, "session_stopped", Map.of());

        sessions.remove(ctx.sessionId);
        log.info("[实时语音] 会话已移除: sessionId={}", ctx.sessionId);
    }

    private void handleInterrupt(SessionContext ctx) {
        log.info("[实时语音] 用户打断: sessionId={}", ctx.sessionId);

        ctx.isInterrupted.set(true);

        Disposable subscription = ctx.currentSubscription.get();
        if (subscription != null && !subscription.isDisposed()) {
            subscription.dispose();
            ctx.currentSubscription.set(null);
        }

        QwenTtsRealtime tts = ctx.ttsRef.get();
        if (tts != null) {
            try {
                tts.close();
                ctx.ttsRef.set(null);
            } catch (Exception e) {
                log.warn("[实时语音] 打断时关闭TTS失败: {}", e.getMessage());
            }
        }

        sendJsonMessage(ctx.session, "interrupted", Map.of(
            "partialResponse", ctx.lastResponse != null ? ctx.lastResponse : ""
        ));

        ctx.executorService.schedule(() -> {
            ctx.isInterrupted.set(false);
            ctx.lastResponse = null;
            log.info("[实时语音] 打断恢复，准备继续监听");
        }, 300, TimeUnit.MILLISECONDS);
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) throws Exception {
        String sessionId = session.getId();
        log.info("[实时语音] WebSocket连接关闭: sessionId={}, status={}", sessionId, status);

        SessionContext ctx = sessions.remove(sessionId);
        if (ctx != null) {
            ctx.cleanup();
        }
    }

    @Override
    public void handleTransportError(WebSocketSession session, Throwable exception) throws Exception {
        log.error("[实时语音] 传输错误: sessionId={}", session.getId(), exception);
    }

    private void sendJsonMessage(WebSocketSession session, String type, Map<String, Object> data) {
        String sessionId = session.getId();
        SessionContext ctx = sessions.get(sessionId);
        if (ctx == null) return;

        try {
            ObjectNode message = objectMapper.createObjectNode();
            message.put("type", type);
            data.forEach((key, value) -> {
                if (value instanceof String) {
                    message.put(key, (String) value);
                } else if (value instanceof Integer) {
                    message.put(key, (Integer) value);
                } else if (value instanceof Boolean) {
                    message.put(key, (Boolean) value);
                } else {
                    message.putPOJO(key, value);
                }
            });
            ctx.writeLock.lock();
            try {
                session.sendMessage(new TextMessage(objectMapper.writeValueAsString(message)));
            } finally {
                ctx.writeLock.unlock();
            }
        } catch (Exception e) {
            log.error("[实时语音] 发送JSON消息失败", e);
        }
    }

    private void sendBinaryMessage(WebSocketSession session, byte[] audioData) throws Exception {
        String sessionId = session.getId();
        SessionContext ctx = sessions.get(sessionId);
        if (ctx == null) return;

        ctx.writeLock.lock();
        try {
            session.sendMessage(new BinaryMessage(ByteBuffer.wrap(audioData)));
        } finally {
            ctx.writeLock.unlock();
        }
    }

    private static class SessionContext {
        final String sessionId;
        final WebSocketSession session;
        final ScheduledExecutorService executorService;
        final ReentrantLock writeLock = new ReentrantLock();
        final AtomicBoolean isInterrupted = new AtomicBoolean(false);
        final AtomicBoolean isStopped = new AtomicBoolean(false);
        final AtomicBoolean asrReady = new AtomicBoolean(false);
        final AtomicReference<String> partialText = new AtomicReference<>("");
        final AtomicReference<String> currentSentence = new AtomicReference<>("");
        final AtomicReference<Disposable> currentSubscription = new AtomicReference<>();
        final AtomicReference<QwenTtsRealtime> ttsRef = new AtomicReference<>();

        int userId;
        int botId;
        String botName;
        String lastResponse;

        Recognition recognizer;
        ResultCallback<RecognitionResult> asrCallback;

        SessionContext(String sessionId, WebSocketSession session) {
            this.sessionId = sessionId;
            this.session = session;
            this.executorService = Executors.newSingleThreadScheduledExecutor();
        }

        void cleanup() {
            log.info("[实时语音] 清理会话资源: sessionId={}", sessionId);

            isStopped.set(true);
            isInterrupted.set(true);
            asrReady.set(false);

            executorService.shutdownNow();

            Disposable subscription = currentSubscription.get();
            if (subscription != null && !subscription.isDisposed()) {
                subscription.dispose();
            }

            QwenTtsRealtime tts = ttsRef.get();
            if (tts != null) {
                try {
                    tts.finish();
                    tts.close();
                    ttsRef.set(null);
                    log.info("[实时语音] TTS已关闭: sessionId={}", sessionId);
                } catch (Exception e) {
                    log.warn("[实时语音] 关闭TTS失败: {}", e.getMessage());
                }
            }

            if (recognizer != null) {
                try {
                    recognizer.stop();
                    recognizer.getDuplexApi().close(1000, "cleanup");
                    recognizer = null;
                } catch (Exception e) {
                    log.warn("[实时语音] 清理ASR失败: {}", e.getMessage());
                }
            }
        }
    }
}
