package com.chat.ai.config;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.openai.OpenAiChatModel;
import org.springframework.ai.openai.OpenAiChatOptions;
import org.springframework.ai.openai.api.OpenAiApi;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MultimodalConfig {

    @Value("${multimodal.openai.api-key}")
    private String apiKey;

    @Value("${multimodal.openai.base-url}")
    private String baseUrl;

    @Value("${multimodal.openai.model}")
    private String model;

    @Value("${multimodal.openai.temperature}")
    private Double temperature;

    @Bean
    public OpenAiApi multimodalOpenAiApi() {
        return new OpenAiApi(baseUrl, apiKey);
    }

    @Bean
    public OpenAiChatOptions multimodalChatOptions() {
        return OpenAiChatOptions.builder()
            .withModel(model)
            .withTemperature(temperature)
            .build();
    }

    @Bean
    public OpenAiChatModel multimodalChatModel() {
        return new OpenAiChatModel(multimodalOpenAiApi(), multimodalChatOptions());
    }

    @Bean
    public ChatClient multimodalChatClient() {
        return ChatClient.builder(multimodalChatModel()).build();
    }
}
