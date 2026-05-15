package com.chat.ai.service;

import com.chat.ai.rpc.ChatProto;
import com.chat.ai.rpc.RpcPushService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.util.*;
import java.util.concurrent.TimeUnit;

@Service
public class CareerAdviceService {

    private static final Logger log = LoggerFactory.getLogger(CareerAdviceService.class);
    private static final String CAREER_PROFILE_KEY = "career:profile:";
    private static final int CAREER_MSG_ID = 80;

    private final ChatClient chatClient;
    private final RpcPushService rpcPushService;
    private final Neo4jClient neo4jClient;
    private final StringRedisTemplate redisTemplate;
    private final ObjectMapper objectMapper;

    public CareerAdviceService(ChatClient.Builder chatClientBuilder,
                                RpcPushService rpcPushService,
                                Neo4jClient neo4jClient,
                                StringRedisTemplate redisTemplate,
                                ObjectMapper objectMapper) {
        this.chatClient = chatClientBuilder.build();
        this.rpcPushService = rpcPushService;
        this.neo4jClient = neo4jClient;
        this.redisTemplate = redisTemplate;
        this.objectMapper = objectMapper;
    }

    public void analyzeAndPush(long userId, String codeContent) {
        try {
            Set<String> masteredConcepts = getMasteredConcepts(userId);
            List<String> skills = extractSkillsFromConcepts(masteredConcepts);
            String resumeHighlight = generateResumeHighlight(skills, masteredConcepts);
            String learningAdvice = generateLearningAdvice(skills, masteredConcepts);

            saveCareerProfile(userId, skills, resumeHighlight, learningAdvice);

            pushCareerAdviceToCpp(userId, skills, resumeHighlight, learningAdvice);

            log.info("[CareerAdvice] Profile updated for user={}: skills={}, advice length={}",
                     userId, skills.size(), learningAdvice.length());
        } catch (Exception e) {
            log.error("[CareerAdvice] Error analyzing for user={}: {}", userId, e.getMessage(), e);
        }
    }

    private Set<String> getMasteredConcepts(long userId) {
        Set<String> concepts = new HashSet<>();
        try {
            String key = "user:" + userId + ":mastered";
            Set<String> redisConcepts = redisTemplate.opsForSet().members(key);
            if (redisConcepts != null) {
                concepts.addAll(redisConcepts);
            }
        } catch (Exception e) {
            log.warn("[CareerAdvice] Failed to get mastered concepts from Redis for user={}", userId);
        }

        try {
            Optional<Map<String, Object>> result = neo4jClient.query(
                    "MATCH (u:User {userId: $userId})-[r:COGNITION]->(c:Concept) " +
                    "WHERE r.score >= 0.6 " +
                    "RETURN collect(c.name) AS concepts"
                ).bind(String.valueOf(userId)).to("userId")
                .fetch().one();

            if (result.isPresent() && result.get().get("concepts") != null) {
                @SuppressWarnings("unchecked")
                List<String> neoConcepts = (List<String>) result.get().get("concepts");
                concepts.addAll(neoConcepts);
            }
        } catch (Exception e) {
            log.warn("[CareerAdvice] Neo4j query failed for user={}: {}", userId, e.getMessage());
        }

        return concepts;
    }

    private List<String> extractSkillsFromConcepts(Set<String> concepts) {
        if (concepts.isEmpty()) {
            return List.of("计算机基础");
        }

        String conceptsStr = String.join(", ", concepts.stream().limit(30).toList());

        try {
            String response = chatClient.prompt()
                    .user(u -> u.text(
                            "基于以下已掌握的知识点，提取出对应的IT技术栈技能标签（如编程语言、框架、工具等）。\n" +
                            "只返回技能标签列表，用逗号分隔，不要其他内容。\n\n" +
                            "已掌握知识点：{concepts}"
                    ).param("concepts", conceptsStr))
                    .call()
                    .content();

            if (response != null && !response.isBlank()) {
                return Arrays.stream(response.split("[,，、\\n]"))
                        .map(String::trim)
                        .filter(s -> !s.isEmpty() && s.length() < 20)
                        .distinct()
                        .limit(15)
                        .toList();
            }
        } catch (Exception e) {
            log.warn("[CareerAdvice] AI skill extraction failed: {}", e.getMessage());
        }

        return List.of("计算机基础");
    }

    private String generateResumeHighlight(List<String> skills, Set<String> concepts) {
        String skillsStr = String.join(", ", skills);
        String conceptsStr = String.join(", ", concepts.stream().limit(15).toList());

        try {
            return chatClient.prompt()
                    .user(u -> u.text(
                            "基于以下技术栈和已掌握知识点，用STAR法则生成一段简历亮点描述（100字以内）。\n" +
                            "技术栈：{skills}\n已掌握知识点：{concepts}"
                    ).param("skills", skillsStr).param("concepts", conceptsStr))
                    .call()
                    .content();
        } catch (Exception e) {
            log.warn("[CareerAdvice] Resume highlight generation failed: {}", e.getMessage());
            return "具备" + skillsStr + "等技术能力";
        }
    }

    private String generateLearningAdvice(List<String> skills, Set<String> concepts) {
        String skillsStr = String.join(", ", skills);

        try {
            return chatClient.prompt()
                    .user(u -> u.text(
                            "基于当前技术栈{skills}，给出3条针对性的下一步学习建议和就业方向指导。\n" +
                            "每条建议50字以内，用编号列出。"
                    ).param("skills", skillsStr))
                    .call()
                    .content();
        } catch (Exception e) {
            log.warn("[CareerAdvice] Learning advice generation failed: {}", e.getMessage());
            return "1. 深入学习数据结构与算法\n2. 掌握系统设计基础\n3. 积累项目实战经验";
        }
    }

    private void saveCareerProfile(long userId, List<String> skills,
                                    String resumeHighlight, String learningAdvice) {
        try {
            Map<String, Object> profile = new HashMap<>();
            profile.put("skills", skills);
            profile.put("resumeHighlight", resumeHighlight);
            profile.put("learningAdvice", learningAdvice);
            profile.put("updatedAt", System.currentTimeMillis());

            String json = objectMapper.writeValueAsString(profile);
            redisTemplate.opsForValue().set(CAREER_PROFILE_KEY + userId, json, 7, TimeUnit.DAYS);
        } catch (Exception e) {
            log.warn("[CareerAdvice] Failed to save profile to Redis: {}", e.getMessage());
        }
    }

    private void pushCareerAdviceToCpp(long userId, List<String> skills,
                                         String resumeHighlight, String learningAdvice) {
        String skillsStr = String.join(",", skills);
        rpcPushService.publishCareerAdvice((int) userId, skillsStr, resumeHighlight, learningAdvice);
        log.info("[CareerAdvice] Pushed career advice to C++ for user={}", userId);
    }
}
