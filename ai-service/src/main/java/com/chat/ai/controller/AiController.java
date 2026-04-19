package com.chat.ai.controller;

import com.chat.ai.config.annotation.RateLimit;
import com.chat.ai.service.AiChatService;
import com.chat.ai.service.AiPersonaRegistry;
import com.chat.ai.service.CompanionReadingService;
import com.chat.ai.service.MultimodalChatService;
import com.chat.ai.service.PdfParseService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.util.Map;

@Slf4j
@RestController
@RequestMapping("/api/ai")
@RequiredArgsConstructor
public class AiController {

    private final AiChatService aiChatService;
    private final MultimodalChatService multimodalChatService;
    private final CompanionReadingService companionReadingService;
    private final PdfParseService pdfParseService;

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

    @PostMapping("/companion-read")
    @RateLimit(dimension = RateLimit.Dimension.USER, count = 20, interval = 1, timeUnit = RateLimit.TimeUnit.MINUTES)
    @RateLimit(dimension = RateLimit.Dimension.IP, count = 40, interval = 1, timeUnit = RateLimit.TimeUnit.MINUTES)
    public ResponseEntity<CompanionReadResponse> companionRead(@RequestBody CompanionReadRequest request) {
        log.info("Received companion-read request: userId={}, action={}, textLength={}",
            request.getUserId(), request.getAction(),
            request.getText() != null ? request.getText().length() : 0);

        if (request.getText() == null || request.getText().trim().isEmpty()) {
            return ResponseEntity.badRequest()
                .body(CompanionReadResponse.error("划选文本不能为空"));
        }

        if (request.getUserId() == null) {
            return ResponseEntity.badRequest()
                .body(CompanionReadResponse.error("用户ID不能为空"));
        }

        try {
            CompanionReadingService.CompanionReadResult result =
                companionReadingService.companionRead(request.getUserId(), request.getText());

            if (result.success()) {
                return ResponseEntity.ok(
                    CompanionReadResponse.success(result.audioUrl(), result.explanationText()));
            } else {
                return ResponseEntity.internalServerError()
                    .body(CompanionReadResponse.error(result.error()));
            }

        } catch (Exception e) {
            log.error("Error processing companion-read request", e);
            return ResponseEntity.internalServerError()
                .body(CompanionReadResponse.error("处理请求时发生错误: " + e.getMessage()));
        }
    }

    @PostMapping("/parse-pdf")
    public ResponseEntity<Map<String, String>> parsePdf(@RequestParam("file") MultipartFile file) {
        log.info("Received PDF parse request: filename={}, size={}KB",
            file.getOriginalFilename(), file.getSize() / 1024);

        if (file.isEmpty()) {
            return ResponseEntity.badRequest()
                .body(Map.of("error", "文件不能为空"));
        }

        String filename = file.getOriginalFilename();
        if (filename == null || !filename.toLowerCase().endsWith(".pdf")) {
            return ResponseEntity.badRequest()
                .body(Map.of("error", "仅支持 PDF 文件"));
        }

        try {
            String text = pdfParseService.parsePdf(file);

            if (text == null || text.trim().isEmpty()) {
                return ResponseEntity.ok()
                    .body(Map.of("text", "", "warning", "PDF 内容为空或无法提取文本"));
            }

            return ResponseEntity.ok()
                .body(Map.of("text", text, "filename", filename));

        } catch (IOException e) {
            log.error("PDF parse failed", e);
            return ResponseEntity.internalServerError()
                .body(Map.of("error", "PDF 解析失败: " + e.getMessage()));
        }
    }
}
