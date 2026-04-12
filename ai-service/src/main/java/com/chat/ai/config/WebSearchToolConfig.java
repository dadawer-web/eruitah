package com.chat.ai.config;

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

    public record SearchRequest(String query) {}

    @Bean
    @Description("这是一个联网搜索工具。当你被问及实时的互联网资讯、最新分数线等超出你知识库的问题时，必须调用此工具。传入搜索词，我会返回网上的最新搜索结果。")
    public Function<SearchRequest, String> webSearchTool() {
        return request -> {
            System.out.println("大模型触发了联网搜索，搜索词：" + request.query());
            
            try {
                RestTemplate restTemplate = new RestTemplate();
                HttpHeaders headers = new HttpHeaders();
                headers.setContentType(MediaType.APPLICATION_JSON);
                headers.set("X-API-KEY", serperApiKey);

                String jsonBody = "{\"q\":\"" + request.query() + "\"}";
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
