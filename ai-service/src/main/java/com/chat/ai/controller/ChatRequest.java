package com.chat.ai.controller;

import lombok.Data;

@Data
public class ChatRequest {
    private String message;
    private Integer userId;
    private String userName;
    private String sessionId;
}
