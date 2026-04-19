package com.chat.ai.controller;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class CompanionReadResponse {
    private String audioUrl;
    private String explanationText;
    private boolean success;
    private String error;

    public static CompanionReadResponse success(String audioUrl, String explanationText) {
        return new CompanionReadResponse(audioUrl, explanationText, true, null);
    }

    public static CompanionReadResponse error(String error) {
        return new CompanionReadResponse(null, null, false, error);
    }
}
