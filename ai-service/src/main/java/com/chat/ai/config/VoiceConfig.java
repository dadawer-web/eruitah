package com.chat.ai.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Data
@Configuration
@ConfigurationProperties(prefix = "voice")
public class VoiceConfig {

    private AliyunConfig aliyun = new AliyunConfig();
    private XiaomiConfig xiaomi = new XiaomiConfig();
    private StorageConfig storage = new StorageConfig();

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
    public static class StorageConfig {
        private String path = "/tmp/audio";
        private String urlPrefix = "http://localhost:8081/audio";
    }
}
