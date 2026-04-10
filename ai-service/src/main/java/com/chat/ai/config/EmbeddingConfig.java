package com.chat.ai.config;

import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.document.MetadataMode;
import org.springframework.ai.embedding.EmbeddingModel;
import org.springframework.ai.openai.OpenAiEmbeddingModel;
import org.springframework.ai.openai.OpenAiEmbeddingOptions;
import org.springframework.ai.openai.api.OpenAiApi;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

@Slf4j
@Configuration
public class EmbeddingConfig {

    @Value("${embedding.siliconflow.api-key}")
    private String apiKey;

    @Value("${embedding.siliconflow.base-url}")
    private String baseUrl;

    @Value("${embedding.siliconflow.model:BAAI/bge-m3}")
    private String model;

    @Bean
    @Primary
    public EmbeddingModel embeddingModel() {
        log.info("Initializing SiliconFlow Embedding Model: {} at {}", model, baseUrl);
        
        OpenAiApi siliconFlowApi = new OpenAiApi(baseUrl, apiKey);
        
        OpenAiEmbeddingOptions options = OpenAiEmbeddingOptions.builder()
            .withModel(model)
            .build();
        
        OpenAiEmbeddingModel embeddingModel = new OpenAiEmbeddingModel(
            siliconFlowApi, 
            MetadataMode.EMBED,
            options
        );
        
        log.info("SiliconFlow Embedding Model initialized successfully");
        return embeddingModel;
    }
}
