package com.chat.ai.rpc;

import io.netty.bootstrap.Bootstrap;
import io.netty.buffer.ByteBuf;
import io.netty.channel.*;
import io.netty.channel.nio.NioEventLoopGroup;
import io.netty.channel.socket.SocketChannel;
import io.netty.channel.socket.nio.NioSocketChannel;
import io.netty.handler.codec.ByteToMessageDecoder;
import io.netty.handler.timeout.IdleState;
import io.netty.handler.timeout.IdleStateEvent;
import io.netty.handler.timeout.IdleStateHandler;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.function.Consumer;
import java.util.zip.Adler32;

public class ProtobufRpcClient {

    private static final Logger log = LoggerFactory.getLogger(ProtobufRpcClient.class);
    private static final int HEADER_LEN = 4;
    private static final long STREAM_TIMEOUT_SECONDS = 600;
    private static final long RECONNECT_DELAY_MS = 5000;

    private final String host;
    private final int port;
    private volatile Channel channel;
    private volatile boolean closed = false;
    private volatile int reconnectAttempts = 0;
    private final EventLoopGroup group = new NioEventLoopGroup(2);
    private final Map<Long, StreamContext> pendingStreams = new ConcurrentHashMap<>();
    private final Map<Long, UnaryContext<?>> pendingUnaries = new ConcurrentHashMap<>();
    private final ScheduledExecutorService timeoutScheduler = Executors.newSingleThreadScheduledExecutor(r -> {
        Thread t = new Thread(r, "rpc-timeout-");
        t.setDaemon(true);
        return t;
    });
    private final Map<Long, ScheduledFuture<?>> streamTimeouts = new ConcurrentHashMap<>();
    private final AtomicLong idCounter = new AtomicLong(0);

    public ProtobufRpcClient(String host, int port) {
        this.host = host;
        this.port = port;
    }

    public void connect() {
        closed = false;
        doConnect();
    }

    private void doConnect() {
        if (closed) return;

        Bootstrap bootstrap = new Bootstrap();
        bootstrap.group(group)
                .channel(NioSocketChannel.class)
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 5000)
                .option(ChannelOption.TCP_NODELAY, true)
                .handler(new ChannelInitializer<SocketChannel>() {
                    @Override
                    protected void initChannel(SocketChannel ch) {
                        ch.pipeline().addLast(new IdleStateHandler(600, 0, 0));
                        ch.pipeline().addLast(new ProtobufFrameDecoder());
                        ch.pipeline().addLast(new RpcMessageHandler());
                    }
                });

        bootstrap.connect(host, port).addListener((ChannelFutureListener) future -> {
            if (closed) return;
            if (future.isSuccess()) {
                channel = future.channel();
                reconnectAttempts = 0;
                log.info("Connected to RPC server at {}:{}", host, port);
            } else {
                reconnectAttempts++;
                if (reconnectAttempts <= 3) {
                    log.warn("Failed to connect to RPC server at {}:{}, retrying in {}ms (attempt {}): {}",
                             host, port, RECONNECT_DELAY_MS, reconnectAttempts, future.cause().getMessage());
                } else {
                    log.debug("Failed to connect to RPC server at {}:{}, retrying in {}ms (attempt {}): {}",
                              host, port, RECONNECT_DELAY_MS, reconnectAttempts, future.cause().getMessage());
                }
                scheduleReconnect();
            }
        });
    }

    private void scheduleReconnect() {
        if (closed) return;
        group.schedule(() -> doConnect(), RECONNECT_DELAY_MS, TimeUnit.MILLISECONDS);
    }

    public void disconnect() {
        closed = true;
        timeoutScheduler.shutdownNow();
        failAllPending("Client disconnecting");
        if (channel != null && channel.isActive()) {
            channel.close();
        }
        group.shutdownGracefully();
    }

    public boolean isConnected() {
        return channel != null && channel.isActive();
    }

    public <T extends com.google.protobuf.Message> void callUnary(
            String serviceName, String methodName,
            com.google.protobuf.Message request,
            Class<T> responseClass,
            Consumer<T> onResponse,
            Consumer<Throwable> onError) {

        if (!isConnected()) {
            if (onError != null) onError.accept(new RuntimeException("RPC not connected"));
            return;
        }

        long rpcId = idCounter.incrementAndGet();

        ChatProto.RpcMessage rpcMsg = ChatProto.RpcMessage.newBuilder()
                .setType(ChatProto.RpcMessage.Type.REQUEST)
                .setId(rpcId)
                .setServiceName(serviceName)
                .setMethodName(methodName)
                .setPayload(request.toByteString())
                .build();

        UnaryContext<T> ctx = new UnaryContext<>(rpcId, responseClass, onResponse, onError);
        pendingUnaries.put(rpcId, ctx);

        ByteBuf buf = channel.alloc().buffer();
        encodeProtobuf(rpcMsg, buf);
        channel.writeAndFlush(buf);

        log.info("Sent unary RPC: {}.{} id={}", serviceName, methodName, rpcId);
    }

    public void callStream(ChatProto.SandboxExecuteRequest request,
                           Consumer<ChatProto.SandboxToolEvent> onChunk,
                           Runnable onEnd,
                           Consumer<Throwable> onError) {
        if (!isConnected()) {
            if (onError != null) onError.accept(new RuntimeException("RPC not connected"));
            return;
        }

        long rpcId = idCounter.incrementAndGet();

        ChatProto.RpcMessage rpcMsg = ChatProto.RpcMessage.newBuilder()
                .setType(ChatProto.RpcMessage.Type.REQUEST)
                .setId(rpcId)
                .setServiceName("SwarmService")
                .setMethodName("Chat")
                .setPayload(request.toByteString())
                .build();

        StreamContext ctx = new StreamContext(rpcId, onChunk, onEnd, onError);
        pendingStreams.put(rpcId, ctx);

        ScheduledFuture<?> timeout = timeoutScheduler.schedule(() -> {
            StreamContext timedOut = pendingStreams.remove(rpcId);
            if (timedOut != null) {
                log.error("Stream RPC timed out: id={}", rpcId);
                if (timedOut.onError != null) {
                    timedOut.onError.accept(new RuntimeException("Stream timed out after " + STREAM_TIMEOUT_SECONDS + "s"));
                }
            }
            streamTimeouts.remove(rpcId);
        }, STREAM_TIMEOUT_SECONDS, TimeUnit.SECONDS);
        streamTimeouts.put(rpcId, timeout);

        ByteBuf buf = channel.alloc().buffer();
        encodeProtobuf(rpcMsg, buf);
        channel.writeAndFlush(buf);

        log.info("Sent streaming RPC: SwarmService.Chat id={}", rpcId);
    }

    private void completeStream(long rpcId) {
        streamTimeouts.remove(rpcId);
        pendingStreams.remove(rpcId);
    }

    private void failAllPending(String reason) {
        for (Map.Entry<Long, StreamContext> entry : pendingStreams.entrySet()) {
            ScheduledFuture<?> timeout = streamTimeouts.remove(entry.getKey());
            if (timeout != null) timeout.cancel(false);
            if (entry.getValue().onError != null) {
                entry.getValue().onError.accept(new RuntimeException(reason));
            }
        }
        pendingStreams.clear();

        for (Map.Entry<Long, UnaryContext<?>> entry : pendingUnaries.entrySet()) {
            if (entry.getValue().onError != null) {
                entry.getValue().onError.accept(new RuntimeException(reason));
            }
        }
        pendingUnaries.clear();
    }

    private void encodeProtobuf(ChatProto.RpcMessage message, ByteBuf out) {
        String typeName = message.getDescriptorForType().getFullName();
        byte[] nameBytes = typeName.getBytes();
        int nameLen = nameBytes.length + 1;
        byte[] payload = message.toByteArray();
        int payloadLen = payload.length;
        int totalLen = 2 * HEADER_LEN + nameLen + payloadLen;

        out.ensureWritable(totalLen + HEADER_LEN + HEADER_LEN);

        writeInt32LE(out, totalLen);
        writeInt32LE(out, nameLen);
        out.writeBytes(nameBytes);
        out.writeByte(0);
        out.writeBytes(payload);

        Adler32 adler32 = new Adler32();
        int dataLen = out.readableBytes();
        byte[] checkData = new byte[dataLen];
        out.getBytes(out.readerIndex(), checkData, 0, dataLen);
        adler32.update(checkData, 0, dataLen);
        writeInt32LE(out, (int) adler32.getValue());
    }

    private static void writeInt32LE(ByteBuf buf, int value) {
        buf.writeByte(value & 0xFF);
        buf.writeByte((value >> 8) & 0xFF);
        buf.writeByte((value >> 16) & 0xFF);
        buf.writeByte((value >> 24) & 0xFF);
    }

    private static int readInt32LE(byte[] data, int offset) {
        return (data[offset] & 0xFF)
                | ((data[offset + 1] & 0xFF) << 8)
                | ((data[offset + 2] & 0xFF) << 16)
                | ((data[offset + 3] & 0xFF) << 24);
    }

    private class RpcMessageHandler extends SimpleChannelInboundHandler<ChatProto.RpcMessage> {
        @Override
        protected void channelRead0(ChannelHandlerContext ctx, ChatProto.RpcMessage msg) {
            StreamContext streamCtx = pendingStreams.get(msg.getId());
            UnaryContext<?> unaryCtx = pendingUnaries.remove(msg.getId());

            if (msg.getType() == ChatProto.RpcMessage.Type.STREAM && streamCtx != null) {
                try {
                    ChatProto.SandboxToolEvent event = ChatProto.SandboxToolEvent.parseFrom(msg.getPayload());
                    streamCtx.onChunk.accept(event);
                } catch (Exception e) {
                    log.error("Failed to parse stream chunk id={}", msg.getId(), e);
                }
            } else if (msg.getType() == ChatProto.RpcMessage.Type.STREAM_END && streamCtx != null) {
                completeStream(msg.getId());
                streamCtx.onEnd.run();
            } else if (msg.getType() == ChatProto.RpcMessage.Type.ERROR) {
                String errorDesc = msg.getErrorDesc();
                int errorCode = msg.getErrorCode();
                log.error("RPC error: id={} code={} desc={}", msg.getId(), errorCode, errorDesc);

                if (streamCtx != null) {
                    completeStream(msg.getId());
                    streamCtx.onError.accept(new RuntimeException("RPC error [" + errorCode + "]: " + errorDesc));
                }
                if (unaryCtx != null) {
                    unaryCtx.onError.accept(new RuntimeException("RPC error [" + errorCode + "]: " + errorDesc));
                }
            } else if (msg.getType() == ChatProto.RpcMessage.Type.RESPONSE) {
                if (streamCtx != null) {
                    completeStream(msg.getId());
                    try {
                        ChatProto.SandboxToolEvent event = ChatProto.SandboxToolEvent.parseFrom(msg.getPayload());
                        streamCtx.onChunk.accept(event);
                    } catch (Exception e) {
                        log.error("Failed to parse response as stream chunk id={}", msg.getId(), e);
                    }
                    streamCtx.onEnd.run();
                }
                if (unaryCtx != null) {
                    try {
                        Object response = unaryCtx.responseClass.getDeclaredMethod("parseFrom", byte[].class)
                                .invoke(null, msg.getPayload().toByteArray());
                        @SuppressWarnings("unchecked")
                        java.util.function.Consumer<com.google.protobuf.Message> typedConsumer =
                                (java.util.function.Consumer<com.google.protobuf.Message>) unaryCtx.onResponse;
                        typedConsumer.accept((com.google.protobuf.Message) response);
                    } catch (Exception e) {
                        unaryCtx.onError.accept(e);
                    }
                }
            }
        }

        @Override
        public void exceptionCaught(ChannelHandlerContext ctx, Throwable cause) {
            log.error("RPC connection error, failing all pending requests", cause);
            failAllPending("Connection error: " + cause.getMessage());
            ctx.close();
        }

        @Override
        public void channelInactive(ChannelHandlerContext ctx) {
            log.warn("RPC connection to {}:{} closed by remote, failing all pending requests", host, port);
            failAllPending("Connection closed by remote");
            if (!closed) {
                scheduleReconnect();
            }
        }

        @Override
        public void userEventTriggered(ChannelHandlerContext ctx, Object evt) {
            if (evt instanceof IdleStateEvent) {
                IdleStateEvent ise = (IdleStateEvent) evt;
                if (ise.state() == IdleState.READER_IDLE) {
                    log.warn("RPC connection to {}:{} read idle (server dead?), closing to trigger reconnect", host, port);
                    ctx.close();
                }
            }
        }
    }

    private static class ProtobufFrameDecoder extends ByteToMessageDecoder {
        @Override
        protected void decode(ChannelHandlerContext ctx, ByteBuf in, List<Object> out) throws Exception {
            while (in.readableBytes() >= HEADER_LEN * 3 + 2) {
                in.markReaderIndex();

                int totalLen = in.readIntLE();
                if (totalLen < 2 * HEADER_LEN + 2) {
                    throw new IllegalArgumentException("Invalid message length: " + totalLen);
                }

                if (in.readableBytes() < totalLen) {
                    in.resetReaderIndex();
                    return;
                }

                in.resetReaderIndex();

                byte[] frame = new byte[totalLen + HEADER_LEN];
                in.readBytes(frame);

                int offset = 0;
                int readTotalLen = readInt32LE(frame, offset);
                offset += HEADER_LEN;

                int nameLen = readInt32LE(frame, offset);
                offset += HEADER_LEN;

                String typeName = new String(frame, offset, nameLen - 1);
                offset += nameLen;

                int payloadLen = readTotalLen - 2 * HEADER_LEN - nameLen;
                byte[] payload = new byte[payloadLen];
                System.arraycopy(frame, offset, payload, 0, payloadLen);
                offset += payloadLen;

                int receivedCheckSum = readInt32LE(frame, offset);

                Adler32 adler32 = new Adler32();
                adler32.update(frame, 0, readTotalLen);
                int computedCheckSum = (int) adler32.getValue();

                if (computedCheckSum != receivedCheckSum) {
                    throw new IllegalArgumentException(
                            "Checksum mismatch: expected=" + receivedCheckSum + " actual=" + computedCheckSum);
                }

                if ("bridge.RpcMessage".equals(typeName)) {
                    out.add(ChatProto.RpcMessage.parseFrom(payload));
                }
            }
        }
    }

    private static class StreamContext {
        final long id;
        final Consumer<ChatProto.SandboxToolEvent> onChunk;
        final Runnable onEnd;
        final Consumer<Throwable> onError;

        StreamContext(long id, Consumer<ChatProto.SandboxToolEvent> onChunk, Runnable onEnd, Consumer<Throwable> onError) {
            this.id = id;
            this.onChunk = onChunk;
            this.onEnd = onEnd;
            this.onError = onError;
        }
    }

    private static class UnaryContext<T extends com.google.protobuf.Message> {
        final long id;
        final Class<T> responseClass;
        final Consumer<T> onResponse;
        final Consumer<Throwable> onError;

        UnaryContext(long id, Class<T> responseClass, Consumer<T> onResponse, Consumer<Throwable> onError) {
            this.id = id;
            this.responseClass = responseClass;
            this.onResponse = onResponse;
            this.onError = onError;
        }
    }
}
