package com.chat.ai.rpc;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Instant;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

public class RpcPushService {

    private static final Logger log = LoggerFactory.getLogger(RpcPushService.class);

    private final ProtobufRpcClient cppRpcClient;
    private final ObjectMapper objectMapper;

    private static final int GROUP_DISPATCH_MSG_ID = 17;
    private static final int ONE_CHAT_MSG_ID = 6;
    private static final int VOICE_MSG_ID = 60;
    private static final int FARM_ACK_MSG_ID = 73;
    private static final int FARM_BROADCAST_MSG_ID = 78;

    public RpcPushService(ProtobufRpcClient cppRpcClient, ObjectMapper objectMapper) {
        this.cppRpcClient = cppRpcClient;
        this.objectMapper = objectMapper;
    }

    public void publishDirectMessage(Integer userId, String content, int botId, String botName) {
        Map<String, Object> message = new HashMap<>();
        message.put("msgid", ONE_CHAT_MSG_ID);
        message.put("from", botId);
        message.put("to", userId);
        message.put("msg", content);
        message.put("name", botName);
        message.put("timestamp", Instant.now().toEpochMilli());

        pushToCpp(userId, 0, ChatProto.InternalMsgType.CHAT_PRIVATE, message);
    }

    public void publishDirectMessage(Integer userId, String content) {
        publishDirectMessage(userId, content, -1, "AI助手");
    }

    public void publishAgentGroupMessage(Long groupId, String content, int botId, String botName, String messageType) {
        Map<String, Object> message = new HashMap<>();
        message.put("msgid", GROUP_DISPATCH_MSG_ID);
        message.put("groupid", groupId);
        message.put("from", botId);
        message.put("fromName", botName);
        message.put("msg", content);
        message.put("timestamp", Instant.now().toEpochMilli());

        pushToCpp(0, groupId, ChatProto.InternalMsgType.CHAT_GROUP, message, true);
    }

    public void publishGroupMessage(Long groupId, String content, Integer replyTo) {
        Map<String, Object> message = new HashMap<>();
        message.put("groupId", groupId);
        message.put("senderId", -1);
        message.put("senderName", "AI助手");
        message.put("content", content);
        message.put("timestamp", Instant.now().toEpochMilli());
        message.put("replyTo", replyTo);
        message.put("type", "AI_SUMMARY");

        pushToCpp(0, groupId, ChatProto.InternalMsgType.CHAT_GROUP, message, true);
    }

    public void publishGroupMessage(Long groupId, String content) {
        publishGroupMessage(groupId, content, null);
    }

    public void publishStreamStart(Integer userId, int botId, String botName) {
        Map<String, Object> message = new HashMap<>();
        message.put("msgid", ONE_CHAT_MSG_ID);
        message.put("from", botId);
        message.put("to", userId);
        message.put("msg", "[STREAM_CHUNK]: ");
        message.put("name", botName);
        message.put("timestamp", Instant.now().toEpochMilli());

        pushToCpp(userId, 0, ChatProto.InternalMsgType.CHAT_PRIVATE, message);
    }

    public void publishStreamChunk(Integer userId, String chunk, int botId, String botName) {
        Map<String, Object> message = new HashMap<>();
        message.put("msgid", ONE_CHAT_MSG_ID);
        message.put("from", botId);
        message.put("to", userId);
        message.put("msg", "[STREAM_CHUNK]:" + chunk);
        message.put("name", botName);
        message.put("timestamp", Instant.now().toEpochMilli());

        pushToCpp(userId, 0, ChatProto.InternalMsgType.CHAT_PRIVATE, message);
    }

    public void publishStreamEnd(Integer userId, int botId, String botName) {
        Map<String, Object> message = new HashMap<>();
        message.put("msgid", ONE_CHAT_MSG_ID);
        message.put("from", botId);
        message.put("to", userId);
        message.put("msg", "[STREAM_CHUNK]:[STREAM_END]");
        message.put("name", botName);
        message.put("timestamp", Instant.now().toEpochMilli());

        pushToCpp(userId, 0, ChatProto.InternalMsgType.CHAT_PRIVATE, message);
    }

    public void publishStreamClear(Integer userId, int botId, String botName) {
        Map<String, Object> message = new HashMap<>();
        message.put("msgid", ONE_CHAT_MSG_ID);
        message.put("from", botId);
        message.put("to", userId);
        message.put("msg", "[STREAM_CHUNK]:[STREAM_CLEAR]");
        message.put("name", botName);
        message.put("timestamp", Instant.now().toEpochMilli());

        pushToCpp(userId, 0, ChatProto.InternalMsgType.CHAT_PRIVATE, message);
    }

    public void publishVoiceMessage(Integer userId, String voiceUrl, int duration, int botId, String botName) {
        Map<String, Object> message = new HashMap<>();
        message.put("msgid", VOICE_MSG_ID);
        message.put("from", botId);
        message.put("toid", userId);
        message.put("voiceUrl", voiceUrl);
        message.put("duration", duration);
        message.put("name", botName);
        message.put("timestamp", Instant.now().toEpochMilli());

        pushToCpp(userId, 0, ChatProto.InternalMsgType.VOICE_CHAT, message);
    }

    public void publishFarmAck(int userId, int plotId, int ownerId, boolean canHarvest, int score, String feedback) {
        Map<String, Object> message = new HashMap<>();
        message.put("msgid", FARM_ACK_MSG_ID);
        message.put("errno", 0);
        message.put("plotid", plotId);
        message.put("canHarvest", canHarvest);
        message.put("score", score);
        message.put("feedback", feedback);
        message.put("userid", userId);
        message.put("ownerid", ownerId);

        pushToCpp(userId, 0, ChatProto.InternalMsgType.POINTS_UPDATE, message);
    }

    public void publishFarmBroadcast(String broadcastMsg) {
        Map<String, Object> message = new HashMap<>();
        message.put("msgid", FARM_BROADCAST_MSG_ID);
        message.put("msg", broadcastMsg);

        pushToCpp(0, 0, ChatProto.InternalMsgType.SYSTEM_NOTIFICATION, message, true);
    }

    public void pushExperienceUpdate(int userId, Map<String, Object> expData) {
        pushToCpp(userId, 0, ChatProto.InternalMsgType.EXPERIENCE_UPDATE, expData);
    }

    private void pushToCpp(int receiverId, long groupId, ChatProto.InternalMsgType msgType, Map<String, Object> message) {
        pushToCpp(receiverId, groupId, msgType, message, false);
    }

    private void pushToCpp(int receiverId, long groupId, ChatProto.InternalMsgType msgType,
                           Map<String, Object> message, boolean broadcast) {
        try {
            String payloadJson = objectMapper.writeValueAsString(message);

            ChatProto.InternalPushRequest request = ChatProto.InternalPushRequest.newBuilder()
                    .setReceiverId(receiverId)
                    .setGroupId(groupId)
                    .setMsgType(msgType)
                    .setPayloadJson(payloadJson)
                    .setTraceId(UUID.randomUUID().toString().substring(0, 8))
                    .setTimestamp(Instant.now().toEpochMilli())
                    .setBroadcast(broadcast)
                    .build();

            if (cppRpcClient.isConnected()) {
                cppRpcClient.callUnary(
                        "InternalRouterService", "PushToClient", request,
                        ChatProto.InternalPushResponse.class,
                        response -> {
                            if (!response.getSuccess()) {
                                log.error("PushToClient failed: {}", response.getError());
                            }
                        },
                        error -> log.error("PushToClient RPC error: {}", error.getMessage())
                );
            } else {
                log.warn("C++ RPC not connected, dropping message: msgType={}, receiverId={}", msgType, receiverId);
            }

        } catch (Exception e) {
            log.error("Error pushing to C++: msgType={}, receiverId={}", msgType, receiverId, e);
        }
    }
}
