package com.chat.ai.service;

import com.alibaba.dashscope.audio.asr.recognition.Recognition;
import com.alibaba.dashscope.audio.asr.recognition.RecognitionParam;
import com.alibaba.dashscope.audio.qwen_tts_realtime.*;
import com.alibaba.dashscope.utils.Constants;
import com.chat.ai.config.VoiceConfig;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.gson.JsonObject;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.messages.SystemMessage;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Base64;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

@Slf4j
@Service
public class VoiceChatService {

    private final VoiceConfig voiceConfig;
    private final ChatClient fastChatClient;
    private final RedisPubSubService redisPubSubService;
    private final WebClient webClient;
    private final ObjectMapper objectMapper = new ObjectMapper();

    private final String audioStoragePath = "/tmp/audio";
    private final String audioUrlPrefix = "http://localhost:8081/audio";

    public VoiceChatService(
            VoiceConfig voiceConfig,
            @Qualifier("fastChatClient") ChatClient fastChatClient,
            RedisPubSubService redisPubSubService,
            WebClient.Builder webClientBuilder) {
        this.voiceConfig = voiceConfig;
        this.fastChatClient = fastChatClient;
        this.redisPubSubService = redisPubSubService;
        this.webClient = webClientBuilder.build();
        
        Constants.baseWebsocketApiUrl = "wss://dashscope.aliyuncs.com/api-ws/v1/inference";
        Constants.baseHttpApiUrl = "https://dashscope.aliyuncs.com/api/v1";
        
        try {
            Path storageDir = Paths.get(audioStoragePath);
            if (!Files.exists(storageDir)) {
                Files.createDirectories(storageDir);
                log.info("创建音频存储目录: {}", audioStoragePath);
            }
        } catch (Exception e) {
            log.error("创建音频存储目录失败", e);
        }
    }

    public VoiceChatResult handleVoiceChat(String audioUrl, Integer userId, Integer botId, Integer inputDuration) {
        log.info("开始处理语音聊天: userId={}, botId={}, audioUrl={}", userId, botId, audioUrl);
        
        String localFilePath = downloadAudioFile(audioUrl);
        if (localFilePath == null) {
            log.error("下载音频文件失败: {}", audioUrl);
            return new VoiceChatResult("抱歉，语音处理失败，请重试。", null, 0);
        }
        
        String userText = transcribeAudio(localFilePath);
        log.info("ASR识别结果: {}", userText);
        
        if (userText == null || userText.trim().isEmpty()) {
            userText = "[无法识别的语音内容]";
        }
        
        SystemMessage systemMessage = AiPersonaRegistry.getPersonaByBotId(botId);
        String aiTextReply = fastChatClient.prompt()
            .system(systemMessage.getContent())
            .user(userText)
            .call()
            .content();
        
        log.info("LLM回复: {}", aiTextReply.substring(0, Math.min(100, aiTextReply.length())) + "...");
        
        String aiVoiceUrl = synthesizeSpeech(aiTextReply);
        log.info("TTS合成完成: {}", aiVoiceUrl);
        
        return new VoiceChatResult(aiTextReply, aiVoiceUrl, estimateDuration(aiTextReply));
    }

    private String transcribeAudio(String localFilePath) {
        try {
            String apiKey = voiceConfig.getDashscope().getApiKey();
            String asrModel = voiceConfig.getDashscope().getAsrModel();
            
            log.info("开始ASR识别, 本地文件: {}, 模型: {}", localFilePath, asrModel);
            
            Recognition recognizer = new Recognition();
            RecognitionParam param = RecognitionParam.builder()
                .model(asrModel != null ? asrModel : "fun-asr-realtime")
                .apiKey(apiKey)
                .format("wav")
                .sampleRate(16000)
                .build();
            
            File audioFile = new File(localFilePath);
            if (!audioFile.exists()) {
                log.error("音频文件不存在: {}", localFilePath);
                return null;
            }
            
            String result = recognizer.call(param, audioFile);
            log.info("ASR原始响应: {}", result);
            
            recognizer.getDuplexApi().close(1000, "done");
            
            return parseAsrResult(result);
            
        } catch (Exception e) {
            log.error("ASR识别失败", e);
            return null;
        }
    }
    
    private String parseAsrResult(String jsonResult) {
        if (jsonResult == null || jsonResult.isEmpty()) {
            return null;
        }
        
        try {
            JsonNode root = objectMapper.readTree(jsonResult);
            
            if (root.has("sentences")) {
                StringBuilder textBuilder = new StringBuilder();
                JsonNode sentences = root.get("sentences");
                for (JsonNode sentence : sentences) {
                    if (sentence.has("text")) {
                        textBuilder.append(sentence.get("text").asText());
                    }
                }
                String text = textBuilder.toString().trim();
                log.info("ASR解析文本: {}", text);
                return text;
            }
            
            if (root.has("text")) {
                return root.get("text").asText();
            }
            
            return jsonResult;
        } catch (Exception e) {
            log.warn("解析ASR结果失败，返回原始结果", e);
            return jsonResult;
        }
    }

    private String downloadAudioFile(String audioUrl) {
        try {
            String fileName = "input_" + UUID.randomUUID().toString() + ".wav";
            String localPath = audioStoragePath + "/" + fileName;
            
            log.info("开始下载音频文件: {} -> {}", audioUrl, localPath);
            
            byte[] audioData = webClient.get()
                .uri(audioUrl)
                .retrieve()
                .bodyToMono(byte[].class)
                .block();
            
            if (audioData != null && audioData.length > 0) {
                try (FileOutputStream fos = new FileOutputStream(localPath)) {
                    fos.write(audioData);
                }
                log.info("音频文件下载完成: {} bytes", audioData.length);
                return localPath;
            }
            
            return null;
        } catch (Exception e) {
            log.error("下载音频文件失败: {}", audioUrl, e);
            return null;
        }
    }

    private String synthesizeSpeech(String text) {
        try {
            String apiKey = voiceConfig.getDashscope().getApiKey();
            String ttsModel = voiceConfig.getDashscope().getTtsModel();
            String voiceName = voiceConfig.getDashscope().getTtsVoice();
            
            String fileName = "ai_" + UUID.randomUUID().toString() + ".wav";
            String outputPath = audioStoragePath + "/" + fileName;
            
            log.info("开始TTS合成, model={}, voice={}, text长度={}", ttsModel, voiceName, text.length());
            
            ByteArrayOutputStream audioBuffer = new ByteArrayOutputStream();
            CountDownLatch completeLatch = new CountDownLatch(1);
            AtomicReference<String> errorRef = new AtomicReference<>(null);
            
            QwenTtsRealtimeParam param = QwenTtsRealtimeParam.builder()
                .model(ttsModel != null ? ttsModel : "qwen3-tts-flash-realtime")
                .url("wss://dashscope.aliyuncs.com/api-ws/v1/realtime")
                .apikey(apiKey)
                .build();
            
            QwenTtsRealtime qwenTts = new QwenTtsRealtime(param, new QwenTtsRealtimeCallback() {
                @Override
                public void onOpen() {
                    log.debug("TTS WebSocket连接已建立");
                }
                
                @Override
                public void onEvent(JsonObject message) {
                    String type = message.get("type").getAsString();
                    switch (type) {
                        case "session.created":
                            log.debug("TTS会话已创建");
                            break;
                        case "response.audio.delta":
                            String audioB64 = message.get("delta").getAsString();
                            byte[] rawAudio = Base64.getDecoder().decode(audioB64);
                            audioBuffer.write(rawAudio, 0, rawAudio.length);
                            break;
                        case "response.done":
                            log.debug("TTS响应完成");
                            break;
                        case "session.finished":
                            log.debug("TTS会话结束");
                            completeLatch.countDown();
                            break;
                        case "error":
                            String errorMsg = message.has("error") ? message.get("error").toString() : "Unknown error";
                            log.error("TTS错误: {}", errorMsg);
                            errorRef.set(errorMsg);
                            completeLatch.countDown();
                            break;
                    }
                }
                
                @Override
                public void onClose(int code, String reason) {
                    log.debug("TTS WebSocket关闭: code={}, reason={}", code, reason);
                }
            });
            
            qwenTts.connect();
            
            QwenTtsRealtimeConfig config = QwenTtsRealtimeConfig.builder()
                .voice(voiceName != null ? voiceName : "Cherry")
                .responseFormat(QwenTtsRealtimeAudioFormat.PCM_24000HZ_MONO_16BIT)
                .format("wav")
                .mode("server_commit")
                .build();
            qwenTts.updateSession(config);
            
            qwenTts.appendText(text);
            qwenTts.finish();
            
            completeLatch.await();
            qwenTts.close();
            
            if (errorRef.get() != null) {
                log.error("TTS合成失败: {}", errorRef.get());
                return null;
            }
            
            byte[] audioData = audioBuffer.toByteArray();
            if (audioData.length > 0) {
                byte[] wavData = addWavHeader(audioData, 24000, 16, 1);
                try (FileOutputStream fos = new FileOutputStream(outputPath)) {
                    fos.write(wavData);
                }
                log.info("TTS音频已保存: {} ({} bytes)", outputPath, wavData.length);
                return audioUrlPrefix + "/" + fileName;
            }
            
            log.error("TTS合成失败: 未获取到音频数据");
            return null;
            
        } catch (Exception e) {
            log.error("TTS合成失败", e);
            return null;
        }
    }

    private int estimateDuration(String text) {
        int charCount = text.length();
        return Math.max(1, charCount / 4);
    }

    public String synthesizeSpeechPublic(String text) {
        return synthesizeSpeech(text);
    }
    
    private byte[] addWavHeader(byte[] pcmData, int sampleRate, int bitsPerSample, int channels) {
        int byteRate = sampleRate * channels * bitsPerSample / 8;
        int blockAlign = channels * bitsPerSample / 8;
        int dataSize = pcmData.length;
        int fileSize = 36 + dataSize;
        
        byte[] wavData = new byte[44 + dataSize];
        
        wavData[0] = 'R'; wavData[1] = 'I'; wavData[2] = 'F'; wavData[3] = 'F';
        wavData[4] = (byte) (fileSize & 0xff);
        wavData[5] = (byte) ((fileSize >> 8) & 0xff);
        wavData[6] = (byte) ((fileSize >> 16) & 0xff);
        wavData[7] = (byte) ((fileSize >> 24) & 0xff);
        wavData[8] = 'W'; wavData[9] = 'A'; wavData[10] = 'V'; wavData[11] = 'E';
        wavData[12] = 'f'; wavData[13] = 'm'; wavData[14] = 't'; wavData[15] = ' ';
        wavData[16] = 16; wavData[17] = 0; wavData[18] = 0; wavData[19] = 0;
        wavData[20] = 1; wavData[21] = 0;
        wavData[22] = (byte) channels; wavData[23] = 0;
        wavData[24] = (byte) (sampleRate & 0xff);
        wavData[25] = (byte) ((sampleRate >> 8) & 0xff);
        wavData[26] = (byte) ((sampleRate >> 16) & 0xff);
        wavData[27] = (byte) ((sampleRate >> 24) & 0xff);
        wavData[28] = (byte) (byteRate & 0xff);
        wavData[29] = (byte) ((byteRate >> 8) & 0xff);
        wavData[30] = (byte) ((byteRate >> 16) & 0xff);
        wavData[31] = (byte) ((byteRate >> 24) & 0xff);
        wavData[32] = (byte) blockAlign; wavData[33] = 0;
        wavData[34] = (byte) bitsPerSample; wavData[35] = 0;
        wavData[36] = 'd'; wavData[37] = 'a'; wavData[38] = 't'; wavData[39] = 'a';
        wavData[40] = (byte) (dataSize & 0xff);
        wavData[41] = (byte) ((dataSize >> 8) & 0xff);
        wavData[42] = (byte) ((dataSize >> 16) & 0xff);
        wavData[43] = (byte) ((dataSize >> 24) & 0xff);
        
        System.arraycopy(pcmData, 0, wavData, 44, dataSize);
        
        return wavData;
    }

    public record VoiceChatResult(String textReply, String voiceUrl, int duration) {}
}
