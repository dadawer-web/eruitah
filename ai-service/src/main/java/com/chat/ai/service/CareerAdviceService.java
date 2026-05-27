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

import java.time.Duration;
import java.util.*;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

@Service
public class CareerAdviceService {

    private static final Logger log = LoggerFactory.getLogger(CareerAdviceService.class);
    private static final String CAREER_PROFILE_KEY = "career:profile:";
    private static final String IDEMPOTENT_LOCK_KEY = "lock:career:advice:";
    private static final Duration IDEMPOTENT_LOCK_TTL = Duration.ofMinutes(2);
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

    public boolean saveAndPushProfile(int userId, List<String> skills,
                                       String resumeHighlight, String learningAdvice) {
        try {
            String contentHash = computeContentHash(userId, skills, resumeHighlight);
            String lockKey = IDEMPOTENT_LOCK_KEY + userId + ":" + contentHash;

            Boolean acquired = redisTemplate.opsForValue().setIfAbsent(lockKey, "locked", IDEMPOTENT_LOCK_TTL);
            if (acquired == null || !acquired) {
                log.info("[RPC-Idempotent] 拦截到重复的技能分析汇报，用户: {}, hash: {}", userId, contentHash);
                return true;
            }

            log.info("[RPC-Idempotent] 首次处理技能分析汇报，用户: {}, hash: {}", userId, contentHash);

            lightUpSkillsInNeo4j(userId, skills);

            mergeCareerProfile(userId, skills, resumeHighlight, learningAdvice);

            pushCareerAdviceToCpp(userId, skills, resumeHighlight, learningAdvice);

            log.info("[CareerAdvice] Profile saved and pushed for user={}: skills={}", userId, skills.size());
            return true;
        } catch (Exception e) {
            log.error("[CareerAdvice] Error saving/pushing profile for user={}: {}", userId, e.getMessage(), e);
            return false;
        }
    }

    public void analyzeAndPush(long userId, String codeContent) {
        try {
            Set<String> masteredConcepts = getMasteredConcepts(userId);
            List<String> skills = extractSkillsFromConcepts(masteredConcepts);
            String resumeHighlight = generateResumeHighlight(skills, masteredConcepts);
            String learningAdvice = generateLearningAdvice(skills, masteredConcepts);

            saveAndPushProfile((int) userId, skills, resumeHighlight, learningAdvice);

            log.info("[CareerAdvice] Profile updated for user={}: skills={}, advice length={}",
                     userId, skills.size(), learningAdvice.length());
        } catch (Exception e) {
            log.error("[CareerAdvice] Error analyzing for user={}: {}", userId, e.getMessage(), e);
        }
    }

    private String computeContentHash(int userId, List<String> skills, String resumeHighlight) {
        String raw = userId + ":" +
                     skills.stream().sorted().collect(Collectors.joining(",")) + ":" +
                     (resumeHighlight != null ? resumeHighlight.hashCode() : 0);
        return Integer.toHexString(raw.hashCode());
    }

    private void lightUpSkillsInNeo4j(int userId, List<String> skills) {
        String userIdStr = String.valueOf(userId);
        int successCount = 0;
        for (String skill : skills) {
            try {
                neo4jClient.query(
                        "MERGE (s:Skill {name: $skillName}) " +
                        "ON CREATE SET s.createdAt = timestamp() " +
                        "MERGE (u:User {userId: $userId}) " +
                        "ON CREATE SET u.createdAt = timestamp() " +
                        "MERGE (u)-[r:MASTERED]->(s) " +
                        "ON CREATE SET r.createdAt = timestamp(), r.score = 1.0 " +
                        "ON MATCH SET r.score = r.score + 0.1, r.updatedAt = timestamp()"
                    ).bind(skill).to("skillName")
                    .bind(userIdStr).to("userId")
                    .run();
                successCount++;
            } catch (Exception e) {
                log.warn("[CareerAdvice] Failed to light up skill '{}' for user={}: {}", skill, userId, e.getMessage());
            }
        }
        log.info("[CareerAdvice] Lit up {}/{} skills in Neo4j for user={}", successCount, skills.size(), userId);
    }

    private void mergeCareerProfile(int userId, List<String> newSkills,
                                     String newHighlight, String newAdvice) {
        try {
            String existingJson = redisTemplate.opsForValue().get(CAREER_PROFILE_KEY + userId);
            List<Map<String, Object>> records = new ArrayList<>();
            Set<String> allSkills = new LinkedHashSet<>();

            if (existingJson != null) {
                JsonNode existing = objectMapper.readTree(existingJson);
                JsonNode recordsNode = existing.path("records");
                if (recordsNode.isArray()) {
                    for (JsonNode rec : recordsNode) {
                        Map<String, Object> recMap = new LinkedHashMap<>();
                        recMap.put("skills", toList(rec.path("skills")));
                        recMap.put("resumeHighlight", rec.path("resumeHighlight").asText(""));
                        recMap.put("learningAdvice", rec.path("learningAdvice").asText(""));
                        recMap.put("timestamp", rec.path("timestamp").asText(""));
                        records.add(recMap);
                    }
                } else {
                    JsonNode existingSkills = existing.path("skills");
                    if (existingSkills.isArray()) {
                        List<String> legacySkills = toList(existingSkills);
                        allSkills.addAll(legacySkills);
                        if (!legacySkills.isEmpty() || !existing.path("resumeHighlight").asText("").isEmpty()) {
                            Map<String, Object> legacyRec = new LinkedHashMap<>();
                            legacyRec.put("skills", legacySkills);
                            legacyRec.put("resumeHighlight", existing.path("resumeHighlight").asText(""));
                            legacyRec.put("learningAdvice", existing.path("learningAdvice").asText(""));
                            legacyRec.put("timestamp", existing.path("updatedAt").asText(""));
                            records.add(legacyRec);
                        }
                    }
                }
            }

            for (Map<String, Object> rec : records) {
                @SuppressWarnings("unchecked")
                List<String> recSkills = (List<String>) rec.get("skills");
                if (recSkills != null) allSkills.addAll(recSkills);
            }
            allSkills.addAll(newSkills);

            Map<String, Object> newRecord = new LinkedHashMap<>();
            newRecord.put("skills", new ArrayList<>(newSkills));
            newRecord.put("resumeHighlight", newHighlight != null ? newHighlight : "");
            newRecord.put("learningAdvice", newAdvice != null ? newAdvice : "");
            newRecord.put("timestamp", String.valueOf(System.currentTimeMillis()));
            records.add(0, newRecord);

            if (records.size() > 50) {
                records = records.subList(0, 50);
            }

            Map<String, Object> profile = new LinkedHashMap<>();
            profile.put("skills", new ArrayList<>(allSkills));
            profile.put("resumeHighlight", newHighlight);
            profile.put("learningAdvice", newAdvice);
            profile.put("nextSuggestion", newAdvice);
            profile.put("updatedAt", System.currentTimeMillis());
            profile.put("source", "ai_analysis");
            profile.put("records", records);

            String json = objectMapper.writeValueAsString(profile);
            redisTemplate.opsForValue().set(CAREER_PROFILE_KEY + userId, json, 7, TimeUnit.DAYS);

            log.info("[CareerAdvice] Merged profile for user={}: total skills={}, records={}", userId, allSkills.size(), records.size());
        } catch (Exception e) {
            log.warn("[CareerAdvice] Failed to merge profile to Redis: {}", e.getMessage());
            saveCareerProfile(userId, newSkills, newHighlight, newAdvice);
        }
    }

    @SuppressWarnings("unchecked")
    public boolean deleteRecord(int userId, int recordIndex) {
        try {
            String existingJson = redisTemplate.opsForValue().get(CAREER_PROFILE_KEY + userId);
            if (existingJson == null || existingJson.isBlank()) {
                log.info("[CareerAdvice] No profile found for user={}, nothing to delete", userId);
                return true;
            }

            JsonNode existing = objectMapper.readTree(existingJson);
            List<Map<String, Object>> records = parseRecordsFromProfile(existing);

            if (records.isEmpty()) {
                log.info("[CareerAdvice] Records list empty for user={}, clearing entire profile", userId);
                redisTemplate.delete(CAREER_PROFILE_KEY + userId);
                return true;
            }

            if (recordIndex < 0 || recordIndex >= records.size()) {
                log.warn("[CareerAdvice] Invalid recordIndex={} for user={}, size={}", recordIndex, userId, records.size());
                return false;
            }

            @SuppressWarnings("unchecked")
            List<String> deletedSkills = (List<String>) records.get(recordIndex).get("skills");
            records.remove(recordIndex);

            if (records.isEmpty()) {
                log.info("[CareerAdvice] Last record deleted for user={}, clearing entire profile", userId);
                redisTemplate.delete(CAREER_PROFILE_KEY + userId);
                removeOrphanSkillsFromNeo4j(userId, new HashSet<>(deletedSkills));
                return true;
            }

            Set<String> remainingSkills = new LinkedHashSet<>();
            for (Map<String, Object> rec : records) {
                @SuppressWarnings("unchecked")
                List<String> recSkills = (List<String>) rec.get("skills");
                if (recSkills != null) remainingSkills.addAll(recSkills);
            }

            Set<String> orphanSkills = new HashSet<>(deletedSkills);
            orphanSkills.removeAll(remainingSkills);

            if (!orphanSkills.isEmpty()) {
                removeOrphanSkillsFromNeo4j(userId, orphanSkills);
            }

            String latestHighlight = records.isEmpty() ? "" : (String) records.get(0).get("resumeHighlight");
            String latestAdvice = records.isEmpty() ? "" : (String) records.get(0).get("learningAdvice");

            Map<String, Object> profile = new LinkedHashMap<>();
            profile.put("skills", new ArrayList<>(remainingSkills));
            profile.put("resumeHighlight", latestHighlight);
            profile.put("learningAdvice", latestAdvice);
            profile.put("nextSuggestion", latestAdvice);
            profile.put("updatedAt", System.currentTimeMillis());
            profile.put("source", "ai_analysis");
            profile.put("records", records);

            String json = objectMapper.writeValueAsString(profile);
            redisTemplate.opsForValue().set(CAREER_PROFILE_KEY + userId, json, 7, TimeUnit.DAYS);

            log.info("[CareerAdvice] Deleted record[{}] for user={}, remaining records={}, orphan skills={}",
                     recordIndex, userId, records.size(), orphanSkills);
            return true;
        } catch (Exception e) {
            log.error("[CareerAdvice] Failed to delete record for user={}: {}", userId, e.getMessage(), e);
            return false;
        }
    }

    public boolean deleteRecordByHighlightText(int userId, String highlightText) {
        try {
            String existingJson = redisTemplate.opsForValue().get(CAREER_PROFILE_KEY + userId);
            if (existingJson == null || existingJson.isBlank()) {
                log.info("[CareerAdvice] No profile found for user={}, nothing to delete", userId);
                return true;
            }

            JsonNode existing = objectMapper.readTree(existingJson);
            List<Map<String, Object>> records = parseRecordsFromProfile(existing);

            if (records.isEmpty()) {
                log.info("[CareerAdvice] Records list empty for user={}, clearing entire profile", userId);
                redisTemplate.delete(CAREER_PROFILE_KEY + userId);
                return true;
            }

            String normalizedTarget = highlightText.trim().replaceAll("\\s+", " ");
            int targetIndex = -1;
            for (int i = 0; i < records.size(); i++) {
                String existingHighlight = (String) records.get(i).get("resumeHighlight");
                if (existingHighlight != null) {
                    String normalizedExisting = existingHighlight.trim().replaceAll("\\s+", " ");
                    if (normalizedExisting.equals(normalizedTarget) ||
                        normalizedExisting.contains(normalizedTarget) ||
                        normalizedTarget.contains(normalizedExisting)) {
                        targetIndex = i;
                        break;
                    }
                }
            }

            if (targetIndex == -1) {
                log.warn("[CareerAdvice] No matching record found for highlightText in user={}", userId);
                return false;
            }

            @SuppressWarnings("unchecked")
            List<String> deletedSkills = (List<String>) records.get(targetIndex).get("skills");
            records.remove(targetIndex);

            if (records.isEmpty()) {
                log.info("[CareerAdvice] Last record deleted by highlightText for user={}, clearing entire profile", userId);
                redisTemplate.delete(CAREER_PROFILE_KEY + userId);
                if (deletedSkills != null) {
                    removeOrphanSkillsFromNeo4j(userId, new HashSet<>(deletedSkills));
                }
                return true;
            }

            Set<String> remainingSkills = new LinkedHashSet<>();
            for (Map<String, Object> rec : records) {
                @SuppressWarnings("unchecked")
                List<String> recSkills = (List<String>) rec.get("skills");
                if (recSkills != null) remainingSkills.addAll(recSkills);
            }

            String latestHighlight = records.isEmpty() ? "" : (String) records.get(0).get("resumeHighlight");
            String latestAdvice = records.isEmpty() ? "" : (String) records.get(0).get("learningAdvice");

            Map<String, Object> profile = new LinkedHashMap<>();
            profile.put("skills", new ArrayList<>(remainingSkills));
            profile.put("resumeHighlight", latestHighlight);
            profile.put("learningAdvice", latestAdvice);
            profile.put("nextSuggestion", latestAdvice);
            profile.put("updatedAt", System.currentTimeMillis());
            profile.put("source", "ai_analysis");
            profile.put("records", records);

            String json = objectMapper.writeValueAsString(profile);
            redisTemplate.opsForValue().set(CAREER_PROFILE_KEY + userId, json, 7, TimeUnit.DAYS);

            log.info("[CareerAdvice] Deleted record by highlightText for user={}, remaining records={}", userId, records.size());
            return true;
        } catch (Exception e) {
            log.error("[CareerAdvice] Failed to delete record by highlightText for user={}: {}", userId, e.getMessage(), e);
            return false;
        }
    }

    private List<Map<String, Object>> parseRecordsFromProfile(JsonNode profile) {
        List<Map<String, Object>> records = new ArrayList<>();

        JsonNode recordsNode = profile.path("records");
        if (recordsNode.isArray()) {
            for (JsonNode rec : recordsNode) {
                Map<String, Object> recMap = new LinkedHashMap<>();
                recMap.put("skills", toList(rec.path("skills")));
                recMap.put("resumeHighlight", rec.path("resumeHighlight").asText(""));
                recMap.put("learningAdvice", rec.path("learningAdvice").asText(""));
                recMap.put("timestamp", rec.path("timestamp").asText(""));
                records.add(recMap);
            }
        } else {
            JsonNode existingSkills = profile.path("skills");
            if (existingSkills.isArray()) {
                List<String> legacySkills = toList(existingSkills);
                if (!legacySkills.isEmpty() || !profile.path("resumeHighlight").asText("").isEmpty()) {
                    Map<String, Object> legacyRec = new LinkedHashMap<>();
                    legacyRec.put("skills", legacySkills);
                    legacyRec.put("resumeHighlight", profile.path("resumeHighlight").asText(""));
                    legacyRec.put("learningAdvice", profile.path("learningAdvice").asText(""));
                    legacyRec.put("timestamp", profile.path("updatedAt").asText(""));
                    records.add(legacyRec);
                }
            }
        }

        return records;
    }

    private void removeOrphanSkillsFromNeo4j(int userId, Set<String> orphanSkills) {
        String userIdStr = String.valueOf(userId);
        int removedCount = 0;
        for (String skill : orphanSkills) {
            try {
                neo4jClient.query(
                        "MATCH (u:User {userId: $userId})-[r:MASTERED]->(s:Skill {name: $skillName}) " +
                        "DELETE r"
                    ).bind(userIdStr).to("userId")
                    .bind(skill).to("skillName")
                    .run();

                neo4jClient.query(
                        "MATCH (s:Skill {name: $skillName}) " +
                        "WHERE NOT (s)--() " +
                        "DELETE s"
                    ).bind(skill).to("skillName")
                    .run();

                removedCount++;
            } catch (Exception e) {
                log.warn("[CareerAdvice] Failed to remove orphan skill '{}' for user={}: {}", skill, userId, e.getMessage());
            }
        }
        log.info("[CareerAdvice] Removed {}/{} orphan skills from Neo4j for user={}", removedCount, orphanSkills.size(), userId);
    }

    private List<String> toList(JsonNode arrayNode) {
        List<String> result = new ArrayList<>();
        if (arrayNode.isArray()) {
            for (JsonNode node : arrayNode) {
                result.add(node.asText());
            }
        }
        return result;
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
