package com.chat.ai.controller;

import com.chat.ai.service.GraphExamService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.*;

@Slf4j
@RestController
@RequestMapping("/api/analysis")
public class DashboardController {

    private final GraphExamService graphExamService;
    private final Neo4jClient neo4jClient;
    private final ChatClient fastChatClient;

    public DashboardController(
            GraphExamService graphExamService,
            Neo4jClient neo4jClient,
            @Qualifier("fastChatClient") ChatClient fastChatClient) {
        this.graphExamService = graphExamService;
        this.neo4jClient = neo4jClient;
        this.fastChatClient = fastChatClient;
    }

    @GetMapping("/dashboard/{userId}")
    public ResponseEntity<Map<String, Object>> getDashboardData(@PathVariable String userId) {
        log.info("📊 获取考情大屏数据: userId={}", userId);

        try {
            Map<String, Double> subjectMastery = graphExamService.calculateUserSubjectMastery(userId);

            List<Double> radarData = Arrays.asList(
                subjectMastery.getOrDefault("数据结构", 0.0),
                subjectMastery.getOrDefault("计算机组成原理", 0.0),
                subjectMastery.getOrDefault("计算机操作系统", 0.0),
                subjectMastery.getOrDefault("计算机网络", 0.0)
            );

            List<Integer> lineData = getWeeklyActivity(userId);

            Map<String, Object> response = new LinkedHashMap<>();
            response.put("radar", radarData);
            response.put("line", lineData);
            response.put("userId", userId);
            response.put("updateTime", LocalDate.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd")));

            log.info("📊 考情数据: radar={}, line={}", radarData, lineData);

            return ResponseEntity.ok(response);
        } catch (Exception e) {
            log.error("📊 获取考情数据失败: userId={}, error={}", userId, e.getMessage(), e);
            
            Map<String, Object> errorResponse = new LinkedHashMap<>();
            errorResponse.put("radar", Arrays.asList(0.0, 0.0, 0.0, 0.0));
            errorResponse.put("line", Arrays.asList(0, 0, 0, 0, 0, 0, 0));
            errorResponse.put("userId", userId);
            errorResponse.put("error", e.getMessage());
            
            return ResponseEntity.ok(errorResponse);
        }
    }

    @GetMapping("/dashboard/{userId}/radar")
    public ResponseEntity<Map<String, Object>> getRadarData(@PathVariable String userId) {
        log.info("📊 获取雷达图数据: userId={}", userId);

        Map<String, Double> subjectMastery = graphExamService.calculateUserSubjectMastery(userId);

        Map<String, Object> response = new LinkedHashMap<>();
        response.put("data", Arrays.asList(
            subjectMastery.getOrDefault("数据结构", 0.0),
            subjectMastery.getOrDefault("计算机组成原理", 0.0),
            subjectMastery.getOrDefault("计算机操作系统", 0.0),
            subjectMastery.getOrDefault("计算机网络", 0.0)
        ));
        response.put("subjects", Arrays.asList("数据结构", "计算机组成原理", "操作系统", "计算机网络"));

        return ResponseEntity.ok(response);
    }

    @GetMapping("/dashboard/{userId}/activity")
    public ResponseEntity<Map<String, Object>> getActivityData(@PathVariable String userId) {
        log.info("📊 获取活跃度数据: userId={}", userId);

        List<Integer> activity = getWeeklyActivity(userId);

        Map<String, Object> response = new LinkedHashMap<>();
        response.put("data", activity);
        response.put("labels", getWeekdayLabels());

        return ResponseEntity.ok(response);
    }

    @PostMapping("/dashboard/{userId}/report")
    public ResponseEntity<Map<String, String>> generateWeeklyReport(@PathVariable String userId) {
        log.info("📊 生成周报: userId={}", userId);

        try {
            Map<String, Double> subjectMastery = graphExamService.calculateUserSubjectMastery(userId);
            List<Integer> weeklyActivity = getWeeklyActivity(userId);

            String prompt = buildReportPrompt(subjectMastery, weeklyActivity);

            String report = fastChatClient.prompt()
                .user(prompt)
                .call()
                .content();

            Map<String, String> response = new LinkedHashMap<>();
            response.put("report", report != null ? report : "周报生成失败，请稍后重试");
            response.put("userId", userId);
            response.put("generatedAt", LocalDate.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd")));

            log.info("📊 周报生成成功: userId={}, reportLength={}", userId, report != null ? report.length() : 0);

            return ResponseEntity.ok(response);

        } catch (Exception e) {
            log.error("📊 周报生成失败: userId={}, error={}", userId, e.getMessage(), e);

            Map<String, String> errorResponse = new LinkedHashMap<>();
            errorResponse.put("error", "周报生成失败: " + e.getMessage());
            return ResponseEntity.internalServerError().body(errorResponse);
        }
    }

    private String buildReportPrompt(Map<String, Double> subjectMastery, List<Integer> weeklyActivity) {
        StringBuilder dataBuilder = new StringBuilder();
        String[] subjects = {"数据结构", "计算机组成原理", "操作系统", "计算机网络"};
        double[] values = {
            subjectMastery.getOrDefault("数据结构", 0.0),
            subjectMastery.getOrDefault("计算机组成原理", 0.0),
            subjectMastery.getOrDefault("计算机操作系统", 0.0),
            subjectMastery.getOrDefault("计算机网络", 0.0)
        };

        for (int i = 0; i < subjects.length; i++) {
            int percentage = (int) (values[i] * 100);
            dataBuilder.append(String.format("- %s: %d%%\n", subjects[i], percentage));
        }

        int totalQuestions = weeklyActivity.stream().mapToInt(Integer::intValue).sum();
        String activityStr = weeklyActivity.toString();

        String weekInfo = getWeekInfo();

        return String.format("""
            你是一个408考研严师，专注于计算机考研辅导。请根据以下数据生成一份约300字的Markdown格式学习诊断周报。

            ## 用户本周学习数据
            
            ### 各科掌握度
            %s

            ### 本周做题活跃度
            - 周一至周日做题数: %s
            - 本周累计做题: %d 题

            ## 报告要求
            
            1. **总体评价**：简要概括用户本周整体学习状态（1-2句话）
            2. **薄弱点分析**：指出掌握度低于60%%的科目，分析可能的原因，给出具体建议
            3. **优势科目**：肯定用户表现较好的科目，鼓励保持
            4. **下周建议**：给出具体、可执行的学习建议（包括重点章节、推荐练习题型等）
            
            ## 输出格式
            
            请使用Markdown格式输出，包含清晰的标题和列表。语气要严谨但鼓励，像一位负责任的导师。
            
            注意：报告时间范围是 %s
            """,
            dataBuilder.toString(),
            activityStr,
            totalQuestions,
            weekInfo
        );
    }

    private String getWeekInfo() {
        LocalDate now = LocalDate.now();
        LocalDate weekStart = now.minusDays(7);
        DateTimeFormatter formatter = DateTimeFormatter.ofPattern("MM月dd日");
        return String.format("%s 至 %s", weekStart.format(formatter), now.format(formatter));
    }

    private List<Integer> getWeeklyActivity(String userId) {
        List<Integer> activity = new ArrayList<>();

        LocalDate today = LocalDate.now();
        LocalDate monday = today.with(DayOfWeek.MONDAY);

        for (int i = 0; i < 7; i++) {
            LocalDate date = monday.plusDays(i);
            int count = getDailyQuestionCount(userId, date);
            activity.add(count);
        }

        return activity;
    }

    private int getDailyQuestionCount(String userId, LocalDate date) {
        long startOfDay = date.atStartOfDay(java.time.ZoneId.systemDefault()).toInstant().toEpochMilli();
        long endOfDay = date.plusDays(1).atStartOfDay(java.time.ZoneId.systemDefault()).toInstant().toEpochMilli();

        String cypher = """
            MATCH (u:User {userId: $userId})-[r:COGNITION]->(c:Concept)
            WHERE r.last_update >= $startOfDay AND r.last_update < $endOfDay
            RETURN count(r) AS count
            """;

        Optional<Long> result = neo4jClient.query(cypher)
            .bind(userId).to("userId")
            .bind(startOfDay).to("startOfDay")
            .bind(endOfDay).to("endOfDay")
            .fetchAs(Long.class)
            .one();

        return result.map(Long::intValue).orElse(0);
    }

    private List<String> getWeekdayLabels() {
        return Arrays.asList("周一", "周二", "周三", "周四", "周五", "周六", "周日");
    }

    @GetMapping("/dashboard/{userId}/summary")
    public ResponseEntity<Map<String, Object>> getDashboardSummary(@PathVariable String userId) {
        log.info("📊 获取考情摘要: userId={}", userId);

        Map<String, Double> subjectMastery = graphExamService.calculateUserSubjectMastery(userId);

        double avgMastery = subjectMastery.values().stream()
            .mapToDouble(Double::doubleValue)
            .average()
            .orElse(0.0);

        String strongestSubject = subjectMastery.entrySet().stream()
            .max(Map.Entry.comparingByValue())
            .map(Map.Entry::getKey)
            .orElse("无");

        String weakestSubject = subjectMastery.entrySet().stream()
            .min(Map.Entry.comparingByValue())
            .map(Map.Entry::getKey)
            .orElse("无");

        List<Integer> weeklyActivity = getWeeklyActivity(userId);
        int totalQuestions = weeklyActivity.stream().mapToInt(Integer::intValue).sum();

        Map<String, Object> summary = new LinkedHashMap<>();
        summary.put("avgMastery", Math.round(avgMastery * 100) / 100.0);
        summary.put("strongestSubject", strongestSubject);
        summary.put("weakestSubject", weakestSubject);
        summary.put("totalQuestionsThisWeek", totalQuestions);
        summary.put("subjectDetails", subjectMastery);

        return ResponseEntity.ok(summary);
    }
}
