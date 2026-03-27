package com.chat.ai.controller;

import com.chat.ai.service.AiChatService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Flux;

@Slf4j
@RestController
@RequestMapping("/api/ai")
@RequiredArgsConstructor
public class AiStreamController {

    private final AiChatService aiChatService;

    @GetMapping(value = "/stream-chat", produces = MediaType.TEXT_PLAIN_VALUE)
    public Flux<String> getAiStream(
            @RequestParam String message,
            @RequestParam(required = false) String sessionId) {
        log.info("Received stream chat request: sessionId={}, message={}", sessionId, message);

        return aiChatService.streamChat(message, 0, "用户", sessionId);
    }
}
