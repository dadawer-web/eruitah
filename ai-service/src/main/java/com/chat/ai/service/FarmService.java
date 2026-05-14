package com.chat.ai.service;

import com.chat.ai.model.HarvestJudgment;
import com.chat.ai.rpc.RpcPushService;
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
    private final RpcPushService rpcPushService;

    private static final String FARM_LOCK_PREFIX = "farm:lock:";
    private static final int FARM_DISPATCH_CHANNEL = 9996;
    private static final int FARM_ANSWER_MSG_ACK = 73;
    private static final int FARM_BROADCAST_MSG = 78;

    public FarmService(FarmAiJudgeService farmAiJudgeService,
                       StringRedisTemplate stringRedisTemplate,
                       ObjectMapper objectMapper,
                       RpcPushService rpcPushService) {
        this.farmAiJudgeService = farmAiJudgeService;
        this.stringRedisTemplate = stringRedisTemplate;
        this.objectMapper = objectMapper;
        this.rpcPushService = rpcPushService;
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
                farmAiJudgeService.extractAndSaveKnowledgeGraph(userId, question, answer, judgment.score());
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

    public void addExperience(int userId, int experience, String type, String source) {
        log.info("[RPC] addExperience: userId={}, exp={}, type={}, source={}", userId, experience, type, source);

        try {
            int calculatedExp = calculateExperience(userId, experience, type);

            Map<String, Object> expUpdate = new HashMap<>();
            expUpdate.put("userid", userId);
            expUpdate.put("experience", calculatedExp);
            expUpdate.put("type", type);
            expUpdate.put("source", source);
            expUpdate.put("timestamp", System.currentTimeMillis());

            rpcPushService.pushExperienceUpdate(userId, expUpdate);

            log.info("[RPC] Experience update pushed to C++: userId={}, exp={}", userId, calculatedExp);

        } catch (Exception e) {
            log.error("[RPC] Error in addExperience: userId={}", userId, e);
        }
    }

    private int calculateExperience(int userId, int baseExp, String type) {
        int multiplier = 1;

        if ("answer_correct".equals(type)) {
            multiplier = 2;
        } else if ("harvest".equals(type)) {
            multiplier = 1;
        } else if ("plant".equals(type)) {
            multiplier = 1;
        }

        return baseExp * multiplier;
    }
}
