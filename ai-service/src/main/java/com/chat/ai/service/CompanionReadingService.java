package com.chat.ai.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

@Slf4j
@Service
@RequiredArgsConstructor
public class CompanionReadingService {

    private final GraphRetrievalService graphRetrievalService;
    private final VoiceChatService voiceChatService;
    @Qualifier("fastChatClient")
    private final ChatClient fastChatClient;

    public CompanionReadResult companionRead(Integer userId, String selectedText) {
        log.info("伴读请求: userId={}, text长度={}", userId, selectedText.length());

        if (selectedText == null || selectedText.trim().isEmpty()) {
            return CompanionReadResult.error("划选文本不能为空");
        }

        try {
            String graphContext = retrieveGraphContext(selectedText);
            log.info("图谱检索完成, 上下文长度: {}", graphContext.length());

            String explanation = generateExplanation(selectedText, graphContext);
            log.info("讲解生成完成, 长度: {}", explanation.length());

            String audioUrl = synthesizeAudio(explanation);
            log.info("语音合成完成: {}", audioUrl);

            return CompanionReadResult.success(audioUrl, explanation);

        } catch (Exception e) {
            log.error("伴读处理失败: userId={}", userId, e);
            return CompanionReadResult.error("处理失败: " + e.getMessage());
        }
    }

    private String retrieveGraphContext(String query) {
        try {
            List<String> concepts = graphRetrievalService.searchConcepts(query);
            if (concepts == null || concepts.isEmpty()) {
                log.info("图谱未检索到相关概念, query={}", query);
                return "暂无相关知识点";
            }

            String context = concepts.stream()
                .limit(5)
                .collect(Collectors.joining("；"));

            log.info("图谱检索到 {} 个相关概念: {}", concepts.size(), context);
            return context;

        } catch (Exception e) {
            log.warn("图谱检索异常, 降级为空上下文", e);
            return "暂无相关知识点";
        }
    }

    private String generateExplanation(String selectedText, String graphContext) {
        String prompt = String.format(
            "用户在阅读408教材时对以下文字不理解：【%s】。" +
            "请结合以下知识库上下文：【%s】，" +
            "用通俗、口语化的'学长'语气进行100字左右的精简讲解。" +
            "不要使用markdown格式，用纯文本。" +
            "开头用'同学你好~'，语气亲切自然。",
            selectedText, graphContext
        );

        try {
            String result = fastChatClient.prompt()
                .system("你是「温柔学长」，一位已经成功上岸408考研的热心学长。擅长用生活中的通俗例子来解释抽象的计算机概念。回复控制在100字左右，用纯文本，不要markdown。")
                .user(prompt)
                .call()
                .content();

            if (result == null || result.trim().isEmpty()) {
                return "这个概念确实不太好理解，建议多看看教材原文，结合例题来消化~";
            }

            return result.trim();
        } catch (Exception e) {
            log.error("LLM调用失败，降级返回默认提示", e);
            return "同学你好~ 这个知识点确实有点抽象，建议结合教材中的例题来理解。如果还是不太明白，可以试试换个角度，或者和同学讨论一下，往往会有新的收获哦~";
        }
    }

    private String synthesizeAudio(String text) {
        try {
            String audioUrl = voiceChatService.synthesizeSpeechPublic(text);
            if (audioUrl == null || audioUrl.isEmpty()) {
                log.warn("TTS合成返回空URL，将仅返回文本讲解");
            }
            return audioUrl;
        } catch (Exception e) {
            log.warn("TTS合成失败，将仅返回文本讲解", e);
            return null;
        }
    }

    public record CompanionReadResult(
        String audioUrl,
        String explanationText,
        boolean success,
        String error
    ) {
        public static CompanionReadResult success(String audioUrl, String explanationText) {
            return new CompanionReadResult(audioUrl, explanationText, true, null);
        }

        public static CompanionReadResult error(String error) {
            return new CompanionReadResult(null, null, false, error);
        }
    }
}
