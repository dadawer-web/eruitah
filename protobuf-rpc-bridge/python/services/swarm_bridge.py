import asyncio
import json
import logging
import os
import socket
import threading
import time
import uuid
from typing import Callable, Dict, List, Optional

from bridge import chat_pb2

logger = logging.getLogger(__name__)

DEFAULT_HUB_HOST = os.environ.get("ERUITAH_SWARM_HOST", "127.0.0.1")
DEFAULT_HUB_PORT = int(os.environ.get("ERUITAH_SWARM_PORT", "9000"))
BUFFER_SIZE = 65536
MESSAGE_DELIMITER = b"\n"


class SwarmBridge:
    """
    Protobuf-RPC-Bridge <-> eruitah-sandbox Swarm Hub 桥接

    连接到 eruitah-sandbox 的 Swarm Hub (TCP JSON 换行符协议)，
    将 Swarm 消息转换为 Protobuf 格式转发给 Java/C++ 后端，
    同时将 Java/C++ 后端的 Protobuf SwarmMessage 转发到 Swarm Hub。

    协议映射:
      Swarm Hub JSON  <-->  Protobuf SwarmMessage
      {"type": "register", ...}  <-->  SwarmMessage.REGISTER
      {"type": "broadcast", ...}  <-->  SwarmMessage.BROADCAST
      {"type": "direct", ...}  <-->  SwarmMessage.DIRECT
      {"type": "help_request", ...}  <-->  SwarmMessage.HELP_REQUEST
      {"type": "help_response", ...}  <-->  SwarmMessage.HELP_RESPONSE
    """

    TYPE_MAP_JSON_TO_PB = {
        "register": chat_pb2.SwarmMessage.REGISTER,
        "broadcast": chat_pb2.SwarmMessage.BROADCAST,
        "direct": chat_pb2.SwarmMessage.DIRECT,
        "help_request": chat_pb2.SwarmMessage.HELP_REQUEST,
        "help_response": chat_pb2.SwarmMessage.HELP_RESPONSE,
        "node_list": chat_pb2.SwarmMessage.NODE_LIST,
        "heartbeat": chat_pb2.SwarmMessage.HEARTBEAT,
    }

    TYPE_MAP_PB_TO_JSON = {v: k for k, v in TYPE_MAP_JSON_TO_PB.items()}

    def __init__(
        self,
        agent_id: str = "protobuf_bridge",
        capabilities: Optional[List[str]] = None,
        specialties: Optional[List[str]] = None,
        hub_host: str = DEFAULT_HUB_HOST,
        hub_port: int = DEFAULT_HUB_PORT,
    ):
        self.agent_id = agent_id
        self.capabilities = capabilities or ["protobuf_bridge", "rpc_relay"]
        self.specialties = specialties or ["Protobuf RPC", "Cross-language Bridge"]
        self.hub_host = hub_host
        self.hub_port = hub_port
        self._socket: Optional[socket.socket] = None
        self._connected = False
        self._lock = threading.Lock()
        self._on_message_callback: Optional[Callable] = None
        self._recv_thread: Optional[threading.Thread] = None

    def set_message_callback(self, callback: Callable[[chat_pb2.SwarmMessage], None]):
        self._on_message_callback = callback

    def connect(self) -> bool:
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.connect((self.hub_host, self.hub_port))
            self._connected = True

            register_msg = {
                "type": "register",
                "from_id": self.agent_id,
                "capabilities": self.capabilities,
                "content": ",".join(self.specialties),
            }
            self._send_json(register_msg)

            self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
            self._recv_thread.start()

            logger.info(f"Swarm Bridge '{self.agent_id}' connected to Hub {self.hub_host}:{self.hub_port}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to Swarm Hub: {e}")
            self._connected = False
            return False

    def disconnect(self):
        self._connected = False
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
        logger.info(f"Swarm Bridge '{self.agent_id}' disconnected")

    @property
    def connected(self) -> bool:
        return self._connected

    def send_protobuf_message(self, msg: chat_pb2.SwarmMessage) -> bool:
        json_msg = self._pb_to_json(msg)
        return self._send_json(json_msg)

    def send_help_request(self, task: str, from_id: str = "") -> bool:
        msg = chat_pb2.SwarmMessage(
            type=chat_pb2.SwarmMessage.HELP_REQUEST,
            from_id=from_id or self.agent_id,
            task=task,
            msg_id=str(uuid.uuid4())[:8],
            timestamp=int(time.time() * 1000),
        )
        return self.send_protobuf_message(msg)

    def send_broadcast(self, content: str, from_id: str = "") -> bool:
        msg = chat_pb2.SwarmMessage(
            type=chat_pb2.SwarmMessage.BROADCAST,
            from_id=from_id or self.agent_id,
            content=content,
            msg_id=str(uuid.uuid4())[:8],
            timestamp=int(time.time() * 1000),
        )
        return self.send_protobuf_message(msg)

    def send_direct(self, to_id: str, content: str, from_id: str = "") -> bool:
        msg = chat_pb2.SwarmMessage(
            type=chat_pb2.SwarmMessage.DIRECT,
            from_id=from_id or self.agent_id,
            to_id=to_id,
            content=content,
            msg_id=str(uuid.uuid4())[:8],
            timestamp=int(time.time() * 1000),
        )
        return self.send_protobuf_message(msg)

    def _send_json(self, data: dict) -> bool:
        if not self._connected or not self._socket:
            return False
        try:
            with self._lock:
                msg = json.dumps(data) + "\n"
                self._socket.sendall(msg.encode("utf-8"))
            return True
        except Exception as e:
            logger.error(f"Send error: {e}")
            self._connected = False
            return False

    def _recv_loop(self):
        buffer = b""
        while self._connected:
            try:
                data = self._socket.recv(BUFFER_SIZE)
                if not data:
                    logger.info("Swarm Hub connection closed")
                    self._connected = False
                    break

                buffer += data
                while MESSAGE_DELIMITER in buffer:
                    line, buffer = buffer.split(MESSAGE_DELIMITER, 1)
                    if not line.strip():
                        continue
                    try:
                        json_msg = json.loads(line.decode("utf-8"))
                        pb_msg = self._json_to_pb(json_msg)
                        if pb_msg and self._on_message_callback:
                            self._on_message_callback(pb_msg)
                    except json.JSONDecodeError as e:
                        logger.warning(f"Invalid JSON from Swarm Hub: {e}")
                    except Exception as e:
                        logger.error(f"Error processing Swarm message: {e}")

            except socket.timeout:
                continue
            except Exception as e:
                if self._connected:
                    logger.error(f"Swarm recv error: {e}")
                self._connected = False
                break

    def _json_to_pb(self, json_msg: dict) -> Optional[chat_pb2.SwarmMessage]:
        msg_type_str = json_msg.get("type", "")
        pb_type = self.TYPE_MAP_JSON_TO_PB.get(msg_type_str, chat_pb2.SwarmMessage.BROADCAST)

        return chat_pb2.SwarmMessage(
            type=pb_type,
            from_id=json_msg.get("from_id", ""),
            to_id=json_msg.get("to_id", ""),
            content=json_msg.get("content", ""),
            task=json_msg.get("task", ""),
            result=json_msg.get("result", ""),
            msg_id=json_msg.get("msg_id", str(uuid.uuid4())[:8]),
            timestamp=int(json_msg.get("timestamp", time.time() * 1000)),
        )

    def _pb_to_json(self, msg: chat_pb2.SwarmMessage) -> dict:
        msg_type_str = self.TYPE_MAP_PB_TO_JSON.get(msg.type, "broadcast")

        result = {
            "type": msg_type_str,
            "from_id": msg.from_id or self.agent_id,
            "to_id": msg.to_id,
            "content": msg.content,
            "task": msg.task,
            "result": msg.result,
            "msg_id": msg.msg_id,
            "timestamp": msg.timestamp or int(time.time() * 1000),
        }
        return {k: v for k, v in result.items() if v}
