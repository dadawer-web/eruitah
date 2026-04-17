package com.bridge.server;

import io.netty.buffer.ByteBuf;
import io.netty.channel.ChannelHandlerContext;
import io.netty.handler.codec.MessageToByteEncoder;
import com.google.protobuf.Message;
import java.util.zip.Adler32;

public class ProtobufEncoder extends MessageToByteEncoder<Message> {

    private static final int HEADER_LEN = 4;

    @Override
    protected void encode(ChannelHandlerContext ctx, Message msg, ByteBuf out) throws Exception {
        String typeName = msg.getDescriptorForType().getFullName();
        byte[] nameBytes = typeName.getBytes();
        byte[] payload = msg.toByteArray();

        int nameLen = nameBytes.length + 1;
        int totalLen = 2 * HEADER_LEN + nameLen + payload.length;

        out.writeInt(totalLen);
        out.writeInt(nameLen);
        out.writeBytes(nameBytes);
        out.writeByte(0);
        out.writeBytes(payload);

        Adler32 adler32 = new Adler32();
        int checkStartIdx = out.writerIndex() - totalLen - HEADER_LEN;
        int checkLen = totalLen + HEADER_LEN;
        byte[] dataToChecksum = new byte[checkLen];
        out.getBytes(checkStartIdx, dataToChecksum);
        adler32.update(dataToChecksum);
        out.writeInt((int) adler32.getValue());
    }
}
