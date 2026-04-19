package com.chat.ai.config;

import com.chat.ai.config.WebSearchToolConfig.SearchRequest;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.model.function.FunctionCallback;
import org.springframework.ai.model.function.FunctionCallbackWrapper;
import org.springframework.ai.openai.OpenAiChatModel;
import org.springframework.ai.openai.OpenAiChatOptions;
import org.springframework.ai.openai.api.OpenAiApi;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

import java.util.function.Function;

@Configuration
public class ChatClientConfig {

    @Value("${spring.ai.openai.api-key}")
    private String apiKey;

    @Value("${spring.ai.openai.base-url}")
    private String baseUrl;

    @Value("${spring.ai.openai.chat.options.model}")
    private String model;

    @Value("${spring.ai.openai.chat.options.temperature}")
    private Double temperature;

    @Bean
    @Primary
    public OpenAiApi standardOpenAiApi() {
        return new OpenAiApi(baseUrl, apiKey);
    }

    @Bean
    @Primary
    public OpenAiChatOptions standardChatOptions() {
        return OpenAiChatOptions.builder()
            .withModel(model)
            .withTemperature(temperature)
            .build();
    }

    @Bean
    @Primary
    public OpenAiChatModel standardChatModel() {
        return new OpenAiChatModel(standardOpenAiApi(), standardChatOptions());
    }

    @Bean
    @Primary
    @Qualifier("smartChatClient")
    public ChatClient smartChatClient(
            @Qualifier("webSearchTool") Function<SearchRequest, String> webSearchTool,
            @Qualifier("cppCompilerToolCallback") FunctionCallback cppCompilerToolCallback) {
        
        FunctionCallback webSearchCallback = FunctionCallbackWrapper.builder(webSearchTool)
            .withName("webSearchTool")
            .withDescription("联网搜索工具。当你需要实时的互联网资讯、最新分数线等超出你知识库的问题时，必须调用此工具。必须严格按照格式传入包含 'query' 字段的 JSON 对象。")
            .withInputType(SearchRequest.class)
            .build();
        
        return ChatClient.builder(standardChatModel())
            .defaultFunctions(webSearchCallback, cppCompilerToolCallback)
            .build();
    }

    @Bean
    @Qualifier("fastChatClient")
    public ChatClient fastChatClient() {
        return ChatClient.builder(standardChatModel())
            .build();
    }
}
