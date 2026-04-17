package com.bridge.service.impl;

import com.bridge.proto.ChatProto;
import com.bridge.service.ChatService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.HashMap;
import java.util.Map;

public class AIChatService implements ChatService {

    private static final Logger logger = LoggerFactory.getLogger(AIChatService.class);

    private static final Map<Integer, String> BOT_NAMES = new HashMap<>();
    private static final Map<Integer, String> BOT_PROMPTS = new HashMap<>();

    static {
        BOT_NAMES.put(10000, "旗舰大师");
        BOT_NAMES.put(10001, "严厉导师");
        BOT_NAMES.put(10002, "温柔学长");
        BOT_NAMES.put(10003, "代码审查员");
        BOT_NAMES.put(10004, "严厉大Boss");
        BOT_NAMES.put(10005, "慈祥老教授");
        BOT_NAMES.put(10006, "挑刺狂魔");
        BOT_NAMES.put(10007, "解题大王");
        BOT_NAMES.put(10008, "语音小助手");
        BOT_NAMES.put(10009, "心理委员");

        BOT_PROMPTS.put(10000, "你是旗舰大师，408计算机考研的终极辅导专家。回复控制在300字以内，纯文本。");
        BOT_PROMPTS.put(10001, "你是严厉导师，一丝不苟。回复控制在150字以内，纯文本。");
        BOT_PROMPTS.put(10002, "你是温柔学长，耐心温暖。回复控制在150字以内，纯文本。");
        BOT_PROMPTS.put(10003, "你是代码审查员，高冷极客。回复控制在100字以内，纯文本。");
        BOT_PROMPTS.put(10008, "你是语音小助手，友好简洁。回复控制在100字以内，纯文本。");
    }

    @Override
    public ChatProto.ChatResponse chat(ChatProto.ChatRequest request) {
        logger.info("Processing chat request: userId={}, botId={}({}), message={}",
                request.getUserId(), request.getBotId(),
                BOT_NAMES.getOrDefault(request.getBotId(), "AI助手"),
                request.getMessage().substring(0, Math.min(50, request.getMessage().length())));

        String botName = BOT_NAMES.getOrDefault(request.getBotId(), "AI助手");
        String reply = processWithAI(request.getMessage(), request.getUserId(), request.getBotId());

        ChatProto.ChatResponse.Builder responseBuilder = ChatProto.ChatResponse.newBuilder()
                .setUserId(request.getUserId())
                .setBotId(request.getBotId())
                .setBotName(botName)
                .setMessage(reply)
                .setSessionId(request.getSessionId())
                .setSuccess(true)
                .setMsgType(6)
                .setTimestamp(System.currentTimeMillis());

        responseBuilder.putMetadata("model", "qwen3.5-plus");
        responseBuilder.putMetadata("source", "protobuf-rpc-bridge");

        ChatProto.ChatResponse response = responseBuilder.build();

        logger.info("Chat response generated for user={}, bot={}", request.getUserId(), botName);
        return response;
    }

    @Override
    public ChatProto.GroupChatResponse groupChat(ChatProto.GroupChatRequest request) {
        logger.info("Processing group chat request: groupId={}, senderId={}",
                request.getGroupId(), request.getSenderId());

        String reply = processWithAI(request.getContent(), request.getSenderId(), 10000);

        ChatProto.GroupChatResponse response = ChatProto.GroupChatResponse.newBuilder()
                .setGroupId(request.getGroupId())
                .setBotId(10000)
                .setBotName("旗舰大师")
                .setContent(reply)
                .setSuccess(true)
                .setTimestamp(System.currentTimeMillis())
                .build();

        return response;
    }

    private String processWithAI(String message, int userId, int botId) {
        String lowerMessage = message.toLowerCase();

        if (lowerMessage.contains("hello") || lowerMessage.contains("hi") || lowerMessage.contains("你好")) {
            return "你好！我是" + BOT_NAMES.getOrDefault(botId, "AI助手") + "，有什么可以帮你的吗？";
        } else if (lowerMessage.contains("数据结构")) {
            return "数据结构是408考试的重点科目，常考的有线性表、树、图、查找和排序。你想了解哪个部分？";
        } else if (lowerMessage.contains("操作系统")) {
            return "操作系统主要考察进程管理、内存管理、文件系统和IO管理。进程同步和死锁是高频考点。";
        } else if (lowerMessage.contains("计算机网络")) {
            return "计网重点在TCP/IP协议栈，特别是三次握手四次挥手、拥塞控制、HTTP协议等。";
        } else if (lowerMessage.contains("组成原理") || lowerMessage.contains("计组")) {
            return "计组重点在数据表示、运算器、存储系统和指令系统。流水线是常考大题。";
        } else if (lowerMessage.contains("代码") || lowerMessage.contains("code")) {
            return "请把代码发给我，我来帮你审查。注意检查边界条件和内存泄漏。";
        } else if (lowerMessage.contains("bye") || lowerMessage.contains("再见")) {
            return "再见！祝你考研顺利！";
        } else {
            return String.format(
                    "[Protobuf RPC Bridge] 收到你的消息：\"%s\"。这是模拟AI回复。" +
                    "在生产环境中，这里会对接你的 ai-service 后端（Spring AI + 通义千问）。",
                    message.substring(0, Math.min(30, message.length()))
            );
        }
    }
}
