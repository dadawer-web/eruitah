package com.chat.ai.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Service;

import java.util.Collection;
import java.util.Map;
import java.util.stream.Collectors;

@Slf4j
@Service
@RequiredArgsConstructor
public class ReviewService {

    private final ChatClient.Builder chatClientBuilder;
    private final Neo4jClient neo4jClient;

    public String generateReviewAdvice(Integer userId) {
        try {
            log.info("Generating review advice for user={}", userId);

            String cypher = """
                MATCH (u:User {userId: $userId})-[r:MASTERED]->(c:Concept)
                WHERE r.score < 0.6
                OPTIONAL MATCH (c)-[:PREREQUISITE_FOR]->(next:Concept)
                RETURN c.name as weakPoint, r.score as currentScore, count(next) as impactCount
                ORDER BY impactCount DESC, currentScore ASC
                LIMIT 3
                """;

            Collection<Map<String, Object>> weakPoints = neo4jClient.query(cypher)
                .bind(userId.toString()).to("userId")
                .fetch().all();

            if (weakPoints.isEmpty()) {
                return "🎉 太棒了！根据图谱分析，你目前的知识点掌握情况良好，没有明显的短板。\n\n继续保持，挑战更高难度的题目吧！";
            }

            String context = weakPoints.stream()
                .map(m -> {
                    String name = (String) m.get("weakPoint");
                    Double score = m.get("currentScore") != null ? ((Number) m.get("currentScore")).doubleValue() : 0.0;
                    Long impact = m.get("impactCount") != null ? ((Number) m.get("impactCount")).longValue() : 0L;
                    return String.format("- %s (掌握度: %.0f%%, 影响后续考点: %d个)", 
                        name, score * 100, impact);
                })
                .collect(Collectors.joining("\n"));

            ChatClient chatClient = chatClientBuilder.build();

            String prompt = """
                我是正在备考408计算机考研的大三学生。根据我的模拟测试和农场答题表现，Neo4j知识图谱分析出我的短板如下：
                
                %s
                
                请作为408旗舰大师（一位严厉但专业的考研导师），给我制定一个今天下午的紧急复习计划。
                要求：
                1. 针对性：重点攻克上述短板
                2. 实操性：给出具体的学习方法和推荐资源
                3. 激励性：用略带攻击性但幽默的语气激励我
                4. 控制在200字以内
                """.formatted(context);

            String advice = chatClient.prompt()
                .user(prompt)
                .call()
                .content();

            log.info("Generated review advice for user={}", userId);
            return advice;

        } catch (Exception e) {
            log.error("Error generating review advice for user={}", userId, e);
            return "⚠️ 复习建议生成失败，请稍后重试。";
        }
    }
}
