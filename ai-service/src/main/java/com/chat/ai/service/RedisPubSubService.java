package com.chat.ai.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.HashMap;
import java.util.Map;

@Slf4j
@Service
public class RedisPubSubService {
    
    private final RedisTemplate<String, Object> redisTemplate;
    private final ObjectMapper objectMapper;
    
    private static final String GROUP_CHANNEL_PREFIX = "group:message:";
    private static final String AI_SENDER_NAME = "AI助手";
    private static final int AI_SENDER_ID = -1;
    
    public RedisPubSubService(RedisTemplate<String, Object> redisTemplate, ObjectMapper objectMapper) {
        this.redisTemplate = redisTemplate;
        this.objectMapper = objectMapper;
    }
    
    public void publishGroupMessage(Long groupId, String content, Integer replyTo) {
        String channel = GROUP_CHANNEL_PREFIX + groupId;
        
        try {
            Map<String, Object> message = new HashMap<>();
            message.put("groupId", groupId);
            message.put("senderId", AI_SENDER_ID);
            message.put("senderName", AI_SENDER_NAME);
            message.put("content", content);
            message.put("timestamp", Instant.now().toEpochMilli());
            message.put("replyTo", replyTo);
            message.put("type", "AI_SUMMARY");
            
            String jsonMessage = objectMapper.writeValueAsString(message);
            
            redisTemplate.convertAndSend(channel, jsonMessage);
            
            log.info("Published AI message to channel: {}, replyTo: {}", channel, replyTo);
            
        } catch (Exception e) {
            log.error("Error publishing message to channel: {}", channel, e);
        }
    }
    
    public void publishGroupMessage(Long groupId, String content) {
        publishGroupMessage(groupId, content, null);
    }
    
    public void publishDirectMessage(Integer userId, String content) {
        String channel = "user:message:" + userId;
        
        try {
            Map<String, Object> message = new HashMap<>();
            message.put("receiverId", userId);
            message.put("senderId", AI_SENDER_ID);
            message.put("senderName", AI_SENDER_NAME);
            message.put("content", content);
            message.put("timestamp", Instant.now().toEpochMilli());
            message.put("type", "AI_DIRECT");
            
            String jsonMessage = objectMapper.writeValueAsString(message);
            
            redisTemplate.convertAndSend(channel, jsonMessage);
            
            log.info("Published direct AI message to user: {}", userId);
            
        } catch (Exception e) {
            log.error("Error publishing direct message to user: {}", userId, e);
        }
    }
}
