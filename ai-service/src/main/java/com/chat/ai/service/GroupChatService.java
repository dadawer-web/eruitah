package com.chat.ai.service;

import com.chat.ai.model.AiTask;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.client.advisor.MessageChatMemoryAdvisor;
import org.springframework.ai.chat.memory.ChatMemory;
import org.springframework.ai.chat.messages.SystemMessage;
import org.springframework.ai.chat.messages.UserMessage;
import org.springframework.ai.chat.prompt.Prompt;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

import static org.springframework.ai.chat.client.advisor.AbstractChatMemoryAdvisor.CHAT_MEMORY_CONVERSATION_ID_KEY;
import static org.springframework.ai.chat.client.advisor.AbstractChatMemoryAdvisor.CHAT_MEMORY_RETRIEVE_SIZE_KEY;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Random;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Slf4j
@Service
public class GroupChatService {

    private final GroupChatMemoryService groupChatMemoryService;
    private final ChatMemory chatMemory;
    private final RedisPubSubService redisPubSubService;
    private final RedisTemplate<String, Object> redisTemplate;
    private final ChatClient smartChatClient;
    private final ChatClient fastChatClient;
    private final ObjectMapper objectMapper;

    private static final String TASK_QUEUE_KEY = "ai:task:queue";
    private static final int DEFAULT_MESSAGE_COUNT = 100;

    private static final int MIN_DELAY_MS = 1000;
    private static final int MAX_DELAY_MS = 3000;

    private static final String MESSAGE_TYPE_AGENT_CHAT = "AI_AGENT_CHAT";

    private static final Set<Integer> INTERVIEWER_IDS = new HashSet<>(
        Arrays.asList(
            AiPersonaRegistry.INTERVIEWER_BOSS_ID,
            AiPersonaRegistry.INTERVIEWER_PROF_ID,
            AiPersonaRegistry.INTERVIEWER_CODER_ID
        )
    );

    private static final String ROUTER_SYSTEM_PROMPT =
        "你是一个面试主持人。根据用户的消息内容，决定由哪位专家来追问。\n" +
        "三位专家的领域如下：\n" +
        "- 10004：底层原理专家（操作系统、计算机网络、系统设计）\n" +
        "- 10005：项目经验专家（项目架构、软技能、团队协作）\n" +
        "- 10006：算法代码专家（数据结构、算法、代码优化）\n\n" +
        "请根据消息内容的主题，选择最合适的专家。只输出一个数字ID（10004、10005或10006），不要输出任何其他字符！";

    private static final Pattern MENTION_PATTERN = Pattern.compile("@[^\\s@]+");

    private final Random random = new Random();

    private final ExecutorService agentExecutor = Executors.newFixedThreadPool(8);

    private static final String SUMMARY_SYSTEM_PROMPT =
        "你是一个群聊纪要助手，专门负责总结群聊内容并生成简洁、有趣的摘要。\n" +
        "你的任务：\n" +
        "1. 分析群聊记录，提取主要讨论话题\n" +
        "2. 总结关键信息和结论\n" +
        "3. 如果有争议或有趣的观点，可以适当'吃瓜'点评\n" +
        "4. 用轻松幽默的语气，让摘要更有趣\n\n" +
        "输出格式要求：\n" +
        "📢 **群聊摘要**\n" +
        "━━━━━━━━━━━━━━━━\n" +
        "🔥 热门话题：[列出主要话题]\n" +
        "📝 讨论要点：\n" +
        "- [要点1]\n" +
        "- [要点2]\n" +
        "🍉 吃瓜点评：[有趣的点评]\n" +
        "━━━━━━━━━━━━━━━━\n" +
        "请保持摘要简洁，突出重点，风格活泼。";

    private static final Pattern SUMMARY_TRIGGER_PATTERN =
        Pattern.compile("@AI\\s*总结一下(今天)?群里聊了什么", Pattern.CASE_INSENSITIVE);

    public GroupChatService(
            GroupChatMemoryService groupChatMemoryService,
            ChatMemory chatMemory,
            RedisPubSubService redisPubSubService,
            RedisTemplate<String, Object> redisTemplate,
            @Qualifier("smartChatClient") ChatClient smartChatClient,
            @Qualifier("fastChatClient") ChatClient fastChatClient,
            ObjectMapper objectMapper) {
        this.groupChatMemoryService = groupChatMemoryService;
        this.chatMemory = chatMemory;
        this.redisPubSubService = redisPubSubService;
        this.redisTemplate = redisTemplate;
        this.smartChatClient = smartChatClient;
        this.fastChatClient = fastChatClient;
        this.objectMapper = objectMapper;
    }

    // ==================== 多智能体群聊核心逻辑（重构后） ====================

    /**
     * 判断是否需要触发AI群聊回复
     *
     * 条件：发送者为真实用户（senderId < 10000）
     *
     * @param groupId  群组ID
     * @param senderId 发送者ID
     * @return 是否为真实用户发送的消息
     */
    public boolean isRealUserMessage(Long groupId, Integer senderId) {
        return senderId != null && !AiPersonaRegistry.isAiBot(senderId);
    }

    /**
     * 多智能体群聊核心入口（两级责任链重构）
     *
     * 【两级责任链路由】
     * 1. 显式路由（兼容旧版）：检查消息是否包含明确的 @某人，如果有则只让被@的AI回复
     * 2. 智能路由（面试核心）：如果没有@，且群内包含面试官矩阵，则使用Router AI决定由谁回复
     *
     * @param groupId         群组ID
     * @param senderId        发送者ID（真实用户）
     * @param message         消息内容
     * @param aiBotIdsInGroup 群内的AI角色ID列表
     */
    public void handleMultiAgentChat(Long groupId, int senderId, String message,
                                      List<Integer> aiBotIdsInGroup) {
        if (aiBotIdsInGroup == null || aiBotIdsInGroup.isEmpty()) {
            log.warn("aiBotIdsInGroup为空，跳过多智能体群聊: groupId={}", groupId);
            return;
        }

        log.info("=== 触发多智能体群聊 === groupId={}, senderId={}, aiBots={}, message={}",
            groupId, senderId, aiBotIdsInGroup, message);

        List<Integer> targetBotIds = resolveTargetBots(groupId, message, aiBotIdsInGroup);

        if (targetBotIds.isEmpty()) {
            log.info("没有需要回复的AI角色，跳过: groupId={}", groupId);
            return;
        }

        String conversationId = buildGroupConversationId(groupId);

        List<CompletableFuture<Void>> futures = new ArrayList<>();

        for (int botId : targetBotIds) {
            AiPersonaRegistry.AiPersona persona = AiPersonaRegistry.getPersona(botId);
            if (persona == null) {
                log.warn("未找到botId={}的人设，跳过", botId);
                continue;
            }

            CompletableFuture<Void> future = CompletableFuture.runAsync(
                () -> invokeAgentAndPublish(botId, persona, message, conversationId, groupId),
                agentExecutor
            );

            future.whenComplete((v, ex) -> {
                if (ex != null) {
                    log.error("[{}]回复失败: groupId={}", persona.name(), groupId, ex);
                } else {
                    log.info("[{}]回复完成: groupId={}", persona.name(), groupId);
                }
            });

            futures.add(future);
        }

        CompletableFuture.allOf(futures.toArray(new CompletableFuture[0]))
            .exceptionally(ex -> {
                log.error("多智能体群聊部分异常: groupId={}", groupId, ex);
                return null;
            });

        log.info("{}个AI角色的并发调用已提交，等待各自完成...", futures.size());
    }

    /**
     * 解析目标AI角色列表（两级责任链核心）
     *
     * 【第一级：显式路由】
     * - 检查消息是否包含 @某人
     * - 如果有明确@某个AI，则只让被@的AI回复
     *
     * 【第二级：智能路由】
     * - 如果没有@，且群内包含完整的面试官矩阵（10004, 10005, 10006）
     * - 则使用Router AI决定由哪个面试官回复
     *
     * @param groupId         群组ID
     * @param message         消息内容
     * @param aiBotIdsInGroup 群内的AI角色ID列表
     * @return 需要回复的AI角色ID列表
     */
    private List<Integer> resolveTargetBots(Long groupId, String message, List<Integer> aiBotIdsInGroup) {
        List<Integer> mentionedBotIds = extractMentionedBots(message, aiBotIdsInGroup);

        if (!mentionedBotIds.isEmpty()) {
            log.info("显式路由：消息中@了AI角色 {}, 仅让这些AI回复", mentionedBotIds);
            return mentionedBotIds;
        }

        if (isInterviewGroup(aiBotIdsInGroup)) {
            log.info("智能路由：检测到面试群组，触发Router AI决策");
            int selectedBotId = routeToInterviewer(message);
            log.info("Router AI 选择了面试官: {}", selectedBotId);
            return List.of(selectedBotId);
        }

        log.info("默认路由：所有AI角色并发回复");
        return aiBotIdsInGroup;
    }

    /**
     * 提取消息中被@的AI角色ID
     *
     * @param message         消息内容
     * @param aiBotIdsInGroup 群内的AI角色ID列表
     * @return 被@的AI角色ID列表
     */
    private List<Integer> extractMentionedBots(String message, List<Integer> aiBotIdsInGroup) {
        List<Integer> mentionedBotIds = new ArrayList<>();
        Matcher matcher = MENTION_PATTERN.matcher(message);

        while (matcher.find()) {
            String mention = matcher.group().substring(1);
            for (int botId : aiBotIdsInGroup) {
                AiPersonaRegistry.AiPersona persona = AiPersonaRegistry.getPersona(botId);
                if (persona != null && persona.name().equals(mention)) {
                    mentionedBotIds.add(botId);
                    break;
                }
            }
        }

        return mentionedBotIds;
    }

    /**
     * 判断是否是面试群组
     *
     * 面试群组需要包含完整的面试官矩阵：10004, 10005, 10006
     *
     * @param aiBotIdsInGroup 群内的AI角色ID列表
     * @return 是否是面试群组
     */
    private boolean isInterviewGroup(List<Integer> aiBotIdsInGroup) {
        Set<Integer> botIdSet = new HashSet<>(aiBotIdsInGroup);
        return botIdSet.containsAll(INTERVIEWER_IDS);
    }

    /**
     * 使用Router AI决定由哪个面试官回复
     *
     * @param message 用户消息内容
     * @return 被选中的面试官ID
     */
    private int routeToInterviewer(String message) {
        try {
            List<org.springframework.ai.chat.messages.Message> promptMessages = new ArrayList<>();
            promptMessages.add(new SystemMessage(ROUTER_SYSTEM_PROMPT));
            promptMessages.add(new UserMessage("用户说：" + message));

            Prompt prompt = new Prompt(promptMessages);
            String response = fastChatClient.prompt(prompt)
                .call()
                .content()
                .trim();

            log.info("Router AI 原始响应: {}", response);

            int selectedId = parseBotIdFromResponse(response);
            if (INTERVIEWER_IDS.contains(selectedId)) {
                return selectedId;
            }

            log.warn("Router AI 返回了无效的ID: {}, 默认使用慈祥老教授(10005)", response);
            return AiPersonaRegistry.INTERVIEWER_PROF_ID;

        } catch (Exception e) {
            log.error("Router AI 调用失败，默认使用慈祥老教授(10005)", e);
            return AiPersonaRegistry.INTERVIEWER_PROF_ID;
        }
    }

    /**
     * 从Router AI响应中解析Bot ID
     *
     * @param response Router AI的响应
     * @return 解析出的Bot ID
     */
    private int parseBotIdFromResponse(String response) {
        String digits = response.replaceAll("[^0-9]", "");
        if (!digits.isEmpty()) {
            try {
                return Integer.parseInt(digits);
            } catch (NumberFormatException e) {
                log.warn("无法解析Bot ID: {}", response);
            }
        }
        return AiPersonaRegistry.INTERVIEWER_PROF_ID;
    }

    /**
     * 调用单个AI角色并发布回复（重构后）
     *
     * 【权限分支逻辑】
     * - 旗舰大师(10000)：使用smartChatClient，已挂载RAG知识库和Code Tool
     * - 严厉导师(10001)：使用fastChatClient + RAG增强（hasRag=true）
     * - 温柔学长(10002)：使用fastChatClient（纯Prompt，hasRag=false）
     * - 代码审查员(10003)：使用fastChatClient + Code Tool（hasTools=true）
     *
     * 【延迟拟真】
     * 每个AI角色回复后添加1~3秒随机延迟，模拟真人打字节奏
     *
     * @param botId   AI角色ID
     * @param persona AI角色人设
     * @param message 用户原始消息
     * @param conversationId 会话ID（用于记忆管理）
     * @param groupId 群组ID
     */
    private void invokeAgentAndPublish(int botId, AiPersonaRegistry.AiPersona persona,
                                        String message, String conversationId, Long groupId) {
        try {
            long startTime = System.currentTimeMillis();

            /**
             * 【核心权限判断】
             * 旗舰大师：smartChatClient（RAG + Tools 全挂载）
             * 其他角色：fastChatClient（纯Prompt）
             *   - hasRag的角色：人设Prompt中已包含"优先参考知识库"的指引
             *   - hasTools的角色：人设Prompt中已包含"可以编译验证代码"的指引
             *   - 纯Prompt角色：完全依赖人设和上下文
             * 
             * 【记忆管理】
             * 使用 MessageChatMemoryAdvisor 自动管理群聊历史记忆
             */
            String response;
            if (AiPersonaRegistry.isMasterBot(botId)) {
                response = smartChatClient.prompt()
                    .system(persona.systemPrompt())
                    .user(message)
                    .advisors(spec -> spec
                        .param(CHAT_MEMORY_CONVERSATION_ID_KEY, conversationId)
                        .param(CHAT_MEMORY_RETRIEVE_SIZE_KEY, 15))
                    .call()
                    .content();
            } else {
                response = fastChatClient.prompt()
                    .system(persona.systemPrompt())
                    .user(message)
                    .advisors(spec -> spec
                        .param(CHAT_MEMORY_CONVERSATION_ID_KEY, conversationId)
                        .param(CHAT_MEMORY_RETRIEVE_SIZE_KEY, 15))
                    .call()
                    .content();
            }

            long llmTime = System.currentTimeMillis() - startTime;
            log.info("[{}] LLM响应耗时: {}ms, 回复长度: {}字符", persona.name(), llmTime, response.length());

            int delayMs = MIN_DELAY_MS + random.nextInt(MAX_DELAY_MS - MIN_DELAY_MS);
            Thread.sleep(delayMs);

            redisPubSubService.publishAgentGroupMessage(
                groupId, response, botId, persona.name(), MESSAGE_TYPE_AGENT_CHAT
            );

            long totalTime = System.currentTimeMillis() - startTime;
            log.info("[{}] 回复已推送: groupId={}, 总耗时: {}ms (LLM:{}ms + 延迟:{}ms)",
                persona.name(), groupId, totalTime, llmTime, delayMs);

        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            log.error("[{}] 被中断: groupId={}", persona.name(), groupId, e);
        } catch (Exception e) {
            log.error("[{}] 调用失败: groupId={}", persona.name(), groupId, e);
        }
    }

    private String buildGroupConversationId(Long groupId) {
        return "group_" + groupId;
    }

    // ==================== 摘要功能原有代码 ====================

    public boolean isSummaryRequest(String content) {
        if (content == null) return false;
        Matcher matcher = SUMMARY_TRIGGER_PATTERN.matcher(content.trim());
        return matcher.find();
    }

    public void submitSummaryTask(Long groupId, Integer replyTo, String replyToName, String triggerMessage) {
        try {
            AiTask task = AiTask.summaryTask(groupId, replyTo, replyToName, triggerMessage);
            String taskJson = objectMapper.writeValueAsString(task);

            redisTemplate.opsForList().leftPush(TASK_QUEUE_KEY, taskJson);

            log.info("Submitted summary task to queue: groupId={}, replyTo={}", groupId, replyTo);

        } catch (Exception e) {
            log.error("Error submitting summary task for group: {}", groupId, e);
        }
    }

    public String generateSummarySync(Long groupId, int messageCount) {
        log.info("Generating sync summary for group: {}, messageCount: {}", groupId, messageCount);

        try {
            List<String> messages = groupChatMemoryService.getRecentMessages(groupId, messageCount);

            if (messages.isEmpty()) {
                return "📢 **群聊摘要**\n\n群聊记录为空，还没有人说话呢~";
            }

            String chatLog = groupChatMemoryService.formatMessagesForSummary(messages);

            List<org.springframework.ai.chat.messages.Message> promptMessages = new ArrayList<>();
            promptMessages.add(new SystemMessage(SUMMARY_SYSTEM_PROMPT));
            promptMessages.add(new UserMessage("以下是群聊记录，请生成摘要：\n\n" + chatLog));

            Prompt prompt = new Prompt(promptMessages);
            String response = fastChatClient.prompt(prompt)
                .call()
                .content();

            log.info("Generated summary for group: {}, length: {}", groupId, response.length());
            return response;

        } catch (Exception e) {
            log.error("Error generating summary for group: {}", groupId, e);
            return "📢 **群聊摘要**\n\n抱歉，生成摘要时出现问题：" + e.getMessage();
        }
    }

    public GroupChatSummary getGroupChatInfo(Long groupId) {
        long totalCount = groupChatMemoryService.getMessageCount(groupId);
        return new GroupChatSummary(groupId, totalCount);
    }

    public void clearGroupMessages(Long groupId) {
        groupChatMemoryService.clearGroupMessages(groupId);
        String conversationId = buildGroupConversationId(groupId);
        chatMemory.clear(conversationId);
        log.info("Cleared messages for group: {}", groupId);
    }

    public record GroupChatSummary(Long groupId, long totalMessages) {}
}
