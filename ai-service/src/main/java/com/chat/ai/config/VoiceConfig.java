package com.chat.ai.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

import java.util.HashMap;
import java.util.Map;

@Data
@Configuration
@ConfigurationProperties(prefix = "voice")
public class VoiceConfig {

    private AliyunConfig aliyun = new AliyunConfig();
    private XiaomiConfig xiaomi = new XiaomiConfig();
    private StorageConfig storage = new StorageConfig();
    private Map<String, ExternalConfig> externals = new HashMap<>();

    @Data
    public static class AliyunConfig {
        private String apiKey;
        private String asrModel = "fun-asr-realtime-2026-02-28";
        private String realtimeTtsModel = "qwen3-tts-instruct-flash-realtime";
        private String realtimeTtsVoice = "Cherry";
    }

    @Data
    public static class XiaomiConfig {
        private String apiKey;
        private String baseUrl = "https://token-plan-cn.xiaomimimo.com/v1";
        private String ttsModel = "mimo-v2.5-tts";
        private String ttsVoice = "冰糖";
    }

    @Data
    public static class ExternalConfig {
        private String apiKey;
        private String baseUrl;
        private String ttsModel;
        private String ttsVoice;
        private String endpoint = "/chat/completions";
        private String format = "wav";
        private String prompt = "用温和耐心的语气，语速适中，吐字清晰。";
    }

    @Data
    public static class StorageConfig {
        private String path = "/tmp/audio";
        private String urlPrefix = "http://localhost:8081/audio";
    }
}
