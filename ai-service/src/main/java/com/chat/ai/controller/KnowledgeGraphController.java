package com.chat.ai.controller;

import com.chat.ai.model.graph.KnowledgeTriplet;
import com.chat.ai.service.GraphExamService;
import com.chat.ai.service.GraphRetrievalService;
import com.chat.ai.service.KnowledgeExtractorService;
import com.chat.ai.service.KnowledgeTreeService;
import com.chat.ai.service.ReviewService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;

@Slf4j
@RestController
@RequestMapping("/api/graph")
@RequiredArgsConstructor
public class KnowledgeGraphController {

    private final GraphRetrievalService graphRetrievalService;
    private final KnowledgeExtractorService knowledgeExtractorService;
    private final ReviewService reviewService;
    private final GraphExamService graphExamService;
    private final KnowledgeTreeService knowledgeTreeService;

    @GetMapping("/user/{userId}/tree")
    public ResponseEntity<KnowledgeTreeService.TreeNode> getKnowledgeTree(@PathVariable String userId) {
        log.info("🌳 获取知识树: userId={}", userId);
        KnowledgeTreeService.TreeNode tree = knowledgeTreeService.getFullTree(userId);
        return ResponseEntity.ok(tree);
    }

    @GetMapping("/user/{userId}/tree/{parentName}")
    public ResponseEntity<KnowledgeTreeService.TreeNode> getSubTree(
            @PathVariable String userId,
            @PathVariable String parentName,
            @RequestParam(defaultValue = "3") int depth) {
        log.info("🌳 懒加载子树: userId={}, parent={}, depth={}", userId, parentName, depth);
        KnowledgeTreeService.TreeNode subTree = knowledgeTreeService.getSubTree(userId, parentName, depth);
        return ResponseEntity.ok(subTree);
    }

    @GetMapping("/user/{userId}/tree-stats")
    public ResponseEntity<Map<String, Object>> getTreeStats(@PathVariable String userId) {
        log.info("📊 获取知识树统计: userId={}", userId);
        Map<String, Object> stats = knowledgeTreeService.getTreeStats(userId);
        return ResponseEntity.ok(stats);
    }

    @DeleteMapping("/user/{userId}/mastery-cache")
    public ResponseEntity<Map<String, String>> invalidateMasteryCache(@PathVariable String userId) {
        log.info("🧹 清除掌握度缓存: userId={}", userId);
        knowledgeTreeService.invalidateMasteryCache(userId);
        return ResponseEntity.ok(Map.of("message", "缓存已清除"));
    }

    @GetMapping("/user/{userId}/echarts")
    public ResponseEntity<Map<String, Object>> getUserGraphForECharts(@PathVariable String userId) {
        log.info("Getting ECharts graph for user={}", userId);
        Map<String, Object> graph = graphRetrievalService.getUserGraphForECharts(userId);
        return ResponseEntity.ok(graph);
    }

    @GetMapping("/user/{userId}/mastered")
    public ResponseEntity<List<String>> getMasteredConcepts(@PathVariable String userId) {
        log.info("Getting mastered concepts for user={}", userId);
        return ResponseEntity.ok(List.of());
    }

    @GetMapping("/user/{userId}/fuzzy")
    public ResponseEntity<List<String>> getFuzzyConcepts(@PathVariable String userId) {
        log.info("Getting fuzzy concepts for user={}", userId);
        return ResponseEntity.ok(List.of());
    }

    @GetMapping("/user/{userId}/not-mastered")
    public ResponseEntity<List<String>> getNotMasteredConcepts(@PathVariable String userId) {
        log.info("Getting not-mastered concepts for user={}", userId);
        return ResponseEntity.ok(List.of());
    }

    @GetMapping("/user/{userId}/review")
    public ResponseEntity<Map<String, String>> getReviewRecommendation(@PathVariable String userId) {
        log.info("Getting review recommendation for user={}", userId);
        String recommendation = graphRetrievalService.generateReviewRecommendation(userId);
        return ResponseEntity.ok(Map.of("recommendation", recommendation));
    }

    @GetMapping("/user/{userId}/review-ai")
    public CompletableFuture<ResponseEntity<Map<String, String>>> getAIReviewAdvice(@PathVariable Integer userId) {
        log.info("Getting AI review advice for user={}", userId);
        return CompletableFuture.supplyAsync(() -> {
            String advice = reviewService.generateReviewAdvice(userId);
            return ResponseEntity.ok(Map.of("advice", advice));
        });
    }

    @PostMapping("/extract")
    public ResponseEntity<List<KnowledgeTriplet>> extractKnowledge(
            @RequestParam String userMessage,
            @RequestParam String aiFeedback,
            @RequestParam(defaultValue = "用户") String subjectName) {
        log.info("Extracting knowledge for subject={}", subjectName);
        List<KnowledgeTriplet> triplets = knowledgeExtractorService.extractKnowledge(userMessage, aiFeedback, subjectName);
        return ResponseEntity.ok(triplets);
    }

    @GetMapping("/user/{userId}/exam-dashboard")
    public ResponseEntity<Map<String, Object>> getExamDashboard(@PathVariable String userId) {
        log.info("Getting exam dashboard for user={}", userId);
        Map<String, Object> dashboard = graphExamService.getExamDashboard(userId);
        return ResponseEntity.ok(dashboard);
    }

    @GetMapping("/user/{userId}/weak-points")
    public ResponseEntity<List<GraphExamService.WeakPoint>> getWeakPoints(@PathVariable String userId) {
        log.info("Getting weak points for user={}", userId);
        List<GraphExamService.WeakPoint> weakPoints = graphExamService.findWeakPointsForPrerequisiteChain(userId);
        return ResponseEntity.ok(weakPoints);
    }

    @GetMapping("/user/{userId}/learning-path")
    public ResponseEntity<GraphExamService.LearningPath> getLearningPath(@PathVariable String userId) {
        log.info("Getting learning path for user={}", userId);
        GraphExamService.LearningPath path = graphExamService.generateDynamicLearningPath(userId);
        return ResponseEntity.ok(path);
    }

    @GetMapping("/user/{userId}/next-concept")
    public ResponseEntity<Map<String, String>> getNextConcept(@PathVariable String userId) {
        log.info("Getting next concept for user={}", userId);
        return graphExamService.selectNextQuestionConcept(userId)
            .map(concept -> ResponseEntity.ok(Map.of("concept", concept)))
            .orElse(ResponseEntity.ok(Map.of("concept", "已完成所有知识点")));
    }

    @GetMapping("/search")
    public ResponseEntity<List<String>> searchConcepts(@RequestParam String keyword) {
        log.info("Searching concepts with keyword={}", keyword);
        List<String> concepts = graphRetrievalService.searchConcepts(keyword);
        return ResponseEntity.ok(concepts);
    }

    @GetMapping("/subject/{subject}/tree")
    public ResponseEntity<Map<String, Object>> getSubjectTree(@PathVariable String subject) {
        log.info("Getting subject tree for={}", subject);
        Map<String, Object> tree = graphRetrievalService.getSubjectTree(subject);
        return ResponseEntity.ok(tree);
    }
}
