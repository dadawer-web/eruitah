package com.bridge.test;

import com.bridge.proto.ChatProto;
import java.io.*;
import java.util.zip.Adler32;

public class CrossLangTest {
    private static final int HEADER_LEN = 4;

    public static void main(String[] args) throws Exception {
        if (args.length < 2) {
            System.err.println("Usage: CrossLangTest <encode|decode> <file>");
            return;
        }

        String mode = args[0];
        String filename = args[1];

        if ("encode".equals(mode)) {
            ChatProto.ChatRequest request = ChatProto.ChatRequest.newBuilder()
                    .setUserId(3)
                    .setBotId(10002)
                    .setUserName("java_tester")
                    .setMessage("hello from Java")
                    .setSessionId("java_session_1")
                    .setTimestamp(3000)
                    .build();

            String typeName = request.getDescriptorForType().getFullName();
            byte[] nameBytes = typeName.getBytes();
            byte[] payload = request.toByteArray();

            int nameLen = nameBytes.length + 1;
            int totalLen = 2 * HEADER_LEN + nameLen + payload.length;

            ByteArrayOutputStream baos = new ByteArrayOutputStream();
            DataOutputStream dos = new DataOutputStream(baos);
            writeInt32LE(dos, totalLen);
            writeInt32LE(dos, nameLen);
            dos.write(nameBytes);
            dos.writeByte(0);
            dos.write(payload);

            Adler32 adler32 = new Adler32();
            byte[] dataToChecksum = baos.toByteArray();
            adler32.update(dataToChecksum);
            int checksum = (int) adler32.getValue();
            writeInt32LE(dos, checksum);

            byte[] result = baos.toByteArray();

            FileOutputStream fos = new FileOutputStream(filename);
            fos.write(result);
            fos.close();

            System.out.println("Encoded ChatRequest to " + filename);
            System.out.println("  totalLen=" + totalLen + " nameLen=" + nameLen
                    + " payloadLen=" + payload.length + " checksum=" + checksum);
        }
        else if ("decode".equals(mode)) {
            File file = new File(filename);
            byte[] data = new byte[(int) file.length()];
            FileInputStream fis = new FileInputStream(file);
            fis.read(data);
            fis.close();

            int totalLen = readInt32LE(data, 0);
            int nameLen = readInt32LE(data, 4);

            String typeName = new String(data, 8, nameLen - 1);
            int payloadLen = totalLen - 8 - nameLen;
            byte[] payload = new byte[payloadLen];
            System.arraycopy(data, 8 + nameLen, payload, 0, payloadLen);

            int expectedChecksum = readInt32LE(data, 8 + nameLen + payloadLen);

            Adler32 adler32 = new Adler32();
            adler32.update(data, 0, 8 + nameLen + payloadLen);
            int computedChecksum = (int) adler32.getValue();

            System.out.println("Decoding from " + filename);
            System.out.println("  totalLen=" + totalLen + " nameLen=" + nameLen
                    + " payloadLen=" + payloadLen);
            System.out.println("  typeName=" + typeName);
            System.out.println("  expectedChecksum=" + expectedChecksum
                    + " computedChecksum=" + computedChecksum);

            if (expectedChecksum != computedChecksum) {
                System.err.println("  CHECKSUM MISMATCH!");
                System.exit(1);
            }

            if ("bridge.ChatRequest".equals(typeName)) {
                ChatProto.ChatRequest request = ChatProto.ChatRequest.parseFrom(payload);
                System.out.println("  ChatRequest: user_id=" + request.getUserId()
                        + " bot_id=" + request.getBotId()
                        + " message=" + request.getMessage());
            } else if ("bridge.RpcMessage".equals(typeName)) {
                ChatProto.RpcMessage rpc = ChatProto.RpcMessage.parseFrom(payload);
                System.out.println("  RpcMessage: id=" + rpc.getId()
                        + " service=" + rpc.getServiceName()
                        + " method=" + rpc.getMethodName());
            }

            System.out.println("  CHECKSUM OK!");
        }
    }

    private static int readInt32LE(byte[] data, int offset) {
        return (data[offset] & 0xFF)
                | ((data[offset + 1] & 0xFF) << 8)
                | ((data[offset + 2] & 0xFF) << 16)
                | ((data[offset + 3] & 0xFF) << 24);
    }

    private static void writeInt32LE(DataOutputStream dos, int value) throws IOException {
        dos.writeByte(value & 0xFF);
        dos.writeByte((value >> 8) & 0xFF);
        dos.writeByte((value >> 16) & 0xFF);
        dos.writeByte((value >> 24) & 0xFF);
    }
}
