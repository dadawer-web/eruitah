package com.chat.ai.controller;

import com.chat.ai.service.AiChatService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@Slf4j
@RestController
@RequestMapping("/api/ai")
@RequiredArgsConstructor
public class AiController {
    
    private final AiChatService aiChatService;
    
    @PostMapping("/chat")
    public ResponseEntity<ChatResponse> chat(@RequestBody ChatRequest request) {
        log.info("Received chat request: sessionId={}, userId={}, message={}", 
            request.getSessionId(), request.getUserId(), request.getMessage());
        
        if (request.getMessage() == null || request.getMessage().trim().isEmpty()) {
            return ResponseEntity.badRequest()
                .body(ChatResponse.error("消息不能为空"));
        }
        
        try {
            AiChatService.ChatResult result = aiChatService.chat(
                request.getMessage(),
                request.getUserId(),
                request.getUserName(),
                request.getSessionId()
            );
            
            return ResponseEntity.ok(ChatResponse.success(result.message(), result.sessionId()));
            
        } catch (Exception e) {
            log.error("Error processing chat request", e);
            return ResponseEntity.internalServerError()
                .body(ChatResponse.error("处理请求时发生错误: " + e.getMessage()));
        }
    }
    
    @DeleteMapping("/session/{sessionId}")
    public ResponseEntity<ChatResponse> clearSession(@PathVariable String sessionId) {
        log.info("Clearing session: {}", sessionId);
        aiChatService.clearSessionHistory(sessionId);
        return ResponseEntity.ok(ChatResponse.success("会话已清除"));
    }
    
    @GetMapping("/health")
    public ResponseEntity<String> health() {
        return ResponseEntity.ok("AI Service is running");
    }
}
