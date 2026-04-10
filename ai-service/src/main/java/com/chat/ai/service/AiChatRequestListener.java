package com.chat.ai.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.messages.SystemMessage;
import org.springframework.ai.chat.messages.UserMessage;
import org.springframework.ai.chat.prompt.Prompt;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;
import org.springframework.stereotype.Service;

import org.springframework.beans.factory.annotation.Qualifier;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import java.util.ArrayList;
import java.util.List;

@Slf4j
@Service
public class AiChatRequestListener {

    private final RedisTemplate<String, Object> redisTemplate;
    private final RedisPubSubService redisPubSubService;
    private final ChatClient fastChatClient;
    private final VectorStore vectorStore;
    private final ObjectMapper objectMapper;
    private final AgentOrchestratorService agentOrchestratorService;
    private RedisMessageListenerContainer listenerContainer;

    private static final String AI_REQUEST_CHANNEL = "9999";

    public AiChatRequestListener(
            RedisTemplate<String, Object> redisTemplate,
            RedisPubSubService redisPubSubService,
            @Qualifier("fastChatClient") ChatClient fastChatClient,
            VectorStore vectorStore,
            ObjectMapper objectMapper,
            AgentOrchestratorService agentOrchestratorService) {
        this.redisTemplate = redisTemplate;
        this.redisPubSubService = redisPubSubService;
        this.fastChatClient = fastChatClient;
        this.vectorStore = vectorStore;
        this.objectMapper = objectMapper;
        this.agentOrchestratorService = agentOrchestratorService;
    }

    @PostConstruct
    public void start() {
        listenerContainer = new RedisMessageListenerContainer();
        listenerContainer.setConnectionFactory(redisTemplate.getConnectionFactory());

        MessageListener listener = (org.springframework.data.redis.connection.Message message, byte[] pattern) -> {
            String messageBody = new String(message.getBody());
            handleAiRequest(messageBody);
        };

        listenerContainer.addMessageListener(listener, new ChannelTopic(AI_REQUEST_CHANNEL));
        listenerContainer.afterPropertiesSet();
        listenerContainer.start();

        log.info("AI Chat Request Listener started, listening on channel: {}", AI_REQUEST_CHANNEL);
    }

    @PreDestroy
    public void stop() {
        if (listenerContainer != null) {
            listenerContainer.stop();
            try {
                listenerContainer.destroy();
            } catch (Exception e) {
                log.debug("Error destroying listener container: {}", e.getMessage());
            }
        }
        log.info("AI Chat Request Listener stopped");
    }

    private void handleAiRequest(String messageBody) {
        Integer userId = null;
        int botId = -1;
        
        try {
            log.info("Received AI request: {}", messageBody);

            JsonNode request = objectMapper.readTree(messageBody);
            userId = request.get("userId").asInt();
            botId = request.get("botId").asInt();
            String userMessage = request.get("message").asText();
            String userName = request.has("userName") ? request.get("userName").asText() : "用户";

            log.info("Processing AI chat: userId={}, botId={}({}), message={}",
                userId, botId, AiPersonaRegistry.getBotName(botId), userMessage);

            String response;

            /*
             * 旗舰大师(10000)：使用 AgentOrchestratorService 多智能体编排
             *   - Router → Solver → Reflection 三阶段流水线
             *   - 自动根据意图选择挂载RAG或Tools
             * 其他AI角色：使用fastChatClient + 人设Prompt
             */
            
            // 发送流式开始标记（AI开始思考）
            redisPubSubService.publishStreamStart(userId, botId, AiPersonaRegistry.getBotName(botId));
            
            if (AiPersonaRegistry.isMasterBot(botId)) {
                log.info("[旗舰大师] 使用 AgentOrchestratorService 多智能体编排（Router → Solver → Reflection）");

                AgentOrchestratorService.AgentResult agentResult = agentOrchestratorService.processUserQuery(userMessage);

                log.info("[旗舰大师] 意图: {}, 初稿长度: {}, 最终答案长度: {}",
                    agentResult.intent(), agentResult.draftAnswer().length(), agentResult.finalAnswer().length());

                response = agentResult.finalAnswer();

            } else {
                log.info("[{}] 使用fastChatClient（纯Prompt）", AiPersonaRegistry.getBotName(botId));

                SystemMessage systemMessage = AiPersonaRegistry.getPersonaByBotId(botId);

                List<Message> messages = new ArrayList<>();
                messages.add(systemMessage);
                messages.add(new UserMessage(userMessage));

                Prompt prompt = new Prompt(messages);
                response = fastChatClient.prompt(prompt)
                    .call()
                    .content();
            }

            log.info("[{}] 回复长度: {}字符", AiPersonaRegistry.getBotName(botId), response.length());
            
            // 流式发送响应（模拟流式效果，每次发送20个字符）
            int chunkSize = 20;
            for (int i = 0; i < response.length(); i += chunkSize) {
                int end = Math.min(i + chunkSize, response.length());
                String chunk = response.substring(i, end);
                redisPubSubService.publishStreamChunk(userId, chunk, botId, AiPersonaRegistry.getBotName(botId));
                Thread.sleep(30);  // 30ms延迟，模拟打字效果
            }
            
            // 发送流式结束标记
            redisPubSubService.publishStreamEnd(userId, botId, AiPersonaRegistry.getBotName(botId));

            log.info("AI response sent to user: {}", userId);

        } catch (Exception e) {
            log.error("Error handling AI request: {}", messageBody, e);
            
            // 发生异常时，发送错误消息并确保发送结束标记
            if (userId != null && botId > 0) {
                try {
                    String errorMessage = "抱歉，AI处理您的请求时出现错误，请稍后重试。";
                    redisPubSubService.publishStreamChunk(userId, errorMessage, botId, AiPersonaRegistry.getBotName(botId));
                    redisPubSubService.publishStreamEnd(userId, botId, AiPersonaRegistry.getBotName(botId));
                    log.info("Sent error message and stream end to user: {}", userId);
                } catch (Exception ex) {
                    log.error("Error sending error message to user: {}", userId, ex);
                }
            }
        }
    }
}
