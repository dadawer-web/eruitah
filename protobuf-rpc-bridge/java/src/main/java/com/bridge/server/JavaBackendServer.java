package com.bridge.server;

import com.bridge.service.ChatService;
import com.bridge.service.impl.AIChatService;
import io.netty.bootstrap.ServerBootstrap;
import io.netty.channel.*;
import io.netty.channel.nio.NioEventLoopGroup;
import io.netty.channel.socket.SocketChannel;
import io.netty.channel.socket.nio.NioServerSocketChannel;
import io.netty.handler.logging.LogLevel;
import io.netty.handler.logging.LoggingHandler;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class JavaBackendServer {

    private static final Logger logger = LoggerFactory.getLogger(JavaBackendServer.class);

    private final int port;
    private final ChatService chatService;
    private EventLoopGroup bossGroup;
    private EventLoopGroup workerGroup;
    private Channel serverChannel;

    public JavaBackendServer(int port) {
        this.port = port;
        this.chatService = new AIChatService();
    }

    public void start() throws InterruptedException {
        bossGroup = new NioEventLoopGroup(1);
        workerGroup = new NioEventLoopGroup();

        try {
            ServerBootstrap bootstrap = new ServerBootstrap();
            bootstrap.group(bossGroup, workerGroup)
                    .channel(NioServerSocketChannel.class)
                    .handler(new LoggingHandler(LogLevel.INFO))
                    .childHandler(new ChannelInitializer<SocketChannel>() {
                        @Override
                        protected void initChannel(SocketChannel ch) {
                            ChannelPipeline pipeline = ch.pipeline();
                            pipeline.addLast("decoder", new ProtobufDecoder());
                            pipeline.addLast("encoder", new ProtobufEncoder());
                            pipeline.addLast("handler", new RpcMessageHandler(chatService));
                        }
                    })
                    .option(ChannelOption.SO_BACKLOG, 128)
                    .childOption(ChannelOption.SO_KEEPALIVE, true)
                    .childOption(ChannelOption.TCP_NODELAY, true);

            ChannelFuture future = bootstrap.bind(port).sync();
            serverChannel = future.channel();

            logger.info("=============================================");
            logger.info("Java Backend Server started on port {}", port);
            logger.info("Ready to accept Protobuf RPC connections from C++ muduo bridge");
            logger.info("Supported services: ChatService.Chat, ChatService.GroupChat");
            logger.info("=============================================");

            serverChannel.closeFuture().sync();
        } finally {
            shutdown();
        }
    }

    public void shutdown() {
        logger.info("Shutting down Java Backend Server...");

        if (serverChannel != null) {
            serverChannel.close();
        }
        if (bossGroup != null) {
            bossGroup.shutdownGracefully();
        }
        if (workerGroup != null) {
            workerGroup.shutdownGracefully();
        }

        logger.info("Java Backend Server stopped");
    }

    public static void main(String[] args) {
        int port = 9999;

        if (args.length > 0) {
            try {
                port = Integer.parseInt(args[0]);
            } catch (NumberFormatException e) {
                logger.warn("Invalid port number: {}, using default port 9999", args[0]);
            }
        }

        JavaBackendServer server = new JavaBackendServer(port);

        Runtime.getRuntime().addShutdownHook(new Thread(server::shutdown));

        try {
            server.start();
        } catch (InterruptedException e) {
            logger.error("Server interrupted", e);
            Thread.currentThread().interrupt();
        }
    }
}
