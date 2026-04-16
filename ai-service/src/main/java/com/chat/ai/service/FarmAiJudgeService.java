package com.chat.ai.service;

import com.chat.ai.config.ai.StructuredOutputInvoker;
import com.chat.ai.exception.BusinessException;
import com.chat.ai.exception.ErrorCode;
import com.chat.ai.model.HarvestJudgment;
import com.chat.ai.model.graph.KnowledgeTriplet;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.converter.BeanOutputConverter;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

import java.util.List;

@Slf4j
@Service
public class FarmAiJudgeService {

    private final ChatClient chatClient;
    private final ObjectMapper objectMapper;
    private final KnowledgeExtractorService knowledgeExtractorService;
    private final GraphExamService graphExamService;
    private final StringRedisTemplate stringRedisTemplate;
    private final StructuredOutputInvoker structuredOutputInvoker;

    private static final String JUDGE_SYSTEM_PROMPT = """
            你是一个极其严格的 408 计算机考研阅卷官。
            现在有一位玩家在"408农场"中试图回答别人的问题来收菜。
            
            请严格判断该答案是否正确、切中要害。
            如果正确，canHarvest设为true；如果有明显事实错误或太敷衍，设为false。
            
            请严格按照以下JSON格式返回：
            {"canHarvest": boolean, "score": number(0-100), "feedback": "string"}
            """;

    private static final String EXTRACT_SYSTEM_PROMPT = """
            根据以下408考研问答，提取出该用户成功掌握的1到3个核心专业术语（如：死锁预防、页面置换、TCP三次握手）。
            只返回专业术语，不要解释。
            
            请严格按照以下JSON数组格式返回：
            ["术语1", "术语2"]
            """;

    public FarmAiJudgeService(
            @Qualifier("fastChatClient") ChatClient chatClient,
            ObjectMapper objectMapper,
            KnowledgeExtractorService knowledgeExtractorService,
            GraphExamService graphExamService,
            StringRedisTemplate stringRedisTemplate,
            StructuredOutputInvoker structuredOutputInvoker) {
        this.chatClient = chatClient;
        this.objectMapper = objectMapper;
        this.knowledgeExtractorService = knowledgeExtractorService;
        this.graphExamService = graphExamService;
        this.stringRedisTemplate = stringRedisTemplate;
        this.structuredOutputInvoker = structuredOutputInvoker;
    }

    public HarvestJudgment judgeAnswer(String question, String studentAnswer) {
        try {
            log.info("Farm AI judging: question={}, answer={}",
                question.substring(0, Math.min(50, question.length())),
                studentAnswer.substring(0, Math.min(50, studentAnswer.length())));

            String userPrompt = String.format("【原问题】：%s\n【玩家答案】：%s", question, studentAnswer);

            BeanOutputConverter<HarvestJudgment> converter = new BeanOutputConverter<>(HarvestJudgment.class);

            HarvestJudgment judgment = structuredOutputInvoker.invoke(
                chatClient,
                JUDGE_SYSTEM_PROMPT,
                userPrompt,
                converter,
                ErrorCode.AI_SERVICE_ERROR,
                "AI判卷失败：",
                "farm_judge",
                log
            );

            log.info("Farm AI judgment: canHarvest={}, score={}, feedback={}",
                judgment.canHarvest(), judgment.score(), judgment.feedback());

            return judgment;

        } catch (BusinessException e) {
            throw e;
        } catch (Exception e) {
            log.error("Error in farm AI judgment, defaulting to false", e);
            return new HarvestJudgment(false, 0, "AI判卷出错，请重试");
        }
    }

    @Async
    public void extractAndSaveKnowledgeGraph(int userId, String question, String answer, int score) {
        try {
            log.info("Starting async knowledge graph extraction for user={}", userId);

            String userPrompt = String.format("【问题】：%s\n【答案】：%s", question, answer);

            String extractPrompt = EXTRACT_SYSTEM_PROMPT + "\n\n" + userPrompt;

            String aiResponse = chatClient.prompt()
                .user(extractPrompt)
                .call()
                .content();

            log.info("Knowledge extraction raw response for user={}: {}", userId, aiResponse);

            String jsonStr = cleanJsonResponse(aiResponse);

            List<String> concepts = objectMapper.readValue(jsonStr, new TypeReference<List<String>>() {});
            log.info("Extracted concepts for user={}: {}", userId, concepts);

            String userIdStr = String.valueOf(userId);
            
            for (String conceptName : concepts) {
                if (graphExamService.findConceptByTag(conceptName).isPresent()) {
                    graphExamService.updateCognitionScore(userIdStr, conceptName, score);
                    log.info("💡 点亮知识点: {} -> {} (得分:{})", userIdStr, conceptName, score);
                } else {
                    log.warn("⚠️ 知识点不存在于图谱中: {}", conceptName);
                }

                stringRedisTemplate.opsForSet().add("user:" + userIdStr + ":mastered", conceptName);
                log.info("Redis SADD user:{}:mastered <- {}", userIdStr, conceptName);
            }

            log.info("Saved knowledge graph for user={}, processed {} concepts", userId, concepts.size());

        } catch (Exception e) {
            log.error("Error in async knowledge graph extraction for user={}", userId, e);
        }
    }

    @Async
    public void extractAndSaveKnowledgeGraphAdvanced(int userId, String question, String answer, 
                                                      String feedback, int score) {
        try {
            log.info("Starting advanced knowledge extraction for user={}", userId);

            String userMessage = "问题：" + question + "\n我的回答：" + answer;
            List<KnowledgeTriplet> triplets = knowledgeExtractorService.extractKnowledge(
                userMessage, feedback, String.valueOf(userId));

            if (!triplets.isEmpty()) {
                for (KnowledgeTriplet triplet : triplets) {
                    int adjustedScore = score;
                    if (triplet.isFuzzy()) {
                        adjustedScore = Math.max(30, score - 20);
                    } else if (triplet.isNotMastered()) {
                        adjustedScore = Math.max(0, score - 40);
                    }
                    
                    if (graphExamService.findConceptByTag(triplet.object()).isPresent()) {
                        graphExamService.updateCognitionScore(String.valueOf(userId), triplet.object(), adjustedScore);
                        log.info("💡 点亮知识点: {} -> {} ({}, 原始分:{}, 调整分:{})", 
                            userId, triplet.object(), triplet.relation(), score, adjustedScore);
                    } else {
                        log.warn("⚠️ 知识点不存在于图谱中: {}", triplet.object());
                    }
                }
                log.info("Processed {} triplets for user={}", triplets.size(), userId);
            }

        } catch (Exception e) {
            log.error("Error in advanced knowledge extraction for user={}", userId, e);
        }
    }

    private String cleanJsonResponse(String response) {
        String jsonStr = response;
        if (jsonStr.contains("```json")) {
            jsonStr = jsonStr.substring(jsonStr.indexOf("```json") + 7);
            jsonStr = jsonStr.substring(0, jsonStr.indexOf("```"));
        } else if (jsonStr.contains("```")) {
            jsonStr = jsonStr.substring(jsonStr.indexOf("```") + 3);
            jsonStr = jsonStr.substring(0, jsonStr.indexOf("```"));
        }
        return jsonStr.trim();
    }
}
