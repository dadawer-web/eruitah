package com.chat.ai.controller;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class GroupChatResponse {
    private String message;
    private boolean success;
    private String error;
    private Long groupId;
    private Object data;
    
    public static GroupChatResponse success(String message) {
        return new GroupChatResponse(message, true, null, null, null);
    }
    
    public static GroupChatResponse success(String message, Long groupId) {
        return new GroupChatResponse(message, true, null, groupId, null);
    }
    
    public static GroupChatResponse success(String message, Long groupId, Object data) {
        return new GroupChatResponse(message, true, null, groupId, data);
    }
    
    public static GroupChatResponse error(String error) {
        return new GroupChatResponse(null, false, error, null, null);
    }
    
    public static GroupChatResponse error(String error, Long groupId) {
        return new GroupChatResponse(null, false, error, groupId, null);
    }
}
