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

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

@Slf4j
@Service
public class AiTaskConsumer {
    
    private final RedisTemplate<String, Object> redisTemplate;
    private final GroupChatMemoryService groupChatMemoryService;
    private final RedisPubSubService redisPubSubService;
    private final ChatClient chatClient;
    private final ObjectMapper objectMapper;
    
    private static final String TASK_QUEUE_KEY = "ai:task:queue";
    private static final int DEFAULT_MESSAGE_COUNT = 100;
    
    private final AtomicBoolean running = new AtomicBoolean(false);
    private ExecutorService executorService;
    
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
    
    public AiTaskConsumer(
            RedisTemplate<String, Object> redisTemplate,
            GroupChatMemoryService groupChatMemoryService,
            RedisPubSubService redisPubSubService,
            ChatClient.Builder chatClientBuilder,
            ObjectMapper objectMapper) {
        this.redisTemplate = redisTemplate;
        this.groupChatMemoryService = groupChatMemoryService;
        this.redisPubSubService = redisPubSubService;
        this.chatClient = chatClientBuilder.build();
        this.objectMapper = objectMapper;
    }
    
    @PostConstruct
    public void start() {
        running.set(true);
        int workerCount = Runtime.getRuntime().availableProcessors();
        executorService = Executors.newFixedThreadPool(workerCount);
        
        for (int i = 0; i < workerCount; i++) {
            executorService.submit(this::consumeTasks);
        }
        
        log.info("AI Task Consumer started with {} workers", workerCount);
    }
    
    @PreDestroy
    public void stop() {
        running.set(false);
        if (executorService != null) {
            executorService.shutdown();
            try {
                if (!executorService.awaitTermination(10, TimeUnit.SECONDS)) {
                    executorService.shutdownNow();
                }
            } catch (InterruptedException e) {
                executorService.shutdownNow();
                Thread.currentThread().interrupt();
            }
        }
        log.info("AI Task Consumer stopped");
    }
    
    private void consumeTasks() {
        log.info("Worker started, listening on queue: {}", TASK_QUEUE_KEY);
        
        while (running.get()) {
            try {
                Object taskData = redisTemplate.opsForList()
                    .rightPop(TASK_QUEUE_KEY, 5, TimeUnit.SECONDS);
                
                if (taskData == null) {
                    continue;
                }
                
                log.info("Received task from queue: {}", taskData);
                processTask(taskData.toString());
                
            } catch (Exception e) {
                if (running.get()) {
                    log.error("Error consuming task", e);
                    try {
                        Thread.sleep(1000);
                    } catch (InterruptedException ie) {
                        Thread.currentThread().interrupt();
                        break;
                    }
                }
            }
        }
        
        log.info("Worker stopped");
    }
    
    private void processTask(String taskJson) {
        try {
            AiTask task = objectMapper.readValue(taskJson, AiTask.class);
            log.info("Processing task: groupId={}, type={}, replyTo={}", 
                task.getGroupId(), task.getTaskType(), task.getReplyTo());
            
            switch (task.getTaskType()) {
                case SUMMARY:
                    processSummaryTask(task);
                    break;
                case CHAT_REPLY:
                    processChatReplyTask(task);
                    break;
                default:
                    log.warn("Unknown task type: {}", task.getTaskType());
            }
            
        } catch (Exception e) {
            log.error("Error processing task: {}", taskJson, e);
        }
    }
    
    private void processSummaryTask(AiTask task) {
        Long groupId = task.getGroupId();
        
        try {
            List<String> messages = groupChatMemoryService.getRecentMessages(groupId, DEFAULT_MESSAGE_COUNT);
            
            if (messages.isEmpty()) {
                String emptyMsg = "📢 **群聊摘要**\n\n群聊记录为空，还没有人说话呢~";
                publishResult(groupId, emptyMsg, task.getReplyTo());
                return;
            }
            
            String chatLog = groupChatMemoryService.formatMessagesForSummary(messages);
            
            List<Message> promptMessages = new ArrayList<>();
            promptMessages.add(new SystemMessage(SUMMARY_SYSTEM_PROMPT));
            promptMessages.add(new UserMessage("以下是群聊记录，请生成摘要：\n\n" + chatLog));
            
            Prompt prompt = new Prompt(promptMessages);
            String summary = chatClient.prompt(prompt)
                .call()
                .content();
            
            log.info("Generated summary for group: {}, length: {}", groupId, summary.length());
            publishResult(groupId, summary, task.getReplyTo());
            
        } catch (Exception e) {
            log.error("Error generating summary for group: {}", groupId, e);
            String errorMsg = "📢 **群聊摘要**\n\n抱歉，生成摘要时出现问题：" + e.getMessage();
            publishResult(groupId, errorMsg, task.getReplyTo());
        }
    }
    
    private void processChatReplyTask(AiTask task) {
        log.info("Processing chat reply task: {}", task);
    }
    
    private void publishResult(Long groupId, String content, Integer replyTo) {
        try {
            redisPubSubService.publishGroupMessage(groupId, content, replyTo);
            log.info("Published result to group: {}, replyTo: {}", groupId, replyTo);
        } catch (Exception e) {
            log.error("Error publishing result for group: {}", groupId, e);
        }
    }
}
