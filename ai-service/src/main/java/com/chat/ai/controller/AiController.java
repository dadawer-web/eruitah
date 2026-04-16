package com.chat.ai.controller;

import com.chat.ai.config.annotation.RateLimit;
import com.chat.ai.service.AiChatService;
import com.chat.ai.service.AiPersonaRegistry;
import com.chat.ai.service.MultimodalChatService;
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
    private final MultimodalChatService multimodalChatService;

    @PostMapping("/chat")
    @RateLimit(dimension = RateLimit.Dimension.USER, count = 30, interval = 1, timeUnit = RateLimit.TimeUnit.MINUTES)
    @RateLimit(dimension = RateLimit.Dimension.IP, count = 60, interval = 1, timeUnit = RateLimit.TimeUnit.MINUTES)
    public ResponseEntity<ChatResponse> chat(@RequestBody ChatRequest request) {
        log.info("Received chat request: userId={}, botId={}, message={}, images={}",
            request.getUserId(), request.getBotId(), request.getMessage(),
            request.getImages() != null ? request.getImages().size() : 0);

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

            Object result;
            if (AiPersonaRegistry.isProblemSolverBot(botId)) {
                log.info("[解题大王] 使用多模态服务处理请求");
                result = multimodalChatService.chat(
                    request.getUserId(),
                    botId,
                    request.getMessage(),
                    request.getImages()
                );
            } else {
                result = aiChatService.chat(
                    request.getUserId(),
                    botId,
                    request.getMessage()
                );
            }

            if (result instanceof AiChatService.ChatResult chatResult) {
                return ResponseEntity.ok(ChatResponse.success(chatResult.message(), chatResult.sessionId()));
            } else if (result instanceof MultimodalChatService.ChatResult multimodalResult) {
                return ResponseEntity.ok(ChatResponse.success(multimodalResult.message(), multimodalResult.sessionId()));
            }

            return ResponseEntity.internalServerError()
                .body(ChatResponse.error("未知的结果类型"));

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

    @PostMapping("/mindmap")
    @RateLimit(dimension = RateLimit.Dimension.USER, count = 10, interval = 1, timeUnit = RateLimit.TimeUnit.MINUTES)
    @RateLimit(dimension = RateLimit.Dimension.IP, count = 20, interval = 1, timeUnit = RateLimit.TimeUnit.MINUTES)
    public ResponseEntity<ChatResponse> generateMindmap(@RequestBody MindmapRequest request) {
        log.info("Received mindmap request: userId={}, topic={}", request.getUserId(), request.getTopic());

        if (request.getTopic() == null || request.getTopic().trim().isEmpty()) {
            return ResponseEntity.badRequest()
                .body(ChatResponse.error("主题不能为空"));
        }

        if (request.getUserId() == null) {
            return ResponseEntity.badRequest()
                .body(ChatResponse.error("用户ID不能为空"));
        }

        try {
            String prompt = String.format("请帮我总结一下%s的所有知识点，使用Mermaid思维导图语法输出。", request.getTopic());
            
            MultimodalChatService.ChatResult result = multimodalChatService.chat(
                request.getUserId(),
                AiPersonaRegistry.PROBLEM_SOLVER_ID,
                prompt,
                null
            );

            return ResponseEntity.ok(ChatResponse.success(result.message(), result.sessionId()));

        } catch (Exception e) {
            log.error("Error processing mindmap request", e);
            return ResponseEntity.internalServerError()
                .body(ChatResponse.error("处理请求时发生错误: " + e.getMessage()));
        }
    }
}
