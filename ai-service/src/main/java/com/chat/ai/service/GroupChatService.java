package com.chat.ai.service;

import com.chat.ai.model.AiTask;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.messages.SystemMessage;
import org.springframework.ai.chat.messages.UserMessage;
import org.springframework.ai.chat.prompt.Prompt;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Slf4j
@Service
public class GroupChatService {
    
    private final GroupChatMemoryService groupChatMemoryService;
    private final RedisPubSubService redisPubSubService;
    private final RedisTemplate<String, Object> redisTemplate;
    private final ChatClient chatClient;
    private final ObjectMapper objectMapper;
    
    private static final String TASK_QUEUE_KEY = "ai:task:queue";
    private static final int DEFAULT_MESSAGE_COUNT = 100;
    
    private static final String SUMMARY_SYSTEM_PROMPT = 
        "你是一个群聊纪要助手，专门负责总结群聊内容并生成简洁、有趣的摘要。\n" +
        "你的任务：\n" +
        "1. 分析群聊记录，提取主要讨论话题\n" +
        "2. 总结关键信息和结论\n" +
        "3. 如果有争议或有趣的观点，可以适当'吃瓜'点评\n" +
        "4. 用轻松幽默的语气，让摘要更有趣\n\n" +
        "输出格式要求：\n" +
        "📢 **群聊摘要**\n" +
        "━━━━━━━━━━━━━━━━\n" +
        "🔥 热门话题：[列出主要话题]\n" +
        "📝 讨论要点：\n" +
        "- [要点1]\n" +
        "- [要点2]\n" +
        "🍉 吃瓜点评：[有趣的点评]\n" +
        "━━━━━━━━━━━━━━━━\n" +
        "请保持摘要简洁，突出重点，风格活泼。";
    
    private static final Pattern SUMMARY_TRIGGER_PATTERN = 
        Pattern.compile("@AI\\s*总结一下(今天)?群里聊了什么", Pattern.CASE_INSENSITIVE);
    
    public GroupChatService(
            GroupChatMemoryService groupChatMemoryService,
            RedisPubSubService redisPubSubService,
            RedisTemplate<String, Object> redisTemplate,
            ChatClient.Builder chatClientBuilder,
            ObjectMapper objectMapper) {
        this.groupChatMemoryService = groupChatMemoryService;
        this.redisPubSubService = redisPubSubService;
        this.redisTemplate = redisTemplate;
        this.chatClient = chatClientBuilder.build();
        this.objectMapper = objectMapper;
    }
    
    public boolean isSummaryRequest(String content) {
        if (content == null) return false;
        Matcher matcher = SUMMARY_TRIGGER_PATTERN.matcher(content.trim());
        return matcher.find();
    }
    
    public void submitSummaryTask(Long groupId, Integer replyTo, String replyToName, String triggerMessage) {
        try {
            AiTask task = AiTask.summaryTask(groupId, replyTo, replyToName, triggerMessage);
            String taskJson = objectMapper.writeValueAsString(task);
            
            redisTemplate.opsForList().leftPush(TASK_QUEUE_KEY, taskJson);
            
            log.info("Submitted summary task to queue: groupId={}, replyTo={}", groupId, replyTo);
            
        } catch (Exception e) {
            log.error("Error submitting summary task for group: {}", groupId, e);
        }
    }
    
    public String generateSummarySync(Long groupId, int messageCount) {
        log.info("Generating sync summary for group: {}, messageCount: {}", groupId, messageCount);
        
        try {
            List<String> messages = groupChatMemoryService.getRecentMessages(groupId, messageCount);
            
            if (messages.isEmpty()) {
                return "📢 **群聊摘要**\n\n群聊记录为空，还没有人说话呢~";
            }
            
            String chatLog = groupChatMemoryService.formatMessagesForSummary(messages);
            
            List<Message> promptMessages = new ArrayList<>();
            promptMessages.add(new SystemMessage(SUMMARY_SYSTEM_PROMPT));
            promptMessages.add(new UserMessage("以下是群聊记录，请生成摘要：\n\n" + chatLog));
            
            Prompt prompt = new Prompt(promptMessages);
            String response = chatClient.prompt(prompt)
                .call()
                .content();
            
            log.info("Generated summary for group: {}, length: {}", groupId, response.length());
            return response;
            
        } catch (Exception e) {
            log.error("Error generating summary for group: {}", groupId, e);
            return "📢 **群聊摘要**\n\n抱歉，生成摘要时出现问题：" + e.getMessage();
        }
    }
    
    public GroupChatSummary getGroupChatInfo(Long groupId) {
        long totalCount = groupChatMemoryService.getMessageCount(groupId);
        return new GroupChatSummary(groupId, totalCount);
    }
    
    public void clearGroupMessages(Long groupId) {
        groupChatMemoryService.clearGroupMessages(groupId);
        log.info("Cleared messages for group: {}", groupId);
    }
    
    public record GroupChatSummary(Long groupId, long totalMessages) {}
}
