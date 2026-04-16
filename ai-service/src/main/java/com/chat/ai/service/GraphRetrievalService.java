package com.chat.ai.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.util.*;
import java.util.stream.Collectors;

@Slf4j
@Service
@RequiredArgsConstructor
public class GraphRetrievalService {

    private final Neo4jClient neo4jClient;
    private final StringRedisTemplate stringRedisTemplate;

    public Map<String, Object> getUserGraphForECharts(String userId) {
        Map<String, Object> result = new HashMap<>();
        List<Map<String, Object>> nodes = new ArrayList<>();
        List<Map<String, Object>> links = new ArrayList<>();

        ensureUserNodeExists(userId);
        nodes.add(createNode(userId, "user", "用户 " + userId, "#5470c6", 50));

        Map<String, Double> userMastery = getUserMasteryMap(userId);

        String conceptCypher = """
            MATCH (c:Concept)
            WHERE c.level >= 3 AND c.level <= 6
            OPTIONAL MATCH (c)-[:BELONGS_TO]->(parent:Concept)
            RETURN c.name as name, c.subject as subject, c.level as level, 
                   c.size as size, parent.name as parentName
            ORDER BY c.subject, c.level
            LIMIT 500
            """;
        
        Collection<Map<String, Object>> allConcepts = neo4jClient.query(conceptCypher)
            .fetch().all();

        Set<String> addedNodes = new HashSet<>();
        Set<String> masteredConcepts = new HashSet<>();

        for (Map<String, Object> concept : allConcepts) {
            String name = (String) concept.get("name");
            String subject = (String) concept.get("subject");
            Integer level = concept.get("level") != null ? ((Number) concept.get("level")).intValue() : 3;
            Integer sizeAttr = concept.get("size") != null ? ((Number) concept.get("size")).intValue() : 5;
            String parentName = (String) concept.get("parentName");
            
            String nodeId = "concept_" + Math.abs(name.hashCode());
            if (addedNodes.contains(nodeId)) continue;
            addedNodes.add(nodeId);

            Double score = userMastery.get(name);
            String color;
            if (score != null) {
                masteredConcepts.add(name);
                if (score >= 0.7) {
                    color = "#91cc75";
                } else if (score >= 0.4) {
                    color = "#fac858";
                } else {
                    color = "#ee6666";
                }
            } else {
                color = "#4a5568";
            }
            
            int symbolSize = Math.max(15, 35 - level * 3);
            nodes.add(createNode(nodeId, "concept", name, color, symbolSize));

            if (parentName != null) {
                String parentId = "concept_" + Math.abs(parentName.hashCode());
                links.add(createLink(nodeId, parentId, ""));
            }
        }

        for (String conceptName : masteredConcepts) {
            String nodeId = "concept_" + Math.abs(conceptName.hashCode());
            Double score = userMastery.get(conceptName);
            String label = score != null ? String.format("%.0f%%", score * 100) : "";
            links.add(createLink(userId, nodeId, label));
        }

        result.put("nodes", nodes);
        result.put("links", links);
        log.info("📊 知识图谱: 用户 {}, 总节点 {}, 已掌握 {}", userId, nodes.size(), masteredConcepts.size());
        return result;
    }

    private void ensureUserNodeExists(String userId) {
        String cypher = "MERGE (u:User {userId: $userId}) RETURN u.userId";
        neo4jClient.query(cypher)
            .bind(userId).to("userId")
            .fetch().one();
    }

    private Map<String, Double> getUserMasteryMap(String userId) {
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

    private Map<String, Object> createNode(String id, String type, String name, String color, int symbolSize) {
        Map<String, Object> node = new HashMap<>();
        node.put("id", id);
        node.put("name", name);
        node.put("category", type);
        node.put("itemStyle", Map.of("color", color));
        node.put("symbolSize", symbolSize);
        return node;
    }

    private Map<String, Object> createLink(String source, String target, String relation) {
        Map<String, Object> link = new HashMap<>();
        link.put("source", source);
        link.put("target", target);
        link.put("value", relation);
        return link;
    }

    public String generateReviewRecommendation(String userId) {
        try {
            ensureUserNodeExists(userId);
            
            String cypher = """
                MATCH (u:User {userId: $userId})-[r:COGNITION]->(c:Concept)
                WHERE r.score < 0.6 AND c.level >= 3
                OPTIONAL MATCH (c)-[:BELONGS_TO]->(parent:Concept)
                RETURN c.name as weakPoint, r.score as currentScore, count(parent) as impactCount
                ORDER BY impactCount DESC, currentScore ASC
                LIMIT 5
                """;

            Collection<Map<String, Object>> weakPoints = neo4jClient.query(cypher)
                .bind(userId).to("userId")
                .fetch().all();

            if (weakPoints.isEmpty()) {
                return "太棒了！你目前掌握得很好，继续保持！";
            }

            StringBuilder sb = new StringBuilder();
            sb.append("📚 建议复习计划：\n\n");
            
            for (Map<String, Object> wp : weakPoints) {
                String name = (String) wp.get("weakPoint");
                Double score = wp.get("currentScore") != null ? ((Number) wp.get("currentScore")).doubleValue() : 0.0;
                Long impact = wp.get("impactCount") != null ? ((Number) wp.get("impactCount")).longValue() : 0L;
                sb.append(String.format("- %s (掌握度: %.0f%%, 影响 %d 个相关知识点)\n", 
                    name, score * 100, impact));
            }

            return sb.toString();

        } catch (Exception e) {
            log.error("Error generating review recommendation for user={}", userId, e);
            return "暂无复习建议，继续答题积累知识点吧！";
        }
    }

    public Map<String, Object> getSubjectTree(String subject) {
        Map<String, Object> result = new HashMap<>();
        List<Map<String, Object>> nodes = new ArrayList<>();
        List<Map<String, Object>> links = new ArrayList<>();

        String cypher = """
            MATCH (c:Concept)
            WHERE c.subject = $subject
            OPTIONAL MATCH (c)-[:BELONGS_TO]->(parent:Concept)
            RETURN c.name as name, c.level as level, parent.name as parentName
            ORDER BY c.level
            """;

        Collection<Map<String, Object>> concepts = neo4jClient.query(cypher)
            .bind(subject).to("subject")
            .fetch().all();

        for (Map<String, Object> concept : concepts) {
            String name = (String) concept.get("name");
            Integer level = concept.get("level") != null ? ((Number) concept.get("level")).intValue() : 0;
            String parentName = (String) concept.get("parentName");
            
            String nodeId = "concept_" + name.hashCode();
            int size = Math.max(10, 40 - level * 8);
            nodes.add(createNode(nodeId, "concept", name, "#6b7280", size));
            
            if (parentName != null) {
                String parentId = "concept_" + parentName.hashCode();
                links.add(createLink(nodeId, parentId, ""));
            }
        }

        result.put("nodes", nodes);
        result.put("links", links);
        return result;
    }

    public List<String> searchConcepts(String keyword) {
        String cypher = """
            MATCH (c:Concept)
            WHERE c.name CONTAINS $keyword AND c.level >= 3
            RETURN c.name as name
            LIMIT 10
            """;
        
        Collection<Map<String, Object>> results = neo4jClient.query(cypher)
            .bind(keyword).to("keyword")
            .fetch().all();
        
        return results.stream()
            .map(m -> (String) m.get("name"))
            .collect(Collectors.toList());
    }
}
