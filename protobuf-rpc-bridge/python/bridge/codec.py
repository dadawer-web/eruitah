import struct
import zlib
from google.protobuf.message import Message as ProtobufMessage
from bridge import chat_pb2

HEADER_LEN = 4
MIN_MESSAGE_LEN = 2 * HEADER_LEN + 2
MAX_MESSAGE_LEN = 64 * 1024 * 1024

_TYPE_MAP = {
    "bridge.ChatRequest": chat_pb2.ChatRequest,
    "bridge.ChatResponse": chat_pb2.ChatResponse,
    "bridge.GroupChatRequest": chat_pb2.GroupChatRequest,
    "bridge.GroupChatResponse": chat_pb2.GroupChatResponse,
    "bridge.CompanionReadRequest": chat_pb2.CompanionReadRequest,
    "bridge.CompanionReadResponse": chat_pb2.CompanionReadResponse,
    "bridge.DashboardRequest": chat_pb2.DashboardRequest,
    "bridge.DashboardResponse": chat_pb2.DashboardResponse,
    "bridge.DashboardSummaryRequest": chat_pb2.DashboardSummaryRequest,
    "bridge.DashboardSummaryResponse": chat_pb2.DashboardSummaryResponse,
    "bridge.WeeklyReportRequest": chat_pb2.WeeklyReportRequest,
    "bridge.WeeklyReportResponse": chat_pb2.WeeklyReportResponse,
    "bridge.PdfParseRequest": chat_pb2.PdfParseRequest,
    "bridge.PdfParseResponse": chat_pb2.PdfParseResponse,
    "bridge.SandboxExecuteRequest": chat_pb2.SandboxExecuteRequest,
    "bridge.SandboxExecuteResponse": chat_pb2.SandboxExecuteResponse,
    "bridge.SandboxTaskRequest": chat_pb2.SandboxTaskRequest,
    "bridge.SandboxTaskResponse": chat_pb2.SandboxTaskResponse,
    "bridge.SandboxToolEvent": chat_pb2.SandboxToolEvent,
    "bridge.SwarmMessage": chat_pb2.SwarmMessage,
    "bridge.SwarmRegisterRequest": chat_pb2.SwarmRegisterRequest,
    "bridge.SwarmRegisterResponse": chat_pb2.SwarmRegisterResponse,
    "bridge.SwarmHelpRequest": chat_pb2.SwarmHelpRequest,
    "bridge.SwarmHelpResponse": chat_pb2.SwarmHelpResponse,
    "bridge.SwarmNodeListResponse": chat_pb2.SwarmNodeListResponse,
    "bridge.RpcMessage": chat_pb2.RpcMessage,
}


def encode(message: ProtobufMessage) -> bytes:
    type_name = message.DESCRIPTOR.full_name
    name_bytes = type_name.encode("utf-8")
    name_len = len(name_bytes) + 1
    payload = message.SerializeToString()
    payload_len = len(payload)
    total_len = 2 * HEADER_LEN + name_len + payload_len

    header = struct.pack("<II", total_len, name_len)
    body = name_bytes + b"\x00" + payload

    checksum_data = header + body
    checksum = zlib.adler32(checksum_data) & 0xFFFFFFFF

    return checksum_data + struct.pack("<I", checksum)


def decode(data: bytes) -> ProtobufMessage:
    offset = 0

    total_len = struct.unpack_from("<I", data, offset)[0]
    offset += HEADER_LEN

    name_len = struct.unpack_from("<I", data, offset)[0]
    offset += HEADER_LEN

    type_name = data[offset : offset + name_len - 1].decode("utf-8")
    offset += name_len

    payload_len = total_len - 2 * HEADER_LEN - name_len
    payload = data[offset : offset + payload_len]
    offset += payload_len

    expected_checksum = struct.unpack_from("<I", data, offset)[0]

    check_data = data[:offset]
    computed_checksum = zlib.adler32(check_data) & 0xFFFFFFFF
    if computed_checksum != expected_checksum:
        raise ValueError(
            f"Checksum mismatch: expected={expected_checksum}, got={computed_checksum}"
        )

    msg_class = _TYPE_MAP.get(type_name)
    if msg_class is None:
        raise ValueError(f"Unknown message type: {type_name}")

    msg = msg_class()
    msg.ParseFromString(payload)
    return msg


class ProtobufCodec:
    def __init__(self):
        self._buffer = bytearray()

    def feed(self, data: bytes, callback):
        self._buffer.extend(data)
        while len(self._buffer) >= MIN_MESSAGE_LEN + HEADER_LEN:
            total_len = struct.unpack_from("<I", self._buffer, 0)[0]
            if total_len < MIN_MESSAGE_LEN or total_len > MAX_MESSAGE_LEN:
                raise ValueError(f"Invalid message length: {total_len}")

            frame_len = total_len + HEADER_LEN
            if len(self._buffer) < frame_len:
                break

            frame = bytes(self._buffer[:frame_len])
            self._buffer = self._buffer[frame_len:]

            message = decode(frame)
            callback(message)
