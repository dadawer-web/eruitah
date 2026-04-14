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
            RedisMessageListenerContainer listenerContainer) {
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
    }

    @PostConstruct
    public void start() {
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

        log.info("AI Chat Request Listener started, listening on channels: {} (private), {} (group)", 
            AI_PRIVATE_CHANNEL, AI_GROUP_CHANNEL);
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

            log.info("Processing private AI chat: userId={}, botId={}({}), message={}, conversationId={}",
                userId, botId, AiPersonaRegistry.getBotName(botId), userMessage, conversationId);

            String response = null;

            if (AiPersonaRegistry.isVoiceAssistantBot(botId) && request.has("voiceUrl")) {
                log.info("[语音小助手] 使用 VoiceChatService 处理语音消息");
                
                String voiceUrl = request.get("voiceUrl").asText();
                int duration = request.has("duration") ? request.get("duration").asInt() : 0;
                
                log.info("[语音小助手] voiceUrl={}, duration={}s", voiceUrl, duration);
                
                VoiceChatService.VoiceChatResult voiceResult = voiceChatService.handleVoiceChat(
                    voiceUrl, userId, botId, duration);
                
                String textReply = voiceResult.textReply();
                
                log.info("[语音小助手] ASR转文字: {}, TTS语音URL: {}", 
                    textReply.substring(0, Math.min(50, textReply.length())) + "...",
                    voiceResult.voiceUrl());
                
                if (voiceResult.voiceUrl() != null) {
                    redisPubSubService.publishVoiceMessage(userId, voiceResult.voiceUrl(), voiceResult.duration(), botId, AiPersonaRegistry.getBotName(botId));
                }
                
                log.info("[语音小助手] 语音消息处理完成");
                return;
            }

            redisPubSubService.publishStreamStart(userId, botId, AiPersonaRegistry.getBotName(botId));

            if (AiPersonaRegistry.isMasterBot(botId)) {
                log.info("[旗舰大师] 使用 AgentOrchestratorService 多智能体编排（Router → Solver → Reflection）");

                AgentOrchestratorService.AgentResult agentResult = agentOrchestratorService.processUserQuery(userId, userMessage);

                log.info("[旗舰大师] 意图: {}, 初稿长度: {}, 最终答案长度: {}",
                    agentResult.intent(), agentResult.draftAnswer().length(), agentResult.finalAnswer().length());

                response = agentResult.finalAnswer();

                chatMemory.add(conversationId, List.of(
                    new UserMessage(userMessage),
                    new AssistantMessage(response)
                ));

            } else if (AiPersonaRegistry.isProblemSolverBot(botId)) {
                log.info("[解题大王] 使用 MultimodalChatService 多模态服务");
                
                List<ChatRequest.ImageData> images = extractImagesFromMessage(userMessage);
                String cleanMessage = removeImageTagsFromMessage(userMessage);
                
                log.info("[解题大王] 消息中包含 {} 张图片", images.size());
                
                MultimodalChatService.ChatResult multimodalResult = multimodalChatService.chat(
                    userId, botId, cleanMessage.isEmpty() ? "请分析这张图片" : cleanMessage, images);
                
                response = multimodalResult.message();

                chatMemory.add(conversationId, List.of(
                    new UserMessage(cleanMessage.isEmpty() ? "请分析这张图片" : cleanMessage),
                    new AssistantMessage(response)
                ));

            } else if (AiPersonaRegistry.isCodeReviewerBot(botId)) {
                log.info("[代码审查员] 使用 CodeReviewerService + MCP文件系统工具");

                response = codeReviewerService.reviewCode(userMessage);

                chatMemory.add(conversationId, List.of(
                    new UserMessage(userMessage),
                    new AssistantMessage(response)
                ));

            } else {
                log.info("[{}] 使用fastChatClient（纯Prompt）", AiPersonaRegistry.getBotName(botId));

                SystemMessage systemMessage = AiPersonaRegistry.getPersonaByBotId(botId);

                response = fastChatClient.prompt()
                    .system(systemMessage.getContent())
                    .user(userMessage)
                    .advisors(spec -> spec
                        .param(CHAT_MEMORY_CONVERSATION_ID_KEY, conversationId)
                        .param(CHAT_MEMORY_RETRIEVE_SIZE_KEY, 10))
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
