package com.chat.ai.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.document.Document;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.stereotype.Service;
import redis.clients.jedis.JedisPooled;
import redis.clients.jedis.search.Query;
import redis.clients.jedis.search.SearchResult;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Slf4j
@Service
@RequiredArgsConstructor
public class HybridRetrievalService {

    private final VectorStore vectorStore;
    private final JedisPooled jedisPooled;

    private static final String INDEX_NAME = "rag-knowledge-index";
    private static final String KEY_PREFIX = "rag:doc:";
    private static final int BM25_TOP_K = 10;

    public List<Document> hybridSearch(List<String> subQueries) {
        log.info("[HybridRetrieval] 开始混合召回，子问题数: {}", subQueries.size());

        LinkedHashMap<String, Document> mergedDocs = new LinkedHashMap<>();

        for (String query : subQueries) {
            log.info("[HybridRetrieval] 处理子问题: {}", query);

            List<Document> vectorResults = vectorSearch(query);
            log.info("[HybridRetrieval] 向量检索召回 {} 个文档", vectorResults.size());
            for (int i = 0; i < Math.min(3, vectorResults.size()); i++) {
                String preview = vectorResults.get(i).getContent();
                log.info("[HybridRetrieval] 向量文档[{}]: {}", i, 
                    preview.length() > 100 ? preview.substring(0, 100) + "..." : preview);
            }

            List<Document> bm25Results = bm25Search(query);
            log.info("[HybridRetrieval] BM25检索召回 {} 个文档", bm25Results.size());

            for (Document doc : vectorResults) {
                String docKey = buildDocKey(doc);
                if (!mergedDocs.containsKey(docKey)) {
                    doc.getMetadata().putIfAbsent("retrieval_source", "vector");
                    mergedDocs.put(docKey, doc);
                }
            }

            for (Document doc : bm25Results) {
                String docKey = buildDocKey(doc);
                if (!mergedDocs.containsKey(docKey)) {
                    mergedDocs.put(docKey, doc);
                }
            }
        }

        List<Document> result = new ArrayList<>(mergedDocs.values());
        log.info("[HybridRetrieval] 混合召回完成，去重后共 {} 个候选文档", result.size());
        return result;
    }

    private List<Document> vectorSearch(String query) {
        try {
            return vectorStore.similaritySearch(query);
        } catch (Exception e) {
            log.warn("[HybridRetrieval] 向量检索失败: {}", e.getMessage());
            return List.of();
        }
    }

    private List<Document> bm25Search(String query) {
        try {
            String escapedQuery = escapeFTSQuery(query);
            String ftQuery = "@content:" + escapedQuery;

            Query searchQuery = new Query(ftQuery)
                .limit(0, BM25_TOP_K)
                .setWithScores();

            SearchResult searchResult = jedisPooled.ftSearch(INDEX_NAME, searchQuery);

            List<Document> documents = new ArrayList<>();
            for (redis.clients.jedis.search.Document redisDoc : searchResult.getDocuments()) {
                String content = redisDoc.getString("content");
                if (content == null || content.isBlank()) continue;

                Map<String, Object> metadata = new HashMap<>();
                String id = redisDoc.getId();
                if (id.startsWith(KEY_PREFIX)) {
                    metadata.put("redis_doc_id", id);
                }

                for (Map.Entry<String, Object> entry : redisDoc.getProperties()) {
                    String key = entry.getKey();
                    if (key.equals("content") || key.equals("embedding")) continue;
                    Object value = entry.getValue();
                    if (value != null) {
                        try {
                            String strValue = value.toString();
                            if (key.startsWith("metadata_")) {
                                metadata.put(key.substring("metadata_".length()), strValue);
                            } else {
                                metadata.put(key, strValue);
                            }
                        } catch (Exception e) {
                            log.debug("[HybridRetrieval] 跳过无法转换的字段: {}", key);
                        }
                    }
                }

                metadata.put("retrieval_source", "bm25");
                documents.add(new Document(id, content, metadata));
            }

            return documents;
        } catch (Exception e) {
            log.warn("[HybridRetrieval] BM25检索失败（可能索引尚未建立）: {}", e.getMessage());
            return List.of();
        }
    }

    private String escapeFTSQuery(String query) {
        String escaped = query
            .replace("@", "\\@")
            .replace("|", "\\|")
            .replace("(", "\\(")
            .replace(")", "\\)")
            .replace("{", "\\{")
            .replace("}", "\\}")
            .replace("[", "\\[")
            .replace("]", "\\]")
            .replace("+", "\\+")
            .replace("-", "\\-")
            .replace("*", "\\*")
            .replace("~", "\\~")
            .replace(":", "\\:")
            .replace("\"", "\\\"");

        String[] terms = escaped.split("\\s+");
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < terms.length; i++) {
            if (i > 0) sb.append(" | ");
            sb.append(terms[i]);
        }
        return sb.toString();
    }

    private String buildDocKey(Document doc) {
        String content = doc.getContent();
        if (content.length() > 100) {
            return content.substring(0, 100);
        }
        return content;
    }
}
