package com.chat.ai.config;

import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.embedding.EmbeddingModel;
import org.springframework.ai.vectorstore.RedisVectorStore;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import redis.clients.jedis.JedisPooled;

@Slf4j
@Configuration
public class RedisVectorStoreConfig {

    @Value("${spring.data.redis.host:localhost}")
    private String redisHost;

    @Value("${spring.data.redis.port:6379}")
    private int redisPort;

    @Value("${spring.data.redis.password:}")
    private String redisPassword;

    @Value("${spring.data.redis.database:0}")
    private int redisDatabase;

    @Bean
    public JedisPooled jedisPooled() {
        log.info("Creating JedisPooled connection to {}:{}", redisHost, redisPort);
        String url;
        if (redisPassword != null && !redisPassword.isEmpty()) {
            url = String.format("redis://:%s@%s:%d/%d", redisPassword, redisHost, redisPort, redisDatabase);
        } else {
            url = String.format("redis://%s:%d/%d", redisHost, redisPort, redisDatabase);
        }
        return new JedisPooled(url);
    }

    @Bean
    @Primary
    public VectorStore vectorStore(JedisPooled jedisPooled, EmbeddingModel embeddingModel) {
        log.info("Creating RedisVectorStore...");
        
        RedisVectorStore.RedisVectorStoreConfig config = RedisVectorStore.RedisVectorStoreConfig.builder()
            .withIndexName("rag-knowledge-index")
            .withPrefix("rag:doc:")
            .build();
        
        RedisVectorStore vectorStore = new RedisVectorStore(config, embeddingModel, jedisPooled, true);
        log.info("RedisVectorStore created successfully");
        return vectorStore;
    }
}
