package com.chat.ai.service;

import com.chat.ai.model.HarvestJudgment;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.TimeUnit;

@Slf4j
@Service
public class FarmService {

    private final FarmAiJudgeService farmAiJudgeService;
    private final StringRedisTemplate stringRedisTemplate;
    private final ObjectMapper objectMapper;

    private static final String FARM_LOCK_PREFIX = "farm:lock:";
    private static final int FARM_DISPATCH_CHANNEL = 9996;
    private static final int FARM_ANSWER_MSG_ACK = 73;
    private static final int FARM_BROADCAST_MSG = 78;

    public FarmService(FarmAiJudgeService farmAiJudgeService,
                       StringRedisTemplate stringRedisTemplate,
                       ObjectMapper objectMapper) {
        this.farmAiJudgeService = farmAiJudgeService;
        this.stringRedisTemplate = stringRedisTemplate;
        this.objectMapper = objectMapper;
    }

    public HarvestJudgment processAnswer(int userId, int plotId, int ownerId,
                                          String question, String answer) {
        String lockKey = FARM_LOCK_PREFIX + plotId;
        Boolean locked = stringRedisTemplate.opsForValue()
            .setIfAbsent(lockKey, String.valueOf(userId), 30, TimeUnit.SECONDS);

        if (locked == null || !locked) {
            log.warn("Farm plot {} is locked by another user, rejecting answer from user {}", plotId, userId);
            HarvestJudgment rejected = new HarvestJudgment(false, 0, "这块地正在被别人回答，请稍后再试~");
            sendAnswerAck(userId, plotId, ownerId, rejected);
            return rejected;
        }

        try {
            HarvestJudgment judgment = farmAiJudgeService.judgeAnswer(question, answer);
            sendAnswerAck(userId, plotId, ownerId, judgment);

            if (judgment.canHarvest()) {
                sendBroadcast(userId, ownerId, judgment.feedback());
            }

            return judgment;

        } finally {
            stringRedisTemplate.delete(lockKey);
        }
    }

    private void sendAnswerAck(int userId, int plotId, int ownerId, HarvestJudgment judgment) {
        try {
            Map<String, Object> response = new HashMap<>();
            response.put("msgid", FARM_ANSWER_MSG_ACK);
            response.put("errno", 0);
            response.put("plotid", plotId);
            response.put("canHarvest", judgment.canHarvest());
            response.put("score", judgment.score());
            response.put("feedback", judgment.feedback());
            response.put("userid", userId);
            response.put("ownerid", ownerId);

            String jsonMessage = objectMapper.writeValueAsString(response);
            stringRedisTemplate.convertAndSend(String.valueOf(FARM_DISPATCH_CHANNEL), jsonMessage);

            log.info("Sent farm answer ACK to channel 9996: userId={}, canHarvest={}, score={}", 
                userId, judgment.canHarvest(), judgment.score());

        } catch (Exception e) {
            log.error("Error sending farm answer ACK", e);
        }
    }

    private void sendBroadcast(int userId, int ownerId, String feedback) {
        try {
            Map<String, Object> broadcast = new HashMap<>();
            broadcast.put("msgid", FARM_BROADCAST_MSG);
            broadcast.put("msg", String.format("玩家%d 成功收割了玩家%d的菜！AI评语：%s",
                userId, ownerId, feedback));

            String broadcastJson = objectMapper.writeValueAsString(broadcast);
            stringRedisTemplate.convertAndSend(String.valueOf(FARM_DISPATCH_CHANNEL), broadcastJson);

            log.info("Broadcast farm harvest: user {} harvested from owner {}", userId, ownerId);

        } catch (Exception e) {
            log.error("Error broadcasting farm harvest", e);
        }
    }
}
