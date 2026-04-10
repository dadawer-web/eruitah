package com.chat.ai.service;

import com.chat.ai.model.AiTask;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.messages.SystemMessage;
import org.springframework.ai.chat.messages.UserMessage;
import org.springframework.ai.chat.prompt.Prompt;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;
import java.util.Random;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Slf4j
@Service
public class GroupChatService {

    private final GroupChatMemoryService groupChatMemoryService;
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
            RedisPubSubService redisPubSubService,
            RedisTemplate<String, Object> redisTemplate,
            @Qualifier("smartChatClient") ChatClient smartChatClient,
            @Qualifier("fastChatClient") ChatClient fastChatClient,
            ObjectMapper objectMapper) {
        this.groupChatMemoryService = groupChatMemoryService;
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
     * 多智能体群聊核心入口（重构后）
     *
     * 【重构要点】
     * 原来硬编码了两个AI角色（101/102），现在改为接收 aiBotIdsInGroup 列表，
     * 通过 AiPersonaRegistry 动态获取每个AI角色的人设和能力。
     *
     * 【并发编排原理】
     * 遍历 aiBotIdsInGroup，为每个AI角色创建一个 CompletableFuture.runAsync() 任务：
     * - 所有AI角色的LLM调用并发执行，互不等待
     * - 每个AI角色独立获取人设Prompt、选择ChatClient、调用LLM、添加延迟、推送Redis
     * - 任何单个AI角色失败不影响其他角色
     *
     * 【权限分支】
     * - 旗舰大师(10000)：使用smartChatClient（RAG + Tools）
     * - 其他AI角色：使用fastChatClient（纯Prompt）
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

        List<String> recentMessages = groupChatMemoryService.getRecentMessages(groupId, DEFAULT_MESSAGE_COUNT);
        String chatContext = groupChatMemoryService.formatMessagesForSummary(recentMessages);

        String userPrompt = buildUserPrompt(String.valueOf(senderId), message, chatContext);

        List<CompletableFuture<Void>> futures = new ArrayList<>();

        for (int botId : aiBotIdsInGroup) {
            AiPersonaRegistry.AiPersona persona = AiPersonaRegistry.getPersona(botId);
            if (persona == null) {
                log.warn("未找到botId={}的人设，跳过", botId);
                continue;
            }

            CompletableFuture<Void> future = CompletableFuture.runAsync(
                () -> invokeAgentAndPublish(botId, persona, userPrompt, groupId),
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
     * @param userPrompt 用户消息+上下文
     * @param groupId 群组ID
     */
    private void invokeAgentAndPublish(int botId, AiPersonaRegistry.AiPersona persona,
                                        String userPrompt, Long groupId) {
        try {
            long startTime = System.currentTimeMillis();

            List<Message> promptMessages = new ArrayList<>();
            promptMessages.add(new SystemMessage(persona.systemPrompt()));
            promptMessages.add(new UserMessage(userPrompt));

            Prompt prompt = new Prompt(promptMessages);

            /**
             * 【核心权限判断】
             * 旗舰大师：smartChatClient（RAG + Tools 全挂载）
             * 其他角色：fastChatClient（纯Prompt）
             *   - hasRag的角色：人设Prompt中已包含"优先参考知识库"的指引
             *   - hasTools的角色：人设Prompt中已包含"可以编译验证代码"的指引
             *   - 纯Prompt角色：完全依赖人设和上下文
             */
            String response;
            if (AiPersonaRegistry.isMasterBot(botId)) {
                response = smartChatClient.prompt(prompt)
                    .call()
                    .content();
            } else {
                response = fastChatClient.prompt(prompt)
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

    private String buildUserPrompt(String senderName, String content, String chatContext) {
        return "【当前群聊上下文】\n" + chatContext + "\n\n"
            + "【最新消息】\n" + senderName + " 说：" + content + "\n\n"
            + "请根据你的角色设定，针对这条消息做出回复。";
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

            List<Message> promptMessages = new ArrayList<>();
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
        log.info("Cleared messages for group: {}", groupId);
    }

    public record GroupChatSummary(Long groupId, long totalMessages) {}
}
