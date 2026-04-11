package com.chat.ai.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.HashMap;
import java.util.Map;

@Slf4j
@Service
public class RedisPubSubService {

    private final StringRedisTemplate stringRedisTemplate;
    private final ObjectMapper objectMapper;

    private static final String GROUP_CHANNEL_PREFIX = "group:message:";
    private static final String DIRECT_CHANNEL_PREFIX = "user:message:";
    
    private static final int GROUP_DISPATCH_CHANNEL = 9997;
    private static final int GROUP_CHAT_MSG = 17;

    public RedisPubSubService(StringRedisTemplate stringRedisTemplate, ObjectMapper objectMapper) {
        this.stringRedisTemplate = stringRedisTemplate;
        this.objectMapper = objectMapper;
    }

    public void publishGroupMessage(Long groupId, String content, Integer replyTo) {
        String channel = GROUP_CHANNEL_PREFIX + groupId;

        try {
            Map<String, Object> message = new HashMap<>();
            message.put("groupId", groupId);
            message.put("senderId", -1);
            message.put("senderName", "AI助手");
            message.put("content", content);
            message.put("timestamp", Instant.now().toEpochMilli());
            message.put("replyTo", replyTo);
            message.put("type", "AI_SUMMARY");

            String jsonMessage = objectMapper.writeValueAsString(message);
            stringRedisTemplate.convertAndSend(channel, jsonMessage);

            log.info("Published AI summary message to channel: {}, replyTo: {}", channel, replyTo);

        } catch (Exception e) {
            log.error("Error publishing message to channel: {}", channel, e);
        }
    }

    public void publishGroupMessage(Long groupId, String content) {
        publishGroupMessage(groupId, content, null);
    }

    /**
     * 发布AI角色的群聊消息
     * 发布到群组消息分发频道(9997)，由ChatServer分发给群成员
     *
     * @param groupId    群组ID
     * @param content    消息内容
     * @param botId      AI角色ID（10000~10099）
     * @param botName    AI角色名称
     * @param messageType 消息类型
     */
    public void publishAgentGroupMessage(Long groupId, String content, int botId, String botName, String messageType) {
        try {
            Map<String, Object> message = new HashMap<>();
            message.put("msgid", GROUP_CHAT_MSG);
            message.put("groupid", groupId);
            message.put("from", botId);
            message.put("fromName", botName);
            message.put("msg", content);
            message.put("timestamp", Instant.now().toEpochMilli());

            String jsonMessage = objectMapper.writeValueAsString(message);
            
            stringRedisTemplate.convertAndSend(String.valueOf(GROUP_DISPATCH_CHANNEL), jsonMessage);

            log.info("Published agent group message to dispatch channel: {}, groupId: {}, botId: {}",
                GROUP_DISPATCH_CHANNEL, groupId, botId);

        } catch (Exception e) {
            log.error("Error publishing agent message to group: {}, botId: {}", groupId, botId, e);
        }
    }

    /**
     * 发布AI角色的私聊消息（重构后）
     * 注意：ChatServer订阅的是用户ID作为频道号（如 "22"），不是 "user:message:22"
     * 消息格式需要与ChatServer的oneChat处理逻辑一致，包含msgid=6(ONE_CHAT_MSG)
     *
     * @param userId   接收用户ID
     * @param content  消息内容
     * @param botId    AI角色ID（10000~10099）
     * @param botName  AI角色名称
     */
    public void publishDirectMessage(Integer userId, String content, int botId, String botName) {
        String channel = String.valueOf(userId);

        try {
            Map<String, Object> message = new HashMap<>();
            message.put("msgid", 6);
            message.put("from", botId);
            message.put("to", userId);
            message.put("msg", content);
            message.put("name", botName);
            message.put("timestamp", Instant.now().toEpochMilli());

            String jsonMessage = objectMapper.writeValueAsString(message);
            stringRedisTemplate.convertAndSend(channel, jsonMessage);

            log.info("Published direct AI message to channel: {}, from bot: {}({})", channel, botId, botName);

        } catch (Exception e) {
            log.error("Error publishing direct message to user: {}, from bot: {}", userId, botId, e);
        }
    }

    /**
     * 兼容旧接口的私聊消息发布（默认AI助手）
     */
    public void publishDirectMessage(Integer userId, String content) {
        publishDirectMessage(userId, content, -1, "AI助手");
    }

    /**
     * 发送流式消息开始标记（AI开始思考）
     */
    public void publishStreamStart(Integer userId, int botId, String botName) {
        String channel = String.valueOf(userId);

        try {
            Map<String, Object> message = new HashMap<>();
            message.put("msgid", 6);
            message.put("from", botId);
            message.put("to", userId);
            message.put("msg", "[STREAM_CHUNK]: ");  // 空内容，触发思考提示
            message.put("name", botName);
            message.put("timestamp", Instant.now().toEpochMilli());

            String jsonMessage = objectMapper.writeValueAsString(message);
            stringRedisTemplate.convertAndSend(channel, jsonMessage);

            log.info("Published stream start to user: {}, bot: {}", userId, botName);

        } catch (Exception e) {
            log.error("Error publishing stream start to user: {}", userId, e);
        }
    }

    /**
     * 发送流式消息块
     */
    public void publishStreamChunk(Integer userId, String chunk, int botId, String botName) {
        String channel = String.valueOf(userId);

        try {
            Map<String, Object> message = new HashMap<>();
            message.put("msgid", 6);
            message.put("from", botId);
            message.put("to", userId);
            message.put("msg", "[STREAM_CHUNK]:" + chunk);
            message.put("name", botName);
            message.put("timestamp", Instant.now().toEpochMilli());

            String jsonMessage = objectMapper.writeValueAsString(message);
            stringRedisTemplate.convertAndSend(channel, jsonMessage);

        } catch (Exception e) {
            log.error("Error publishing stream chunk to user: {}", userId, e);
        }
    }

    /**
     * 发送流式消息结束标记
     */
    public void publishStreamEnd(Integer userId, int botId, String botName) {
        String channel = String.valueOf(userId);

        try {
            Map<String, Object> message = new HashMap<>();
            message.put("msgid", 6);
            message.put("from", botId);
            message.put("to", userId);
            message.put("msg", "[STREAM_CHUNK]:[STREAM_END]");
            message.put("name", botName);
            message.put("timestamp", Instant.now().toEpochMilli());

            String jsonMessage = objectMapper.writeValueAsString(message);
            stringRedisTemplate.convertAndSend(channel, jsonMessage);

            log.info("Published stream end to user: {}", userId);

        } catch (Exception e) {
            log.error("Error publishing stream end to user: {}", userId, e);
        }
    }
}
