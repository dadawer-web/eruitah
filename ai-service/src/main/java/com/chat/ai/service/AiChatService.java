package com.chat.ai.service;

import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.client.advisor.MessageChatMemoryAdvisor;
import org.springframework.ai.chat.memory.ChatMemory;
import org.springframework.ai.chat.messages.AssistantMessage;
import org.springframework.ai.chat.messages.SystemMessage;
import org.springframework.ai.chat.messages.UserMessage;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

import java.time.Duration;
import java.util.List;

import static org.springframework.ai.chat.client.advisor.AbstractChatMemoryAdvisor.CHAT_MEMORY_CONVERSATION_ID_KEY;
import static org.springframework.ai.chat.client.advisor.AbstractChatMemoryAdvisor.CHAT_MEMORY_RETRIEVE_SIZE_KEY;

@Slf4j
@Service
public class AiChatService {

    private final ChatClient smartChatClient;
    private final ChatClient fastChatClient;
    private final ChatMemory chatMemory;
    private final RedisPubSubService redisPubSubService;
    private final AgentOrchestratorService agentOrchestratorService;

    private static final String SESSION_ID_PREFIX = "[SESSION:";
    private static final String SESSION_ID_SUFFIX = "]";

    public AiChatService(
            @Qualifier("smartChatClient") ChatClient smartChatClient,
            @Qualifier("fastChatClient") ChatClient fastChatClient,
            ChatMemory chatMemory,
            RedisPubSubService redisPubSubService,
            AgentOrchestratorService agentOrchestratorService) {
        this.smartChatClient = smartChatClient;
        this.fastChatClient = fastChatClient;
        this.chatMemory = chatMemory;
        this.redisPubSubService = redisPubSubService;
        this.agentOrchestratorService = agentOrchestratorService;
    }

    /**
     * 1v1 AI聊天核心入口（重构后）
     *
     * 【权限分支逻辑】
     * 1. 通过 AiPersonaRegistry.getPersonaByBotId(botId) 获取该AI角色的人设SystemMessage
     * 2. 如果是旗舰大师(botId == 10000)：使用 AgentOrchestratorService 多智能体编排
     *    - Router: 意图识别（代码求助/理论解答/日常闲聊）
     *    - Solver: 根据意图选择合适的Solver（代码Solver挂载Tool，理论Solver挂载RAG）
     *    - Reflection: 审核反思，确保答案准确
     * 3. 否则（普通闲聊AI如10001/10002/10003）：使用 fastChatClient（纯Prompt聊天）
     * 4. 结合用户的历史记忆构建完整Prompt，调用大模型
     * 5. 将结果通过Redis发回，发送者设置为botId
     *
     * @param userId  真实用户ID
     * @param botId   AI角色ID（10000~10099）
     * @param message 用户消息内容
     * @return ChatResult 包含AI回复和sessionId
     */
    public ChatResult chat(int userId, int botId, String message) {
        String conversationId = buildConversationId(userId, botId);
        log.info("1v1聊天: userId={}, botId={}({}), message={}, conversationId={}",
            userId, botId, AiPersonaRegistry.getBotName(botId), message, conversationId);

        try {
            String response;

            /**
             * 【核心权限判断】
             * 旗舰大师(10000)：使用 AgentOrchestratorService 多智能体编排
             *   - Router → Solver → Reflection 三阶段流水线
             *   - 自动根据意图选择挂载RAG或Tools
             * 其他AI角色：使用fastChatClient，纯Prompt聊天
             */
            if (AiPersonaRegistry.isMasterBot(botId)) {
                log.info("[旗舰大师] 使用 AgentOrchestratorService 多智能体编排（Router → Solver → Reflection）");

                AgentOrchestratorService.AgentResult agentResult = agentOrchestratorService.processUserQuery(userId, message);

                log.info("[旗舰大师] 意图: {}, 初稿长度: {}, 最终答案长度: {}",
                    agentResult.intent(), agentResult.draftAnswer().length(), agentResult.finalAnswer().length());

                response = agentResult.finalAnswer();

                chatMemory.add(conversationId, List.of(
                    new UserMessage(message),
                    new AssistantMessage(response)
                ));

            } else {
                log.info("[{}] 使用fastChatClient（纯Prompt）", AiPersonaRegistry.getBotName(botId));

                SystemMessage systemMessage = AiPersonaRegistry.getPersonaByBotId(botId);

                response = fastChatClient.prompt()
                    .system(systemMessage.getContent())
                    .user(message)
                    .advisors(spec -> spec
                        .param(CHAT_MEMORY_CONVERSATION_ID_KEY, conversationId)
                        .param(CHAT_MEMORY_RETRIEVE_SIZE_KEY, 10))
                    .call()
                    .content();
            }

            log.info("[{}] 回复长度: {}字符", AiPersonaRegistry.getBotName(botId), response.length());

            redisPubSubService.publishDirectMessage(userId, response, botId, AiPersonaRegistry.getBotName(botId));

            return new ChatResult(response, conversationId);

        } catch (Exception e) {
            log.error("1v1聊天失败: userId={}, botId={}", userId, botId, e);
            throw new RuntimeException("AI回复失败: " + e.getMessage(), e);
        }
    }

    /**
     * 兼容旧接口的chat方法（botId默认为旗舰大师10000）
     */
    public ChatResult chat(String userMessage, Integer userId, String userName, String sessionId) {
        return chat(userId, AiPersonaRegistry.MASTER_408_ID, userMessage);
    }

    /**
     * 流式聊天（保留兼容）
     */
    public Flux<String> streamChat(String userMessage, Integer userId, String userName, String sessionId) {
        String conversationId;
        if (sessionId == null || sessionId.trim().isEmpty()) {
            conversationId = buildConversationId(userId, AiPersonaRegistry.MASTER_408_ID);
        } else {
            conversationId = sessionId;
        }

        final String finalConversationId = conversationId;

        log.info("流式聊天: userId={}, conversationId={}", userId, finalConversationId);

        SystemMessage systemMessage = AiPersonaRegistry.getPersonaByBotId(AiPersonaRegistry.MASTER_408_ID);

        final StringBuilder fullResponse = new StringBuilder();

        return Flux.using(
            () -> {
                log.info("Starting stream for conversation: {}", finalConversationId);
                return true;
            },
            resource -> Flux.concat(
                Flux.just(SESSION_ID_PREFIX + finalConversationId + SESSION_ID_SUFFIX + "\n\n"),
                fastChatClient.prompt()
                    .system(systemMessage.getContent())
                    .user(userMessage)
                    .advisors(spec -> spec
                        .param(CHAT_MEMORY_CONVERSATION_ID_KEY, finalConversationId)
                        .param(CHAT_MEMORY_RETRIEVE_SIZE_KEY, 10))
                    .stream()
                    .content()
                    .doOnNext(content -> {
                        if (content != null && !content.isEmpty()) {
                            fullResponse.append(content);
                        }
                    })
                    .filter(content -> content != null && !content.isEmpty())
                    .map(content -> content + "\n\n")
            ),
            resource -> {
                log.info("Stream ended for conversation: {}, response length: {}", 
                    finalConversationId, fullResponse.length());
            }
        ).timeout(Duration.ofSeconds(120));
    }

    private String buildConversationId(Integer userId, int botId) {
        return "chat_" + userId + "_" + botId;
    }

    public void clearSessionHistory(String conversationId) {
        chatMemory.clear(conversationId);
        log.info("Cleared chat memory for conversation: {}", conversationId);
    }

    public record ChatResult(String message, String sessionId) {}
}
