package com.chat.ai.rpc;

import com.google.protobuf.ByteString;
import io.netty.bootstrap.ServerBootstrap;
import io.netty.buffer.ByteBuf;
import io.netty.channel.*;
import io.netty.channel.nio.NioEventLoopGroup;
import io.netty.channel.socket.SocketChannel;
import io.netty.channel.socket.nio.NioServerSocketChannel;
import io.netty.handler.codec.ByteToMessageDecoder;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;
import java.util.function.Consumer;
import java.util.zip.Adler32;

public class InternalRpcServer {

    private static final Logger log = LoggerFactory.getLogger(InternalRpcServer.class);
    private static final int HEADER_LEN = 4;

    private final int port;
    private final Consumer<ChatProto.RpcMessage> requestHandler;
    private EventLoopGroup bossGroup;
    private EventLoopGroup workerGroup;
    private Channel serverChannel;

    public InternalRpcServer(int port, Consumer<ChatProto.RpcMessage> requestHandler) {
        this.port = port;
        this.requestHandler = requestHandler;
    }

    public void start() throws InterruptedException {
        bossGroup = new NioEventLoopGroup(1);
        workerGroup = new NioEventLoopGroup(4);

        ServerBootstrap bootstrap = new ServerBootstrap();
        bootstrap.group(bossGroup, workerGroup)
                .channel(NioServerSocketChannel.class)
                .childHandler(new ChannelInitializer<SocketChannel>() {
                    @Override
                    protected void initChannel(SocketChannel ch) {
                        ch.pipeline().addLast(new FrameDecoder());
                        ch.pipeline().addLast(new RequestDispatcher());
                    }
                })
                .option(ChannelOption.SO_BACKLOG, 128)
                .childOption(ChannelOption.SO_KEEPALIVE, true);

        ChannelFuture future = bootstrap.bind(port).sync();
        serverChannel = future.channel();
        log.info("Internal RPC Server started on port {}, waiting for C++ connections", port);
    }

    public void stop() {
        if (serverChannel != null) {
            serverChannel.close();
        }
        if (bossGroup != null) {
            bossGroup.shutdownGracefully();
        }
        if (workerGroup != null) {
            workerGroup.shutdownGracefully();
        }
        log.info("Internal RPC Server stopped");
    }

    private class RequestDispatcher extends SimpleChannelInboundHandler<ChatProto.RpcMessage> {
        @Override
        protected void channelRead0(ChannelHandlerContext ctx, ChatProto.RpcMessage msg) {
            if (msg.getType() == ChatProto.RpcMessage.Type.REQUEST) {
                requestHandler.accept(msg);

                try {
                    String method = msg.getMethodName();
                    ByteString responsePayload;

                    if ("UpdateCareerProfile".equals(method)) {
                        ChatProto.CareerAdviceRequest request = ChatProto.CareerAdviceRequest.parseFrom(msg.getPayload());
                        responsePayload = ChatProto.CareerAdviceResponse.newBuilder().build().toByteString();
                    } else {
                        ChatProto.InternalForwardRequest request = ChatProto.InternalForwardRequest.parseFrom(msg.getPayload());
                        ChatProto.InternalForwardResponse response = ChatProto.InternalForwardResponse.newBuilder()
                                .setSuccess(true)
                                .setTraceId(request.getTraceId())
                                .build();
                        responsePayload = response.toByteString();
                    }

                    ChatProto.RpcMessage responseMsg = ChatProto.RpcMessage.newBuilder()
                            .setType(ChatProto.RpcMessage.Type.RESPONSE)
                            .setId(msg.getId())
                            .setPayload(responsePayload)
                            .build();

                    ByteBuf buf = ctx.alloc().buffer();
                    encodeProtobuf(responseMsg, buf);
                    ctx.writeAndFlush(buf);

                } catch (Exception e) {
                    log.error("Error processing request id={}", msg.getId(), e);

                    ChatProto.RpcMessage errorMsg = ChatProto.RpcMessage.newBuilder()
                            .setType(ChatProto.RpcMessage.Type.ERROR)
                            .setId(msg.getId())
                            .setErrorCode(500)
                            .setErrorDesc(e.getMessage())
                            .build();

                    ByteBuf buf = ctx.alloc().buffer();
                    encodeProtobuf(errorMsg, buf);
                    ctx.writeAndFlush(buf);
                }
            }
        }

        @Override
        public void exceptionCaught(ChannelHandlerContext ctx, Throwable cause) {
            log.error("Internal RPC connection error", cause);
            ctx.close();
        }
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

    private static class FrameDecoder extends ByteToMessageDecoder {
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
}
