package com.bridge.server;

import com.bridge.proto.ChatProto;
import com.bridge.service.ChatService;
import com.google.protobuf.Message;
import io.netty.channel.ChannelHandlerContext;
import io.netty.channel.SimpleChannelInboundHandler;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Map;
import java.util.concurrent.*;

public class RpcMessageHandler extends SimpleChannelInboundHandler<Message> {

    private static final Logger logger = LoggerFactory.getLogger(RpcMessageHandler.class);

    private final ChatService chatService;
    private final ExecutorService executorService;

    public RpcMessageHandler(ChatService chatService) {
        this.chatService = chatService;
        this.executorService = Executors.newFixedThreadPool(Runtime.getRuntime().availableProcessors() * 2);
    }

    @Override
    protected void channelRead0(ChannelHandlerContext ctx, Message msg) throws Exception {
        if (msg instanceof ChatProto.RpcMessage) {
            handleRpcMessage(ctx, (ChatProto.RpcMessage) msg);
        } else if (msg instanceof ChatProto.ChatRequest) {
            handleChatRequest(ctx, (ChatProto.ChatRequest) msg);
        } else if (msg instanceof ChatProto.GroupChatRequest) {
            handleGroupChatRequest(ctx, (ChatProto.GroupChatRequest) msg);
        }
    }

    private void handleRpcMessage(ChannelHandlerContext ctx, ChatProto.RpcMessage rpcMessage) {
        logger.info("Received RPC message: type={}, id={}, service={}, method={}",
                rpcMessage.getType(), rpcMessage.getId(),
                rpcMessage.getServiceName(), rpcMessage.getMethodName());

        if (rpcMessage.getType() == ChatProto.RpcMessage.Type.REQUEST) {
            executorService.submit(() -> {
                try {
                    Message response = processRequest(rpcMessage);
                    sendResponse(ctx, rpcMessage.getId(), response);
                } catch (Exception e) {
                    logger.error("Error processing RPC request", e);
                    sendError(ctx, rpcMessage.getId(), e.getMessage());
                }
            });
        }
    }

    private void handleChatRequest(ChannelHandlerContext ctx, ChatProto.ChatRequest request) {
        logger.info("Received direct chat request from user: {}, bot: {}, session: {}",
                request.getUserId(), request.getBotId(), request.getSessionId());

        executorService.submit(() -> {
            try {
                ChatProto.ChatResponse response = chatService.chat(request);
                ctx.writeAndFlush(response);
            } catch (Exception e) {
                logger.error("Error processing chat request", e);
                ChatProto.ChatResponse errorResponse = ChatProto.ChatResponse.newBuilder()
                        .setUserId(request.getUserId())
                        .setBotId(request.getBotId())
                        .setSuccess(false)
                        .setError("Internal server error: " + e.getMessage())
                        .setTimestamp(System.currentTimeMillis())
                        .build();
                ctx.writeAndFlush(errorResponse);
            }
        });
    }

    private void handleGroupChatRequest(ChannelHandlerContext ctx, ChatProto.GroupChatRequest request) {
        logger.info("Received group chat request from group: {}, sender: {}",
                request.getGroupId(), request.getSenderId());

        executorService.submit(() -> {
            try {
                ChatProto.GroupChatResponse response = chatService.groupChat(request);
                ctx.writeAndFlush(response);
            } catch (Exception e) {
                logger.error("Error processing group chat request", e);
                ChatProto.GroupChatResponse errorResponse = ChatProto.GroupChatResponse.newBuilder()
                        .setGroupId(request.getGroupId())
                        .setSuccess(false)
                        .setError("Internal server error: " + e.getMessage())
                        .setTimestamp(System.currentTimeMillis())
                        .build();
                ctx.writeAndFlush(errorResponse);
            }
        });
    }

    private Message processRequest(ChatProto.RpcMessage rpcMessage) throws Exception {
        String serviceName = rpcMessage.getServiceName();
        String methodName = rpcMessage.getMethodName();

        if ("ChatService".equals(serviceName)) {
            switch (methodName) {
                case "Chat":
                    ChatProto.ChatRequest chatReq = ChatProto.ChatRequest.parseFrom(rpcMessage.getPayload());
                    return chatService.chat(chatReq);
                case "GroupChat":
                    ChatProto.GroupChatRequest groupReq = ChatProto.GroupChatRequest.parseFrom(rpcMessage.getPayload());
                    return chatService.groupChat(groupReq);
                default:
                    throw new IllegalArgumentException("Unknown method: " + methodName);
            }
        }

        throw new IllegalArgumentException("Unknown service: " + serviceName);
    }

    private void sendResponse(ChannelHandlerContext ctx, long id, Message response) {
        ChatProto.RpcMessage rpcResponse = ChatProto.RpcMessage.newBuilder()
                .setType(ChatProto.RpcMessage.Type.RESPONSE)
                .setId(id)
                .setPayload(response.toByteString())
                .build();

        ctx.writeAndFlush(rpcResponse);
        logger.info("Sent RPC response for id={}", id);
    }

    private void sendError(ChannelHandlerContext ctx, long id, String errorMessage) {
        ChatProto.RpcMessage errorResponse = ChatProto.RpcMessage.newBuilder()
                .setType(ChatProto.RpcMessage.Type.ERROR)
                .setId(id)
                .setErrorCode(500)
                .setErrorDesc(errorMessage != null ? errorMessage : "Unknown error")
                .build();

        ctx.writeAndFlush(errorResponse);
        logger.error("Sent RPC error for id={}: {}", id, errorMessage);
    }

    @Override
    public void exceptionCaught(ChannelHandlerContext ctx, Throwable cause) {
        logger.error("Exception in RPC handler", cause);
        ctx.close();
    }

    public void shutdown() {
        executorService.shutdown();
    }
}
