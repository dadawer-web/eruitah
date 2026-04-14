package com.chat.ai.service;

import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;

@Slf4j
@Service
public class QueryRewriteService {

    private final ObjectProvider<ChatClient.Builder> chatClientBuilderProvider;

    private static final String QUERY_REWRITE_PROMPT = """
        你是一个查询改写专家。你的任务是将用户的简短或模糊的查询，改写为多个具体的子问题，以便在知识库中进行更精准的检索。
        
        规则：
        1. 将用户的查询拆解为2-4个具体的子问题
        2. 每个子问题应该是一个独立的、具体的技术问题
        3. 子问题应该覆盖用户原始查询的不同方面
        4. 子问题应该使用专业术语，而非口语化表达
        5. 如果用户查询已经足够具体，可以只输出1-2个改写后的问题
        
        示例：
        - 用户输入："考考我网络" → 输出：1. TCP拥塞控制机制 2. HTTP状态码分类 3. IP分片与重组机制
        - 用户输入："操作系统进程" → 输出：1. 进程与线程的区别 2. 进程调度算法 3. 进程间通信方式
        - 用户输入："TCP粘包" → 输出：1. TCP粘包产生原因 2. TCP粘包解决方案
        
        请直接输出子问题，每行一个，编号格式为"1. 2. 3."，不要输出任何其他内容。
        """;

    public QueryRewriteService(ObjectProvider<ChatClient.Builder> chatClientBuilderProvider) {
        this.chatClientBuilderProvider = chatClientBuilderProvider;
    }

    public List<String> rewriteQuery(String originalQuery) {
        log.info("[QueryRewrite] 原始查询: {}", originalQuery);

        ChatClient rewriteClient = chatClientBuilderProvider.getObject().build();

        String response = rewriteClient.prompt()
            .system(QUERY_REWRITE_PROMPT)
            .user(originalQuery)
            .call()
            .content();

        List<String> subQueries = parseSubQueries(response);
        subQueries.add(0, originalQuery);

        log.info("[QueryRewrite] 改写结果: {} 个子问题 -> {}", subQueries.size(), subQueries);
        return subQueries;
    }

    private List<String> parseSubQueries(String response) {
        List<String> queries = new ArrayList<>();
        String[] lines = response.trim().split("\n");

        for (String line : lines) {
            String trimmed = line.trim();
            if (trimmed.isEmpty()) continue;

            String cleaned = trimmed.replaceAll("^\\d+\\.\\s*", "").trim();
            if (!cleaned.isEmpty()) {
                queries.add(cleaned);
            }
        }

        return queries;
    }
}
