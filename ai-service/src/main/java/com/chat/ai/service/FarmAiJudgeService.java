package com.chat.ai.service;

import com.chat.ai.model.HarvestJudgment;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Slf4j
@Service
public class FarmAiJudgeService {

    private final ChatClient chatClient;
    private final ObjectMapper objectMapper;

    public FarmAiJudgeService(@Qualifier("fastChatClient") ChatClient chatClient, ObjectMapper objectMapper) {
        this.chatClient = chatClient;
        this.objectMapper = objectMapper;
    }

    public HarvestJudgment judgeAnswer(String question, String studentAnswer) {
        try {
            log.info("Farm AI judging: question={}, answer={}", 
                question.substring(0, Math.min(50, question.length())),
                studentAnswer.substring(0, Math.min(50, studentAnswer.length())));

            String prompt = """
                    你是一个极其严格的 408 计算机考研阅卷官。
                    现在有一位玩家在"408农场"中试图回答别人的问题来收菜。
                    
                    【原问题】：%s
                    【玩家答案】：%s
                    
                    请严格判断该答案是否正确、切中要害。
                    如果正确，canHarvest设为true；如果有明显事实错误或太敷衍，设为false。
                    
                    请严格按照以下JSON格式返回，不要包含任何其他文字：
                    {"canHarvest": true或false, "score": 0到100的整数, "feedback": "简短评语"}
                    """.formatted(question, studentAnswer);

            String aiResponse = chatClient.prompt()
                .user(prompt)
                .call()
                .content();

            log.info("Farm AI raw response: {}", aiResponse);

            String jsonStr = aiResponse;
            if (aiResponse.contains("```json")) {
                jsonStr = aiResponse.substring(aiResponse.indexOf("```json") + 7);
                jsonStr = jsonStr.substring(0, jsonStr.indexOf("```"));
            } else if (aiResponse.contains("```")) {
                jsonStr = aiResponse.substring(aiResponse.indexOf("```") + 3);
                jsonStr = jsonStr.substring(0, jsonStr.indexOf("```"));
            }
            jsonStr = jsonStr.trim();

            HarvestJudgment judgment = objectMapper.readValue(jsonStr, HarvestJudgment.class);
            log.info("Farm AI judgment: canHarvest={}, score={}, feedback={}", 
                judgment.canHarvest(), judgment.score(), judgment.feedback());

            return judgment;

        } catch (Exception e) {
            log.error("Error in farm AI judgment, defaulting to false", e);
            return new HarvestJudgment(false, 0, "AI判卷出错，请重试");
        }
    }
}
