package com.chat.ai.memory;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import lombok.extern.slf4j.Slf4j;

import org.springframework.ai.chat.memory.ChatMemory;
import org.springframework.ai.chat.messages.Message;
import org.springframework.data.redis.core.StringRedisTemplate;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

@Slf4j
public class RedisChatMemory implements ChatMemory {

    private static final String KEY_PREFIX = "chat:memory:";
    private static final long DEFAULT_TTL_HOURS = 24;

    private final StringRedisTemplate stringRedisTemplate;
    private final ObjectMapper objectMapper;

    public RedisChatMemory(StringRedisTemplate stringRedisTemplate, ObjectMapper objectMapper) {
        this.stringRedisTemplate = stringRedisTemplate;
        this.objectMapper = objectMapper;
    }

    @Override
    public void add(String conversationId, List<Message> messages) {
        if (messages == null || messages.isEmpty()) {
            return;
        }

        String key = buildKey(conversationId);

        try {
            for (Message message : messages) {
                MessageWrapper wrapper = MessageWrapper.fromMessage(message);
                String json = objectMapper.writeValueAsString(wrapper);
                stringRedisTemplate.opsForList().rightPush(key, json);
                log.info("Saved to Redis key: {}, messageType: {}, content preview: {}", 
                    key, wrapper.getClass().getSimpleName(), 
                    json.length() > 100 ? json.substring(0, 100) + "..." : json);
            }

            stringRedisTemplate.expire(key, DEFAULT_TTL_HOURS, TimeUnit.HOURS);

            log.info("=== Redis Chat Memory Saved ===");
            log.info("ConversationId: {}", conversationId);
            log.info("Redis Key: {}", key);
            log.info("Messages Count: {}", messages.size());
            log.info("TTL: {} hours", DEFAULT_TTL_HOURS);
            log.info("================================");

        } catch (JsonProcessingException e) {
            log.error("Failed to serialize messages for conversation: {}", conversationId, e);
            throw new RuntimeException("Failed to serialize messages", e);
        }
    }

    @Override
    public List<Message> get(String conversationId, int lastN) {
        String key = buildKey(conversationId);
        List<Message> result = new ArrayList<>();

        try {
            Long size = stringRedisTemplate.opsForList().size(key);
            if (size == null || size == 0) {
                log.info("No messages found in Redis for key: {}", key);
                return result;
            }

            long start = Math.max(0, size - lastN);
            List<String> jsonList = stringRedisTemplate.opsForList().range(key, start, -1);

            if (jsonList == null || jsonList.isEmpty()) {
                return result;
            }

            for (String json : jsonList) {
                try {
                    MessageWrapper wrapper = objectMapper.readValue(json, MessageWrapper.class);
                    result.add(wrapper.toMessage());
                } catch (JsonProcessingException e) {
                    log.warn("Failed to deserialize message for conversation: {}, json: {}", 
                        conversationId, json, e);
                }
            }

            log.info("=== Redis Chat Memory Retrieved ===");
            log.info("ConversationId: {}", conversationId);
            log.info("Redis Key: {}", key);
            log.info("Total Messages in Redis: {}", size);
            log.info("Retrieved Messages: {}", result.size());
            log.info("====================================");

        } catch (Exception e) {
            log.error("Failed to get messages for conversation: {}", conversationId, e);
        }

        return result;
    }

    @Override
    public void clear(String conversationId) {
        String key = buildKey(conversationId);
        stringRedisTemplate.delete(key);
        log.info("Cleared chat memory for conversation: {}, Redis key: {}", conversationId, key);
    }

    private String buildKey(String conversationId) {
        return KEY_PREFIX + conversationId;
    }
}
