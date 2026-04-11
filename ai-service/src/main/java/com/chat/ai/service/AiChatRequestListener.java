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
import org.springframework.data.redis.core.StringRedisTemplate;
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

    private final StringRedisTemplate stringRedisTemplate;
    private final RedisPubSubService redisPubSubService;
    private final ChatClient fastChatClient;
    private final VectorStore vectorStore;
    private final ObjectMapper objectMapper;
    private final AgentOrchestratorService agentOrchestratorService;
    private final GroupChatService groupChatService;
    private RedisMessageListenerContainer listenerContainer;

    private static final String AI_PRIVATE_CHANNEL = "9999";
    private static final String AI_GROUP_CHANNEL = "9998";

    public AiChatRequestListener(
            StringRedisTemplate stringRedisTemplate,
            RedisPubSubService redisPubSubService,
            @Qualifier("fastChatClient") ChatClient fastChatClient,
            VectorStore vectorStore,
            ObjectMapper objectMapper,
            AgentOrchestratorService agentOrchestratorService,
            GroupChatService groupChatService) {
        this.stringRedisTemplate = stringRedisTemplate;
        this.redisPubSubService = redisPubSubService;
        this.fastChatClient = fastChatClient;
        this.vectorStore = vectorStore;
        this.objectMapper = objectMapper;
        this.agentOrchestratorService = agentOrchestratorService;
        this.groupChatService = groupChatService;
    }

    @PostConstruct
    public void start() {
        listenerContainer = new RedisMessageListenerContainer();
        listenerContainer.setConnectionFactory(stringRedisTemplate.getConnectionFactory());

        MessageListener privateListener = (org.springframework.data.redis.connection.Message message, byte[] pattern) -> {
            String messageBody = new String(message.getBody());
            handlePrivateAiRequest(messageBody);
        };

        MessageListener groupListener = (org.springframework.data.redis.connection.Message message, byte[] pattern) -> {
            String messageBody = new String(message.getBody());
            handleGroupAiRequest(messageBody);
        };

        listenerContainer.addMessageListener(privateListener, new ChannelTopic(AI_PRIVATE_CHANNEL));
        listenerContainer.addMessageListener(groupListener, new ChannelTopic(AI_GROUP_CHANNEL));
        listenerContainer.afterPropertiesSet();
        listenerContainer.start();

        log.info("AI Chat Request Listener started, listening on channels: {} (private), {} (group)", 
            AI_PRIVATE_CHANNEL, AI_GROUP_CHANNEL);
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

    private void handlePrivateAiRequest(String messageBody) {
        Integer userId = null;
        int botId = -1;
        
        try {
            log.info("Received private AI request: {}", messageBody);

            JsonNode request = objectMapper.readTree(messageBody);
            userId = request.get("userId").asInt();
            botId = request.get("botId").asInt();
            String userMessage = request.get("message").asText();
            String userName = request.has("userName") ? request.get("userName").asText() : "用户";

            log.info("Processing private AI chat: userId={}, botId={}({}), message={}",
                userId, botId, AiPersonaRegistry.getBotName(botId), userMessage);

            String response;

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
            
            int chunkSize = 20;
            for (int i = 0; i < response.length(); i += chunkSize) {
                int end = Math.min(i + chunkSize, response.length());
                String chunk = response.substring(i, end);
                redisPubSubService.publishStreamChunk(userId, chunk, botId, AiPersonaRegistry.getBotName(botId));
                Thread.sleep(30);
            }
            
            redisPubSubService.publishStreamEnd(userId, botId, AiPersonaRegistry.getBotName(botId));

            log.info("Private AI response sent to user: {}", userId);

        } catch (Exception e) {
            log.error("Error handling private AI request: {}", messageBody, e);
            
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

    private void handleGroupAiRequest(String messageBody) {
        Long groupId = null;
        
        try {
            log.info("Received group AI request: {}", messageBody);

            JsonNode request = objectMapper.readTree(messageBody);
            groupId = request.get("groupId").asLong();
            int senderId = request.get("senderId").asInt();
            String senderName = request.has("senderName") ? request.get("senderName").asText() : "用户";
            String content = request.get("content").asText();
            
            JsonNode aiBotIdsNode = request.get("aiBotIds");
            List<Integer> aiBotIds = new ArrayList<>();
            if (aiBotIdsNode != null && aiBotIdsNode.isArray()) {
                for (JsonNode node : aiBotIdsNode) {
                    aiBotIds.add(node.asInt());
                }
            }

            log.info("Processing group AI chat: groupId={}, senderId={}, senderName={}, content={}, aiBotIds={}",
                groupId, senderId, senderName, content, aiBotIds);

            if (aiBotIds.isEmpty()) {
                log.warn("No AI bots in group request, skipping");
                return;
            }

            groupChatService.handleMultiAgentChat(groupId, senderId, content, aiBotIds);

            log.info("Group AI chat dispatched to {} bots for group: {}", aiBotIds.size(), groupId);

        } catch (Exception e) {
            log.error("Error handling group AI request: {}", messageBody, e);
            
            if (groupId != null) {
                try {
                    String errorMessage = "抱歉，AI处理群聊请求时出现错误。";
                    redisPubSubService.publishAgentGroupMessage(groupId, errorMessage, 10000, "AI助手", "AI_ERROR");
                    log.info("Sent error message to group: {}", groupId);
                } catch (Exception ex) {
                    log.error("Error sending error message to group: {}", groupId, ex);
                }
            }
        }
    }
}
