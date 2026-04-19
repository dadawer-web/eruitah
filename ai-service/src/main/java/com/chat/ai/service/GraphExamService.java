package com.chat.ai.service;

import com.chat.ai.repository.ConceptRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.util.*;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

@Slf4j
@Service
@RequiredArgsConstructor
public class GraphExamService {

    private final Neo4jClient neo4jClient;
    private final KnowledgeExtractorService knowledgeExtractorService;
    private final KnowledgeTreeService knowledgeTreeService;
    private final StringRedisTemplate redisTemplate;
    private final ConceptRepository conceptRepository;

    private static final String RECENT_QUESTIONS_PREFIX = "exam:recent:";
    private static final int RECENT_QUESTIONS_TTL_HOURS = 24;
    private static final int MAX_RECENT_QUESTIONS = 20;

    public static record WeakPoint(
        String conceptName,
        double score,
        int impactCount,
        String subject
    ) {}

    public static record LearningPath(
        List<String> concepts,
        String rationale,
        int estimatedMinutes
    ) {}

    public void updateCognitionScore(String userId, String tagName, int aiScore) {
        double normalizedScore = aiScore / 100.0;

        String cypher = """
            MATCH (u:User {userId: $userId})
            MATCH (c:Concept {name: $tagName})
            
            WITH u, c, coalesce(c.size, 5.0) AS conceptSize
            
            WITH u, c, conceptSize, (1.0 / conceptSize) AS alpha
            
            MERGE (u)-[r:COGNITION]->(c)
            ON CREATE SET r.score = alpha * $normalizedScore, r.last_update = timestamp()
            ON MATCH SET r.score = r.score + alpha * ($normalizedScore - r.score), r.last_update = timestamp()
            
            RETURN r.score
            """;

        Optional<Double> result = neo4jClient.query(cypher)
            .bind(userId).to("userId")
            .bind(tagName).to("tagName")
            .bind(normalizedScore).to("normalizedScore")
            .fetchAs(Double.class)
            .one();

        double newScore = result.orElse(0.0);
        
        knowledgeTreeService.updateMasteryCache(userId, tagName, newScore);
        
        log.info("💡【知识追踪】用户 {} 答题得分: {}/100, 考点: [{}], 当前掌握度: {:.2f}%", 
            userId, aiScore, tagName, newScore * 100);
    }

    public void lightUpNode(String userId, String tagName, double scoreChange) {
        int aiScore = (int) (scoreChange * 100 + 50);
        aiScore = Math.max(0, Math.min(100, aiScore));
        updateCognitionScore(userId, tagName, aiScore);
    }

    public void processExamAnswer(String userId, String question, String userAnswer, 
                                   String standardAnswer, int score) {
        try {
            List<com.chat.ai.model.graph.KnowledgeTriplet> triplets = 
                knowledgeExtractorService.extractKnowledge(
                    "问题：" + question + "\n我的回答：" + userAnswer,
                    "标准答案：" + standardAnswer + "\n得分：" + score,
                    userId
                );

            for (com.chat.ai.model.graph.KnowledgeTriplet triplet : triplets) {
                String conceptName = triplet.object();
                String matchedConcept = findBestMatchingConcept(conceptName);
                
                if (matchedConcept != null) {
                    int adjustedScore = score;
                    if (triplet.isFuzzy()) {
                        adjustedScore = Math.max(30, score - 20);
                    } else if (triplet.isNotMastered()) {
                        adjustedScore = Math.max(0, score - 40);
                    }
                    
                    if (!matchedConcept.equals(conceptName)) {
                        log.info("🔄 模糊匹配: [{}] -> [{}]", conceptName, matchedConcept);
                    }
                    
                    updateCognitionScore(userId, matchedConcept, adjustedScore);
                    log.info("✅ 点亮知识点: {} -> {} ({}, 原始分:{}, 调整分:{})", 
                        userId, matchedConcept, triplet.relation(), score, adjustedScore);
                } else {
                    log.warn("⚠️ 知识点不存在于图谱中: {}", conceptName);
                    List<String> suggestions = searchConcepts(extractKeywords(conceptName));
                    if (!suggestions.isEmpty()) {
                        log.info("💡 可能的知识点: {}", suggestions.subList(0, Math.min(3, suggestions.size())));
                    }
                }
            }

            log.info("Processed exam answer for user={}, extracted {} triplets", userId, triplets.size());

        } catch (Exception e) {
            log.error("Error processing exam answer for user={}", userId, e);
        }
    }

    public Optional<String> findConceptByTag(String tagName) {
        String cypher = "MATCH (c:Concept {name: $name}) RETURN c.name as name, c.size as size";
        return neo4jClient.query(cypher)
            .bind(tagName).to("name")
            .fetch()
            .one()
            .map(m -> (String) m.get("name"));
    }

    public String findBestMatchingConcept(String conceptName) {
        Optional<String> exactMatch = findConceptByTag(conceptName);
        if (exactMatch.isPresent()) {
            return exactMatch.get();
        }
        
        String keywords = extractKeywords(conceptName);
        List<String> candidates = searchConcepts(keywords);
        
        if (!candidates.isEmpty()) {
            String bestMatch = candidates.get(0);
            double similarity = calculateSimilarity(conceptName, bestMatch);
            if (similarity > 0.3) {
                return bestMatch;
            }
        }
        
        for (String word : conceptName.split("[，、和与及的]")) {
            word = word.trim();
            if (word.length() >= 2) {
                List<String> partialMatches = searchConcepts(word);
                if (!partialMatches.isEmpty()) {
                    return partialMatches.get(0);
                }
            }
        }
        
        return null;
    }

    private String extractKeywords(String conceptName) {
        String cleaned = conceptName
            .replaceAll("[的与和及]", "")
            .replaceAll("技术|方法|原理|概念|特点|区别|联系", "")
            .trim();
        
        if (cleaned.length() > 10) {
            return cleaned.substring(0, 10);
        }
        return cleaned;
    }

    private double calculateSimilarity(String s1, String s2) {
        if (s1 == null || s2 == null) return 0.0;
        
        Set<Character> set1 = new HashSet<>();
        Set<Character> set2 = new HashSet<>();
        
        for (char c : s1.toCharArray()) set1.add(c);
        for (char c : s2.toCharArray()) set2.add(c);
        
        Set<Character> intersection = new HashSet<>(set1);
        intersection.retainAll(set2);
        
        Set<Character> union = new HashSet<>(set1);
        union.addAll(set2);
        
        return union.isEmpty() ? 0.0 : (double) intersection.size() / union.size();
    }

    public List<String> searchConcepts(String keyword) {
        String cypher = """
            MATCH (c:Concept)
            WHERE c.name CONTAINS $keyword
            RETURN c.name as name, c.size as size
            LIMIT 10
            """;
        
        Collection<Map<String, Object>> results = neo4jClient.query(cypher)
            .bind(keyword).to("keyword")
            .fetch()
            .all();
        
        return results.stream()
            .map(m -> (String) m.get("name"))
            .collect(Collectors.toList());
    }

    public Optional<WeakPoint> findCriticalWeakPoint(String userId) {
        ensureUserNodeExists(userId);
        
        String cypher = """
            MATCH (u:User {userId: $userId})-[r:COGNITION]->(c:Concept)
            WHERE r.score < 0.6
            MATCH (c)-[:BELONGS_TO]->(parent:Concept)
            RETURN c.name AS focusPoint, c.subject AS subject, r.score AS currentScore, 
                   count(parent) AS impactCount
            ORDER BY impactCount DESC, currentScore ASC
            LIMIT 1
            """;

        return neo4jClient.query(cypher)
            .bind(userId).to("userId")
            .fetch()
            .one()
            .map(m -> new WeakPoint(
                (String) m.get("focusPoint"),
                m.get("currentScore") != null ? ((Number) m.get("currentScore")).doubleValue() : 0.0,
                m.get("impactCount") != null ? ((Number) m.get("impactCount")).intValue() : 0,
                (String) m.get("subject")
            ));
    }

    public List<WeakPoint> findWeakPointsForPrerequisiteChain(String userId) {
        return findWeakPointsForSubject(userId, null);
    }

    public List<WeakPoint> findWeakPointsForSubject(String userId, String targetSubject) {
        ensureUserNodeExists(userId);
        
        String subjectFilter = "";
        if (targetSubject != null) {
            subjectFilter = "AND (c.subject = $targetSubject OR EXISTS {" +
                "MATCH (c)-[:BELONGS_TO*1..10]->(root:Concept {name: $targetSubject})" +
                "})";
        }
        
        String cypher = """
            MATCH (u:User {userId: $userId})-[r:COGNITION]->(c:Concept)
            WHERE r.score < 0.6 %s
            OPTIONAL MATCH (c)-[:BELONGS_TO]->(parent:Concept)
            RETURN c.name AS conceptName, c.subject AS subject, r.score AS score, 
                   count(parent) AS impactCount
            ORDER BY impactCount DESC, score ASC
            LIMIT 5
            """.formatted(subjectFilter);

        var query = neo4jClient.query(cypher)
            .bind(userId).to("userId");
        
        if (targetSubject != null) {
            query = query.bind(targetSubject).to("targetSubject");
        }

        Collection<Map<String, Object>> results = query.fetch().all();

        return results.stream()
            .map(m -> new WeakPoint(
                (String) m.get("conceptName"),
                m.get("score") != null ? ((Number) m.get("score")).doubleValue() : 0.0,
                m.get("impactCount") != null ? ((Number) m.get("impactCount")).intValue() : 0,
                (String) m.get("subject")
            ))
            .collect(Collectors.toList());
    }

    public LearningPath generateDynamicLearningPath(String userId) {
        return generateDynamicLearningPath(userId, Collections.emptySet(), null);
    }

    public LearningPath generateDynamicLearningPath(String userId, Set<String> excludeConcepts) {
        return generateDynamicLearningPath(userId, excludeConcepts, null);
    }

    public LearningPath generateDynamicLearningPath(String userId, Set<String> excludeConcepts, String targetSubject) {
        ensureUserNodeExists(userId);
        
        String excludeList = excludeConcepts.isEmpty() ? "" : 
            "AND NOT all.name IN ['" + String.join("','", excludeConcepts) + "']";
        
        String subjectFilter = "";
        if (targetSubject != null) {
            subjectFilter = "AND (all.subject = $targetSubject OR EXISTS {" +
                "MATCH (all)-[:BELONGS_TO*1..10]->(root:Concept {name: $targetSubject})" +
                "})";
        }
        
        String cypher = """
            MATCH (u:User {userId: $userId})
            MATCH (all:Concept)
            WHERE NOT EXISTS {
                MATCH (u)-[r:COGNITION]->(all)
                WHERE r.score >= 0.6
            }
            AND all.level >= 3 AND all.level <= 5
            %s
            %s
            OPTIONAL MATCH (all)-[:BELONGS_TO]->(parent:Concept)
            RETURN all.name AS conceptName, all.subject AS subject, 
                   count(parent) AS upstreamDependencies
            ORDER BY rand()
            LIMIT 10
            """.formatted(excludeList, subjectFilter);

        var query = neo4jClient.query(cypher)
            .bind(userId).to("userId");
        
        if (targetSubject != null) {
            query = query.bind(targetSubject).to("targetSubject");
        }

        Collection<Map<String, Object>> results = query.fetch().all();

        List<String> concepts = results.stream()
            .map(m -> (String) m.get("conceptName"))
            .collect(Collectors.toList());

        int estimatedMinutes = concepts.size() * 15;

        String rationale = String.format(
            "基于你的认知图谱分析，推荐按以下顺序学习 %d 个知识点（预计 %d 分钟）",
            concepts.size(), estimatedMinutes
        );

        return new LearningPath(concepts, rationale, estimatedMinutes);
    }

    public Optional<String> selectNextQuestionConcept(String userId) {
        return selectNextQuestionConcept(userId, null);
    }

    public Optional<String> selectNextQuestionConcept(String userId, String targetSubject) {
        Set<String> recentConcepts = getRecentQuestionConcepts(userId);
        log.info("用户 {} 最近出过的考点: {}, 目标科目: {}", userId, recentConcepts, targetSubject);
        
        Optional<WeakPoint> criticalWeak = findCriticalWeakPointForSubject(userId, targetSubject);
        
        if (criticalWeak.isPresent()) {
            WeakPoint wp = criticalWeak.get();
            if (!recentConcepts.contains(wp.conceptName())) {
                log.info("Selected critical weak point for user {}: {} (impact: {})", 
                    userId, wp.conceptName(), wp.impactCount());
                recordQuestionConcept(userId, wp.conceptName());
                return Optional.of(wp.conceptName());
            }
        }

        LearningPath path = generateDynamicLearningPath(userId, recentConcepts, targetSubject);
        if (!path.concepts().isEmpty()) {
            List<String> availableConcepts = path.concepts().stream()
                .filter(c -> !recentConcepts.contains(c))
                .collect(Collectors.toList());
            
            if (!availableConcepts.isEmpty()) {
                Collections.shuffle(availableConcepts);
                String nextConcept = availableConcepts.get(0);
                log.info("Selected next concept from learning path for user {}: {}", userId, nextConcept);
                recordQuestionConcept(userId, nextConcept);
                return Optional.of(nextConcept);
            }
        }

        String subjectFilter = "";
        if (targetSubject != null) {
            subjectFilter = "AND (c.subject = $targetSubject OR EXISTS {" +
                "MATCH (c)-[:BELONGS_TO*1..10]->(root:Concept {name: $targetSubject})" +
                "})";
        }
        
        String randomCypher = """
            MATCH (c:Concept)
            WHERE c.level >= 3 AND c.level <= 5 %s
            RETURN c.name as name
            ORDER BY rand()
            LIMIT 10
            """.formatted(subjectFilter);
        
        Collection<Map<String, Object>> randomResults;
        if (targetSubject != null) {
            randomResults = neo4jClient.query(randomCypher)
                .bind(targetSubject).to("targetSubject")
                .fetch().all();
        } else {
            randomResults = neo4jClient.query(randomCypher).fetch().all();
        }
        
        List<String> randomConcepts = randomResults.stream()
            .map(m -> (String) m.get("name"))
            .filter(name -> !recentConcepts.contains(name))
            .collect(Collectors.toList());
        
        if (!randomConcepts.isEmpty()) {
            String selected = randomConcepts.get(0);
            log.info("Selected random concept for user {}: {}", userId, selected);
            recordQuestionConcept(userId, selected);
            return Optional.of(selected);
        }
        
        return Optional.empty();
    }

    private Optional<WeakPoint> findCriticalWeakPointForSubject(String userId, String targetSubject) {
        ensureUserNodeExists(userId);
        
        String subjectFilter = "";
        if (targetSubject != null) {
            subjectFilter = "AND (c.subject = $targetSubject OR EXISTS {" +
                "MATCH (c)-[:BELONGS_TO*1..10]->(root:Concept {name: $targetSubject})" +
                "})";
        }
        
        String cypher = """
            MATCH (u:User {userId: $userId})-[r:COGNITION]->(c:Concept)
            WHERE r.score < 0.6 %s
            MATCH (c)-[:BELONGS_TO]->(parent:Concept)
            RETURN c.name AS focusPoint, c.subject AS subject, r.score AS currentScore, 
                   count(parent) AS impactCount
            ORDER BY impactCount DESC, currentScore ASC
            LIMIT 1
            """.formatted(subjectFilter);

        var query = neo4jClient.query(cypher)
            .bind(userId).to("userId");
        
        if (targetSubject != null) {
            query = query.bind(targetSubject).to("targetSubject");
        }

        return query.fetch()
            .one()
            .map(m -> new WeakPoint(
                (String) m.get("focusPoint"),
                m.get("currentScore") != null ? ((Number) m.get("currentScore")).doubleValue() : 0.0,
                m.get("impactCount") != null ? ((Number) m.get("impactCount")).intValue() : 0,
                (String) m.get("subject")
            ));
    }

    private Set<String> getRecentQuestionConcepts(String userId) {
        String key = RECENT_QUESTIONS_PREFIX + userId;
        Set<String> concepts = redisTemplate.opsForSet().members(key);
        return concepts != null ? concepts : Collections.emptySet();
    }

    private void recordQuestionConcept(String userId, String conceptName) {
        String key = RECENT_QUESTIONS_PREFIX + userId;
        redisTemplate.opsForSet().add(key, conceptName);
        redisTemplate.expire(key, RECENT_QUESTIONS_TTL_HOURS, TimeUnit.HOURS);
        
        Long size = redisTemplate.opsForSet().size(key);
        if (size != null && size > MAX_RECENT_QUESTIONS) {
            redisTemplate.opsForSet().pop(key);
        }
    }

    private void ensureUserNodeExists(String userId) {
        String cypher = "MERGE (u:User {userId: $userId}) RETURN u.userId";
        neo4jClient.query(cypher)
            .bind(userId).to("userId")
            .fetch()
            .one();
    }

    public Map<String, Object> getExamDashboard(String userId) {
        ensureUserNodeExists(userId);
        
        Map<String, Object> dashboard = new HashMap<>();

        Optional<WeakPoint> criticalWeak = findCriticalWeakPoint(userId);
        dashboard.put("criticalWeakPoint", criticalWeak.orElse(null));

        List<WeakPoint> weakPoints = findWeakPointsForPrerequisiteChain(userId);
        dashboard.put("weakPoints", weakPoints);

        LearningPath path = generateDynamicLearningPath(userId);
        dashboard.put("learningPath", path);

        String coverageCypher = """
            MATCH (u:User {userId: $userId})-[r:COGNITION]->(c:Concept)
            WITH avg(r.score) AS avgScore, count(c) AS masteredCount
            MATCH (all:Concept)
            WHERE all.level >= 3
            RETURN avgScore, masteredCount, count(all) AS totalCount
            """;

        Optional<Map<String, Object>> coverage = neo4jClient.query(coverageCypher)
            .bind(userId).to("userId")
            .fetch()
            .one();

        if (coverage.isPresent()) {
            Map<String, Object> c = coverage.get();
            double avgScore = c.get("avgScore") != null ? ((Number) c.get("avgScore")).doubleValue() : 0.0;
            int masteredCount = c.get("masteredCount") != null ? ((Number) c.get("masteredCount")).intValue() : 0;
            int totalCount = c.get("totalCount") != null ? ((Number) c.get("totalCount")).intValue() : 1;
            
            dashboard.put("averageMastery", avgScore);
            dashboard.put("masteredConcepts", masteredCount);
            dashboard.put("totalConcepts", totalCount);
            dashboard.put("coverageRate", (double) masteredCount / totalCount);
        } else {
            dashboard.put("averageMastery", 0.0);
            dashboard.put("masteredConcepts", 0);
            dashboard.put("totalConcepts", 3785);
            dashboard.put("coverageRate", 0.0);
        }

        return dashboard;
    }

    public Map<String, Double> calculateUserSubjectMastery(String userId) {
        ensureUserNodeExists(userId);

        Map<String, Double> result = new LinkedHashMap<>();
        result.put("数据结构", 0.0);
        result.put("计算机操作系统", 0.0);
        result.put("计算机组成原理", 0.0);
        result.put("计算机网络", 0.0);

        String cypher = """
            MATCH (root:Concept)
            WHERE root.name IN ['数据结构', '计算机操作系统', '计算机组成原理', '计算机网络']
            OPTIONAL MATCH (root)<-[:BELONGS_TO*1..10]-(leaf:Concept)
            OPTIONAL MATCH (leaf)<-[r:COGNITION]-(u:User {userId: $userId})
            WITH root.name AS subject, avg(r.score) AS avgScore
            RETURN subject, coalesce(avgScore, 0.0) AS mastery
            """;

        neo4jClient.query(cypher)
            .bind(userId).to("userId")
            .fetch()
            .all()
            .forEach(record -> {
                String subject = (String) record.get("subject");
                Object masteryObj = record.get("mastery");
                Double mastery = 0.0;
                if (masteryObj instanceof Number) {
                    mastery = ((Number) masteryObj).doubleValue();
                }
                if (subject != null && result.containsKey(subject)) {
                    result.put(subject, mastery);
                }
            });

        log.info("📊【科目掌握度】用户 {} 的科目掌握度: {}", userId, result);
        return result;
    }
}
