package com.chat.ai.service;

import com.chat.ai.model.ChatMessage;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.messages.SystemMessage;
import org.springframework.ai.chat.messages.UserMessage;
import org.springframework.ai.chat.prompt.Prompt;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

@Slf4j
@Service
public class AiChatService {
    
    private final ChatClient chatClient;
    private final ChatMemoryService chatMemoryService;
    
    private static final String SYSTEM_PROMPT = 
        "你是一个友好的聊天机器人助手。你的名字是'AI Bot'，ID是100。" +
        "请用简洁、友好的方式回答用户的问题。如果用户问的是技术问题，请提供清晰的解释。" +
        "如果用户只是闲聊，请保持轻松愉快的对话氛围。" +
        "请记住用户在对话中提到的个人信息，以便后续对话中使用。";
    
    private static final String SESSION_ID_PREFIX = "[SESSION:";
    private static final String SESSION_ID_SUFFIX = "]";
    
    public AiChatService(ChatClient.Builder chatClientBuilder, ChatMemoryService chatMemoryService) {
        this.chatClient = chatClientBuilder.build();
        this.chatMemoryService = chatMemoryService;
    }
    
    public ChatResult chat(String userMessage, Integer userId, String userName, String sessionId) {
        if (sessionId == null || sessionId.trim().isEmpty()) {
            sessionId = generateSessionId(userId);
            log.info("Generated new sessionId: {} for user: {}", sessionId, userId);
        }
        
        final String finalSessionId = sessionId;
        
        try {
            log.info("Processing chat request from user {} ({}): {}", userId, userName, userMessage);
            
            List<ChatMessage> history = chatMemoryService.getChatHistory(finalSessionId);
            log.debug("Retrieved {} history messages for session: {}", history.size(), finalSessionId);
            
            List<Message> messages = buildMessagesWithHistory(history, userMessage);
            
            Prompt prompt = new Prompt(messages);
            String response = chatClient.prompt(prompt)
                .call()
                .content();
            
            log.info("AI response: {}", response);
            
            chatMemoryService.saveMessage(finalSessionId, ChatMessage.userMessage(userMessage));
            chatMemoryService.saveMessage(finalSessionId, ChatMessage.assistantMessage(response));
            
            return new ChatResult(response, finalSessionId);
            
        } catch (Exception e) {
            log.error("Error processing chat request", e);
            log.error("Error details: {}", e.getMessage());
            
            String errorMsg = "抱歉，我现在遇到了一些问题，无法回答你的问题。请稍后再试。";
            
            if (e.getMessage() != null && e.getMessage().contains("404")) {
                errorMsg = "API端点未找到，请检查配置。";
            } else if (e.getMessage() != null && e.getMessage().contains("401")) {
                errorMsg = "API Key无效或已过期，请检查配置。";
            } else if (e.getMessage() != null && e.getMessage().contains("429")) {
                errorMsg = "API调用频率超限，请稍后再试。";
            }
            
            throw new RuntimeException(errorMsg, e);
        }
    }
    
    public Flux<String> streamChat(String userMessage, Integer userId, String userName, String sessionId) {
        if (sessionId == null || sessionId.trim().isEmpty()) {
            sessionId = generateSessionId(userId);
            log.info("Generated new sessionId: {} for user: {}", sessionId, userId);
        }
        
        final String finalSessionId = sessionId;
        
        log.info("Processing stream chat request from user {} ({}): {}", userId, userName, userMessage);
        
        List<ChatMessage> history = chatMemoryService.getChatHistory(finalSessionId);
        log.debug("Retrieved {} history messages for session: {}", history.size(), finalSessionId);
        
        List<Message> messages = buildMessagesWithHistory(history, userMessage);
        Prompt prompt = new Prompt(messages);
        
        chatMemoryService.saveMessage(finalSessionId, ChatMessage.userMessage(userMessage));
        log.info("Saved user message for session: {}", finalSessionId);
        
        final StringBuilder fullResponse = new StringBuilder();
        
        return Flux.using(
            () -> {
                log.info("Starting stream for session: {}", finalSessionId);
                return true;
            },
            resource -> Flux.concat(
                Flux.just(SESSION_ID_PREFIX + finalSessionId + SESSION_ID_SUFFIX + "\n\n"),
                chatClient.prompt(prompt)
                    .stream()
                    .content()
                    .doOnNext(content -> {
                        if (content != null && !content.isEmpty()) {
                            fullResponse.append(content);
                        }
                    })
                    .filter(content -> content != null && !content.isEmpty())
                    .map(content -> content + "\n\n")
            ),
            resource -> {
                String response = fullResponse.toString();
                log.info("Stream ended, saving assistant message, length: {}", response.length());
                if (!response.isEmpty()) {
                    chatMemoryService.saveMessage(finalSessionId, ChatMessage.assistantMessage(response));
                    log.info("Saved assistant message for session: {}", finalSessionId);
                }
            }
        ).timeout(Duration.ofSeconds(120));
    }
    
    private List<Message> buildMessagesWithHistory(List<ChatMessage> history, String currentMessage) {
        List<Message> messages = new ArrayList<>();
        
        messages.add(new SystemMessage(SYSTEM_PROMPT));
        
        for (ChatMessage msg : history) {
            switch (msg.getRole()) {
                case USER:
                    messages.add(new UserMessage(msg.getContent()));
                    break;
                case ASSISTANT:
                    messages.add(new org.springframework.ai.chat.messages.AssistantMessage(msg.getContent()));
                    break;
                case SYSTEM:
                    messages.add(new SystemMessage(msg.getContent()));
                    break;
            }
        }
        
        messages.add(new UserMessage(currentMessage));
        
        return messages;
    }
    
    private String generateSessionId(Integer userId) {
        return "session_" + userId + "_" + UUID.randomUUID().toString().substring(0, 8);
    }
    
    public void clearSessionHistory(String sessionId) {
        chatMemoryService.clearHistory(sessionId);
    }
    
    public record ChatResult(String message, String sessionId) {}
}
