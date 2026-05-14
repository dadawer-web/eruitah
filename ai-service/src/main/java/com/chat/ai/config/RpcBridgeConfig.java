package com.chat.ai.config;

import com.chat.ai.rpc.*;
import com.chat.ai.service.AiChatRequestListener;
import com.chat.ai.service.FarmAiJudgeService;
import com.chat.ai.service.FarmService;
import com.chat.ai.service.GroupChatService;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.concurrent.Executor;
import java.util.concurrent.Executors;

@Configuration
public class RpcBridgeConfig {

    private static final Logger log = LoggerFactory.getLogger(RpcBridgeConfig.class);

    @Value("${rpc.cpp.host:127.0.0.1}")
    private String cppRpcHost;

    @Value("${rpc.cpp.port:8888}")
    private int cppRpcPort;

    @Value("${rpc.python.host:127.0.0.1}")
    private String pythonRpcHost;

    @Value("${rpc.python.port:9997}")
    private int pythonRpcPort;

    @Value("${rpc.internal.port:9999}")
    private int internalRpcPort;

    @Bean
    public ProtobufRpcClient cppRpcClient() {
        ProtobufRpcClient client = new ProtobufRpcClient(cppRpcHost, cppRpcPort);
        try {
            client.connect();
            log.info("Connected to C++ RPC at {}:{}", cppRpcHost, cppRpcPort);
        } catch (Exception e) {
            log.warn("Failed to connect to C++ RPC at {}:{}, will retry: {}", cppRpcHost, cppRpcPort, e.getMessage());
        }
        return client;
    }

    @Bean
    public ProtobufRpcClient pythonRpcClient() {
        ProtobufRpcClient client = new ProtobufRpcClient(pythonRpcHost, pythonRpcPort);
        try {
            client.connect();
            log.info("Connected to Python RPC at {}:{}", pythonRpcHost, pythonRpcPort);
        } catch (Exception e) {
            log.warn("Failed to connect to Python RPC at {}:{}, will retry: {}", pythonRpcHost, pythonRpcPort, e.getMessage());
        }
        return client;
    }

    @Bean
    public RpcPushService rpcPushService(ProtobufRpcClient cppRpcClient, ObjectMapper objectMapper) {
        return new RpcPushService(cppRpcClient, objectMapper);
    }

    @Bean
    public Executor rpcTaskExecutor() {
        return Executors.newFixedThreadPool(
                Runtime.getRuntime().availableProcessors(),
                r -> {
                    Thread t = new Thread(r, "rpc-task-");
                    t.setDaemon(true);
                    return t;
                });
    }

    @Bean
    public InternalRouterHandler internalRouterHandler(
            AiChatRequestListener aiChatRequestListener,
            FarmService farmService,
            FarmAiJudgeService farmAiJudgeService,
            GroupChatService groupChatService,
            ObjectMapper objectMapper,
            Executor rpcTaskExecutor) {
        return new InternalRouterHandler(aiChatRequestListener, farmService, farmAiJudgeService,
                groupChatService, objectMapper, rpcTaskExecutor);
    }

    @Bean
    public InternalRpcServer internalRpcServer(InternalRouterHandler handler) {
        InternalRpcServer server = new InternalRpcServer(internalRpcPort, handler);
        try {
            server.start();
            log.info("Internal RPC Server started on port {}, C++ can connect for ForwardToJava", internalRpcPort);
        } catch (Exception e) {
            log.error("Failed to start Internal RPC Server on port {}: {}", internalRpcPort, e.getMessage());
        }
        return server;
    }
}
