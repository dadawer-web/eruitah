package com.chat.ai.controller;

import com.chat.ai.service.VoiceChatService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

@Slf4j
@RestController
@RequestMapping("/api/voice")
@RequiredArgsConstructor
public class VoiceController {

    private final VoiceChatService voiceChatService;
    private final String audioStoragePath = "/tmp/audio";
    private final String audioUrlPrefix = "http://localhost:8081/audio";

    @PostMapping("/upload")
    public ResponseEntity<Map<String, Object>> uploadVoice(
            @RequestParam("audio") MultipartFile file,
            @RequestParam("userId") Integer userId,
            @RequestParam("toId") Integer toId,
            @RequestParam("duration") Integer duration) {
        
        log.info("收到语音上传请求: userId={}, toId={}, duration={}s, fileSize={}", 
            userId, toId, duration, file.getSize());
        
        if (file.isEmpty()) {
            return ResponseEntity.badRequest()
                .body(Map.of("success", false, "message", "音频文件为空"));
        }
        
        try {
            Path storageDir = Paths.get(audioStoragePath);
            if (!Files.exists(storageDir)) {
                Files.createDirectories(storageDir);
            }
            
            String fileName = UUID.randomUUID().toString() + ".wav";
            Path filePath = storageDir.resolve(fileName);
            file.transferTo(filePath.toFile());
            
            String voiceUrl = audioUrlPrefix + "/" + fileName;
            
            log.info("语音文件保存成功: path={}, url={}", filePath, voiceUrl);
            
            return ResponseEntity.ok(Map.of(
                "success", true,
                "url", voiceUrl,
                "fileName", fileName,
                "duration", duration
            ));
            
        } catch (IOException e) {
            log.error("保存语音文件失败", e);
            return ResponseEntity.internalServerError()
                .body(Map.of("success", false, "message", "保存文件失败: " + e.getMessage()));
        }
    }

    @PostMapping("/chat")
    public ResponseEntity<Map<String, Object>> voiceChat(
            @RequestParam("audioUrl") String audioUrl,
            @RequestParam("userId") Integer userId,
            @RequestParam("botId") Integer botId,
            @RequestParam(value = "duration", defaultValue = "0") Integer duration) {
        
        log.info("收到语音聊天请求: userId={}, botId={}, audioUrl={}, duration={}s", 
            userId, botId, audioUrl, duration);
        
        try {
            VoiceChatService.VoiceChatResult result = voiceChatService.handleVoiceChat(
                audioUrl, userId, botId, duration
            );
            
            return ResponseEntity.ok(Map.of(
                "success", true,
                "textReply", result.textReply(),
                "voiceUrl", result.voiceUrl(),
                "duration", result.duration()
            ));
            
        } catch (Exception e) {
            log.error("语音聊天处理失败", e);
            return ResponseEntity.internalServerError()
                .body(Map.of("success", false, "message", "处理失败: " + e.getMessage()));
        }
    }

    @GetMapping("/health")
    public ResponseEntity<String> health() {
        return ResponseEntity.ok("Voice Service is running");
    }
}
