package com.chat.ai.config;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonPropertyDescription;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Description;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.RestTemplate;

import java.util.function.Function;

@Configuration
public class WebSearchToolConfig {

    @Value("${serper.api-key}")
    private String serperApiKey;

    @Value("${serper.base-url}")
    private String serperBaseUrl;

    public record SearchRequest(
            @JsonProperty(required = true, value = "query")
            @JsonPropertyDescription("必须提供。要联网搜索的关键词或完整句子，例如：'北邮2024年考研分数线'")
            String query
    ) {}

    @Bean
    @Description("联网搜索工具。当你需要实时的互联网资讯、最新分数线等超出你知识库的问题时，必须调用此工具。必须严格按照格式传入包含 'query' 字段的 JSON 对象。")
    public Function<SearchRequest, String> webSearchTool() {
        return request -> {
            System.out.println("大模型触发了联网搜索，搜索词：" + request.query());
            
            if (request.query() == null || request.query().trim().isEmpty()) {
                return "搜索失败，没有提供搜索词。";
            }
            
            try {
                RestTemplate restTemplate = new RestTemplate();
                HttpHeaders headers = new HttpHeaders();
                headers.setContentType(MediaType.APPLICATION_JSON);
                headers.set("X-API-KEY", serperApiKey);

                String jsonBody = "{\"q\":\"" + request.query().replace("\"", "\\\"") + "\"}";
                HttpEntity<String> entity = new HttpEntity<>(jsonBody, headers);

                ResponseEntity<String> response = restTemplate.postForEntity(
                    serperBaseUrl + "/search",
                    entity,
                    String.class
                );
                
                return "搜索结果：" + response.getBody();
            } catch (Exception e) {
                return "搜索失败，无法获取最新信息。错误：" + e.getMessage();
            }
        };
    }
}
