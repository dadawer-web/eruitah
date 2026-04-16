package com.chat.ai.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.util.*;
import java.util.concurrent.TimeUnit;

@Slf4j
@Service
@RequiredArgsConstructor
public class KnowledgeTreeService {

    private final Neo4jClient neo4jClient;
    private final StringRedisTemplate redisTemplate;
    private final ObjectMapper objectMapper;

    private static final String MASTERY_CACHE_PREFIX = "mastery:user:";
    private static final long CACHE_TTL_HOURS = 24;

    public static record TreeNode(
        String name,
        Double mastery,
        Integer size,
        Integer level,
        String subject,
        List<TreeNode> children
    ) {
        public TreeNode withChildren(List<TreeNode> children) {
            return new TreeNode(name, mastery, size, level, subject, children);
        }
    }

    public TreeNode getFullTree(String userId) {
        Map<String, Double> masteryMap = getUserMasteryWithCache(userId);
        
        TreeNode root = new TreeNode("408计算机学科专业基础", 0.0, 10, 0, "ROOT", null);
        
        List<TreeNode> subjects = getSubjects(userId, masteryMap);
        
        return root.withChildren(subjects);
    }

    public TreeNode getSubTree(String userId, String parentName, int maxDepth) {
        Map<String, Double> masteryMap = getUserMasteryWithCache(userId);
        
        return buildSubTree(parentName, masteryMap, 0, maxDepth);
    }

    private List<TreeNode> getSubjects(String userId, Map<String, Double> masteryMap) {
        String cypher = """
            MATCH (c:Concept)
            WHERE c.level = 1
            RETURN c.name as name, c.size as size, c.subject as subject
            ORDER BY c.name
            """;
        
        Collection<Map<String, Object>> results = neo4jClient.query(cypher)
            .fetch().all();
        
        List<TreeNode> subjects = new ArrayList<>();
        
        for (Map<String, Object> row : results) {
            String name = (String) row.get("name");
            Integer size = row.get("size") != null ? ((Number) row.get("size")).intValue() : 10;
            String subject = (String) row.get("subject");
            
            Double mastery = calculateAggregatedMastery(name, masteryMap);
            
            List<TreeNode> chapters = getChildren(name, 2, masteryMap, new HashSet<>(), 4);
            
            subjects.add(new TreeNode(name, mastery, size, 1, subject, chapters));
        }
        
        return subjects;
    }

    private List<TreeNode> getChildren(String parentName, int currentLevel, Map<String, Double> masteryMap, Set<String> visited, int maxDepth) {
        if (currentLevel > maxDepth) {
            return null;
        }
        
        String cypher = """
            MATCH (c:Concept)-[:BELONGS_TO]->(parent:Concept {name: $parentName})
            RETURN c.name as name, c.size as size, c.level as level, c.subject as subject
            ORDER BY c.name
            LIMIT 100
            """;
        
        Collection<Map<String, Object>> results = neo4jClient.query(cypher)
            .bind(parentName).to("parentName")
            .fetch().all();
        
        if (results.isEmpty()) {
            return null;
        }
        
        List<TreeNode> children = new ArrayList<>();
        
        for (Map<String, Object> row : results) {
            String name = (String) row.get("name");
            if (visited.contains(name)) {
                continue;
            }
            
            Integer size = row.get("size") != null ? ((Number) row.get("size")).intValue() : 5;
            Integer nodeLevel = row.get("level") != null ? ((Number) row.get("level")).intValue() : currentLevel;
            String subject = (String) row.get("subject");
            
            Double mastery = masteryMap.getOrDefault(name, 0.0);
            
            Set<String> newVisited = new HashSet<>(visited);
            newVisited.add(name);
            List<TreeNode> grandChildren = getChildren(name, currentLevel + 1, masteryMap, newVisited, maxDepth);
            
            children.add(new TreeNode(name, mastery, size, nodeLevel, subject, grandChildren));
        }
        
        return children.isEmpty() ? null : children;
    }

    private TreeNode buildSubTree(String parentName, Map<String, Double> masteryMap, int currentDepth, int maxDepth) {
        String cypher = """
            MATCH (c:Concept {name: $name})
            RETURN c.name as name, c.size as size, c.level as level, c.subject as subject
            """;
        
        Optional<Map<String, Object>> result = neo4jClient.query(cypher)
            .bind(parentName).to("name")
            .fetch().one();
        
        if (result.isEmpty()) {
            return null;
        }
        
        Map<String, Object> row = result.get();
        String name = (String) row.get("name");
        Integer size = row.get("size") != null ? ((Number) row.get("size")).intValue() : 5;
        Integer level = row.get("level") != null ? ((Number) row.get("level")).intValue() : 3;
        String subject = (String) row.get("subject");
        
        Double mastery = masteryMap.getOrDefault(name, 0.0);
        
        List<TreeNode> children = null;
        if (currentDepth < maxDepth) {
            children = getChildren(name, level + 1, masteryMap, new HashSet<>(), maxDepth);
        }
        
        return new TreeNode(name, mastery, size, level, subject, children);
    }

    private Double calculateAggregatedMastery(String parentName, Map<String, Double> masteryMap) {
        String cypher = """
            MATCH (c:Concept)-[:BELONGS_TO*]->(parent:Concept {name: $parentName})
            RETURN c.name as name
            """;
        
        Collection<Map<String, Object>> results = neo4jClient.query(cypher)
            .bind(parentName).to("parentName")
            .fetch().all();
        
        if (results.isEmpty()) {
            return masteryMap.getOrDefault(parentName, 0.0);
        }
        
        double totalMastery = 0.0;
        int count = 0;
        
        for (Map<String, Object> row : results) {
            String name = (String) row.get("name");
            Double m = masteryMap.get(name);
            if (m != null) {
                totalMastery += m;
                count++;
            }
        }
        
        return count > 0 ? totalMastery / count : 0.0;
    }

    public Map<String, Double> getUserMasteryWithCache(String userId) {
        String cacheKey = MASTERY_CACHE_PREFIX + userId;
        
        String cached = redisTemplate.opsForValue().get(cacheKey);
        if (cached != null) {
            try {
                return objectMapper.readValue(cached, new TypeReference<Map<String, Double>>() {});
            } catch (JsonProcessingException e) {
                log.warn("Failed to parse cached mastery for user {}", userId);
            }
        }
        
        Map<String, Double> mastery = fetchUserMasteryFromNeo4j(userId);
        
        try {
            redisTemplate.opsForValue().set(
                cacheKey, 
                objectMapper.writeValueAsString(mastery),
                CACHE_TTL_HOURS,
                TimeUnit.HOURS
            );
        } catch (JsonProcessingException e) {
            log.warn("Failed to cache mastery for user {}", userId);
        }
        
        return mastery;
    }

    private Map<String, Double> fetchUserMasteryFromNeo4j(String userId) {
        Map<String, Double> mastery = new HashMap<>();
        
        String cypher = """
            MATCH (u:User {userId: $userId})-[r:COGNITION]->(c:Concept)
            RETURN c.name as name, r.score as score
            """;
        
        Collection<Map<String, Object>> results = neo4jClient.query(cypher)
            .bind(userId).to("userId")
            .fetch().all();
        
        for (Map<String, Object> row : results) {
            String name = (String) row.get("name");
            Double score = row.get("score") != null ? ((Number) row.get("score")).doubleValue() : 0.0;
            mastery.put(name, score);
        }
        
        return mastery;
    }

    public void invalidateMasteryCache(String userId) {
        String cacheKey = MASTERY_CACHE_PREFIX + userId;
        redisTemplate.delete(cacheKey);
        log.info("🧹 已清除用户 {} 的掌握度缓存", userId);
    }

    public void updateMasteryCache(String userId, String conceptName, double newScore) {
        String cacheKey = MASTERY_CACHE_PREFIX + userId;
        
        String cached = redisTemplate.opsForValue().get(cacheKey);
        if (cached != null) {
            try {
                Map<String, Double> mastery = objectMapper.readValue(
                    cached, 
                    new TypeReference<Map<String, Double>>() {}
                );
                mastery.put(conceptName, newScore);
                redisTemplate.opsForValue().set(
                    cacheKey, 
                    objectMapper.writeValueAsString(mastery),
                    CACHE_TTL_HOURS,
                    TimeUnit.HOURS
                );
                log.debug("📝 更新缓存: {} -> {} = {:.2f}", userId, conceptName, newScore);
            } catch (Exception e) {
                log.warn("Failed to update mastery cache for user {}", userId);
            }
        }
    }

    public Map<String, Object> getTreeStats(String userId) {
        Map<String, Object> stats = new HashMap<>();
        
        Map<String, Double> mastery = getUserMasteryWithCache(userId);
        
        long mastered = mastery.values().stream().filter(s -> s >= 0.7).count();
        long familiar = mastery.values().stream().filter(s -> s >= 0.4 && s < 0.7).count();
        long weak = mastery.values().stream().filter(s -> s > 0 && s < 0.4).count();
        
        stats.put("totalConcepts", mastery.size());
        stats.put("mastered", mastered);
        stats.put("familiar", familiar);
        stats.put("weak", weak);
        stats.put("notStarted", 3786 - mastery.size());
        
        double avgMastery = mastery.values().stream()
            .mapToDouble(Double::doubleValue)
            .average()
            .orElse(0.0);
        stats.put("averageMastery", avgMastery);
        
        return stats;
    }
}
