package com.chat.ai.controller;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class AgentRequest {
    private Integer userId;
    private String userName;
    private String message;
}
