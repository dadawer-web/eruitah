package com.chat.ai.model;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.io.Serializable;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class AiTask implements Serializable {
    
    private static final long serialVersionUID = 1L;
    
    public enum TaskType {
        SUMMARY,
        CHAT_REPLY
    }
    
    private Long groupId;
    private Integer replyTo;
    private String replyToName;
    private TaskType taskType;
    private String triggerMessage;
    
    public static AiTask summaryTask(Long groupId, Integer replyTo, String replyToName) {
        return new AiTask(groupId, replyTo, replyToName, TaskType.SUMMARY, null);
    }
    
    public static AiTask summaryTask(Long groupId, Integer replyTo, String replyToName, String triggerMessage) {
        return new AiTask(groupId, replyTo, replyToName, TaskType.SUMMARY, triggerMessage);
    }
}
