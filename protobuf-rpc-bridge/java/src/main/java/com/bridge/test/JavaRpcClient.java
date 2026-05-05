package com.bridge.test;

import com.bridge.proto.ChatProto;
import com.bridge.server.ProtobufEncoder;
import io.netty.bootstrap.Bootstrap;
import io.netty.buffer.ByteBuf;
import io.netty.channel.*;
import io.netty.channel.nio.NioEventLoopGroup;
import io.netty.channel.socket.SocketChannel;
import io.netty.channel.socket.nio.NioSocketChannel;
import io.netty.handler.codec.ByteToMessageDecoder;

import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.zip.Adler32;

public class JavaRpcClient {

    private static final int HEADER_LEN = 4;
    private Channel channel;
    private final CountDownLatch responseLatch = new CountDownLatch(1);
    private volatile ChatProto.RpcMessage response;

    public static void main(String[] args) throws Exception {
        String host = args.length > 0 ? args[0] : "127.0.0.1";
        int port = args.length > 1 ? Integer.parseInt(args[1]) : 9998;

        JavaRpcClient client = new JavaRpcClient();
        client.connect(host, port);

        try {
            Thread.sleep(500);

            ChatProto.SandboxExecuteRequest sandboxReq = ChatProto.SandboxExecuteRequest.newBuilder()
                    .setPrompt("Write a hello world program in Python")
                    .setModel("gpt-4o")
                    .setMaxTurns(5)
                    .build();

            ChatProto.RpcMessage rpcMsg = ChatProto.RpcMessage.newBuilder()
                    .setType(ChatProto.RpcMessage.Type.REQUEST)
                    .setId(1)
                    .setServiceName("SandboxService")
                    .setMethodName("Execute")
                    .setPayload(sandboxReq.toByteString())
                    .build();

            System.out.println("Sending SandboxService.Execute RPC to " + host + ":" + port);
            client.send(rpcMsg);

            ChatProto.RpcMessage resp = client.waitForResponse(10);
            if (resp != null) {
                System.out.println("Received RPC response: id=" + resp.getId()
                        + " service=" + resp.getServiceName()
                        + " method=" + resp.getMethodName()
                        + " error_code=" + resp.getErrorCode()
                        + " error_desc=" + resp.getErrorDesc());

                if (resp.getPayload() != null && !resp.getPayload().isEmpty()) {
                    ChatProto.SandboxExecuteResponse sandboxResp =
                            ChatProto.SandboxExecuteResponse.parseFrom(resp.getPayload());
                    System.out.println("Sandbox response: success=" + sandboxResp.getSuccess()
                            + " result=" + sandboxResp.getFinalResult().substring(0, Math.min(100, sandboxResp.getFinalResult().length())));
                }
            } else {
                System.out.println("No response received (timeout)");
            }

        } finally {
            client.disconnect();
        }
    }

    public void connect(String host, int port) throws Exception {
        EventLoopGroup group = new NioEventLoopGroup();
        Bootstrap bootstrap = new Bootstrap();
        bootstrap.group(group)
                .channel(NioSocketChannel.class)
                .handler(new ChannelInitializer<SocketChannel>() {
                    @Override
                    protected void initChannel(SocketChannel ch) {
                        ch.pipeline().addLast(new ProtobufEncoder());
                        ch.pipeline().addLast(new ClientDecoder());
                        ch.pipeline().addLast(new ClientHandler());
                    }
                });

        ChannelFuture future = bootstrap.connect(host, port).sync();
        channel = future.channel();
        System.out.println("Connected to " + host + ":" + port);
    }

    public void send(ChatProto.RpcMessage msg) {
        channel.writeAndFlush(msg);
    }

    public ChatProto.RpcMessage waitForResponse(int timeoutSeconds) throws InterruptedException {
        responseLatch.await(timeoutSeconds, TimeUnit.SECONDS);
        return response;
    }

    public void disconnect() {
        if (channel != null) {
            channel.close();
        }
        channel.eventLoop().parent().shutdownGracefully();
    }

    private class ClientHandler extends SimpleChannelInboundHandler<ChatProto.RpcMessage> {
        @Override
        protected void channelRead0(ChannelHandlerContext ctx, ChatProto.RpcMessage msg) {
            System.out.println("Client received: type=" + msg.getType() + " id=" + msg.getId());
            response = msg;
            responseLatch.countDown();
        }

        @Override
        public void exceptionCaught(ChannelHandlerContext ctx, Throwable cause) {
            System.err.println("Client error: " + cause.getMessage());
            cause.printStackTrace();
        }
    }

    private static class ClientDecoder extends ByteToMessageDecoder {
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

        private static int readInt32LE(byte[] data, int offset) {
            return (data[offset] & 0xFF)
                    | ((data[offset + 1] & 0xFF) << 8)
                    | ((data[offset + 2] & 0xFF) << 16)
                    | ((data[offset + 3] & 0xFF) << 24);
        }
    }
}
