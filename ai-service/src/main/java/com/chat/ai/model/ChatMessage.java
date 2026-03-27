package com.chat.ai.model;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.io.Serializable;
import java.time.Instant;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class ChatMessage implements Serializable {
    
    private static final long serialVersionUID = 1L;
    
    public enum Role {
        USER,
        ASSISTANT,
        SYSTEM
    }
    
    private Role role;
    private String content;
    private Instant timestamp;
    
    public static ChatMessage userMessage(String content) {
        return new ChatMessage(Role.USER, content, Instant.now());
    }
    
    public static ChatMessage assistantMessage(String content) {
        return new ChatMessage(Role.ASSISTANT, content, Instant.now());
    }
    
    public static ChatMessage systemMessage(String content) {
        return new ChatMessage(Role.SYSTEM, content, Instant.now());
    }
}
