package com.chat.ai.client;

import com.chat.ai.config.VoiceConfig;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.ExchangeStrategies;
import org.springframework.web.reactive.function.client.WebClient;

import java.util.List;
import java.util.Map;

@Slf4j
@Component
public class ExternalTtsClient {

    private final VoiceConfig voiceConfig;
    private final WebClient webClient;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public ExternalTtsClient(VoiceConfig voiceConfig, WebClient.Builder webClientBuilder) {
        this.voiceConfig = voiceConfig;
        ExchangeStrategies strategies = ExchangeStrategies.builder()
            .codecs(configurer -> configurer
                .defaultCodecs()
                .maxInMemorySize(10 * 1024 * 1024))
            .build();
        this.webClient = webClientBuilder
            .exchangeStrategies(strategies)
            .build();
    }

    public byte[] synthesize(String text, String provider, String voiceId) {
        VoiceConfig.ExternalConfig config = resolveConfig(provider);
        if (config == null) {
            log.error("[ExternalTTS] 未找到 provider={} 的配置", provider);
            return null;
        }

        String apiKey = config.getApiKey();
        String baseUrl = config.getBaseUrl();
        String model = config.getTtsModel();
        String voice = voiceId != null ? voiceId : config.getTtsVoice();
        String endpoint = config.getEndpoint();

        log.info("[ExternalTTS] 合成语音: provider={}, model={}, voice={}, text长度={}",
            provider, model, voice, text.length());

        try {
            List<Map<String, String>> messages = List.of(
                Map.of("role", "user", "content", config.getPrompt()),
                Map.of("role", "assistant", "content", text)
            );

            Map<String, Object> audioConfig = Map.of(
                "format", config.getFormat(),
                "voice", voice
            );

            Map<String, Object> requestBody = Map.of(
                "model", model,
                "messages", messages,
                "audio", audioConfig
            );

            byte[] responseData = webClient.post()
                .uri(baseUrl + endpoint)
                .header("Authorization", "Bearer " + apiKey)
                .header(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
                .bodyValue(requestBody)
                .retrieve()
                .bodyToMono(byte[].class)
                .block();

            if (responseData == null || responseData.length == 0) {
                log.error("[ExternalTTS] provider={} 返回空响应", provider);
                return null;
            }

            JsonNode response = objectMapper.readTree(responseData);

            if (!response.has("choices") || response.get("choices").size() == 0) {
                log.error("[ExternalTTS] provider={} 响应无choices", provider);
                if (response.has("error")) {
                    log.error("[ExternalTTS] 错误: {}", response.get("error"));
                }
                return null;
            }

            JsonNode message = response.get("choices").get(0).get("message");
            if (message == null || !message.has("audio") || !message.get("audio").has("data")) {
                log.error("[ExternalTTS] provider={} 响应无audio.data字段", provider);
                return null;
            }

            String audioBase64 = message.get("audio").get("data").asText();
            byte[] audioBytes = java.util.Base64.getDecoder().decode(audioBase64);

            log.info("[ExternalTTS] 合成成功: provider={}, 音频大小={} bytes", provider, audioBytes.length);
            return audioBytes;

        } catch (Exception e) {
            log.error("[ExternalTTS] provider={} 合成失败", provider, e);
            return null;
        }
    }

    private VoiceConfig.ExternalConfig resolveConfig(String provider) {
        Map<String, VoiceConfig.ExternalConfig> externals = voiceConfig.getExternals();
        if (externals != null && externals.containsKey(provider)) {
            return externals.get(provider);
        }
        if ("xiaomi".equals(provider)) {
            VoiceConfig.XiaomiConfig xiaomi = voiceConfig.getXiaomi();
            VoiceConfig.ExternalConfig fallback = new VoiceConfig.ExternalConfig();
            fallback.setApiKey(xiaomi.getApiKey());
            fallback.setBaseUrl(xiaomi.getBaseUrl());
            fallback.setTtsModel(xiaomi.getTtsModel());
            fallback.setTtsVoice(xiaomi.getTtsVoice());
            fallback.setEndpoint("/chat/completions");
            fallback.setFormat("wav");
            fallback.setPrompt("用温和耐心的语气，语速适中，吐字清晰。");
            return fallback;
        }
        return null;
    }
}
