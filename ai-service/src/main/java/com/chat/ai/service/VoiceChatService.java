package com.chat.ai.service;

import com.chat.ai.config.VoiceConfig;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.messages.SystemMessage;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import java.io.FileOutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

@Slf4j
@Service
public class VoiceChatService {

    private final VoiceConfig voiceConfig;
    private final ChatClient fastChatClient;
    private final RedisPubSubService redisPubSubService;
    private final WebClient webClient;
    private final ObjectMapper objectMapper;

    private final String audioStoragePath = "/tmp/audio";
    private final String audioUrlPrefix = "http://localhost:8081/audio";
    private final String DASHSCOPE_API_URL = "https://dashscope.aliyuncs.com/api/v1/services/audio";

    public VoiceChatService(
            VoiceConfig voiceConfig,
            @Qualifier("fastChatClient") ChatClient fastChatClient,
            RedisPubSubService redisPubSubService,
            WebClient.Builder webClientBuilder) {
        this.voiceConfig = voiceConfig;
        this.fastChatClient = fastChatClient;
        this.redisPubSubService = redisPubSubService;
        this.webClient = webClientBuilder.build();
        this.objectMapper = new ObjectMapper();
        
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
        
        String userText = transcribeAudio(audioUrl);
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
        
        redisPubSubService.publishDirectMessage(userId, aiTextReply, botId, AiPersonaRegistry.getBotName(botId));
        
        return new VoiceChatResult(aiTextReply, aiVoiceUrl, estimateDuration(aiTextReply));
    }

    private String transcribeAudio(String audioUrl) {
        try {
            String apiKey = voiceConfig.getDashscope().getApiKey();
            String model = voiceConfig.getDashscope().getAsrModel();
            
            String localPath = audioUrl;
            if (audioUrl.startsWith("http")) {
                localPath = audioUrl.replace(audioUrlPrefix, audioStoragePath);
            }
            
            Path audioPath = Paths.get(localPath);
            if (!Files.exists(audioPath)) {
                log.error("音频文件不存在: {}", localPath);
                return null;
            }
            
            byte[] audioData = Files.readAllBytes(audioPath);
            String base64Audio = java.util.Base64.getEncoder().encodeToString(audioData);
            
            Map<String, Object> requestBody = new HashMap<>();
            requestBody.put("model", model);
            Map<String, Object> input = new HashMap<>();
            input.put("audio", base64Audio);
            requestBody.put("input", input);
            
            String response = webClient.post()
                .uri(DASHSCOPE_API_URL + "/asr/transcription")
                .header("Authorization", "Bearer " + apiKey)
                .header("Content-Type", "application/json")
                .bodyValue(requestBody)
                .retrieve()
                .bodyToMono(String.class)
                .block();
            
            JsonNode root = objectMapper.readTree(response);
            if (root.has("output") && root.get("output").has("text")) {
                return root.get("output").get("text").asText();
            }
            
            if (root.has("output") && root.get("output").has("results")) {
                JsonNode results = root.get("output").get("results");
                if (results.isArray() && results.size() > 0) {
                    return results.get(0).get("transcription_text").asText();
                }
            }
            
            log.warn("ASR响应格式不匹配: {}", response);
            return null;
            
        } catch (Exception e) {
            log.error("ASR识别失败", e);
            return null;
        }
    }

    private String synthesizeSpeech(String text) {
        try {
            String apiKey = voiceConfig.getDashscope().getApiKey();
            String model = voiceConfig.getDashscope().getTtsModel();
            String voice = voiceConfig.getDashscope().getTtsVoice();
            
            String fileName = "ai_" + UUID.randomUUID().toString() + ".wav";
            String outputPath = audioStoragePath + "/" + fileName;
            
            Map<String, Object> requestBody = new HashMap<>();
            requestBody.put("model", model);
            
            Map<String, Object> input = new HashMap<>();
            input.put("text", text);
            requestBody.put("input", input);
            
            Map<String, Object> parameters = new HashMap<>();
            parameters.put("voice", voice);
            parameters.put("format", "wav");
            requestBody.put("parameters", parameters);
            
            byte[] audioData = webClient.post()
                .uri(DASHSCOPE_API_URL + "/tts/synthesis")
                .header("Authorization", "Bearer " + apiKey)
                .header("Content-Type", "application/json")
                .header("Accept", "application/octet-stream")
                .bodyValue(requestBody)
                .retrieve()
                .bodyToMono(byte[].class)
                .block();
            
            if (audioData != null && audioData.length > 0) {
                try (FileOutputStream fos = new FileOutputStream(outputPath)) {
                    fos.write(audioData);
                }
                log.info("TTS音频已保存: {} ({} bytes)", outputPath, audioData.length);
                return audioUrlPrefix + "/" + fileName;
            }
            
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

    public record VoiceChatResult(String textReply, String voiceUrl, int duration) {}
}
