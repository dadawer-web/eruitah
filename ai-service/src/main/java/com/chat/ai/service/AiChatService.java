package com.chat.ai.service;

import com.chat.ai.model.ChatMessage;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.messages.AssistantMessage;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.messages.SystemMessage;
import org.springframework.ai.chat.messages.UserMessage;
import org.springframework.ai.chat.prompt.Prompt;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

@Slf4j
@Service
public class AiChatService {

    private final ChatClient smartChatClient;
    private final ChatClient fastChatClient;
    private final ChatMemoryService chatMemoryService;
    private final RedisPubSubService redisPubSubService;
    private final AgentOrchestratorService agentOrchestratorService;

    private static final String SESSION_ID_PREFIX = "[SESSION:";
    private static final String SESSION_ID_SUFFIX = "]";

    public AiChatService(
            @Qualifier("smartChatClient") ChatClient smartChatClient,
            @Qualifier("fastChatClient") ChatClient fastChatClient,
            ChatMemoryService chatMemoryService,
            RedisPubSubService redisPubSubService,
            AgentOrchestratorService agentOrchestratorService) {
        this.smartChatClient = smartChatClient;
        this.fastChatClient = fastChatClient;
        this.chatMemoryService = chatMemoryService;
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
        String sessionId = generateSessionId(userId, botId);
        log.info("1v1聊天: userId={}, botId={}({}), message={}",
            userId, botId, AiPersonaRegistry.getBotName(botId), message);

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

                AgentOrchestratorService.AgentResult agentResult = agentOrchestratorService.processUserQuery(message);

                log.info("[旗舰大师] 意图: {}, 初稿长度: {}, 最终答案长度: {}",
                    agentResult.intent(), agentResult.draftAnswer().length(), agentResult.finalAnswer().length());

                response = agentResult.finalAnswer();

                chatMemoryService.saveMessage(sessionId, ChatMessage.userMessage(message));
                chatMemoryService.saveMessage(sessionId, ChatMessage.assistantMessage(response));

            } else {
                log.info("[{}] 使用fastChatClient（纯Prompt）", AiPersonaRegistry.getBotName(botId));

                SystemMessage systemMessage = AiPersonaRegistry.getPersonaByBotId(botId);
                List<ChatMessage> history = chatMemoryService.getChatHistory(sessionId);

                List<Message> messages = new ArrayList<>();
                messages.add(systemMessage);

                for (ChatMessage msg : history) {
                    switch (msg.getRole()) {
                        case USER -> messages.add(new UserMessage(msg.getContent()));
                        case ASSISTANT -> messages.add(new AssistantMessage(msg.getContent()));
                        case SYSTEM -> messages.add(new SystemMessage(msg.getContent()));
                    }
                }
                messages.add(new UserMessage(message));

                Prompt prompt = new Prompt(messages);
                response = fastChatClient.prompt(prompt)
                    .call()
                    .content();

                chatMemoryService.saveMessage(sessionId, ChatMessage.userMessage(message));
                chatMemoryService.saveMessage(sessionId, ChatMessage.assistantMessage(response));
            }

            log.info("[{}] 回复长度: {}字符", AiPersonaRegistry.getBotName(botId), response.length());

            redisPubSubService.publishDirectMessage(userId, response, botId, AiPersonaRegistry.getBotName(botId));

            return new ChatResult(response, sessionId);

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
        if (sessionId == null || sessionId.trim().isEmpty()) {
            sessionId = generateSessionId(userId, AiPersonaRegistry.MASTER_408_ID);
        }

        final String finalSessionId = sessionId;

        log.info("流式聊天: userId={}, message={}", userId, userMessage);

        SystemMessage systemMessage = AiPersonaRegistry.getPersonaByBotId(AiPersonaRegistry.MASTER_408_ID);
        List<ChatMessage> history = chatMemoryService.getChatHistory(finalSessionId);

        List<Message> messages = new ArrayList<>();
        messages.add(systemMessage);

        for (ChatMessage msg : history) {
            switch (msg.getRole()) {
                case USER -> messages.add(new UserMessage(msg.getContent()));
                case ASSISTANT -> messages.add(new AssistantMessage(msg.getContent()));
                case SYSTEM -> messages.add(new SystemMessage(msg.getContent()));
            }
        }
        messages.add(new UserMessage(userMessage));

        Prompt prompt = new Prompt(messages);

        chatMemoryService.saveMessage(finalSessionId, ChatMessage.userMessage(userMessage));

        final StringBuilder fullResponse = new StringBuilder();

        return Flux.using(
            () -> {
                log.info("Starting stream for session: {}", finalSessionId);
                return true;
            },
            resource -> Flux.concat(
                Flux.just(SESSION_ID_PREFIX + finalSessionId + SESSION_ID_SUFFIX + "\n\n"),
                fastChatClient.prompt(prompt)
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
                String response = fullResponse.toString();
                log.info("Stream ended, saving assistant message, length: {}", response.length());
                if (!response.isEmpty()) {
                    chatMemoryService.saveMessage(finalSessionId, ChatMessage.assistantMessage(response));
                }
            }
        ).timeout(Duration.ofSeconds(120));
    }

    private String generateSessionId(Integer userId, int botId) {
        return "session_" + userId + "_bot" + botId + "_" + UUID.randomUUID().toString().substring(0, 8);
    }

    public void clearSessionHistory(String sessionId) {
        chatMemoryService.clearHistory(sessionId);
    }

    public record ChatResult(String message, String sessionId) {}
}
