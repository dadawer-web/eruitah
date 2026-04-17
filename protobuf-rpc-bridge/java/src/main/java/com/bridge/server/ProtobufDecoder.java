package com.bridge.server;

import io.netty.buffer.ByteBuf;
import io.netty.channel.ChannelHandlerContext;
import io.netty.handler.codec.ByteToMessageDecoder;
import com.bridge.proto.ChatProto;
import com.google.protobuf.Message;
import java.util.List;

public class ProtobufDecoder extends ByteToMessageDecoder {

    private static final int HEADER_LEN = 4;

    @Override
    protected void decode(ChannelHandlerContext ctx, ByteBuf in, List<Object> out) throws Exception {
        while (in.readableBytes() >= HEADER_LEN * 3 + 2) {
            in.markReaderIndex();

            int totalLen = in.readInt();
            if (totalLen < 2 * HEADER_LEN + 2) {
                throw new IllegalArgumentException("Invalid message length: " + totalLen);
            }

            int remainingAfterTotalLen = totalLen + HEADER_LEN;
            if (in.readableBytes() < remainingAfterTotalLen) {
                in.resetReaderIndex();
                return;
            }

            int nameLen = in.readInt();
            if (nameLen < 2) {
                throw new IllegalArgumentException("Invalid name length: " + nameLen);
            }

            byte[] nameBytes = new byte[nameLen];
            in.readBytes(nameBytes);
            String typeName = new String(nameBytes, 0, nameLen - 1);

            int payloadLen = totalLen - 2 * HEADER_LEN - nameLen;
            if (payloadLen < 0) {
                throw new IllegalArgumentException("Invalid payload length: " + payloadLen);
            }

            byte[] payload = new byte[payloadLen];
            in.readBytes(payload);

            int receivedCheckSum = in.readInt();

            java.util.zip.Adler32 adler32 = new java.util.zip.Adler32();
            byte[] dataToCheck = new byte[totalLen + HEADER_LEN];
            in.resetReaderIndex();
            in.readBytes(dataToCheck, 0, totalLen + HEADER_LEN);
            in.skipBytes(HEADER_LEN);

            adler32.update(dataToCheck);
            int computedCheckSum = (int) adler32.getValue();

            if (computedCheckSum != receivedCheckSum) {
                throw new IllegalArgumentException("Checksum mismatch: expected=" + receivedCheckSum + " actual=" + computedCheckSum);
            }

            Message message = parseMessage(typeName, payload);
            if (message != null) {
                out.add(message);
            }
        }
    }

    private Message parseMessage(String typeName, byte[] payload) throws Exception {
        switch (typeName) {
            case "bridge.ChatRequest":
                return ChatProto.ChatRequest.parseFrom(payload);
            case "bridge.ChatResponse":
                return ChatProto.ChatResponse.parseFrom(payload);
            case "bridge.GroupChatRequest":
                return ChatProto.GroupChatRequest.parseFrom(payload);
            case "bridge.GroupChatResponse":
                return ChatProto.GroupChatResponse.parseFrom(payload);
            case "bridge.RpcMessage":
                return ChatProto.RpcMessage.parseFrom(payload);
            default:
                throw new IllegalArgumentException("Unknown message type: " + typeName);
        }
    }
}
