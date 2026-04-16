package com.chat.ai.controller;

import com.chat.ai.config.annotation.RateLimit;
import com.chat.ai.model.HarvestJudgment;
import com.chat.ai.service.FarmService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@Slf4j
@RestController
@RequestMapping("/api/farm")
public class FarmController {

    private final FarmService farmService;

    public FarmController(FarmService farmService) {
        this.farmService = farmService;
    }

    @PostMapping("/judge")
    @RateLimit(dimension = RateLimit.Dimension.USER, count = 5, interval = 1, timeUnit = RateLimit.TimeUnit.MINUTES)
    @RateLimit(dimension = RateLimit.Dimension.IP, count = 10, interval = 1, timeUnit = RateLimit.TimeUnit.MINUTES)
    public ResponseEntity<HarvestJudgment> judgeAnswer(@RequestBody Map<String, Object> request) {
        try {
            int userId = ((Number) request.get("userId")).intValue();
            int plotId = ((Number) request.get("plotId")).intValue();
            int ownerId = ((Number) request.get("ownerId")).intValue();
            String question = (String) request.get("question");
            String answer = (String) request.get("answer");

            log.info("Farm judge request: userId={}, plotId={}, ownerId={}", userId, plotId, ownerId);

            HarvestJudgment judgment = farmService.processAnswer(userId, plotId, ownerId, question, answer);
            return ResponseEntity.ok(judgment);

        } catch (Exception e) {
            log.error("Error in farm judge endpoint", e);
            return ResponseEntity.ok(new HarvestJudgment(false, 0, "服务器错误，请重试"));
        }
    }

    @GetMapping("/health")
    public ResponseEntity<String> health() {
        return ResponseEntity.ok("Farm AI Service is running");
    }
}
