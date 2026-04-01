package com.chat.ai.service;

import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.TimeUnit;

@Slf4j
@Service
public class GroupChatMemoryService {
    
    private final RedisTemplate<String, Object> redisTemplate;
    
    @Value("${group.chat.max-messages:100}")
    private int maxMessages;
    
    @Value("${group.chat.ttl-hours:24}")
    private int ttlHours;
    
    private static final String GROUP_CHAT_PREFIX = "group:chat:";
    
    public GroupChatMemoryService(RedisTemplate<String, Object> redisTemplate) {
        this.redisTemplate = redisTemplate;
    }
    
    public List<String> getRecentMessages(Long groupId, int count) {
        String key = GROUP_CHAT_PREFIX + groupId;
        try {
            List<Object> rawMessages = redisTemplate.opsForList().range(key, 0, count - 1);
            
            if (rawMessages == null || rawMessages.isEmpty()) {
                log.debug("No messages found for group: {}", groupId);
                return Collections.emptyList();
            }
            
            List<String> messages = new ArrayList<>();
            for (Object msg : rawMessages) {
                if (msg != null) {
                    messages.add(msg.toString());
                }
            }
            
            log.debug("Retrieved {} messages for group: {}", messages.size(), groupId);
            return messages;
            
        } catch (Exception e) {
            log.error("Error retrieving messages for group: {}", groupId, e);
            return Collections.emptyList();
        }
    }
    
    public List<String> getAllMessages(Long groupId) {
        return getRecentMessages(groupId, maxMessages);
    }
    
    public long getMessageCount(Long groupId) {
        String key = GROUP_CHAT_PREFIX + groupId;
        Long size = redisTemplate.opsForList().size(key);
        return size != null ? size : 0;
    }
    
    public void clearGroupMessages(Long groupId) {
        String key = GROUP_CHAT_PREFIX + groupId;
        redisTemplate.delete(key);
        log.info("Cleared all messages for group: {}", groupId);
    }
    
    public void refreshTTL(Long groupId) {
        String key = GROUP_CHAT_PREFIX + groupId;
        redisTemplate.expire(key, ttlHours, TimeUnit.HOURS);
        log.debug("Refreshed TTL for group: {}", groupId);
    }
    
    public String formatMessagesForSummary(List<String> messages) {
        if (messages == null || messages.isEmpty()) {
            return "【群聊记录为空】";
        }
        
        StringBuilder sb = new StringBuilder();
        sb.append("【群聊记录】\n\n");
        
        for (int i = messages.size() - 1; i >= 0; i--) {
            sb.append(messages.get(i)).append("\n");
        }
        
        sb.append("\n【共 ").append(messages.size()).append(" 条消息】");
        return sb.toString();
    }
}
