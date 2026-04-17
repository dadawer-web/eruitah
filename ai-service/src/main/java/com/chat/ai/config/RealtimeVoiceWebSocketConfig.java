package com.chat.ai.config;

import com.chat.ai.websocket.RealtimeVoiceWebSocketHandler;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration
@EnableWebSocket
public class RealtimeVoiceWebSocketConfig implements WebSocketConfigurer {

    private final RealtimeVoiceWebSocketHandler voiceWebSocketHandler;

    public RealtimeVoiceWebSocketConfig(RealtimeVoiceWebSocketHandler voiceWebSocketHandler) {
        this.voiceWebSocketHandler = voiceWebSocketHandler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(voiceWebSocketHandler, "/api/voice/stream")
            .setAllowedOrigins("*");
    }
}
