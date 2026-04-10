package com.chat.ai.controller;

import lombok.Data;

import java.util.List;

@Data
public class GroupMessageRequest {
    private Long groupId;
    private Integer senderId;
    private String senderName;
    private String content;
    private List<Integer> aiBotIds;
}
