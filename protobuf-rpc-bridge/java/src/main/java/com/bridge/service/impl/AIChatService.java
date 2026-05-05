package com.bridge.service.impl;

import com.bridge.proto.ChatProto;
import com.bridge.service.ChatService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

public class AIChatService implements ChatService {

    private static final Logger logger = LoggerFactory.getLogger(AIChatService.class);

    private static final Map<Integer, String> BOT_NAMES = new HashMap<>();
    private final Map<String, ChatProto.SwarmAgentNode> swarmNodes = new ConcurrentHashMap<>();

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
    }

    @Override
    public ChatProto.ChatResponse chat(ChatProto.ChatRequest request) {
        logger.info("Processing chat request: userId={}, botId={}({})",
                request.getUserId(), request.getBotId(),
                BOT_NAMES.getOrDefault(request.getBotId(), "AI助手"));

        String botName = BOT_NAMES.getOrDefault(request.getBotId(), "AI助手");
        String reply = processWithAI(request.getMessage(), request.getUserId(), request.getBotId());

        return ChatProto.ChatResponse.newBuilder()
                .setUserId(request.getUserId())
                .setBotId(request.getBotId())
                .setBotName(botName)
                .setMessage(reply)
                .setSessionId(request.getSessionId())
                .setSuccess(true)
                .setMsgType(6)
                .setTimestamp(System.currentTimeMillis())
                .putMetadata("model", "qwen3.5-plus")
                .putMetadata("source", "protobuf-rpc-bridge")
                .build();
    }

    @Override
    public ChatProto.GroupChatResponse groupChat(ChatProto.GroupChatRequest request) {
        logger.info("Processing group chat request: groupId={}, senderId={}",
                request.getGroupId(), request.getSenderId());

        String reply = processWithAI(request.getContent(), request.getSenderId(), 10000);

        return ChatProto.GroupChatResponse.newBuilder()
                .setGroupId(request.getGroupId())
                .setBotId(10000)
                .setBotName("旗舰大师")
                .setContent(reply)
                .setSuccess(true)
                .setTimestamp(System.currentTimeMillis())
                .build();
    }

    @Override
    public ChatProto.CompanionReadResponse companionRead(ChatProto.CompanionReadRequest request) {
        logger.info("Processing companion read request: userId={}, action={}",
                request.getUserId(), request.getAction());

        String explanation = String.format(
                "同学你好~ 关于【%s】这个知识点，简单来说就是：" +
                "这是408考试中的一个重要概念，建议结合教材例题来理解。",
                request.getText().substring(0, Math.min(30, request.getText().length())));

        return ChatProto.CompanionReadResponse.newBuilder()
                .setExplanationText(explanation)
                .setSuccess(true)
                .build();
    }

    @Override
    public ChatProto.DashboardResponse dashboard(ChatProto.DashboardRequest request) {
        logger.info("Processing dashboard request: userId={}", request.getUserId());

        return ChatProto.DashboardResponse.newBuilder()
                .setUserId(request.getUserId())
                .addRadar(0.65).addRadar(0.42).addRadar(0.58).addRadar(0.73)
                .addLine(3).addLine(5).addLine(2).addLine(7).addLine(4).addLine(6).addLine(1)
                .setUpdateTime(LocalDate.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd")))
                .build();
    }

    @Override
    public ChatProto.DashboardSummaryResponse dashboardSummary(ChatProto.DashboardSummaryRequest request) {
        logger.info("Processing dashboard summary request: userId={}", request.getUserId());

        Map<String, Double> subjectDetails = new LinkedHashMap<>();
        subjectDetails.put("数据结构", 0.65);
        subjectDetails.put("计算机组成原理", 0.42);
        subjectDetails.put("计算机操作系统", 0.58);
        subjectDetails.put("计算机网络", 0.73);

        return ChatProto.DashboardSummaryResponse.newBuilder()
                .setAvgMastery(0.595)
                .setStrongestSubject("计算机网络")
                .setWeakestSubject("计算机组成原理")
                .setTotalQuestionsThisWeek(28)
                .putAllSubjectDetails(subjectDetails)
                .build();
    }

    @Override
    public ChatProto.WeeklyReportResponse weeklyReport(ChatProto.WeeklyReportRequest request) {
        logger.info("Processing weekly report request: userId={}", request.getUserId());

        String report = "## 408 AI 学习诊断周报\n\n" +
                "### 总体评价\n本周学习状态良好。\n\n" +
                "### 薄弱点分析\n计算机组成原理掌握度低于60%。\n\n" +
                "### 下周建议\n1. 重点攻克计组流水线\n2. 每天至少做5道选择题";

        return ChatProto.WeeklyReportResponse.newBuilder()
                .setReport(report)
                .setUserId(request.getUserId())
                .setGeneratedAt(LocalDate.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd")))
                .build();
    }

    @Override
    public ChatProto.PdfParseResponse parsePdf(ChatProto.PdfParseRequest request) {
        logger.info("Processing PDF parse request: filename={}", request.getFilename());

        return ChatProto.PdfParseResponse.newBuilder()
                .setContent("[Protobuf RPC Bridge] PDF解析需要集成 Spring AI PdfDocumentReader。")
                .setPageCount(0)
                .setSuccess(true)
                .build();
    }

    @Override
    public ChatProto.SandboxExecuteResponse sandboxExecute(ChatProto.SandboxExecuteRequest request) {
        logger.info("Processing sandbox execute request: prompt={}, model={}",
                request.getPrompt().substring(0, Math.min(50, request.getPrompt().length())),
                request.getModel());

        String sessionId = request.getSessionId().isEmpty()
                ? UUID.randomUUID().toString().substring(0, 8)
                : request.getSessionId();

        String result = String.format(
                "[Protobuf RPC Bridge] Sandbox execute simulation.\n" +
                "Prompt: %s\nModel: %s\nMaxTurns: %d\n" +
                "In production, this would call eruitah-sandbox's run_agent().",
                request.getPrompt().substring(0, Math.min(80, request.getPrompt().length())),
                request.getModel().isEmpty() ? "gpt-4o" : request.getModel(),
                request.getMaxTurns());

        return ChatProto.SandboxExecuteResponse.newBuilder()
                .setSessionId(sessionId)
                .setSuccess(true)
                .setFinalResult(result)
                .setTurnsUsed(Math.min(request.getMaxTurns(), 3))
                .setTimestamp(System.currentTimeMillis())
                .build();
    }

    @Override
    public ChatProto.SandboxTaskResponse sandboxTask(ChatProto.SandboxTaskRequest request) {
        logger.info("Processing sandbox task request: action={}, taskId={}",
                request.getAction(), request.getTaskId());

        String data = "";
        boolean success = true;

        switch (request.getAction()) {
            case "list_tasks":
                data = "[{\"task_id\":\"task_001\",\"summary\":\"Binary Tree\"}]";
                break;
            case "rollback_task":
                data = "Rolled back to task start state";
                break;
            case "switch_task":
                data = "Switched to task: " + request.getTargetTaskId();
                break;
            case "delete_task":
                data = "Deleted task: " + request.getTargetTaskId();
                break;
            case "stop_agent":
                data = "Agent stopped";
                break;
            default:
                success = false;
                data = "Unknown action: " + request.getAction();
        }

        return ChatProto.SandboxTaskResponse.newBuilder()
                .setSuccess(success)
                .setAction(request.getAction())
                .setData(data)
                .setTaskId(request.getTaskId())
                .build();
    }

    @Override
    public ChatProto.SwarmRegisterResponse swarmRegister(ChatProto.SwarmRegisterRequest request) {
        logger.info("Processing swarm register request: agentId={}, capabilities={}",
                request.getAgentId(), request.getCapabilitiesList());

        ChatProto.SwarmAgentNode node = ChatProto.SwarmAgentNode.newBuilder()
                .setAgentId(request.getAgentId())
                .addAllCapabilities(request.getCapabilitiesList())
                .addAllSpecialties(request.getSpecialtiesList())
                .setStatus("online")
                .setRegisteredAt(System.currentTimeMillis())
                .setLastHeartbeat(System.currentTimeMillis())
                .build();

        swarmNodes.put(request.getAgentId(), node);

        return ChatProto.SwarmRegisterResponse.newBuilder()
                .setSuccess(true)
                .setMessage("Registered successfully, cluster has " + swarmNodes.size() + " nodes")
                .setNodeCount(swarmNodes.size())
                .build();
    }

    @Override
    public ChatProto.SwarmHelpResponse swarmHelp(ChatProto.SwarmHelpRequest request) {
        logger.info("Processing swarm help request: fromId={}, task={}",
                request.getFromId(), request.getTask());

        String result = String.format(
                "[Protobuf RPC Bridge] Swarm help simulation for task: %s. " +
                "In production, this would broadcast to eruitah-sandbox's SwarmHub.",
                request.getTask().substring(0, Math.min(50, request.getTask().length())));

        return ChatProto.SwarmHelpResponse.newBuilder()
                .setFromId("bridge_sim_agent")
                .setToId(request.getFromId())
                .setTask(request.getTask())
                .setResult(result)
                .setFound(true)
                .build();
    }

    @Override
    public ChatProto.SwarmNodeListResponse swarmNodeList() {
        logger.info("Processing swarm node list request, current nodes: {}", swarmNodes.size());

        ChatProto.SwarmNodeListResponse.Builder builder = ChatProto.SwarmNodeListResponse.newBuilder();
        for (ChatProto.SwarmAgentNode node : swarmNodes.values()) {
            builder.addNodes(node);
        }
        return builder.build();
    }

    private String processWithAI(String message, int userId, int botId) {
        String lowerMessage = message.toLowerCase();

        if (lowerMessage.contains("hello") || lowerMessage.contains("hi") || lowerMessage.contains("你好")) {
            return "你好！我是" + BOT_NAMES.getOrDefault(botId, "AI助手") + "，有什么可以帮你的吗？";
        } else if (lowerMessage.contains("数据结构")) {
            return "数据结构是408考试的重点科目，常考的有线性表、树、图、查找和排序。";
        } else if (lowerMessage.contains("操作系统")) {
            return "操作系统主要考察进程管理、内存管理、文件系统和IO管理。";
        } else if (lowerMessage.contains("计算机网络") || lowerMessage.contains("计网")) {
            return "计网重点在TCP/IP协议栈，特别是三次握手四次挥手、拥塞控制。";
        } else if (lowerMessage.contains("组成原理") || lowerMessage.contains("计组")) {
            return "计组重点在数据表示、运算器、存储系统和指令系统。";
        } else {
            return String.format(
                    "[Protobuf RPC Bridge] 收到消息：\"%s\"。模拟AI回复。",
                    message.substring(0, Math.min(30, message.length())));
        }
    }
}
