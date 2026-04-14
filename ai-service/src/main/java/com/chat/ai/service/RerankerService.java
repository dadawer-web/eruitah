package com.chat.ai.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.document.Document;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

@Slf4j
@Service
public class RerankerService {

    private final WebClient rerankWebClient;
    private final ObjectMapper objectMapper;
    private final String apiKey;
    private final String model;
    private final int topN;

    public RerankerService(
            ObjectMapper objectMapper,
            @Value("${reranker.siliconflow.api-key}") String apiKey,
            @Value("${reranker.siliconflow.base-url}") String baseUrl,
            @Value("${reranker.siliconflow.model:BAAI/bge-reranker-v2-m3}") String model,
            @Value("${reranker.siliconflow.top-n:3}") int topN) {
        this.objectMapper = objectMapper;
        this.apiKey = apiKey;
        this.model = model;
        this.topN = topN;
        this.rerankWebClient = WebClient.builder()
            .baseUrl(baseUrl)
            .defaultHeader(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
            .codecs(configurer -> configurer.defaultCodecs().maxInMemorySize(10 * 1024 * 1024))
            .build();
        log.info("[Reranker] 初始化完成, model: {}, topN: {}, baseUrl: {}", model, topN, baseUrl);
    }

    public List<Document> rerank(String query, List<Document> documents) {
        if (documents == null || documents.isEmpty()) {
            log.warn("[Reranker] 输入文档为空，跳过重排");
            return List.of();
        }

        log.info("[Reranker] 开始重排, query: {}, 候选文档数: {}", query, documents.size());

        List<String> docContents = new ArrayList<>();
        for (Document doc : documents) {
            String content = doc.getContent();
            if (content != null && !content.isBlank()) {
                docContents.add(content.length() > 2000 ? content.substring(0, 2000) : content);
            }
        }

        if (docContents.isEmpty()) {
            log.warn("[Reranker] 所有文档内容为空，返回原始文档前{}个", topN);
            return documents.subList(0, Math.min(topN, documents.size()));
        }

        try {
            Map<String, Object> requestBody = Map.of(
                "model", model,
                "query", query,
                "documents", docContents,
                "top_n", Math.min(topN, docContents.size())
            );

            String rawResponse = rerankWebClient.post()
                .uri("/v1/rerank")
                .header("Authorization", "Bearer " + apiKey)
                .bodyValue(requestBody)
                .retrieve()
                .bodyToMono(String.class)
                .block();

            log.debug("[Reranker] API原始响应长度: {}", rawResponse != null ? rawResponse.length() : 0);

            if (rawResponse == null || rawResponse.isBlank()) {
                log.warn("[Reranker] 重排API返回空结果，返回原始文档前{}个", topN);
                return documents.subList(0, Math.min(topN, documents.size()));
            }

            JsonNode root = objectMapper.readTree(rawResponse);
            JsonNode resultsNode = root.get("results");
            
            if (resultsNode == null || !resultsNode.isArray()) {
                log.warn("[Reranker] 响应中没有results数组，返回原始文档前{}个", topN);
                return documents.subList(0, Math.min(topN, documents.size()));
            }

            List<Document> rerankedDocs = new ArrayList<>();
            for (JsonNode result : resultsNode) {
                int index = result.has("index") ? result.get("index").asInt() : -1;
                double score = result.has("relevance_score") ? result.get("relevance_score").asDouble() : 0.0;
                
                if (index >= 0 && index < documents.size()) {
                    Document doc = documents.get(index);
                    doc.getMetadata().put("rerank_score", score);
                    doc.getMetadata().put("rerank_position", rerankedDocs.size() + 1);
                    rerankedDocs.add(doc);
                }
            }

            log.info("[Reranker] 重排完成, 输出 {} 个文档", rerankedDocs.size());
            for (int i = 0; i < rerankedDocs.size(); i++) {
                Document doc = rerankedDocs.get(i);
                String content = doc.getContent();
                String preview = content != null && content.length() > 150 
                    ? content.substring(0, 150).replace("\n", " ") + "..." 
                    : (content != null ? content.replace("\n", " ") : "");
                log.info("[Reranker] Top-{}: score={}, preview={}",
                    i + 1,
                    doc.getMetadata().get("rerank_score"),
                    preview);
            }

            return rerankedDocs;

        } catch (WebClientResponseException e) {
            log.error("[Reranker] API调用失败, status={}, body={}", e.getStatusCode(), e.getResponseBodyAsString());
            return documents.subList(0, Math.min(topN, documents.size()));
        } catch (Exception e) {
            log.error("[Reranker] 重排失败，降级返回原始文档: {}", e.getMessage());
            return documents.subList(0, Math.min(topN, documents.size()));
        }
    }
}
