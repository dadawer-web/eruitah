package com.chat.ai.scheduler;

import com.chat.ai.model.graph.UserNode;
import com.chat.ai.repository.UserRepository;
import com.chat.ai.service.GraphExamService;
import com.chat.ai.service.RedisPubSubService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.retry.annotation.Backoff;
import org.springframework.retry.annotation.Retryable;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.DayOfWeek;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Map;

@Slf4j
@Component
@RequiredArgsConstructor
public class WeeklyReportScheduler {

    private final UserRepository userRepository;
    private final GraphExamService graphExamService;
    private final RedisPubSubService redisPubSubService;

    @Qualifier("fastChatClient")
    private final ChatClient fastChatClient;

    private static final int BOT_ID = 10000;
    private static final String BOT_NAME = "408考研严师";

    @Scheduled(cron = "0 0 22 ? * SUN")
    public void generateWeeklyReports() {
        log.info("📅 [周报任务] 开始执行 - 时间: {}", LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")));

        try {
            List<UserNode> activeUsers = userRepository.findAllActive();
            log.info("📊 [周报任务] 发现 {} 位活跃用户", activeUsers.size());

            int successCount = 0;
            int failCount = 0;

            for (UserNode user : activeUsers) {
                try {
                    generateAndPushReport(user.getUserId());
                    successCount++;
                    Thread.sleep(500);
                } catch (Exception e) {
                    log.error("❌ [周报任务] 用户 {} 周报生成失败: {}", user.getUserId(), e.getMessage());
                    failCount++;
                }
            }

            log.info("✅ [周报任务] 执行完成 - 成功: {}, 失败: {}", successCount, failCount);

        } catch (Exception e) {
            log.error("❌ [周报任务] 执行异常: ", e);
        }
    }

    @Retryable(
        retryFor = {Exception.class},
        maxAttempts = 3,
        backoff = @Backoff(delay = 2000, multiplier = 2)
    )
    public void generateAndPushReport(String userId) {
        log.info("📝 [周报生成] 开始为用户 {} 生成周报", userId);

        Map<String, Double> subjectMastery = graphExamService.calculateUserSubjectMastery(userId);

        String prompt = buildPrompt(subjectMastery);

        String report = callAiModel(prompt);

        pushReportToUser(userId, report);

        log.info("✅ [周报生成] 用户 {} 周报已推送", userId);
    }

    private String buildPrompt(Map<String, Double> subjectMastery) {
        StringBuilder dataBuilder = new StringBuilder();
        subjectMastery.forEach((subject, score) -> {
            int percentage = (int) (score * 100);
            dataBuilder.append(String.format("- %s: %d%%\n", subject, percentage));
        });

        String weekInfo = getWeekInfo();

        return String.format("""
            你是一个408考研严师，专注于计算机考研辅导。请根据以下数据生成一份约300字的Markdown格式学习诊断周报。

            ## 用户本周学习数据
            
            %s

            ## 报告要求
            
            1. **总体评价**：简要概括用户本周整体学习状态
            2. **薄弱点分析**：指出掌握度低于60%%的科目，分析可能的原因
            3. **优势科目**：肯定用户表现较好的科目
            4. **下周建议**：给出具体、可执行的学习建议（包括重点章节、推荐练习题型等）
            
            ## 输出格式
            
            请使用Markdown格式输出，包含清晰的标题和列表。语气要严谨但鼓励，像一位负责任的导师。
            
            注意：报告时间范围是 %s
            """,
            dataBuilder.toString(),
            weekInfo
        );
    }

    private String getWeekInfo() {
        LocalDateTime now = LocalDateTime.now();
        LocalDateTime weekStart = now.minusDays(7);
        DateTimeFormatter formatter = DateTimeFormatter.ofPattern("MM月dd日");
        return String.format("%s 至 %s", weekStart.format(formatter), now.format(formatter));
    }

    private String callAiModel(String prompt) {
        log.debug("🤖 [AI调用] Prompt长度: {} 字符", prompt.length());

        String response = fastChatClient.prompt()
            .user(prompt)
            .call()
            .content();

        log.debug("🤖 [AI调用] 响应长度: {} 字符", response != null ? response.length() : 0);

        return response != null ? response : "周报生成失败，请稍后重试。";
    }

    private void pushReportToUser(String userId, String report) {
        try {
            Integer userIdInt = Integer.parseInt(userId);

            String header = "📅 **408 AI 学习诊断周报**\n\n";
            String fullReport = header + report;

            redisPubSubService.publishDirectMessage(userIdInt, fullReport, BOT_ID, BOT_NAME);

            log.info("📤 [消息推送] 周报已推送至用户 {}", userId);

        } catch (NumberFormatException e) {
            log.error("❌ [消息推送] 用户ID格式错误: {}", userId);
        }
    }

    @Scheduled(cron = "0 5 22 ? * SUN")
    public void sendWeeklyReportSummary() {
        log.info("📊 [周报汇总] 开始生成系统周报汇总");

        try {
            List<UserNode> allUsers = userRepository.findAll();
            long totalUsers = allUsers.size();
            long activeUsers = userRepository.findAllActive().size();

            String summary = String.format("""
                📊 **本周系统运行汇总**
                
                - 注册用户总数: %d
                - 本周活跃用户: %d
                - 活跃率: %.1f%%
                
                系统运行正常，祝大家学习进步！
                """,
                totalUsers,
                activeUsers,
                totalUsers > 0 ? (activeUsers * 100.0 / totalUsers) : 0.0
            );

            log.info("📊 [周报汇总] {}", summary.replace("\n", " "));

        } catch (Exception e) {
            log.error("❌ [周报汇总] 生成失败: ", e);
        }
    }
}
