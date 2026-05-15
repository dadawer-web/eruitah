package com.chat.ai.rpc;

import com.chat.ai.service.AiChatRequestListener;
import com.chat.ai.service.CareerAdviceService;
import com.chat.ai.service.FarmAiJudgeService;
import com.chat.ai.service.FarmService;
import com.chat.ai.service.GroupChatService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.function.Consumer;

public class InternalRouterHandler implements Consumer<ChatProto.RpcMessage> {

    private static final Logger log = LoggerFactory.getLogger(InternalRouterHandler.class);

    private final AiChatRequestListener aiChatRequestListener;
    private final FarmService farmService;
    private final FarmAiJudgeService farmAiJudgeService;
    private final GroupChatService groupChatService;
    private final CareerAdviceService careerAdviceService;
    private final ObjectMapper objectMapper;
    private final Executor streamTaskExecutor;

    public InternalRouterHandler(AiChatRequestListener aiChatRequestListener,
                                  FarmService farmService,
                                  FarmAiJudgeService farmAiJudgeService,
                                  GroupChatService groupChatService,
                                  CareerAdviceService careerAdviceService,
                                  ObjectMapper objectMapper,
                                  Executor streamTaskExecutor) {
        this.aiChatRequestListener = aiChatRequestListener;
        this.farmService = farmService;
        this.farmAiJudgeService = farmAiJudgeService;
        this.groupChatService = groupChatService;
        this.careerAdviceService = careerAdviceService;
        this.objectMapper = objectMapper;
        this.streamTaskExecutor = streamTaskExecutor;
    }

    @Override
    public void accept(ChatProto.RpcMessage rpcMsg) {
        if (rpcMsg.getType() != ChatProto.RpcMessage.Type.REQUEST) {
            return;
        }

        String service = rpcMsg.getServiceName();
        String method = rpcMsg.getMethodName();

        log.info("Received internal RPC: {}.{} id={}", service, method, rpcMsg.getId());

        try {
            ChatProto.InternalForwardRequest request = ChatProto.InternalForwardRequest.parseFrom(rpcMsg.getPayload());
            CompletableFuture.runAsync(() -> handleForwardRequest(request), streamTaskExecutor);
        } catch (Exception e) {
            log.error("Error handling ForwardToJava request", e);
        }
    }

    private void handleForwardRequest(ChatProto.InternalForwardRequest request) {
        ChatProto.InternalMsgType msgType = request.getMsgType();
        String payloadJson = request.getPayloadJson();

        log.info("Handling forward: msgType={}, senderId={}, receiverId={}, traceId={}",
                msgType, request.getSenderId(), request.getReceiverId(), request.getTraceId());

        try {
            switch (msgType) {
                case CHAT_PRIVATE -> handlePrivateChat(payloadJson);
                case AI_AT_MENTION -> handleAtMention(payloadJson);
                case CHAT_GROUP -> handleGroupChat(payloadJson);
                case AI_GRADE_RESULT -> handleFarmAnswer(payloadJson);
                case POINTS_UPDATE -> handlePointsUpdate(payloadJson);
                case EXPERIENCE_UPDATE -> handleExperienceUpdate(payloadJson);
                case COMPANION_READ -> handleCompanionRead(payloadJson);
                case DASHBOARD_QUERY -> handleDashboardQuery(payloadJson);
                case SANDBOX_EXECUTE -> handleSandboxExecute(payloadJson);
                case VOICE_CHAT -> handleVoiceChat(payloadJson);
                case CAREER_ADVICE -> handleCareerAdvice(payloadJson);
                default -> log.warn("Unhandled InternalMsgType: {}", msgType);
            }
        } catch (Exception e) {
            log.error("Error processing msgType={}: {}", msgType, e.getMessage(), e);
        }
    }

    private void handlePrivateChat(String payloadJson) {
        try {
            JsonNode request = objectMapper.readTree(payloadJson);
            Integer userId = request.get("userId").asInt();
            int botId = request.get("botId").asInt();
            String userMessage = request.get("message").asText();
            String userName = request.has("userName") ? request.get("userName").asText() : "用户";

            log.info("[RPC] Private chat: userId={}, botId={}, message={}", userId, botId,
                    userMessage.length() > 50 ? userMessage.substring(0, 50) + "..." : userMessage);

            aiChatRequestListener.processPrivateChat(userId, botId, userMessage, userName, request);

        } catch (Exception e) {
            log.error("[RPC] Error handling private chat", e);
        }
    }

    private void handleAtMention(String payloadJson) {
        try {
            JsonNode request = objectMapper.readTree(payloadJson);
            Integer userId = request.get("userId").asInt();
            int botId = request.has("botId") ? request.get("botId").asInt() : 10000;
            String userMessage = request.get("message").asText();
            String userName = request.has("userName") ? request.get("userName").asText() : "用户";

            log.info("[RPC] @AI mention: userId={}, botId={}", userId, botId);

            aiChatRequestListener.processPrivateChat(userId, botId, userMessage, userName, request);

        } catch (Exception e) {
            log.error("[RPC] Error handling @AI mention", e);
        }
    }

    private void handleGroupChat(String payloadJson) {
        try {
            JsonNode request = objectMapper.readTree(payloadJson);
            Long groupId = request.get("groupId").asLong();
            int senderId = request.get("senderId").asInt();
            String content = request.get("content").asText();

            JsonNode aiBotIdsNode = request.get("aiBotIds");
            List<Integer> aiBotIds = new ArrayList<>();
            if (aiBotIdsNode != null && aiBotIdsNode.isArray()) {
                for (JsonNode node : aiBotIdsNode) {
                    aiBotIds.add(node.asInt());
                }
            }

            log.info("[RPC] Group chat: groupId={}, senderId={}, aiBotIds={}", groupId, senderId, aiBotIds);

            if (aiBotIds.isEmpty()) {
                log.warn("[RPC] No AI bots in group request, skipping");
                return;
            }

            groupChatService.handleMultiAgentChat(groupId, senderId, content, aiBotIds);

        } catch (Exception e) {
            log.error("[RPC] Error handling group chat", e);
        }
    }

    private void handleFarmAnswer(String payloadJson) {
        try {
            JsonNode request = objectMapper.readTree(payloadJson);
            String action = request.has("action") ? request.get("action").asText() : "answer";

            if ("answer".equals(action)) {
                int userId = request.get("userid").asInt();
                int plotId = request.get("plotid").asInt();
                int ownerId = request.get("ownerid").asInt();
                String question = request.get("question").asText();
                String answer = request.get("answer").asText();

                log.info("[RPC] Farm answer: userId={}, plotId={}, ownerId={}", userId, plotId, ownerId);

                farmService.processAnswer(userId, plotId, ownerId, question, answer);
            } else {
                log.warn("[RPC] Unknown farm action: {}", action);
            }

        } catch (Exception e) {
            log.error("[RPC] Error handling farm answer", e);
        }
    }

    private void handlePointsUpdate(String payloadJson) {
        try {
            JsonNode request = objectMapper.readTree(payloadJson);
            int userId = request.get("userId").asInt();
            int points = request.has("points") ? request.get("points").asInt() : 0;
            String type = request.has("type") ? request.get("type").asText() : "unknown";
            String source = request.has("source") ? request.get("source").asText() : "system";

            log.info("[RPC] Points update: userId={}, points={}, type={}", userId, points, type);

            farmService.addExperience(userId, points, type, source);

        } catch (Exception e) {
            log.error("[RPC] Error handling points update", e);
        }
    }

    private void handleExperienceUpdate(String payloadJson) {
        try {
            JsonNode request = objectMapper.readTree(payloadJson);
            int userId = request.get("userId").asInt();
            int experience = request.has("experience") ? request.get("experience").asInt() : 0;
            String type = request.has("type") ? request.get("type").asText() : "unknown";
            String source = request.has("source") ? request.get("source").asText() : "system";

            log.info("[RPC] Experience update: userId={}, exp={}, type={}, source={}", userId, experience, type, source);

            farmService.addExperience(userId, experience, type, source);

        } catch (Exception e) {
            log.error("[RPC] Error handling experience update", e);
        }
    }

    private void handleCompanionRead(String payloadJson) {
        log.info("[RPC] Companion read request received (delegating to existing service)");
    }

    private void handleDashboardQuery(String payloadJson) {
        log.info("[RPC] Dashboard query received (delegating to existing service)");
    }

    private void handleSandboxExecute(String payloadJson) {
        log.info("[RPC] Sandbox execute request received (delegating to existing service)");
    }

    private void handleVoiceChat(String payloadJson) {
        try {
            JsonNode request = objectMapper.readTree(payloadJson);
            Integer userId = request.get("userId").asInt();
            int botId = request.has("botId") ? request.get("botId").asInt() : 10003;
            String userName = request.has("userName") ? request.get("userName").asText() : "用户";

            log.info("[RPC] Voice chat: userId={}, botId={}", userId, botId);

            aiChatRequestListener.processPrivateChat(userId, botId, "", userName, request);

        } catch (Exception e) {
            log.error("[RPC] Error handling voice chat", e);
        }
    }

    private void handleCareerAdvice(String payloadJson) {
        try {
            JsonNode request = objectMapper.readTree(payloadJson);
            long userId = request.get("userId").asLong();
            String codeContent = request.has("codeContent") ? request.get("codeContent").asText() : "";

            log.info("[RPC] Career advice: userId={}", userId);

            careerAdviceService.analyzeAndPush(userId, codeContent);

        } catch (Exception e) {
            log.error("[RPC] Error handling career advice", e);
        }
    }
}
