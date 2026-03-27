package com.bridge.service.impl;

import com.bridge.proto.ChatProto;
import com.bridge.service.ChatService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

@Service
public class AIChatService implements ChatService {
    
    private static final Logger logger = LoggerFactory.getLogger(AIChatService.class);
    
    @Override
    public ChatProto.ChatResponse chat(ChatProto.ChatRequest request) {
        logger.info("Processing chat request from user: {}, message: {}",
                request.getUserId(), request.getMessage());
        
        String reply = processWithAI(request.getMessage(), request.getUserId());
        
        Map<String, String> metadata = new HashMap<>();
        metadata.put("model", "gpt-3.5-turbo");
        metadata.put("tokens_used", String.valueOf(reply.length()));
        
        ChatProto.ChatResponse response = ChatProto.ChatResponse.newBuilder()
                .setSessionId(request.getSessionId())
                .setReply(reply)
                .setStatus(200)
                .setTimestamp(System.currentTimeMillis())
                .putAllMetadata(metadata)
                .build();
        
        logger.info("Chat response generated for user: {}", request.getUserId());
        return response;
    }
    
    private String processWithAI(String message, String userId) {
        try {
            Thread.sleep(10);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
        
        String lowerMessage = message.toLowerCase();
        
        if (lowerMessage.contains("hello") || lowerMessage.contains("hi")) {
            return "Hello! I'm your AI assistant. How can I help you today?";
        } else if (lowerMessage.contains("how are you")) {
            return "I'm doing great, thank you for asking! I'm here to assist you.";
        } else if (lowerMessage.contains("bye") || lowerMessage.contains("goodbye")) {
            return "Goodbye! Have a great day!";
        } else if (lowerMessage.contains("help")) {
            return "I can help you with various tasks. Just ask me anything!";
        } else if (lowerMessage.contains("weather")) {
            return "I don't have access to real-time weather data, but you can check your local weather service!";
        } else if (lowerMessage.contains("time")) {
            return "The current time is: " + new java.util.Date();
        } else {
            return String.format(
                "Thank you for your message: \"%s\". This is a simulated AI response. " +
                "In a production environment, this would be connected to a real AI service.",
                message
            );
        }
    }
}
