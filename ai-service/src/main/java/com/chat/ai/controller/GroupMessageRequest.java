package com.chat.ai.controller;

import lombok.Data;

@Data
public class GroupMessageRequest {
    private Long groupId;
    private Integer senderId;
    private String senderName;
    private String content;
}
