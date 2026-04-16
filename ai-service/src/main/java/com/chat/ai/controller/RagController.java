package com.chat.ai.controller;

import com.chat.ai.config.annotation.RateLimit;
import com.chat.ai.service.RagService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import reactor.core.publisher.Mono;

import java.util.HashMap;
import java.util.Map;

@Slf4j
@RestController
@RequestMapping("/api/rag")
@RequiredArgsConstructor
public class RagController {

    private final RagService ragService;

    @PostMapping(value = "/upload", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @RateLimit(dimension = RateLimit.Dimension.USER, count = 10, interval = 1, timeUnit = RateLimit.TimeUnit.MINUTES)
    @RateLimit(dimension = RateLimit.Dimension.IP, count = 20, interval = 1, timeUnit = RateLimit.TimeUnit.MINUTES)
    public Mono<ResponseEntity<Map<String, Object>>> uploadDocument(
            @RequestPart("file") MultipartFile file) {

        String filename = file.getOriginalFilename();
        if (filename == null || filename.isBlank()) {
            log.warn("上传的文件名为空");
            return Mono.just(ResponseEntity.badRequest()
                .body(createErrorMap("上传文件名不能为空")));
        }

        if (file.isEmpty()) {
            log.warn("上传的文件为空");
            return Mono.just(ResponseEntity.badRequest()
                .body(createErrorMap("上传文件不能为空")));
        }

        log.info("收到RAG文档上传请求: filename={}, size={}KB", filename, file.getSize() / 1024);

        return ragService.uploadAndIndexDocument(file)
            .<ResponseEntity<Map<String, Object>>>map(chunkCount -> {
                log.info("文档 [{}] 处理完成，共生成 {} 个知识块", filename, chunkCount);
                Map<String, Object> result = new HashMap<>();
                result.put("success", true);
                result.put("message", "知识库文档上传并索引成功");
                result.put("filename", filename);
                result.put("chunkCount", chunkCount);
                return ResponseEntity.ok(result);
            })
            .onErrorResume(IllegalArgumentException.class, e -> {
                log.warn("文件格式不支持: {}", e.getMessage());
                return Mono.just(ResponseEntity.badRequest()
                    .body(createErrorMap(e.getMessage())));
            })
            .onErrorResume(Exception.class, e -> {
                log.error("处理RAG文档上传失败: filename={}", filename, e);
                return Mono.just(ResponseEntity.internalServerError()
                    .body(createErrorMap("文档处理失败: " + e.getMessage())));
            });
    }

    private Map<String, Object> createErrorMap(String error) {
        Map<String, Object> map = new HashMap<>();
        map.put("success", false);
        map.put("error", error);
        return map;
    }
}
