package com.chat.ai.config;

import com.chat.ai.rpc.ProtobufRpcClient;
import com.chat.ai.websocket.SimpleIdeWebSocketHandler;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration
@EnableWebSocket
public class SimpleIdeWebSocketConfig implements WebSocketConfigurer {

    private static final Logger log = LoggerFactory.getLogger(SimpleIdeWebSocketConfig.class);

    @Value("${rpc.python.host:127.0.0.1}")
    private String pythonRpcHost;

    @Value("${rpc.python.port:9997}")
    private int pythonRpcPort;

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(simpleIdeWebSocketHandler(), "/ws/simple-ide")
                .setAllowedOrigins("*");
    }

    @Bean
    public ProtobufRpcClient protobufRpcClient() {
        ProtobufRpcClient client = new ProtobufRpcClient(pythonRpcHost, pythonRpcPort);
        client.connect();
        log.info("Python RPC client (IDE) initialized, connecting to {}:{} (auto-reconnect enabled)", pythonRpcHost, pythonRpcPort);
        return client;
    }

    @Bean
    public SimpleIdeWebSocketHandler simpleIdeWebSocketHandler() {
        return new SimpleIdeWebSocketHandler(protobufRpcClient());
    }
}
