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

public class SimpleIdeWebSocketHandler extends TextWebSocketHandler {

    private static final Logger log = LoggerFactory.getLogger(SimpleIdeWebSocketHandler.class);
    private static final ObjectMapper mapper = new ObjectMapper();

    private final ProtobufRpcClient rpcClient;
    private final ConcurrentHashMap<String, WebSocketSession> sessions = new ConcurrentHashMap<>();
    private final ConcurrentHashMap<String, Long> sessionRpcIds = new ConcurrentHashMap<>();

    public SimpleIdeWebSocketHandler(ProtobufRpcClient rpcClient) {
        this.rpcClient = rpcClient;
    }

    @Override
    public void afterConnectionEstablished(WebSocketSession session) {
        sessions.put(session.getId(), session);
        log.info("SimpleIDE WS connected: {}", session.getId());

        try {
            ObjectNode connected = mapper.createObjectNode();
            connected.put("type", "connected");
            connected.put("sessionId", session.getId());
            synchronized (session) {
                session.sendMessage(new TextMessage(mapper.writeValueAsString(connected)));
            }
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

        String prompt = extractField(request, "prompt", "message", "task");
        if (prompt == null || prompt.isBlank()) {
            sendErrorToClient(session, "No prompt provided");
            return;
        }

        if (!rpcClient.isConnected()) {
            sendErrorToClient(session, "Agent 服务连接中断，请稍后重试");
            return;
        }

        ChatProto.SandboxExecuteRequest.Builder reqBuilder = ChatProto.SandboxExecuteRequest.newBuilder()
                .setPrompt(prompt);

        if (request.has("work_dir")) reqBuilder.setWorkDir(request.get("work_dir").asText());
        if (request.has("max_turns")) reqBuilder.setMaxTurns(request.get("max_turns").asInt());
        if (request.has("model")) reqBuilder.setModel(request.get("model").asText());
        if (request.has("api_key")) reqBuilder.setApiKey(request.get("api_key").asText());
        if (request.has("base_url")) reqBuilder.setBaseUrl(request.get("base_url").asText());
        if (request.has("provider")) reqBuilder.setProvider(request.get("provider").asText());
        if (request.has("session_id")) reqBuilder.setSessionId(request.get("session_id").asText());

        ChatProto.SandboxExecuteRequest rpcRequest = reqBuilder.build();

        rpcClient.callStream(
                rpcRequest,
                event -> handleStreamChunk(session, event),
                () -> handleStreamEnd(session),
                error -> handleStreamError(session, error)
        );
    }

    private void handleStreamChunk(WebSocketSession session, ChatProto.SandboxToolEvent event) {
        if (!session.isOpen()) {
            log.warn("WS session {} already closed, dropping chunk", session.getId());
            return;
        }

        try {
            ObjectNode chunk = mapper.createObjectNode();
            chunk.put("type", "agent_event");
            chunk.put("eventType", event.getEventType());
            chunk.put("sessionId", event.getSessionId());
            chunk.put("isError", event.getIsError());
            chunk.put("content", event.getContent());
            chunk.put("toolName", event.getToolName());
            chunk.put("result", event.getResult());
            chunk.put("statusData", event.getStatusData());
            chunk.put("argsJson", event.getArgsJson());
            chunk.put("timestamp", event.getTimestamp());

            if ("chat_finish".equals(event.getEventType())) {
                chunk.put("type", "chat_finish");
                try {
                    JsonNode finishData = mapper.readTree(event.getContent());
                    chunk.set("status", finishData.get("status"));
                    if (finishData.has("error")) {
                        chunk.put("error", finishData.get("error").asText());
                    }
                } catch (Exception ignored) {
                }
            }

            synchronized (session) {
                if (session.isOpen()) {
                    session.sendMessage(new TextMessage(mapper.writeValueAsString(chunk)));
                }
            }
        } catch (IOException e) {
            log.error("Failed to send chunk to WS session {}: {}", session.getId(), e.getMessage());
        } catch (Exception e) {
            log.error("Unexpected error in handleStreamChunk for session {}", session.getId(), e);
        }
    }

    private void handleStreamEnd(WebSocketSession session) {
        sessionRpcIds.remove(session.getId());

        if (!session.isOpen()) {
            return;
        }

        try {
            ObjectNode end = mapper.createObjectNode();
            end.put("type", "stream_end");
            end.put("sessionId", session.getId());

            synchronized (session) {
                if (session.isOpen()) {
                    session.sendMessage(new TextMessage(mapper.writeValueAsString(end)));
                }
            }
            log.info("Stream ended for WS session {}", session.getId());
        } catch (IOException e) {
            log.error("Failed to send stream_end to WS session {}: {}", session.getId(), e.getMessage());
        }
    }

    private void handleStreamError(WebSocketSession session, Throwable error) {
        sessionRpcIds.remove(session.getId());

        String errorMsg = error != null ? error.getMessage() : "Unknown error";
        log.error("Stream error for WS session {}: {}", session.getId(), errorMsg);

        if (!session.isOpen()) {
            return;
        }

        try {
            ObjectNode errorNode = mapper.createObjectNode();
            errorNode.put("type", "error");
            errorNode.put("content", "Agent 连接中断: " + errorMsg);
            errorNode.put("recoverable", false);
            errorNode.put("sessionId", session.getId());

            synchronized (session) {
                if (session.isOpen()) {
                    session.sendMessage(new TextMessage(mapper.writeValueAsString(errorNode)));
                }
            }
        } catch (IOException e) {
            log.error("Failed to send error to WS session {}: {}", session.getId(), e.getMessage());
        }
    }

    @Override
    public void handleTransportError(WebSocketSession session, Throwable exception) {
        log.error("WS transport error for session {}: {}", session.getId(), exception.getMessage());
        sessionRpcIds.remove(session.getId());

        if (session.isOpen()) {
            try {
                ObjectNode errorNode = mapper.createObjectNode();
                errorNode.put("type", "error");
                errorNode.put("content", "WebSocket 传输错误");
                errorNode.put("recoverable", false);
                synchronized (session) {
                    session.sendMessage(new TextMessage(mapper.writeValueAsString(errorNode)));
                }
            } catch (IOException ignored) {
            }
        }
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
        sessions.remove(session.getId());
        sessionRpcIds.remove(session.getId());
        log.info("SimpleIDE WS closed: {} status={}", session.getId(), status);
    }

    private void sendErrorToClient(WebSocketSession session, String errorMessage) {
        if (!session.isOpen()) return;

        try {
            ObjectNode error = mapper.createObjectNode();
            error.put("type", "error");
            error.put("content", errorMessage);
            error.put("recoverable", true);

            synchronized (session) {
                session.sendMessage(new TextMessage(mapper.writeValueAsString(error)));
            }
        } catch (IOException e) {
            log.error("Failed to send error to WS session {}", session.getId(), e);
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
