package com.chat.ai.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.stream.StreamListener;
import org.springframework.stereotype.Service;

import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;

@Slf4j
@Service
public class AiTaskStreamConsumer implements StreamListener<String, MapRecord<String, String, String>> {

    private final AiChatRequestListener aiChatRequestListener;
    private final FarmAiJudgeService farmAiJudgeService;
    private final StringRedisTemplate stringRedisTemplate;
    private final ObjectMapper objectMapper;
    private final Executor streamTaskExecutor;

    private static final String AI_TASK_STREAM = "ai_task_stream";
    private static final String AI_GROUP = "ai_group";

    public AiTaskStreamConsumer(
            AiChatRequestListener aiChatRequestListener,
            FarmAiJudgeService farmAiJudgeService,
            StringRedisTemplate stringRedisTemplate,
            ObjectMapper objectMapper,
            Executor streamTaskExecutor) {
        this.aiChatRequestListener = aiChatRequestListener;
        this.farmAiJudgeService = farmAiJudgeService;
        this.stringRedisTemplate = stringRedisTemplate;
        this.objectMapper = objectMapper;
        this.streamTaskExecutor = streamTaskExecutor;
    }

    @Override
    public void onMessage(MapRecord<String, String, String> record) {
        Map<String, String> body = record.getValue();
        String type = body.get("type");
        String json = body.get("message");
        String recordId = record.getId().getValue();

        log.info("Received Stream task: id={}, type={}", recordId, type);

        try {
            switch (type) {
                case "PRIVATE_CHAT" -> handlePrivateChat(json);
                case "FARM_JUDGE" -> handleFarmJudge(json);
                default -> log.warn("Unknown task type: {}", type);
            }

            acknowledge(recordId);

        } catch (Exception e) {
            log.error("Error processing Stream task: id={}, type={}, error={}", recordId, type, e.getMessage());
        }
    }

    private void handlePrivateChat(String json) {
        CompletableFuture.runAsync(() -> {
            try {
                JsonNode request = objectMapper.readTree(json);
                Integer userId = request.get("userId").asInt();
                int botId = request.get("botId").asInt();
                String userMessage = request.get("message").asText();
                String userName = request.has("userName") ? request.get("userName").asText() : "用户";

                log.info("Processing PRIVATE_CHAT: userId={}, botId={}, message={}", userId, botId, userMessage);

                aiChatRequestListener.processPrivateChat(userId, botId, userMessage, userName, request);

            } catch (Exception e) {
                log.error("Error in PRIVATE_CHAT handler: {}", e.getMessage(), e);
            }
        }, streamTaskExecutor);
    }

    private void handleFarmJudge(String json) {
        CompletableFuture.runAsync(() -> {
            try {
                JsonNode request = objectMapper.readTree(json);
                Integer userId = request.get("userId").asInt();
                String question = request.get("question").asText();
                String answer = request.get("answer").asText();

                log.info("Processing FARM_JUDGE: userId={}, question={}", userId, question);

                var judgment = farmAiJudgeService.judgeAnswer(question, answer);
                log.info("Farm judgment result: canHarvest={}, score={}", judgment.canHarvest(), judgment.score());

            } catch (Exception e) {
                log.error("Error in FARM_JUDGE handler: {}", e.getMessage(), e);
            }
        }, streamTaskExecutor);
    }

    private void acknowledge(String recordId) {
        try {
            stringRedisTemplate.opsForStream().acknowledge(AI_TASK_STREAM, AI_GROUP, recordId);
            log.debug("Acknowledged Stream record: {}", recordId);
        } catch (Exception e) {
            log.error("Failed to acknowledge Stream record: {}", recordId, e);
        }
    }
}
