package com.chat.ai.service;

import com.chat.ai.model.ChatMessage;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

@Slf4j
@Service
public class ChatMemoryService {
    
    private final RedisTemplate<String, Object> redisTemplate;
    private final ObjectMapper objectMapper;
    
    @Value("${chat.memory.max-history:10}")
    private int maxHistory;
    
    @Value("${chat.memory.ttl-minutes:30}")
    private int ttlMinutes;
    
    private static final String CHAT_HISTORY_PREFIX = "chat:history:";
    
    public ChatMemoryService(RedisTemplate<String, Object> redisTemplate, ObjectMapper objectMapper) {
        this.redisTemplate = redisTemplate;
        this.objectMapper = objectMapper;
    }
    
    @SuppressWarnings("unchecked")
    public List<ChatMessage> getChatHistory(String sessionId) {
        String key = CHAT_HISTORY_PREFIX + sessionId;
        try {
            Object history = redisTemplate.opsForValue().get(key);
            if (history == null) {
                log.debug("No chat history found for session: {}", sessionId);
                return new ArrayList<>();
            }
            
            List<?> rawList;
            if (history instanceof List) {
                rawList = (List<?>) history;
            } else {
                log.warn("Unexpected history type: {}", history.getClass());
                return new ArrayList<>();
            }
            
            List<ChatMessage> messages = new ArrayList<>();
            for (Object item : rawList) {
                if (item instanceof ChatMessage) {
                    messages.add((ChatMessage) item);
                } else {
                    String json = objectMapper.writeValueAsString(item);
                    ChatMessage msg = objectMapper.readValue(json, ChatMessage.class);
                    messages.add(msg);
                }
            }
            
            log.debug("Retrieved {} messages for session: {}", messages.size(), sessionId);
            return messages;
            
        } catch (Exception e) {
            log.error("Error deserializing chat history for session: {}", sessionId, e);
            return new ArrayList<>();
        }
    }
    
    @Async
    public void saveMessageAsync(String sessionId, ChatMessage message) {
        saveMessage(sessionId, message);
    }
    
    public void saveMessage(String sessionId, ChatMessage message) {
        String key = CHAT_HISTORY_PREFIX + sessionId;
        try {
            List<ChatMessage> history = getChatHistory(sessionId);
            history.add(message);
            
            if (history.size() > maxHistory) {
                history = new ArrayList<>(history.subList(history.size() - maxHistory, history.size()));
            }
            
            redisTemplate.opsForValue().set(key, history, ttlMinutes, TimeUnit.MINUTES);
            log.info("Saved message for session: {}, role: {}, history size: {}", sessionId, message.getRole(), history.size());
            
        } catch (Exception e) {
            log.error("Error saving chat history for session: {}", sessionId, e);
        }
    }
    
    public void clearHistory(String sessionId) {
        String key = CHAT_HISTORY_PREFIX + sessionId;
        redisTemplate.delete(key);
        log.info("Cleared chat history for session: {}", sessionId);
    }
    
    public void refreshTTL(String sessionId) {
        String key = CHAT_HISTORY_PREFIX + sessionId;
        redisTemplate.expire(key, ttlMinutes, TimeUnit.MINUTES);
        log.debug("Refreshed TTL for session: {}", sessionId);
    }
}
