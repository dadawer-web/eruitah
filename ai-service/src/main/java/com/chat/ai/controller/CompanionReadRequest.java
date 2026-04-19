package com.chat.ai.controller;

import lombok.Data;

@Data
public class CompanionReadRequest {
    private String action;
    private String text;
    private Integer userId;
}
