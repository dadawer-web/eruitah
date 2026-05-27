package com.chat.ai.websocket;

import com.chat.ai.rpc.ChatProto;
import com.chat.ai.rpc.ProtobufRpcClient;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

import java.io.IOException;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

public class SimpleIdeWebSocketHandler extends TextWebSocketHandler {

    private static final Logger log = LoggerFactory.getLogger(SimpleIdeWebSocketHandler.class);
    private static final ObjectMapper mapper = new ObjectMapper();

    private final ProtobufRpcClient rpcClient;
    private final ConcurrentHashMap<String, WebSocketSession> sessions = new ConcurrentHashMap<>();
    private final ConcurrentHashMap<String, AtomicLong> sessionTaskCounters = new ConcurrentHashMap<>();

    public SimpleIdeWebSocketHandler(ProtobufRpcClient rpcClient) {
        this.rpcClient = rpcClient;
    }

    @Override
    public void afterConnectionEstablished(WebSocketSession session) {
        sessions.put(session.getId(), session);
        sessionTaskCounters.put(session.getId(), new AtomicLong(0));
        log.info("SimpleIDE WS connected: {}", session.getId());

        try {
            ObjectNode connected = mapper.createObjectNode();
            connected.put("type", "connected");
            connected.put("sessionId", session.getId());
            sendToSession(session, connected);
        } catch (Exception e) {
            log.warn("Failed to send connected message to {}", session.getId());
        }
    }

    @Override
    protected void handleTextMessage(WebSocketSession session, TextMessage message) throws Exception {
        String payload = message.getPayload();
        JsonNode request;

        try {
            request = mapper.readTree(payload);
        } catch (Exception e) {
            sendErrorToClient(session, "Invalid JSON: " + e.getMessage());
            return;
        }

        String msgType = request.has("type") ? request.get("type").asText() : "";

        switch (msgType) {
            case "chat_new_task":
            case "chat_continue":
                handleChatMessage(session, request);
                break;
            case "system_command":
                handleSystemCommand(session, request);
                break;
            case "user_answer":
                log.info("User answer received for question: {}", request.path("question_id").asText());
                break;
            case "command_confirm":
                log.info("Command confirm: approved={}", request.path("approved").asBoolean());
                break;
            default:
                String prompt = extractField(request, "prompt", "message", "task");
                if (prompt != null && !prompt.isBlank()) {
                    handleChatMessage(session, request);
                } else {
                    sendErrorToClient(session, "Unknown message type: " + msgType);
                }
                break;
        }
    }

    private void handleChatMessage(WebSocketSession session, JsonNode request) {
        String prompt = extractField(request, "task", "prompt", "message");
        if (prompt == null || prompt.isBlank()) {
            sendErrorToClient(session, "No prompt/task provided");
            return;
        }

        if (!rpcClient.isConnected()) {
            sendErrorToClient(session, "Agent 服务连接中断，请稍后重试");
            return;
        }

        String sessionId = session.getId();
        long taskNum = sessionTaskCounters.getOrDefault(sessionId, new AtomicLong(0)).incrementAndGet();
        String taskId = "task_" + sessionId.substring(0, 8) + "_" + taskNum;

        ObjectNode taskStarted = mapper.createObjectNode();
        taskStarted.put("type", "task_started");
        taskStarted.put("task_id", taskId);
        taskStarted.put("task_name", prompt.length() > 30 ? prompt.substring(0, 30) + "..." : prompt);
        if (request.has("work_dir")) {
            taskStarted.put("work_dir", request.get("work_dir").asText());
        }
        sendToSession(session, taskStarted);

        ChatProto.SandboxExecuteRequest.Builder reqBuilder = ChatProto.SandboxExecuteRequest.newBuilder()
                .setPrompt(prompt)
                .setSessionId(taskId);

        if (request.has("work_dir")) reqBuilder.setWorkDir(request.get("work_dir").asText());
        if (request.has("max_turns")) reqBuilder.setMaxTurns(request.get("max_turns").asInt());
        if (request.has("model")) reqBuilder.setModel(request.get("model").asText());
        if (request.has("api_key")) reqBuilder.setApiKey(request.get("api_key").asText());
        if (request.has("base_url")) reqBuilder.setBaseUrl(request.get("base_url").asText());
        if (request.has("provider")) reqBuilder.setProvider(request.get("provider").asText());

        long rpcUserId = 0;
        if (request.has("user_id") && request.get("user_id").asLong() > 0) {
            rpcUserId = request.get("user_id").asLong();
        }
        if (rpcUserId == 0 && request.has("userId") && request.get("userId").asLong() > 0) {
            rpcUserId = request.get("userId").asLong();
        }
        if (rpcUserId <= 0) {
            log.warn("SandboxExecuteRequest missing user_id for session={}, using fallback=1. " +
                     "Python sandbox requires user_id for tenant isolation!", sessionId);
            rpcUserId = 1;
        }
        reqBuilder.setUserId(rpcUserId);

        String rpcSessionId = reqBuilder.getSessionId();
        if (rpcSessionId == null || rpcSessionId.isEmpty()) {
            log.error("SandboxExecuteRequest missing session_id for session={}, this will break " +
                      "Python sandbox tenant isolation!", sessionId);
            reqBuilder.setSessionId(taskId);
        }

        ChatProto.SandboxExecuteRequest rpcRequest = reqBuilder.build();

        log.info("SandboxExecuteRequest built: userId={}, sessionId={}, taskId={}, promptLen={}",
                 rpcUserId, rpcRequest.getSessionId(), taskId, prompt.length());

        rpcClient.callStream(
                rpcRequest,
                event -> handleStreamChunk(session, event, taskId),
                () -> handleStreamEnd(session, taskId),
                error -> handleStreamError(session, error, taskId)
        );
    }

    private void handleSystemCommand(WebSocketSession session, JsonNode request) {
        String action = request.has("action") ? request.get("action").asText() : "";

        switch (action) {
            case "stop_agent":
                ObjectNode stopped = mapper.createObjectNode();
                stopped.put("type", "stopped");
                stopped.put("data", "Agent 已停止");
                sendToSession(session, stopped);
                break;
            case "delete_task": {
                String taskId = request.path("target_task_id").asText("");
                ObjectNode deleted = mapper.createObjectNode();
                deleted.put("type", "task_deleted");
                deleted.put("task_id", taskId);
                sendToSession(session, deleted);
                break;
            }
            case "list_mcp_services": {
                ObjectNode mcpResp = mapper.createObjectNode();
                mcpResp.put("type", "mcp_services");
                mcpResp.put("data", "Java RPC bridge mode - MCP services managed by Python backend");
                sendToSession(session, mcpResp);
                break;
            }
            default:
                log.info("Unhandled system command: {}", action);
                break;
        }
    }

    private void handleStreamChunk(WebSocketSession session, ChatProto.SandboxToolEvent event, String taskId) {
        if (!session.isOpen()) {
            log.warn("WS session {} already closed, dropping chunk", session.getId());
            return;
        }

        try {
            String eventType = event.getEventType();
            String content = event.getContent();
            String toolName = event.getToolName();
            String argsJson = event.getArgsJson();
            String result = event.getResult();
            String statusData = event.getStatusData();
            boolean isError = event.getIsError();

            if ("chat_finish".equals(eventType)) {
                ObjectNode finish = mapper.createObjectNode();
                finish.put("type", "finish");
                finish.put("task_id", taskId);

                try {
                    JsonNode finishData = mapper.readTree(content);
                    String status = finishData.path("status").asText("unknown");
                    finish.put("data", "success".equals(status) ? "任务已完成" : "任务异常");
                    if (finishData.has("error")) {
                        finish.put("error", finishData.get("error").asText());
                    }
                } catch (Exception e) {
                    finish.put("data", content);
                }

                sendToSession(session, finish);
                return;
            }

            if (!toolName.isEmpty()) {
                if (result.isEmpty() && !isError) {
                    ObjectNode toolStart = mapper.createObjectNode();
                    toolStart.put("type", "tool_start");
                    toolStart.put("tool_name", toolName);
                    toolStart.put("task_id", taskId);
                    if (!argsJson.isEmpty()) {
                        try {
                            toolStart.set("args", mapper.readTree(argsJson));
                        } catch (Exception e) {
                            toolStart.put("args", argsJson);
                        }
                    }
                    sendToSession(session, toolStart);
                } else {
                    ObjectNode toolEnd = mapper.createObjectNode();
                    toolEnd.put("type", "tool_end");
                    toolEnd.put("tool_name", toolName);
                    toolEnd.put("task_id", taskId);
                    toolEnd.put("is_error", isError);
                    if (!result.isEmpty()) {
                        toolEnd.put("result", result);
                    }
                    sendToSession(session, toolEnd);
                }
                return;
            }

            if (!content.isEmpty() && !isError) {
                if ("agent_status".equals(eventType) || "agent_state".equals(eventType)) {
                    ObjectNode agentState = mapper.createObjectNode();
                    agentState.put("type", "agent_state");
                    agentState.put("status", "thinking");
                    agentState.put("data", content);
                    agentState.put("task_id", taskId);
                    sendToSession(session, agentState);
                } else if ("typing".equals(eventType)) {
                    ObjectNode typing = mapper.createObjectNode();
                    typing.put("type", "typing");
                    typing.put("content", content);
                    typing.put("task_id", taskId);
                    sendToSession(session, typing);
                } else if ("system_alert".equals(eventType)) {
                    ObjectNode alert = mapper.createObjectNode();
                    alert.put("type", "system_alert");
                    alert.put("content", content);
                    alert.put("task_id", taskId);
                    sendToSession(session, alert);
                } else {
                    ObjectNode msg = mapper.createObjectNode();
                    msg.put("type", "message");
                    msg.put("content", content);
                    msg.put("task_id", taskId);
                    sendToSession(session, msg);
                }
            }

            if (isError && !content.isEmpty()) {
                ObjectNode err = mapper.createObjectNode();
                err.put("type", "error");
                err.put("data", content);
                err.put("task_id", taskId);
                sendToSession(session, err);
            }

        } catch (Exception e) {
            log.error("Unexpected error in handleStreamChunk for session {}", session.getId(), e);
        }
    }

    private void handleStreamEnd(WebSocketSession session, String taskId) {
        if (!session.isOpen()) {
            return;
        }

        ObjectNode end = mapper.createObjectNode();
        end.put("type", "stream_end");
        end.put("task_id", taskId);
        sendToSession(session, end);
        log.info("Stream ended for WS session {} task {}", session.getId(), taskId);
    }

    private void handleStreamError(WebSocketSession session, Throwable error, String taskId) {
        String errorMsg = error != null ? error.getMessage() : "Unknown error";
        log.error("Stream error for WS session {} task {}: {}", session.getId(), taskId, errorMsg);

        if (!session.isOpen()) {
            return;
        }

        ObjectNode errorNode = mapper.createObjectNode();
        errorNode.put("type", "error");
        errorNode.put("data", "Agent 连接中断: " + errorMsg);
        errorNode.put("task_id", taskId);
        sendToSession(session, errorNode);
    }

    @Override
    public void handleTransportError(WebSocketSession session, Throwable exception) {
        log.error("WS transport error for session {}: {}", session.getId(), exception.getMessage());

        if (session.isOpen()) {
            ObjectNode errorNode = mapper.createObjectNode();
            errorNode.put("type", "error");
            errorNode.put("data", "WebSocket 传输错误");
            sendToSession(session, errorNode);
        }
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
        sessions.remove(session.getId());
        sessionTaskCounters.remove(session.getId());
        log.info("SimpleIDE WS closed: {} status={}", session.getId(), status);
    }

    private void sendErrorToClient(WebSocketSession session, String errorMessage) {
        if (!session.isOpen()) return;

        ObjectNode error = mapper.createObjectNode();
        error.put("type", "error");
        error.put("data", errorMessage);
        sendToSession(session, error);
    }

    private void sendToSession(WebSocketSession session, ObjectNode message) {
        synchronized (session) {
            if (session.isOpen()) {
                try {
                    session.sendMessage(new TextMessage(mapper.writeValueAsString(message)));
                } catch (IOException e) {
                    log.error("Failed to send message to WS session {}: {}", session.getId(), e.getMessage());
                }
            }
        }
    }

    private String extractField(JsonNode node, String... fieldNames) {
        for (String name : fieldNames) {
            if (node.has(name) && !node.get(name).isNull() && !node.get(name).asText().isBlank()) {
                return node.get(name).asText();
            }
        }
        return null;
    }
}
