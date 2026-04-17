package com.chat.ai.service;

import com.chat.ai.controller.ChatRequest;
import com.chat.ai.model.ChatMessage;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.messages.SystemMessage;
import org.springframework.ai.chat.messages.UserMessage;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.prompt.Prompt;
import org.springframework.ai.model.Media;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.stereotype.Service;
import org.springframework.util.MimeTypeUtils;
import reactor.core.publisher.Flux;

import java.util.ArrayList;
import java.util.Base64;
import java.util.List;
import java.util.UUID;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Slf4j
@Service
public class MultimodalChatService {

    private final ChatClient multimodalChatClient;
    private final ChatMemoryService chatMemoryService;
    private final RedisPubSubService redisPubSubService;
    
    private static final Pattern IMAGE_PATTERN = Pattern.compile("\\[IMAGE\\]([^,]+),([^\\[]+)");

    public MultimodalChatService(
            @Qualifier("multimodalChatClient") ChatClient multimodalChatClient,
            ChatMemoryService chatMemoryService,
            RedisPubSubService redisPubSubService) {
        this.multimodalChatClient = multimodalChatClient;
        this.chatMemoryService = chatMemoryService;
        this.redisPubSubService = redisPubSubService;
    }

    public ChatResult chat(int userId, int botId, String message, List<ChatRequest.ImageData> images) {
        String sessionId = generateSessionId(userId, botId);
        log.info("多模态聊天: userId={}, botId={}({}), message={}, images={}",
            userId, botId, AiPersonaRegistry.getBotName(botId), message, 
            images != null ? images.size() : 0);

        try {
            SystemMessage systemMessage = AiPersonaRegistry.getPersonaByBotId(botId);

            List<ChatRequest.ImageData> allImages = new ArrayList<>();
            String processedMessage = message;
            
            if (images != null && !images.isEmpty()) {
                allImages.addAll(images);
            }
            
            List<ChatRequest.ImageData> extractedImages = extractImagesFromMessage(message);
            if (!extractedImages.isEmpty()) {
                allImages.addAll(extractedImages);
                processedMessage = removeImageTagsFromMessage(message);
                log.info("[解题大王] 从消息中提取了 {} 张图片", extractedImages.size());
            }

            String response;
            
            if (!allImages.isEmpty()) {
                log.info("[解题大王] 处理多模态消息，图片数量: {}", allImages.size());
                
                List<Media> mediaList = new ArrayList<>();
                for (ChatRequest.ImageData imageData : allImages) {
                    String mimeTypeStr = imageData.getMimeType();
                    if (mimeTypeStr == null || mimeTypeStr.isEmpty()) {
                        mimeTypeStr = "image/jpeg";
                    }
                    
                    String base64Data = imageData.getBase64();
                    if (base64Data.contains(",")) {
                        base64Data = base64Data.split(",")[1];
                    }
                    
                    log.info("[解题大王] 图片数据长度: {} 字符, MIME类型: {}", base64Data.length(), mimeTypeStr);
                    
                    byte[] imageBytes = Base64.getDecoder().decode(base64Data);
                    ByteArrayResource resource = new ByteArrayResource(imageBytes);
                    mediaList.add(new Media(MimeTypeUtils.parseMimeType(mimeTypeStr), resource));
                }
                
                UserMessage userMessage = new UserMessage(processedMessage.isEmpty() ? "请分析这张图片" : processedMessage, mediaList);
                
                List<org.springframework.ai.chat.messages.Message> messages = new ArrayList<>();
                messages.add(systemMessage);
                messages.add(userMessage);
                
                Prompt prompt = new Prompt(messages);
                
                ChatResponse chatResponse = multimodalChatClient.prompt(prompt)
                    .call()
                    .chatResponse();
                    
                response = chatResponse.getResult().getOutput().getContent();
                
                log.info("[解题大王] 模型响应成功");
            } else {
                List<ChatMessage> history = chatMemoryService.getChatHistory(sessionId);
                
                List<org.springframework.ai.chat.messages.Message> messages = new ArrayList<>();
                messages.add(systemMessage);

                for (ChatMessage msg : history) {
                    switch (msg.getRole()) {
                        case USER -> messages.add(new UserMessage(msg.getContent()));
                        case ASSISTANT -> messages.add(new org.springframework.ai.chat.messages.AssistantMessage(msg.getContent()));
                        case SYSTEM -> messages.add(new SystemMessage(msg.getContent()));
                    }
                }
                messages.add(new UserMessage(message));

                Prompt prompt = new Prompt(messages);
                response = multimodalChatClient.prompt(prompt)
                    .call()
                    .content();
            }

            chatMemoryService.saveMessage(sessionId, ChatMessage.userMessage(message));
            chatMemoryService.saveMessage(sessionId, ChatMessage.assistantMessage(response));

            log.info("[解题大王] 回复长度: {}字符", response.length());

            return new ChatResult(response, sessionId);

        } catch (Exception e) {
            log.error("多模态聊天失败: userId={}, botId={}", userId, botId, e);
            throw new RuntimeException("AI回复失败: " + e.getMessage(), e);
        }
    }

    public ChatStreamResult chatStream(int userId, int botId, String message, List<ChatRequest.ImageData> images) {
        String sessionId = generateSessionId(userId, botId);
        log.info("多模态流式聊天: userId={}, botId={}({}), message={}, images={}",
            userId, botId, AiPersonaRegistry.getBotName(botId), message, 
            images != null ? images.size() : 0);

        try {
            SystemMessage systemMessage = AiPersonaRegistry.getPersonaByBotId(botId);

            List<ChatRequest.ImageData> allImages = new ArrayList<>();
            String processedMessage = message;
            
            if (images != null && !images.isEmpty()) {
                allImages.addAll(images);
            }
            
            List<ChatRequest.ImageData> extractedImages = extractImagesFromMessage(message);
            if (!extractedImages.isEmpty()) {
                allImages.addAll(extractedImages);
                processedMessage = removeImageTagsFromMessage(message);
                log.info("[解题大王] 流式模式：从消息中提取了 {} 张图片", extractedImages.size());
            }

            if (!allImages.isEmpty()) {
                log.info("[解题大王] 流式模式：处理多模态消息，图片数量: {}", allImages.size());
                
                List<Media> mediaList = new ArrayList<>();
                for (ChatRequest.ImageData imageData : allImages) {
                    String mimeTypeStr = imageData.getMimeType();
                    if (mimeTypeStr == null || mimeTypeStr.isEmpty()) {
                        mimeTypeStr = "image/jpeg";
                    }
                    
                    String base64Data = imageData.getBase64();
                    if (base64Data.contains(",")) {
                        base64Data = base64Data.split(",")[1];
                    }
                    
                    byte[] imageBytes = Base64.getDecoder().decode(base64Data);
                    ByteArrayResource resource = new ByteArrayResource(imageBytes);
                    mediaList.add(new Media(MimeTypeUtils.parseMimeType(mimeTypeStr), resource));
                }
                
                UserMessage userMessage = new UserMessage(processedMessage.isEmpty() ? "请分析这张图片" : processedMessage, mediaList);
                
                List<org.springframework.ai.chat.messages.Message> messages = new ArrayList<>();
                messages.add(systemMessage);
                messages.add(userMessage);
                
                Prompt prompt = new Prompt(messages);
                
                Flux<String> stream = multimodalChatClient.prompt(prompt)
                    .stream()
                    .content();
                
                return new ChatStreamResult(stream, sessionId);
            } else {
                List<ChatMessage> history = chatMemoryService.getChatHistory(sessionId);
                
                List<org.springframework.ai.chat.messages.Message> messages = new ArrayList<>();
                messages.add(systemMessage);

                for (ChatMessage msg : history) {
                    switch (msg.getRole()) {
                        case USER -> messages.add(new UserMessage(msg.getContent()));
                        case ASSISTANT -> messages.add(new org.springframework.ai.chat.messages.AssistantMessage(msg.getContent()));
                        case SYSTEM -> messages.add(new SystemMessage(msg.getContent()));
                    }
                }
                messages.add(new UserMessage(message));

                Prompt prompt = new Prompt(messages);
                
                Flux<String> stream = multimodalChatClient.prompt(prompt)
                    .stream()
                    .content();
                
                return new ChatStreamResult(stream, sessionId);
            }

        } catch (Exception e) {
            log.error("多模态流式聊天失败: userId={}, botId={}", userId, botId, e);
            throw new RuntimeException("AI流式回复失败: " + e.getMessage(), e);
        }
    }
    
    private List<ChatRequest.ImageData> extractImagesFromMessage(String message) {
        List<ChatRequest.ImageData> images = new ArrayList<>();
        Matcher matcher = IMAGE_PATTERN.matcher(message);
        
        while (matcher.find()) {
            String imageType = matcher.group(1);
            String base64Data = matcher.group(2);
            
            String mimeType = "image/" + imageType.toLowerCase();
            if (imageType.equalsIgnoreCase("jpg")) {
                mimeType = "image/jpeg";
            }
            
            ChatRequest.ImageData imageData = new ChatRequest.ImageData();
            imageData.setBase64(base64Data);
            imageData.setMimeType(mimeType);
            images.add(imageData);
        }
        
        return images;
    }
    
    private String removeImageTagsFromMessage(String message) {
        return IMAGE_PATTERN.matcher(message).replaceAll("").trim();
    }

    private String generateSessionId(Integer userId, int botId) {
        return "session_" + userId + "_bot" + botId + "_" + UUID.randomUUID().toString().substring(0, 8);
    }

    public void clearSessionHistory(String sessionId) {
        chatMemoryService.clearHistory(sessionId);
    }

    public record ChatResult(String message, String sessionId) {}
    
    public record ChatStreamResult(Flux<String> messageStream, String sessionId) {}
}
