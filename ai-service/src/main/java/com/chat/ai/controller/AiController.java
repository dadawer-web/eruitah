package com.chat.ai.controller;

import com.chat.ai.service.AiChatService;
import com.chat.ai.service.AiPersonaRegistry;
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

    /**
     * 1v1 AI聊天接口（重构后）
     *
     * 支持两种调用方式：
     * 1. 新接口：传入 botId，指定与哪个AI角色聊天
     * 2. 兼容旧接口：不传 botId，默认与旗舰大师(10000)聊天
     */
    @PostMapping("/chat")
    public ResponseEntity<ChatResponse> chat(@RequestBody ChatRequest request) {
        log.info("Received chat request: userId={}, botId={}, message={}",
            request.getUserId(), request.getBotId(), request.getMessage());

        if (request.getMessage() == null || request.getMessage().trim().isEmpty()) {
            return ResponseEntity.badRequest()
                .body(ChatResponse.error("消息不能为空"));
        }

        if (request.getUserId() == null) {
            return ResponseEntity.badRequest()
                .body(ChatResponse.error("用户ID不能为空"));
        }

        try {
            int botId = request.getBotId() != null ? request.getBotId() : AiPersonaRegistry.MASTER_408_ID;

            if (!AiPersonaRegistry.isAiBot(botId)) {
                return ResponseEntity.badRequest()
                    .body(ChatResponse.error("无效的AI角色ID: " + botId));
            }

            AiChatService.ChatResult result = aiChatService.chat(
                request.getUserId(),
                botId,
                request.getMessage()
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
