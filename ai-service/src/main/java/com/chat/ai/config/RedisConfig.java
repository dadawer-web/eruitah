package com.chat.ai.config;

import com.chat.ai.service.AiTaskStreamConsumer;
import com.fasterxml.jackson.annotation.JsonAutoDetect;
import com.fasterxml.jackson.annotation.JsonTypeInfo;
import com.fasterxml.jackson.annotation.PropertyAccessor;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.jsontype.impl.LaissezFaireSubTypeValidator;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.stream.*;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;
import org.springframework.data.redis.stream.StreamMessageListenerContainer;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import java.time.Duration;
import java.util.concurrent.Executor;

@Configuration
public class RedisConfig {
    
    private static final String AI_TASK_STREAM = "ai_task_stream";
    private static final String AI_GROUP = "ai_group";

    @Bean
    public RedisTemplate<String, Object> redisTemplate(RedisConnectionFactory connectionFactory) {
        RedisTemplate<String, Object> template = new RedisTemplate<>();
        template.setConnectionFactory(connectionFactory);
        
        ObjectMapper objectMapper = new ObjectMapper();
        objectMapper.registerModule(new JavaTimeModule());
        objectMapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
        objectMapper.setVisibility(PropertyAccessor.ALL, JsonAutoDetect.Visibility.ANY);
        objectMapper.activateDefaultTyping(
            LaissezFaireSubTypeValidator.instance,
            ObjectMapper.DefaultTyping.NON_FINAL,
            JsonTypeInfo.As.PROPERTY
        );
        
        Jackson2JsonRedisSerializer<Object> jsonSerializer = new Jackson2JsonRedisSerializer<>(objectMapper, Object.class);
        StringRedisSerializer stringSerializer = new StringRedisSerializer();
        
        template.setKeySerializer(stringSerializer);
        template.setHashKeySerializer(stringSerializer);
        template.setValueSerializer(jsonSerializer);
        template.setHashValueSerializer(jsonSerializer);
        
        template.afterPropertiesSet();
        return template;
    }
    
    @Bean
    public RedisMessageListenerContainer redisMessageListenerContainer(RedisConnectionFactory connectionFactory) {
        RedisMessageListenerContainer container = new RedisMessageListenerContainer();
        container.setConnectionFactory(connectionFactory);
        return container;
    }

    @Bean
    public CommandLineRunner createStreamConsumerGroup(RedisConnectionFactory connectionFactory) {
        return args -> {
            try {
                var streamCommands = connectionFactory.getConnection().streamCommands();
                
                try {
                    streamCommands.xGroupCreate(AI_TASK_STREAM.getBytes(), AI_GROUP, ReadOffset.from("0"), true);
                    System.out.println("Created consumer group: " + AI_GROUP + " for stream: " + AI_TASK_STREAM);
                } catch (Exception e) {
                    if (e.getMessage() != null && e.getMessage().contains("BUSYGROUP")) {
                        System.out.println("Consumer group " + AI_GROUP + " already exists");
                    } else {
                        System.err.println("Error creating consumer group: " + e.getMessage());
                    }
                }
            } catch (Exception e) {
                System.err.println("Failed to initialize Stream consumer group: " + e.getMessage());
            }
        };
    }

    @Bean
    public StreamMessageListenerContainer<String, MapRecord<String, String, String>> aiTaskStreamContainer(
            RedisConnectionFactory connectionFactory,
            AiTaskStreamConsumer aiTaskStreamConsumer,
            @Qualifier("streamTaskExecutor") Executor streamTaskExecutor) {

        StreamMessageListenerContainer.StreamMessageListenerContainerOptions<String, MapRecord<String, String, String>> options =
                StreamMessageListenerContainer.StreamMessageListenerContainerOptions.builder()
                        .pollTimeout(Duration.ofSeconds(1))
                        .executor(streamTaskExecutor)
                        .build();

        StreamMessageListenerContainer<String, MapRecord<String, String, String>> container =
                StreamMessageListenerContainer.create(connectionFactory, options);

        // container.receive(
        //         Consumer.from(AI_GROUP, "ai_node_1"),
        //         StreamOffset.create(AI_TASK_STREAM, ReadOffset.lastConsumed()),
        //         aiTaskStreamConsumer
        // );

        // container.start();
        // System.out.println("AI Task Stream Container started, listening on stream: " + AI_TASK_STREAM);
        System.out.println("AI Task Stream Container DISABLED - tasks now received via RPC (InternalRouterHandler)");
        return container;
    }
}
