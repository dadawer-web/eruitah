package com.chat.ai.service;

import com.chat.ai.controller.ChatRequest;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.memory.ChatMemory;
import org.springframework.ai.chat.messages.AssistantMessage;
import org.springframework.ai.chat.messages.SystemMessage;
import org.springframework.ai.chat.messages.UserMessage;
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
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import static org.springframework.ai.chat.client.advisor.AbstractChatMemoryAdvisor.CHAT_MEMORY_CONVERSATION_ID_KEY;
import static org.springframework.ai.chat.client.advisor.AbstractChatMemoryAdvisor.CHAT_MEMORY_RETRIEVE_SIZE_KEY;

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
    private final MultimodalChatService multimodalChatService;
    private final CodeReviewerService codeReviewerService;
    private final ChatMemory chatMemory;
    private final VoiceChatService voiceChatService;
    private final RedisMessageListenerContainer listenerContainer;
    private final Executor streamTaskExecutor;

    private static final String AI_PRIVATE_CHANNEL = "9999";
    private static final String AI_GROUP_CHANNEL = "9998";
    private static final Pattern IMAGE_PATTERN = Pattern.compile("\\[IMAGE\\]([^,]+),([^\\[]+)");

    public AiChatRequestListener(
            StringRedisTemplate stringRedisTemplate,
            RedisPubSubService redisPubSubService,
            @Qualifier("fastChatClient") ChatClient fastChatClient,
            VectorStore vectorStore,
            ObjectMapper objectMapper,
            AgentOrchestratorService agentOrchestratorService,
            GroupChatService groupChatService,
            MultimodalChatService multimodalChatService,
            CodeReviewerService codeReviewerService,
            ChatMemory chatMemory,
            VoiceChatService voiceChatService,
            RedisMessageListenerContainer listenerContainer,
            Executor streamTaskExecutor) {
        this.stringRedisTemplate = stringRedisTemplate;
        this.redisPubSubService = redisPubSubService;
        this.fastChatClient = fastChatClient;
        this.vectorStore = vectorStore;
        this.objectMapper = objectMapper;
        this.agentOrchestratorService = agentOrchestratorService;
        this.groupChatService = groupChatService;
        this.multimodalChatService = multimodalChatService;
        this.codeReviewerService = codeReviewerService;
        this.chatMemory = chatMemory;
        this.voiceChatService = voiceChatService;
        this.listenerContainer = listenerContainer;
        this.streamTaskExecutor = streamTaskExecutor;
    }

    @PostConstruct
    public void start() {
        MessageListener privateListener = (org.springframework.data.redis.connection.Message message, byte[] pattern) -> {
            String messageBody = new String(message.getBody());
            handlePrivateAiRequestAsync(messageBody);
        };

        MessageListener groupListener = (org.springframework.data.redis.connection.Message message, byte[] pattern) -> {
            String messageBody = new String(message.getBody());
            handleGroupAiRequestAsync(messageBody);
        };

        listenerContainer.addMessageListener(privateListener, new ChannelTopic(AI_PRIVATE_CHANNEL));
        listenerContainer.addMessageListener(groupListener, new ChannelTopic(AI_GROUP_CHANNEL));

        log.info("AI Chat Request Listener started, listening on channels: {} (private), {} (group)", 
            AI_PRIVATE_CHANNEL, AI_GROUP_CHANNEL);
    }

    private void handlePrivateAiRequestAsync(String messageBody) {
        CompletableFuture.runAsync(() -> handlePrivateAiRequest(messageBody), streamTaskExecutor);
    }

    private void handleGroupAiRequestAsync(String messageBody) {
        CompletableFuture.runAsync(() -> handleGroupAiRequest(messageBody), streamTaskExecutor);
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

            String conversationId = buildConversationId(userId, botId);

            log.info("Processing private AI chat: userId={}, botId={}({}), message={}",
                userId, botId, AiPersonaRegistry.getBotName(botId), userMessage);

            if (AiPersonaRegistry.isVoiceAssistantBot(botId) && request.has("voiceUrl")) {
                handleVoiceAssistant(userId, botId, request);
                return;
            }

            redisPubSubService.publishStreamStart(userId, botId, AiPersonaRegistry.getBotName(botId));

            if (AiPersonaRegistry.isMasterBot(botId)) {
                handleMasterBotStream(userId, botId, userMessage, conversationId);
            } else if (AiPersonaRegistry.isProblemSolverBot(botId)) {
                handleProblemSolverStream(userId, botId, userMessage, conversationId);
            } else if (AiPersonaRegistry.isCodeReviewerBot(botId)) {
                handleCodeReviewerStream(userId, botId, userMessage, conversationId);
            } else {
                handleNormalBotStream(userId, botId, userMessage, conversationId);
            }

        } catch (Exception e) {
            log.error("Error handling private AI request: {}", messageBody, e);
            sendErrorAndEnd(userId, botId, "抱歉，AI处理您的请求时出现错误，请稍后重试。");
        }
    }

    private void handleNormalBotStream(int userId, int botId, String userMessage, String conversationId) {
        SystemMessage systemMessage = AiPersonaRegistry.getPersonaByBotId(botId);
        StringBuilder fullAnswer = new StringBuilder();
        
        final long startTime = System.currentTimeMillis();
        final int[] tokenCount = {0};

        log.info("[{}] 开始真流式调用 LLM: {}", AiPersonaRegistry.getBotName(botId), startTime);

        fastChatClient.prompt()
            .system(systemMessage.getContent())
            .user(userMessage)
            .advisors(spec -> spec
                .param(CHAT_MEMORY_CONVERSATION_ID_KEY, conversationId)
                .param(CHAT_MEMORY_RETRIEVE_SIZE_KEY, 10))
            .stream()
            .content()
            .doOnNext(token -> {
                if (token != null && !token.isEmpty()) {
                    fullAnswer.append(token);
                    tokenCount[0]++;
                    if (tokenCount[0] <= 5 || tokenCount[0] % 20 == 0) {
                        log.info("[{}] Token#{}: [{}], 耗时: {}ms", 
                            AiPersonaRegistry.getBotName(botId), tokenCount[0], token, System.currentTimeMillis() - startTime);
                    }
                    redisPubSubService.publishStreamChunk(userId, token, botId, AiPersonaRegistry.getBotName(botId));
                }
            })
            .doOnError(error -> {
                log.error("[{}] Stream error: {}", AiPersonaRegistry.getBotName(botId), error.getMessage());
                sendErrorAndEnd(userId, botId, "AI 流式输出出错: " + error.getMessage());
            })
            .doOnComplete(() -> {
                long endTime = System.currentTimeMillis();
                log.info("[{}] 真流式输出完成，Token数: {}, 总耗时: {}ms, 平均每Token: {}ms", 
                    AiPersonaRegistry.getBotName(botId), tokenCount[0], endTime - startTime,
                    tokenCount[0] > 0 ? (endTime - startTime) / tokenCount[0] : 0);
                
                chatMemory.add(conversationId, List.of(
                    new UserMessage(userMessage),
                    new AssistantMessage(fullAnswer.toString())
                ));
                
                redisPubSubService.publishStreamEnd(userId, botId, AiPersonaRegistry.getBotName(botId));
            })
            .subscribe();
    }

    private void handleMasterBotStream(int userId, int botId, String userMessage, String conversationId) {
        log.info("[旗舰大师] 使用 AgentOrchestratorService 多智能体编排");

        AgentOrchestratorService.AgentResult agentResult = agentOrchestratorService.processUserQuery(userId, userMessage);

        log.info("[旗舰大师] 意图: {}, 最终答案长度: {}", agentResult.intent(), agentResult.finalAnswer().length());

        String response = agentResult.finalAnswer();

        chatMemory.add(conversationId, List.of(
            new UserMessage(userMessage),
            new AssistantMessage(response)
        ));

        sendResponseInChunks(userId, botId, response);
        redisPubSubService.publishStreamEnd(userId, botId, AiPersonaRegistry.getBotName(botId));
    }

    private void handleProblemSolverStream(int userId, int botId, String userMessage, String conversationId) {
        log.info("[解题大王] 使用 MultimodalChatService");
        
        List<ChatRequest.ImageData> images = extractImagesFromMessage(userMessage);
        String cleanMessage = removeImageTagsFromMessage(userMessage);
        
        log.info("[解题大王] 消息中包含 {} 张图片", images.size());
        
        MultimodalChatService.ChatResult multimodalResult = multimodalChatService.chat(
            userId, botId, cleanMessage.isEmpty() ? "请分析这张图片" : cleanMessage, images);
        
        String response = multimodalResult.message();

        chatMemory.add(conversationId, List.of(
            new UserMessage(cleanMessage.isEmpty() ? "请分析这张图片" : cleanMessage),
            new AssistantMessage(response)
        ));

        sendResponseInChunks(userId, botId, response);
        redisPubSubService.publishStreamEnd(userId, botId, AiPersonaRegistry.getBotName(botId));
    }

    private void handleCodeReviewerStream(int userId, int botId, String userMessage, String conversationId) {
        log.info("[代码审查员] 使用 CodeReviewerService");

        String response = codeReviewerService.reviewCode(userMessage);

        chatMemory.add(conversationId, List.of(
            new UserMessage(userMessage),
            new AssistantMessage(response)
        ));

        sendResponseInChunks(userId, botId, response);
        redisPubSubService.publishStreamEnd(userId, botId, AiPersonaRegistry.getBotName(botId));
    }

    private void handleVoiceAssistant(Integer userId, int botId, JsonNode request) {
        try {
            log.info("[语音小助手] 处理语音消息");
            
            String voiceUrl = request.get("voiceUrl").asText();
            int duration = request.has("duration") ? request.get("duration").asInt() : 0;
            
            VoiceChatService.VoiceChatResult voiceResult = voiceChatService.handleVoiceChat(
                voiceUrl, userId, botId, duration);
            
            String textReply = voiceResult.textReply();
            
            log.info("[语音小助手] ASR转文字: {}, TTS语音URL: {}", 
                textReply.substring(0, Math.min(50, textReply.length())) + "...",
                voiceResult.voiceUrl());
            
            if (voiceResult.voiceUrl() != null) {
                redisPubSubService.publishVoiceMessage(userId, voiceResult.voiceUrl(), voiceResult.duration(), 
                    botId, AiPersonaRegistry.getBotName(botId));
            }
            
            log.info("[语音小助手] 语音消息处理完成");
        } catch (Exception e) {
            log.error("[语音小助手] 处理失败", e);
        }
    }

    private void handleGroupAiRequest(String messageBody) {
        Long groupId = null;
        
        try {
            log.info("Received group AI request: {}", messageBody);

            JsonNode request = objectMapper.readTree(messageBody);
            groupId = request.get("groupId").asLong();
            int senderId = request.get("senderId").asInt();
            String content = request.get("content").asText();
            
            JsonNode aiBotIdsNode = request.get("aiBotIds");
            List<Integer> aiBotIds = new ArrayList<>();
            if (aiBotIdsNode != null && aiBotIdsNode.isArray()) {
                for (JsonNode node : aiBotIdsNode) {
                    aiBotIds.add(node.asInt());
                }
            }

            log.info("Processing group AI chat: groupId={}, senderId={}, aiBotIds={}", groupId, senderId, aiBotIds);

            if (aiBotIds.isEmpty()) {
                log.warn("No AI bots in group request, skipping");
                return;
            }

            groupChatService.handleMultiAgentChat(groupId, senderId, content, aiBotIds);

        } catch (Exception e) {
            log.error("Error handling group AI request: {}", messageBody, e);
            
            if (groupId != null) {
                redisPubSubService.publishAgentGroupMessage(groupId, "抱歉，AI处理群聊请求时出现错误。", 
                    10000, "AI助手", "AI_ERROR");
            }
        }
    }
    
    private void sendResponseInChunks(Integer userId, int botId, String response) {
        if (response == null || response.isEmpty()) {
            return;
        }
        
        int chunkSize = 3;
        for (int i = 0; i < response.length(); i += chunkSize) {
            int end = Math.min(i + chunkSize, response.length());
            String chunk = response.substring(i, end);
            redisPubSubService.publishStreamChunk(userId, chunk, botId, AiPersonaRegistry.getBotName(botId));
        }
    }

    private void sendErrorAndEnd(Integer userId, int botId, String errorMessage) {
        if (userId != null && botId > 0) {
            try {
                redisPubSubService.publishStreamChunk(userId, errorMessage, botId, AiPersonaRegistry.getBotName(botId));
                redisPubSubService.publishStreamEnd(userId, botId, AiPersonaRegistry.getBotName(botId));
            } catch (Exception ex) {
                log.error("Error sending error message to user: {}", userId, ex);
            }
        }
    }
    
    private List<ChatRequest.ImageData> extractImagesFromMessage(String message) {
        List<ChatRequest.ImageData> images = new ArrayList<>();
        Matcher matcher = IMAGE_PATTERN.matcher(message);
        
        while (matcher.find()) {
            String imageType = matcher.group(1);
            String base64Data = matcher.group(2);
            
            String mimeType = "image/" + imageType.toLowerCase();
            if (imageType.equalsIgnoreCase("jpg")) {
                mimeType = "image/jpeg";
            }
            
            ChatRequest.ImageData imageData = new ChatRequest.ImageData();
            imageData.setBase64(base64Data);
            imageData.setMimeType(mimeType);
            images.add(imageData);
        }
        
        return images;
    }
    
    private String removeImageTagsFromMessage(String message) {
        return IMAGE_PATTERN.matcher(message).replaceAll("").trim();
    }

    private String buildConversationId(Integer userId, int botId) {
        return "chat_" + userId + "_" + botId;
    }
}
