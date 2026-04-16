package com.chat.ai.service;

import com.chat.ai.model.graph.KnowledgeTriplet;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.converter.BeanOutputConverter;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.stereotype.Service;

import java.util.List;

@Slf4j
@Service
public class KnowledgeExtractorService {

    private final ChatClient chatClient;

    private static final String SYSTEM_PROMPT = """
            你是一个隐形的知识图谱抽取引擎。你的任务是从对话中提取用户的认知状态三元组。
            
            ## 规则：
            1. 实体（object）必须是408计算机基础领域的具体考点，如：快速排序、进程调度、TCP拥塞控制、页面置换等
            2. 关系（relation）只能是以下三种之一：
               - "掌握"：用户表现出对该考点的清晰理解
               - "模糊"：用户提到该考点但理解不够准确
               - "未掌握"：用户对该考点存在明显误解或错误
            3. 理由（rationale）简要说明判断依据
            
            ## 输出格式：
            返回JSON数组，每个元素包含subject、relation、object、rationale四个字段
            """;

    public KnowledgeExtractorService(@Qualifier("fastChatClient") ChatClient chatClient) {
        this.chatClient = chatClient;
    }

    public List<KnowledgeTriplet> extractKnowledge(String userMessage, String aiFeedback) {
        return extractKnowledge(userMessage, aiFeedback, "用户");
    }

    public List<KnowledgeTriplet> extractKnowledge(String userMessage, String aiFeedback, String subjectName) {
        try {
            log.info("Extracting knowledge triplets for subject={}", subjectName);

            BeanOutputConverter<List<KnowledgeTriplet>> outputConverter = new BeanOutputConverter<>(
                new ParameterizedTypeReference<List<KnowledgeTriplet>>() {}
            );

            String formatInstructions = outputConverter.getFormat();

            String userPrompt = String.format("""
                    请分析以下对话，提取用户的认知三元组：
                    
                    【用户消息】：
                    %s
                    
                    【AI反馈】：
                    %s
                    
                    请提取1-3个最核心的知识点三元组。
                    
                    %s
                    """, userMessage, aiFeedback, formatInstructions);

            String fullPrompt = SYSTEM_PROMPT + "\n\n" + userPrompt;

            String aiResponse = chatClient.prompt()
                .user(fullPrompt)
                .call()
                .content();

            log.info("Knowledge extraction raw response: {}", aiResponse);

            String jsonStr = cleanJsonResponse(aiResponse);
            
            List<KnowledgeTriplet> triplets = outputConverter.convert(jsonStr);
            
            triplets = triplets.stream()
                .map(t -> new KnowledgeTriplet(
                    subjectName,
                    t.relation(),
                    t.object(),
                    t.rationale()
                ))
                .toList();

            log.info("Extracted {} triplets for subject={}", triplets.size(), subjectName);
            return triplets;

        } catch (Exception e) {
            log.error("Error extracting knowledge triplets", e);
            return List.of();
        }
    }

    private String cleanJsonResponse(String response) {
        String jsonStr = response;
        
        if (jsonStr.contains("```json")) {
            jsonStr = jsonStr.substring(jsonStr.indexOf("```json") + 7);
            if (jsonStr.contains("```")) {
                jsonStr = jsonStr.substring(0, jsonStr.indexOf("```"));
            }
        } else if (jsonStr.contains("```")) {
            jsonStr = jsonStr.substring(jsonStr.indexOf("```") + 3);
            if (jsonStr.contains("```")) {
                jsonStr = jsonStr.substring(0, jsonStr.indexOf("```"));
            }
        }
        
        int startIdx = jsonStr.indexOf('[');
        int endIdx = jsonStr.lastIndexOf(']');
        if (startIdx != -1 && endIdx != -1 && endIdx > startIdx) {
            jsonStr = jsonStr.substring(startIdx, endIdx + 1);
        }
        
        return jsonStr.trim();
    }
}
