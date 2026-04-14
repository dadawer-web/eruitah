package com.chat.ai.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.util.concurrent.TimeUnit;

@Slf4j
@Service
public class ExamStateManager {

    private final StringRedisTemplate stringRedisTemplate;
    private final ObjectMapper objectMapper;

    private static final String STATE_KEY_PREFIX = "STATE:EXAMING:";
    private static final long EXAM_STATE_TTL_MINUTES = 30;

    public ExamStateManager(StringRedisTemplate stringRedisTemplate, ObjectMapper objectMapper) {
        this.stringRedisTemplate = stringRedisTemplate;
        this.objectMapper = objectMapper;
    }

    public void enterExamState(Integer userId, ExamContext context) {
        String key = STATE_KEY_PREFIX + userId;
        try {
            String json = objectMapper.writeValueAsString(context);
            stringRedisTemplate.opsForValue().set(key, json, EXAM_STATE_TTL_MINUTES, TimeUnit.MINUTES);
            log.info("[ExamState] 用户 {} 进入考试状态, 科目: {}, 题干: {}",
                userId, context.subject(), context.questionStem());
        } catch (JsonProcessingException e) {
            log.error("[ExamState] 序列化考试上下文失败, userId: {}", userId, e);
            throw new RuntimeException("进入考试状态失败", e);
        }
    }

    public ExamContext getExamContext(Integer userId) {
        String key = STATE_KEY_PREFIX + userId;
        String json = stringRedisTemplate.opsForValue().get(key);
        if (json == null) {
            return null;
        }
        try {
            return objectMapper.readValue(json, ExamContext.class);
        } catch (JsonProcessingException e) {
            log.error("[ExamState] 反序列化考试上下文失败, userId: {}", userId, e);
            return null;
        }
    }

    public boolean isInExamState(Integer userId) {
        String key = STATE_KEY_PREFIX + userId;
        return Boolean.TRUE.equals(stringRedisTemplate.hasKey(key));
    }

    public void exitExamState(Integer userId) {
        String key = STATE_KEY_PREFIX + userId;
        stringRedisTemplate.delete(key);
        log.info("[ExamState] 用户 {} 退出考试状态", userId);
    }

    public record ExamContext(
        String subject,
        String questionStem,
        String standardAnswer,
        String questionSource
    ) {}
}
