package com.chat.ai.config;

import com.chat.ai.memory.RedisChatMemory;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.client.advisor.MessageChatMemoryAdvisor;
import org.springframework.ai.chat.memory.ChatMemory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ChatClientConfig {

    @Bean
    @Qualifier("smartChatClient")
    public ChatClient smartChatClient(ChatClient.Builder builder, ChatMemory chatMemory) {
        return builder
            .defaultAdvisors(new MessageChatMemoryAdvisor(chatMemory))
            .defaultFunctions("webSearchTool", "cppCompilerTool")
            .build();
    }

    @Bean
    @Qualifier("fastChatClient")
    public ChatClient fastChatClient(ChatClient.Builder builder, ChatMemory chatMemory) {
        return builder
            .defaultAdvisors(new MessageChatMemoryAdvisor(chatMemory))
            .build();
    }
}
