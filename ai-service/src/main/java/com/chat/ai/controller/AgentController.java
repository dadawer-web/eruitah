package com.chat.ai.controller;

import com.chat.ai.config.annotation.RateLimit;
import com.chat.ai.service.AgentOrchestratorService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.Map;

@Slf4j
@RestController
@RequestMapping("/api/agent")
@RequiredArgsConstructor
public class AgentController {

    private final AgentOrchestratorService agentOrchestratorService;

    @PostMapping("/chat")
    @RateLimit(dimension = RateLimit.Dimension.USER, count = 20, interval = 1, timeUnit = RateLimit.TimeUnit.MINUTES)
    @RateLimit(dimension = RateLimit.Dimension.IP, count = 40, interval = 1, timeUnit = RateLimit.TimeUnit.MINUTES)
    public ResponseEntity<Map<String, Object>> chat(@RequestBody AgentRequest request) {
        log.info("收到多智能体工作流请求: userId={}, message={}", 
            request.getUserId(), request.getMessage());

        if (request.getMessage() == null || request.getMessage().trim().isEmpty()) {
            return ResponseEntity.badRequest()
                .body(createErrorMap("消息不能为空"));
        }

        try {
            AgentOrchestratorService.AgentResult result = 
                agentOrchestratorService.processUserQuery(request.getMessage());

            String finalAnswer = result.finalAnswerStream()
                .collectList()
                .block()
                .stream()
                .collect(java.util.stream.Collectors.joining());

            Map<String, Object> response = new HashMap<>();
            response.put("success", true);
            response.put("intent", result.intent());
            response.put("draftAnswer", result.draftAnswer());
            response.put("finalAnswer", finalAnswer);

            return ResponseEntity.ok(response);

        } catch (Exception e) {
            log.error("多智能体工作流处理失败", e);
            return ResponseEntity.internalServerError()
                .body(createErrorMap("处理失败: " + e.getMessage()));
        }
    }

    private Map<String, Object> createErrorMap(String error) {
        Map<String, Object> map = new HashMap<>();
        map.put("success", false);
        map.put("error", error);
        return map;
    }
}
