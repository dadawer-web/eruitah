package com.bridge.server;

import io.netty.buffer.ByteBuf;
import io.netty.channel.ChannelHandlerContext;
import io.netty.handler.codec.ByteToMessageDecoder;
import com.bridge.proto.ChatProto;
import com.google.protobuf.Message;
import java.util.List;

public class ProtobufDecoder extends ByteToMessageDecoder {
    
    private static final int HEADER_LEN = 4;
    private static final int MIN_MESSAGE_LEN = 2 * HEADER_LEN + 2;
    private static final int MAX_MESSAGE_LEN = 64 * 1024 * 1024;
    
    @Override
    protected void decode(ChannelHandlerContext ctx, ByteBuf in, List<Object> out) throws Exception {
        while (in.readableBytes() >= MIN_MESSAGE_LEN) {
            in.markReaderIndex();
            
            int totalLen = in.readInt();
            
            if (totalLen > MAX_MESSAGE_LEN || totalLen < MIN_MESSAGE_LEN) {
                throw new IllegalArgumentException("Invalid message length: " + totalLen);
            }
            
            if (in.readableBytes() < totalLen - HEADER_LEN) {
                in.resetReaderIndex();
                return;
            }
            
            int nameLen = in.readInt();
            if (nameLen < 2 || nameLen > totalLen - 2 * HEADER_LEN) {
                throw new IllegalArgumentException("Invalid name length: " + nameLen);
            }
            
            byte[] nameBytes = new byte[nameLen];
            in.readBytes(nameBytes);
            String typeName = new String(nameBytes, 0, nameLen - 1);
            
            int payloadLen = totalLen - 2 * HEADER_LEN - nameLen;
            byte[] payload = new byte[payloadLen];
            in.readBytes(payload);
            
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
            case "bridge.RpcMessage":
                return ChatProto.RpcMessage.parseFrom(payload);
            default:
                throw new IllegalArgumentException("Unknown message type: " + typeName);
        }
    }
}
