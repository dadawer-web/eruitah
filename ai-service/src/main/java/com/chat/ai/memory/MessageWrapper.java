package com.chat.ai.memory;

import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;

import org.springframework.ai.chat.messages.AssistantMessage;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.messages.SystemMessage;
import org.springframework.ai.chat.messages.UserMessage;

import java.io.Serializable;

@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "messageType"
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = MessageWrapper.UserMessageWrapper.class, name = "user"),
    @JsonSubTypes.Type(value = MessageWrapper.AssistantMessageWrapper.class, name = "assistant"),
    @JsonSubTypes.Type(value = MessageWrapper.SystemMessageWrapper.class, name = "system")
})
public sealed interface MessageWrapper extends Serializable permits 
    MessageWrapper.UserMessageWrapper,
    MessageWrapper.AssistantMessageWrapper,
    MessageWrapper.SystemMessageWrapper {
    
    Message toMessage();
    
    static MessageWrapper fromMessage(Message message) {
        if (message instanceof UserMessage userMessage) {
            return new UserMessageWrapper(userMessage.getContent());
        } else if (message instanceof AssistantMessage assistantMessage) {
            return new AssistantMessageWrapper(assistantMessage.getContent());
        } else if (message instanceof SystemMessage systemMessage) {
            return new SystemMessageWrapper(systemMessage.getContent());
        }
        throw new IllegalArgumentException("Unsupported message type: " + message.getClass());
    }
    
    record UserMessageWrapper(String content) implements MessageWrapper {
        @Override
        public Message toMessage() {
            return new UserMessage(content);
        }
    }
    
    record AssistantMessageWrapper(String content) implements MessageWrapper {
        @Override
        public Message toMessage() {
            return new AssistantMessage(content);
        }
    }
    
    record SystemMessageWrapper(String content) implements MessageWrapper {
        @Override
        public Message toMessage() {
            return new SystemMessage(content);
        }
    }
}
