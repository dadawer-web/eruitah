package com.chat.ai.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Data
@Configuration
@ConfigurationProperties(prefix = "voice")
public class VoiceConfig {
    
    private DashScopeConfig dashscope = new DashScopeConfig();
    private StorageConfig storage = new StorageConfig();
    
    @Data
    public static class DashScopeConfig {
        private String apiKey;
        private String asrModel = "paraformer-v2";
        private String ttsModel = "qwen3-tts-vd-2026-01-26";
        private String ttsVoice = "zhimiao_emo";
    }
    
    @Data
    public static class StorageConfig {
        private String path = "/tmp/audio";
        private String urlPrefix = "http://localhost:8081/audio";
    }
}
