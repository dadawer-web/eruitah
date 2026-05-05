package com.bridge.server;

import com.bridge.proto.ChatProto;
import com.bridge.service.ChatService;
import com.google.protobuf.Message;
import io.netty.channel.ChannelHandlerContext;
import io.netty.channel.SimpleChannelInboundHandler;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

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
        } else if (msg instanceof ChatProto.CompanionReadRequest) {
            handleCompanionReadRequest(ctx, (ChatProto.CompanionReadRequest) msg);
        } else if (msg instanceof ChatProto.DashboardRequest) {
            handleDashboardRequest(ctx, (ChatProto.DashboardRequest) msg);
        } else if (msg instanceof ChatProto.DashboardSummaryRequest) {
            handleDashboardSummaryRequest(ctx, (ChatProto.DashboardSummaryRequest) msg);
        } else if (msg instanceof ChatProto.WeeklyReportRequest) {
            handleWeeklyReportRequest(ctx, (ChatProto.WeeklyReportRequest) msg);
        } else if (msg instanceof ChatProto.PdfParseRequest) {
            handlePdfParseRequest(ctx, (ChatProto.PdfParseRequest) msg);
        } else if (msg instanceof ChatProto.SandboxExecuteRequest) {
            handleSandboxExecuteRequest(ctx, (ChatProto.SandboxExecuteRequest) msg);
        } else if (msg instanceof ChatProto.SandboxTaskRequest) {
            handleSandboxTaskRequest(ctx, (ChatProto.SandboxTaskRequest) msg);
        } else if (msg instanceof ChatProto.SwarmRegisterRequest) {
            handleSwarmRegisterRequest(ctx, (ChatProto.SwarmRegisterRequest) msg);
        } else if (msg instanceof ChatProto.SwarmHelpRequest) {
            handleSwarmHelpRequest(ctx, (ChatProto.SwarmHelpRequest) msg);
        } else if (msg instanceof ChatProto.SwarmMessage) {
            handleSwarmMessage(ctx, (ChatProto.SwarmMessage) msg);
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
        logger.info("Direct chat request from user: {}, bot: {}", request.getUserId(), request.getBotId());
        executorService.submit(() -> {
            try {
                ctx.writeAndFlush(chatService.chat(request));
            } catch (Exception e) {
                logger.error("Error processing chat request", e);
                ctx.writeAndFlush(ChatProto.ChatResponse.newBuilder()
                        .setUserId(request.getUserId())
                        .setBotId(request.getBotId())
                        .setSuccess(false)
                        .setError("Internal error: " + e.getMessage())
                        .setTimestamp(System.currentTimeMillis())
                        .build());
            }
        });
    }

    private void handleGroupChatRequest(ChannelHandlerContext ctx, ChatProto.GroupChatRequest request) {
        logger.info("Group chat request from group: {}", request.getGroupId());
        executorService.submit(() -> {
            try {
                ctx.writeAndFlush(chatService.groupChat(request));
            } catch (Exception e) {
                logger.error("Error processing group chat request", e);
                ctx.writeAndFlush(ChatProto.GroupChatResponse.newBuilder()
                        .setGroupId(request.getGroupId())
                        .setSuccess(false)
                        .setError("Internal error: " + e.getMessage())
                        .setTimestamp(System.currentTimeMillis())
                        .build());
            }
        });
    }

    private void handleCompanionReadRequest(ChannelHandlerContext ctx, ChatProto.CompanionReadRequest request) {
        logger.info("Companion read request from user: {}", request.getUserId());
        executorService.submit(() -> {
            try {
                ctx.writeAndFlush(chatService.companionRead(request));
            } catch (Exception e) {
                logger.error("Error processing companion read request", e);
                ctx.writeAndFlush(ChatProto.CompanionReadResponse.newBuilder()
                        .setSuccess(false)
                        .setError("Internal error: " + e.getMessage())
                        .build());
            }
        });
    }

    private void handleDashboardRequest(ChannelHandlerContext ctx, ChatProto.DashboardRequest request) {
        logger.info("Dashboard request from user: {}", request.getUserId());
        executorService.submit(() -> {
            try {
                ctx.writeAndFlush(chatService.dashboard(request));
            } catch (Exception e) {
                logger.error("Error processing dashboard request", e);
                ctx.writeAndFlush(ChatProto.DashboardResponse.newBuilder()
                        .setUserId(request.getUserId())
                        .setError("Internal error: " + e.getMessage())
                        .build());
            }
        });
    }

    private void handleDashboardSummaryRequest(ChannelHandlerContext ctx, ChatProto.DashboardSummaryRequest request) {
        logger.info("Dashboard summary request from user: {}", request.getUserId());
        executorService.submit(() -> {
            try {
                ctx.writeAndFlush(chatService.dashboardSummary(request));
            } catch (Exception e) {
                logger.error("Error processing dashboard summary request", e);
                ctx.writeAndFlush(ChatProto.DashboardSummaryResponse.newBuilder()
                        .build());
            }
        });
    }

    private void handleWeeklyReportRequest(ChannelHandlerContext ctx, ChatProto.WeeklyReportRequest request) {
        logger.info("Weekly report request from user: {}", request.getUserId());
        executorService.submit(() -> {
            try {
                ctx.writeAndFlush(chatService.weeklyReport(request));
            } catch (Exception e) {
                logger.error("Error processing weekly report request", e);
                ctx.writeAndFlush(ChatProto.WeeklyReportResponse.newBuilder()
                        .setUserId(request.getUserId())
                        .setError("Internal error: " + e.getMessage())
                        .build());
            }
        });
    }

    private void handlePdfParseRequest(ChannelHandlerContext ctx, ChatProto.PdfParseRequest request) {
        logger.info("PDF parse request: filename={}", request.getFilename());
        executorService.submit(() -> {
            try {
                ctx.writeAndFlush(chatService.parsePdf(request));
            } catch (Exception e) {
                logger.error("Error processing PDF parse request", e);
                ctx.writeAndFlush(ChatProto.PdfParseResponse.newBuilder()
                        .setSuccess(false)
                        .setError("Internal error: " + e.getMessage())
                        .build());
            }
        });
    }

    private void handleSandboxExecuteRequest(ChannelHandlerContext ctx, ChatProto.SandboxExecuteRequest request) {
        logger.info("Sandbox execute request: prompt={}", request.getPrompt().substring(0, Math.min(50, request.getPrompt().length())));
        executorService.submit(() -> {
            try {
                ctx.writeAndFlush(chatService.sandboxExecute(request));
            } catch (Exception e) {
                logger.error("Error processing sandbox execute request", e);
                ctx.writeAndFlush(ChatProto.SandboxExecuteResponse.newBuilder()
                        .setSuccess(false)
                        .setError("Internal error: " + e.getMessage())
                        .setTimestamp(System.currentTimeMillis())
                        .build());
            }
        });
    }

    private void handleSandboxTaskRequest(ChannelHandlerContext ctx, ChatProto.SandboxTaskRequest request) {
        logger.info("Sandbox task request: action={}", request.getAction());
        executorService.submit(() -> {
            try {
                ctx.writeAndFlush(chatService.sandboxTask(request));
            } catch (Exception e) {
                logger.error("Error processing sandbox task request", e);
                ctx.writeAndFlush(ChatProto.SandboxTaskResponse.newBuilder()
                        .setSuccess(false)
                        .setAction(request.getAction())
                        .setError("Internal error: " + e.getMessage())
                        .build());
            }
        });
    }

    private void handleSwarmRegisterRequest(ChannelHandlerContext ctx, ChatProto.SwarmRegisterRequest request) {
        logger.info("Swarm register request: agentId={}", request.getAgentId());
        executorService.submit(() -> {
            try {
                ctx.writeAndFlush(chatService.swarmRegister(request));
            } catch (Exception e) {
                logger.error("Error processing swarm register request", e);
                ctx.writeAndFlush(ChatProto.SwarmRegisterResponse.newBuilder()
                        .setSuccess(false)
                        .setMessage("Internal error: " + e.getMessage())
                        .build());
            }
        });
    }

    private void handleSwarmHelpRequest(ChannelHandlerContext ctx, ChatProto.SwarmHelpRequest request) {
        logger.info("Swarm help request: fromId={}", request.getFromId());
        executorService.submit(() -> {
            try {
                ctx.writeAndFlush(chatService.swarmHelp(request));
            } catch (Exception e) {
                logger.error("Error processing swarm help request", e);
                ctx.writeAndFlush(ChatProto.SwarmHelpResponse.newBuilder()
                        .setFound(false)
                        .build());
            }
        });
    }

    private void handleSwarmMessage(ChannelHandlerContext ctx, ChatProto.SwarmMessage msg) {
        logger.info("Swarm message: type={}, from={}", msg.getType(), msg.getFromId());
        executorService.submit(() -> {
            try {
                switch (msg.getType()) {
                    case REGISTER:
                        ChatProto.SwarmRegisterRequest regReq = ChatProto.SwarmRegisterRequest.newBuilder()
                                .setAgentId(msg.getFromId())
                                .addAllCapabilities(msg.getCapabilitiesList())
                                .addAllSpecialties(msg.getSpecialtiesList())
                                .build();
                        ctx.writeAndFlush(chatService.swarmRegister(regReq));
                        break;
                    case HELP_REQUEST:
                        ChatProto.SwarmHelpRequest helpReq = ChatProto.SwarmHelpRequest.newBuilder()
                                .setFromId(msg.getFromId())
                                .setTask(msg.getTask())
                                .build();
                        ctx.writeAndFlush(chatService.swarmHelp(helpReq));
                        break;
                    case NODE_LIST:
                        ctx.writeAndFlush(chatService.swarmNodeList());
                        break;
                    default:
                        logger.info("Swarm message type {} handled locally", msg.getType());
                }
            } catch (Exception e) {
                logger.error("Error processing swarm message", e);
            }
        });
    }

    private Message processRequest(ChatProto.RpcMessage rpcMessage) throws Exception {
        String serviceName = rpcMessage.getServiceName();
        String methodName = rpcMessage.getMethodName();

        if ("ChatService".equals(serviceName)) {
            switch (methodName) {
                case "Chat":
                    return chatService.chat(ChatProto.ChatRequest.parseFrom(rpcMessage.getPayload()));
                case "GroupChat":
                    return chatService.groupChat(ChatProto.GroupChatRequest.parseFrom(rpcMessage.getPayload()));
                case "CompanionRead":
                    return chatService.companionRead(ChatProto.CompanionReadRequest.parseFrom(rpcMessage.getPayload()));
                case "Dashboard":
                    return chatService.dashboard(ChatProto.DashboardRequest.parseFrom(rpcMessage.getPayload()));
                case "DashboardSummary":
                    return chatService.dashboardSummary(ChatProto.DashboardSummaryRequest.parseFrom(rpcMessage.getPayload()));
                case "WeeklyReport":
                    return chatService.weeklyReport(ChatProto.WeeklyReportRequest.parseFrom(rpcMessage.getPayload()));
                case "ParsePdf":
                    return chatService.parsePdf(ChatProto.PdfParseRequest.parseFrom(rpcMessage.getPayload()));
                case "SandboxExecute":
                    return chatService.sandboxExecute(ChatProto.SandboxExecuteRequest.parseFrom(rpcMessage.getPayload()));
                case "SandboxTask":
                    return chatService.sandboxTask(ChatProto.SandboxTaskRequest.parseFrom(rpcMessage.getPayload()));
                case "SwarmRegister":
                    return chatService.swarmRegister(ChatProto.SwarmRegisterRequest.parseFrom(rpcMessage.getPayload()));
                case "SwarmHelp":
                    return chatService.swarmHelp(ChatProto.SwarmHelpRequest.parseFrom(rpcMessage.getPayload()));
                case "SwarmNodeList":
                    return chatService.swarmNodeList();
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
