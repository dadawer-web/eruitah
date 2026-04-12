package com.chat.ai.controller;

import lombok.Data;
import java.util.List;

@Data
public class ChatRequest {
    private String message;
    private Integer userId;
    private String userName;
    private String sessionId;
    private Integer botId;
    private List<ImageData> images;

    @Data
    public static class ImageData {
        private String base64;
        private String mimeType;
    }
}
