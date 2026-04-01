package com.chat.ai.controller;

import com.chat.ai.service.GroupChatService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@Slf4j
@RestController
@RequestMapping("/api/group")
@RequiredArgsConstructor
public class GroupChatController {
    
    private final GroupChatService groupChatService;
    
    @PostMapping("/message")
    public ResponseEntity<GroupChatResponse> receiveMessage(@RequestBody GroupMessageRequest request) {
        log.info("Received group message: groupId={}, senderId={}, senderName={}, content={}", 
            request.getGroupId(), request.getSenderId(), request.getSenderName(), request.getContent());
        
        if (request.getGroupId() == null) {
            return ResponseEntity.badRequest()
                .body(GroupChatResponse.error("群组ID不能为空"));
        }
        
        if (request.getContent() == null || request.getContent().trim().isEmpty()) {
            return ResponseEntity.badRequest()
                .body(GroupChatResponse.error("消息内容不能为空", request.getGroupId()));
        }
        
        try {
            if (groupChatService.isSummaryRequest(request.getContent())) {
                log.info("Detected summary request for group: {}", request.getGroupId());
                
                groupChatService.submitSummaryTask(
                    request.getGroupId(),
                    request.getSenderId(),
                    request.getSenderName(),
                    request.getContent()
                );
                
                return ResponseEntity.ok(GroupChatResponse.success(
                    "摘要任务已提交，AI正在处理中，结果将通过群消息推送...", 
                    request.getGroupId()
                ));
            } else {
                return ResponseEntity.ok(GroupChatResponse.success(
                    "消息已由C++网关存储到Redis", 
                    request.getGroupId()
                ));
            }
            
        } catch (Exception e) {
            log.error("Error processing group message", e);
            return ResponseEntity.internalServerError()
                .body(GroupChatResponse.error("处理消息时发生错误: " + e.getMessage(), request.getGroupId()));
        }
    }
    
    @PostMapping("/summary")
    public ResponseEntity<GroupChatResponse> generateSummary(
            @RequestParam Long groupId,
            @RequestParam(defaultValue = "100") int messageCount) {
        log.info("Generating sync summary for group: {}, messageCount: {}", groupId, messageCount);
        
        if (groupId == null) {
            return ResponseEntity.badRequest()
                .body(GroupChatResponse.error("群组ID不能为空"));
        }
        
        try {
            String summary = groupChatService.generateSummarySync(groupId, messageCount);
            return ResponseEntity.ok(GroupChatResponse.success(summary, groupId));
            
        } catch (Exception e) {
            log.error("Error generating summary for group: {}", groupId, e);
            return ResponseEntity.internalServerError()
                .body(GroupChatResponse.error("生成摘要时发生错误: " + e.getMessage(), groupId));
        }
    }
    
    @PostMapping("/task")
    public ResponseEntity<GroupChatResponse> submitSummaryTask(
            @RequestParam Long groupId,
            @RequestParam Integer replyTo,
            @RequestParam(required = false) String replyToName) {
        log.info("Submitting summary task for group: {}, replyTo: {}", groupId, replyTo);
        
        if (groupId == null) {
            return ResponseEntity.badRequest()
                .body(GroupChatResponse.error("群组ID不能为空"));
        }
        
        if (replyTo == null) {
            return ResponseEntity.badRequest()
                .body(GroupChatResponse.error("回复目标用户ID不能为空", groupId));
        }
        
        try {
            groupChatService.submitSummaryTask(groupId, replyTo, replyToName, null);
            return ResponseEntity.ok(GroupChatResponse.success("摘要任务已提交", groupId));
            
        } catch (Exception e) {
            log.error("Error submitting summary task for group: {}", groupId, e);
            return ResponseEntity.internalServerError()
                .body(GroupChatResponse.error("提交任务时发生错误: " + e.getMessage(), groupId));
        }
    }
    
    @GetMapping("/info")
    public ResponseEntity<GroupChatResponse> getGroupInfo(@RequestParam Long groupId) {
        log.info("Getting info for group: {}", groupId);
        
        if (groupId == null) {
            return ResponseEntity.badRequest()
                .body(GroupChatResponse.error("群组ID不能为空"));
        }
        
        try {
            GroupChatService.GroupChatSummary summary = groupChatService.getGroupChatInfo(groupId);
            return ResponseEntity.ok(GroupChatResponse.success("获取成功", groupId, summary));
            
        } catch (Exception e) {
            log.error("Error getting group info: {}", groupId, e);
            return ResponseEntity.internalServerError()
                .body(GroupChatResponse.error("获取群组信息时发生错误: " + e.getMessage(), groupId));
        }
    }
    
    @DeleteMapping("/messages")
    public ResponseEntity<GroupChatResponse> clearMessages(@RequestParam Long groupId) {
        log.info("Clearing messages for group: {}", groupId);
        
        if (groupId == null) {
            return ResponseEntity.badRequest()
                .body(GroupChatResponse.error("群组ID不能为空"));
        }
        
        try {
            groupChatService.clearGroupMessages(groupId);
            return ResponseEntity.ok(GroupChatResponse.success("群聊记录已清除", groupId));
            
        } catch (Exception e) {
            log.error("Error clearing messages for group: {}", groupId, e);
            return ResponseEntity.internalServerError()
                .body(GroupChatResponse.error("清除记录时发生错误: " + e.getMessage(), groupId));
        }
    }
}
