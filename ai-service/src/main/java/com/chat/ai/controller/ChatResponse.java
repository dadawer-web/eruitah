package com.chat.ai.controller;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class ChatResponse {
    private String message;
    private boolean success;
    private String error;
    private String sessionId;
    
    public static ChatResponse success(String message) {
        return new ChatResponse(message, true, null, null);
    }
    
    public static ChatResponse success(String message, String sessionId) {
        return new ChatResponse(message, true, null, sessionId);
    }
    
    public static ChatResponse error(String error) {
        return new ChatResponse(null, false, error, null);
    }
}
