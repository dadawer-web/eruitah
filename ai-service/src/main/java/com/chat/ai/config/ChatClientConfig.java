package com.chat.ai.config;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.client.advisor.QuestionAnswerAdvisor;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ChatClientConfig {

    @Bean
    @Qualifier("smartChatClient")
    public ChatClient smartChatClient(ChatClient.Builder builder, VectorStore vectorStore) {
        return builder
            .defaultAdvisors(new QuestionAnswerAdvisor(vectorStore))
            .defaultFunctions("compileCppCode")
            .build();
    }

    @Bean
    @Qualifier("fastChatClient")
    public ChatClient fastChatClient(ChatClient.Builder builder) {
        return builder.build();
    }
}
