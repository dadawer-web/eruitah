package com.bridge.server;

import io.netty.buffer.ByteBuf;
import io.netty.channel.ChannelHandlerContext;
import io.netty.handler.codec.ByteToMessageDecoder;
import com.bridge.proto.ChatProto;
import com.google.protobuf.Message;
import java.util.List;
import java.util.zip.Adler32;

public class ProtobufDecoder extends ByteToMessageDecoder {

    private static final int HEADER_LEN = 4;

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

            if (nameLen < 2) {
                throw new IllegalArgumentException("Invalid name length: " + nameLen);
            }

            String typeName = new String(frame, offset, nameLen - 1);
            offset += nameLen;

            int payloadLen = readTotalLen - 2 * HEADER_LEN - nameLen;
            if (payloadLen < 0) {
                throw new IllegalArgumentException("Invalid payload length: " + payloadLen);
            }

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

            Message message = parseMessage(typeName, payload);
            if (message != null) {
                out.add(message);
            }
        }
    }

    private static int readInt32LE(byte[] data, int offset) {
        return (data[offset] & 0xFF)
                | ((data[offset + 1] & 0xFF) << 8)
                | ((data[offset + 2] & 0xFF) << 16)
                | ((data[offset + 3] & 0xFF) << 24);
    }

    private Message parseMessage(String typeName, byte[] payload) throws Exception {
        switch (typeName) {
            case "bridge.ChatRequest": return ChatProto.ChatRequest.parseFrom(payload);
            case "bridge.ChatResponse": return ChatProto.ChatResponse.parseFrom(payload);
            case "bridge.GroupChatRequest": return ChatProto.GroupChatRequest.parseFrom(payload);
            case "bridge.GroupChatResponse": return ChatProto.GroupChatResponse.parseFrom(payload);
            case "bridge.CompanionReadRequest": return ChatProto.CompanionReadRequest.parseFrom(payload);
            case "bridge.CompanionReadResponse": return ChatProto.CompanionReadResponse.parseFrom(payload);
            case "bridge.DashboardRequest": return ChatProto.DashboardRequest.parseFrom(payload);
            case "bridge.DashboardResponse": return ChatProto.DashboardResponse.parseFrom(payload);
            case "bridge.DashboardSummaryRequest": return ChatProto.DashboardSummaryRequest.parseFrom(payload);
            case "bridge.DashboardSummaryResponse": return ChatProto.DashboardSummaryResponse.parseFrom(payload);
            case "bridge.WeeklyReportRequest": return ChatProto.WeeklyReportRequest.parseFrom(payload);
            case "bridge.WeeklyReportResponse": return ChatProto.WeeklyReportResponse.parseFrom(payload);
            case "bridge.PdfParseRequest": return ChatProto.PdfParseRequest.parseFrom(payload);
            case "bridge.PdfParseResponse": return ChatProto.PdfParseResponse.parseFrom(payload);
            case "bridge.SandboxExecuteRequest": return ChatProto.SandboxExecuteRequest.parseFrom(payload);
            case "bridge.SandboxExecuteResponse": return ChatProto.SandboxExecuteResponse.parseFrom(payload);
            case "bridge.SandboxTaskRequest": return ChatProto.SandboxTaskRequest.parseFrom(payload);
            case "bridge.SandboxTaskResponse": return ChatProto.SandboxTaskResponse.parseFrom(payload);
            case "bridge.SandboxToolEvent": return ChatProto.SandboxToolEvent.parseFrom(payload);
            case "bridge.SwarmMessage": return ChatProto.SwarmMessage.parseFrom(payload);
            case "bridge.SwarmRegisterRequest": return ChatProto.SwarmRegisterRequest.parseFrom(payload);
            case "bridge.SwarmRegisterResponse": return ChatProto.SwarmRegisterResponse.parseFrom(payload);
            case "bridge.SwarmHelpRequest": return ChatProto.SwarmHelpRequest.parseFrom(payload);
            case "bridge.SwarmHelpResponse": return ChatProto.SwarmHelpResponse.parseFrom(payload);
            case "bridge.SwarmNodeListResponse": return ChatProto.SwarmNodeListResponse.parseFrom(payload);
            case "bridge.RpcMessage": return ChatProto.RpcMessage.parseFrom(payload);
            default: throw new IllegalArgumentException("Unknown message type: " + typeName);
        }
    }
}
