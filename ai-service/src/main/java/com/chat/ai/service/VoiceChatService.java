package com.chat.ai.service;

import com.alibaba.dashscope.audio.asr.recognition.Recognition;
import com.alibaba.dashscope.audio.asr.recognition.RecognitionParam;
import com.alibaba.dashscope.utils.Constants;
import com.chat.ai.config.VoiceConfig;
import com.chat.ai.rpc.RpcPushService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.messages.SystemMessage;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.ExchangeStrategies;
import org.springframework.web.reactive.function.client.WebClient;

import java.io.File;
import java.io.FileOutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Base64;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@Slf4j
@Service
public class VoiceChatService {

    private final VoiceConfig voiceConfig;
    private final ChatClient fastChatClient;
    private final RpcPushService rpcPushService;
    private final WebClient webClient;
    private final ObjectMapper objectMapper = new ObjectMapper();

    private final String audioStoragePath = "/tmp/audio";
    private final String audioUrlPrefix = "http://localhost:8081/audio";

    public VoiceChatService(
            VoiceConfig voiceConfig,
            @Qualifier("fastChatClient") ChatClient fastChatClient,
            RpcPushService rpcPushService,
            WebClient.Builder webClientBuilder) {
        this.voiceConfig = voiceConfig;
        this.fastChatClient = fastChatClient;
        this.rpcPushService = rpcPushService;
        ExchangeStrategies strategies = ExchangeStrategies.builder()
            .codecs(configurer -> configurer
                .defaultCodecs()
                .maxInMemorySize(10 * 1024 * 1024))
            .build();
        this.webClient = webClientBuilder
            .exchangeStrategies(strategies)
            .build();

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
            String apiKey = voiceConfig.getAliyun().getApiKey();
            String asrModel = voiceConfig.getAliyun().getAsrModel();

            log.info("开始ASR识别, 本地文件: {}, 模型: {}", localFilePath, asrModel);

            Recognition recognizer = new Recognition();
            RecognitionParam param = RecognitionParam.builder()
                .model(asrModel)
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
            String apiKey = voiceConfig.getXiaomi().getApiKey();
            String ttsModel = voiceConfig.getXiaomi().getTtsModel();
            String voiceName = voiceConfig.getXiaomi().getTtsVoice();
            String ttsBaseUrl = voiceConfig.getXiaomi().getBaseUrl();

            String fileName = "ai_" + UUID.randomUUID().toString() + ".wav";
            String outputPath = audioStoragePath + "/" + fileName;

            log.info("开始TTS合成(MiMo), model={}, voice={}, baseUrl={}, text长度={}",
                ttsModel, voiceName, ttsBaseUrl, text.length());

            List<Map<String, String>> messages = List.of(
                Map.of("role", "user", "content", "用温和耐心的语气，像一位经验丰富的考研辅导老师在给学生讲解知识点。语速适中，吐字清晰。"),
                Map.of("role", "assistant", "content", text)
            );

            Map<String, Object> audioConfig = Map.of(
                "format", "wav",
                "voice", voiceName
            );

            Map<String, Object> requestBody = Map.of(
                "model", ttsModel,
                "messages", messages,
                "audio", audioConfig
            );

            byte[] responseData = webClient.post()
                .uri(ttsBaseUrl + "/chat/completions")
                .header("Authorization", "Bearer " + apiKey)
                .header(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
                .bodyValue(requestBody)
                .retrieve()
                .bodyToMono(byte[].class)
                .block();

            if (responseData == null || responseData.length == 0) {
                log.error("MiMo TTS返回空响应");
                return null;
            }

            log.info("MiMo TTS响应大小: {} bytes", responseData.length);

            JsonNode response = objectMapper.readTree(responseData);

            if (!response.has("choices") || response.get("choices").size() == 0) {
                log.error("MiMo TTS响应无choices: {}", new String(responseData, 0, Math.min(500, responseData.length)));
                if (response.has("error")) {
                    log.error("MiMo TTS错误: {}", response.get("error"));
                }
                return null;
            }

            JsonNode message = response.get("choices").get(0).get("message");
            if (message == null || !message.has("audio") || !message.get("audio").has("data")) {
                log.error("MiMo TTS响应无audio.data字段");
                return null;
            }

            String audioBase64 = message.get("audio").get("data").asText();
            byte[] wavBytes = Base64.getDecoder().decode(audioBase64);

            if (wavBytes.length == 0) {
                log.error("MiMo TTS解码后音频数据为空");
                return null;
            }

            try (FileOutputStream fos = new FileOutputStream(outputPath)) {
                fos.write(wavBytes);
            }

            File outputFile = new File(outputPath);
            if (!outputFile.exists() || outputFile.length() == 0) {
                log.error("MiMo TTS音频文件写入失败: {}", outputPath);
                return null;
            }

            log.info("MiMo TTS音频已保存: {} ({} bytes)", outputPath, wavBytes.length);
            return audioUrlPrefix + "/" + fileName;

        } catch (Exception e) {
            log.error("MiMo TTS合成失败", e);
            return null;
        }
    }

    private int estimateDuration(String text) {
        int charCount = text.length();
        return Math.max(1, charCount / 4);
    }

    public String synthesizeSpeechPublic(String text) {
        String result = synthesizeSpeech(text);
        if (result == null) {
            log.warn("TTS合成失败，返回null");
        }
        return result;
    }

    public record VoiceChatResult(String textReply, String voiceUrl, int duration) {}
}
