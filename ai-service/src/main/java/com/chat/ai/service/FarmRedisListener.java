package com.chat.ai.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;
import org.springframework.stereotype.Service;

import jakarta.annotation.PostConstruct;

@Slf4j
@Service
public class FarmRedisListener {

    private final StringRedisTemplate stringRedisTemplate;
    private final FarmService farmService;
    private final ObjectMapper objectMapper;
    private final RedisMessageListenerContainer listenerContainer;

    private static final String FARM_CHANNEL = "9995";

    public FarmRedisListener(StringRedisTemplate stringRedisTemplate,
                              FarmService farmService,
                              ObjectMapper objectMapper,
                              RedisMessageListenerContainer listenerContainer) {
        this.stringRedisTemplate = stringRedisTemplate;
        this.farmService = farmService;
        this.objectMapper = objectMapper;
        this.listenerContainer = listenerContainer;
    }

    @PostConstruct
    public void start() {
        MessageListener farmListener = (org.springframework.data.redis.connection.Message message, byte[] pattern) -> {
            String messageBody = new String(message.getBody());
            handleFarmRequest(messageBody);
        };

        listenerContainer.addMessageListener(farmListener, new ChannelTopic(FARM_CHANNEL));

        log.info("Farm Redis Listener started, listening on channel: {}", FARM_CHANNEL);
    }

    private void handleFarmRequest(String messageBody) {
        try {
            log.info("Received farm request: {}", messageBody);

            JsonNode request = objectMapper.readTree(messageBody);
            String action = request.get("action").asText();

            if ("answer".equals(action)) {
                int userId = request.get("userid").asInt();
                int plotId = request.get("plotid").asInt();
                int ownerId = request.get("ownerid").asInt();
                String question = request.get("question").asText();
                String answer = request.get("answer").asText();

                log.info("Processing farm answer: userId={}, plotId={}, ownerId={}", userId, plotId, ownerId);

                farmService.processAnswer(userId, plotId, ownerId, question, answer);

            } else {
                log.warn("Unknown farm action: {}", action);
            }

        } catch (Exception e) {
            log.error("Error handling farm request: {}", messageBody, e);
        }
    }
}
