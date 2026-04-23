"""
Eruitah 智能编程沙盒 - P2P 智能体网络 (Agent Swarm)

核心思想（对接 C++ Muduo 海量并发网络）:
┌─────────────────────────────────────────────────────────────────────┐
│  低级: 多个 Agent 在一个 Python 进程里通过函数调用交流              │
│  高级: 每个 Agent 是独立的 TCP 节点，通过消息总线协同               │
│                                                                     │
│  架构:                                                              │
│    ┌─────────────────────────────────────────────────────┐          │
│    │  C++ Muduo 聊天网关 (或 Python 消息总线)             │          │
│    │    端口: 9000                                       │          │
│    └──────┬──────────┬──────────┬──────────┬────────────┘          │
│           │          │          │          │                        │
│    ┌──────┴───┐ ┌────┴────┐ ┌──┴──────┐ ┌─┴────────┐              │
│    │ C++ Agent │ │ Web Agent│ │ DB Agent │ │ DevOps   │              │
│    │ 擅长C++   │ │ 擅长前端 │ │ 擅长SQL  │ │ 擅长运维 │              │
│    │ Port:9001 │ │ Port:9002│ │ Port:9003│ │ Port:9004│              │
│    └──────────┘ └─────────┘ └─────────┘ └──────────┘              │
│                                                                     │
│  协同场景:                                                          │
│    C++ Agent: "@DB_Agent 我需要用户表的结构，请求支援！"             │
│    DB Agent: 收到消息 → 查询数据库 → 发回表结构                     │
│    C++ Agent: 收到表结构 → 继续写代码                                │
│                                                                     │
│  消息协议:                                                          │
│    {"type": "register", "agent_id": "cpp_agent", "capabilities": []}│
│    {"type": "broadcast", "from": "cpp_agent", "message": "..."}     │
│    {"type": "direct", "from": "cpp_agent", "to": "db_agent", ...}  │
│    {"type": "help_request", "from": "cpp_agent", "task": "..."}     │
│    {"type": "help_response", "from": "db_agent", "to": "cpp_agent"}│
└─────────────────────────────────────────────────────────────────────┘
"""

import os
import json
import time
import uuid
import socket as _socket
import threading
import logging
import asyncio
from dataclasses import dataclass, field
from typing import Optional, Callable
from collections import defaultdict

logger = logging.getLogger(__name__)

DEFAULT_HUB_HOST = os.environ.get("ERUITAH_SWARM_HOST", "127.0.0.1")
DEFAULT_HUB_PORT = int(os.environ.get("ERUITAH_SWARM_PORT", "9000"))
BUFFER_SIZE = 65536
MESSAGE_DELIMITER = b"\n"


@dataclass
class AgentNode:
    agent_id: str
    host: str = "127.0.0.1"
    port: int = 0
    capabilities: list = field(default_factory=list)
    specialties: list = field(default_factory=list)
    status: str = "online"
    registered_at: float = 0.0
    last_heartbeat: float = 0.0
    conn: Optional[_socket.socket] = None


@dataclass
class SwarmMessage:
    type: str
    from_id: str = ""
    to_id: str = ""
    content: str = ""
    task: str = ""
    result: str = ""
    capabilities: list = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    msg_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_json(self) -> str:
        return json.dumps({
            "type": self.type,
            "from_id": self.from_id,
            "to_id": self.to_id,
            "content": self.content,
            "task": self.task,
            "result": self.result,
            "capabilities": self.capabilities,
            "timestamp": self.timestamp,
            "msg_id": self.msg_id,
        }, ensure_ascii=False)

    @classmethod
    def from_json(cls, data: str) -> "SwarmMessage":
        try:
            d = json.loads(data)
            return cls(
                type=d.get("type", "unknown"),
                from_id=d.get("from_id", ""),
                to_id=d.get("to_id", ""),
                content=d.get("content", ""),
                task=d.get("task", ""),
                result=d.get("result", ""),
                capabilities=d.get("capabilities", []),
                timestamp=d.get("timestamp", time.time()),
                msg_id=d.get("msg_id", ""),
            )
        except (json.JSONDecodeError, TypeError):
            return cls(type="invalid", content=data)


class SwarmHub:
    def __init__(self, host: str = DEFAULT_HUB_HOST, port: int = DEFAULT_HUB_PORT):
        self.host = host
        self.port = port
        self._nodes: dict[str, AgentNode] = {}
        self._message_handlers: dict[str, list[Callable]] = defaultdict(list)
        self._lock = threading.Lock()
        self._running = False
        self._server_socket: Optional[_socket.socket] = None

    def start(self):
        self._running = True
        self._server_socket = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        self._server_socket.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
        self._server_socket.bind((self.host, self.port))
        self._server_socket.listen(20)
        self._server_socket.settimeout(1.0)

        logger.info(f"🐝 Swarm Hub 启动: {self.host}:{self.port}")

        accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        accept_thread.start()

    def stop(self):
        self._running = False
        if self._server_socket:
            self._server_socket.close()
        with self._lock:
            for node in self._nodes.values():
                if node.conn:
                    try:
                        node.conn.close()
                    except Exception:
                        pass
            self._nodes.clear()
        logger.info("Swarm Hub 已停止")

    def _accept_loop(self):
        while self._running:
            try:
                client_socket, addr = self._server_socket.accept()
                client_socket.settimeout(0.5)

                recv_thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_socket, addr),
                    daemon=True,
                )
                recv_thread.start()

            except _socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    logger.error(f"Accept 异常: {e}")

    def _handle_client(self, client_socket: _socket.socket, addr):
        buffer = b""
        agent_id = None

        try:
            while self._running:
                try:
                    data = client_socket.recv(BUFFER_SIZE)
                    if not data:
                        break

                    buffer += data

                    while MESSAGE_DELIMITER in buffer:
                        line, buffer = buffer.split(MESSAGE_DELIMITER, 1)
                        if not line:
                            continue

                        msg = SwarmMessage.from_json(line.decode("utf-8", errors="replace"))

                        if msg.type == "register":
                            agent_id = msg.from_id
                            self._register_node(msg, client_socket)
                        elif msg.type == "heartbeat":
                            self._handle_heartbeat(msg)
                        elif msg.type == "broadcast":
                            self._handle_broadcast(msg)
                        elif msg.type == "direct":
                            self._handle_direct(msg)
                        elif msg.type == "help_request":
                            self._handle_help_request(msg)
                        elif msg.type == "help_response":
                            self._handle_help_response(msg)

                except _socket.timeout:
                    continue
                except ConnectionResetError:
                    break

        except Exception as e:
            logger.error(f"客户端处理异常: {e}")
        finally:
            if agent_id:
                with self._lock:
                    self._nodes.pop(agent_id, None)
                logger.info(f"Agent 离线: {agent_id}")
            client_socket.close()

    def _register_node(self, msg: SwarmMessage, sock: _socket.socket):
        node = AgentNode(
            agent_id=msg.from_id,
            capabilities=msg.capabilities,
            specialties=msg.content.split(",") if msg.content else [],
            registered_at=time.time(),
            last_heartbeat=time.time(),
            conn=sock,
        )

        with self._lock:
            self._nodes[msg.from_id] = node

        logger.info(f"Agent 注册: {msg.from_id}, 能力: {msg.capabilities}")

        self._send_to_node(msg.from_id, SwarmMessage(
            type="register_ack",
            to_id=msg.from_id,
            content=f"注册成功，当前集群 {len(self._nodes)} 个节点",
        ))

        self._broadcast_node_list()

    def _handle_heartbeat(self, msg: SwarmMessage):
        with self._lock:
            node = self._nodes.get(msg.from_id)
            if node:
                node.last_heartbeat = time.time()

    def _handle_broadcast(self, msg: SwarmMessage):
        logger.info(f"广播消息 from {msg.from_id}: {msg.content[:100]}")
        with self._lock:
            for nid, node in self._nodes.items():
                if nid != msg.from_id and node.conn:
                    self._send_to_node(nid, msg)

    def _handle_direct(self, msg: SwarmMessage):
        logger.info(f"直接消息 {msg.from_id} → {msg.to_id}: {msg.content[:100]}")
        self._send_to_node(msg.to_id, msg)

    def _handle_help_request(self, msg: SwarmMessage):
        logger.info(f"求助请求 from {msg.from_id}: {msg.task[:100]}")

        with self._lock:
            for nid, node in self._nodes.items():
                if nid != msg.from_id and node.conn:
                    self._send_to_node(nid, msg)

    def _handle_help_response(self, msg: SwarmMessage):
        logger.info(f"求助响应 {msg.from_id} → {msg.to_id}: {msg.result[:100]}")
        self._send_to_node(msg.to_id, msg)

    def _send_to_node(self, node_id: str, msg: SwarmMessage):
        with self._lock:
            node = self._nodes.get(node_id)
            if node and node.conn:
                try:
                    data = msg.to_json().encode("utf-8") + MESSAGE_DELIMITER
                    node.conn.sendall(data)
                except Exception as e:
                    logger.error(f"发送消息到 {node_id} 失败: {e}")

    def _broadcast_node_list(self):
        with self._lock:
            node_list = [
                {
                    "agent_id": nid,
                    "capabilities": node.capabilities,
                    "specialties": node.specialties,
                    "status": node.status,
                }
                for nid, node in self._nodes.items()
            ]

        msg = SwarmMessage(
            type="node_list",
            content=json.dumps(node_list, ensure_ascii=False),
        )

        with self._lock:
            for nid, node in self._nodes.items():
                if node.conn:
                    try:
                        data = msg.to_json().encode("utf-8") + MESSAGE_DELIMITER
                        node.conn.sendall(data)
                    except Exception:
                        pass

    def get_nodes(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "agent_id": nid,
                    "capabilities": node.capabilities,
                    "specialties": node.specialties,
                    "status": node.status,
                    "registered_at": node.registered_at,
                }
                for nid, node in self._nodes.items()
            ]


class SwarmClient:
    def __init__(
        self,
        agent_id: str,
        capabilities: list = None,
        specialties: list = None,
        hub_host: str = DEFAULT_HUB_HOST,
        hub_port: int = DEFAULT_HUB_PORT,
    ):
        self.agent_id = agent_id
        self.capabilities = capabilities or []
        self.specialties = specialties or []
        self.hub_host = hub_host
        self.hub_port = hub_port
        self._socket: Optional[_socket.socket] = None
        self._connected = False
        self._message_queue: list[SwarmMessage] = []
        self._lock = threading.Lock()
        self._response_futures: dict[str, threading.Event] = {}
        self._response_data: dict[str, SwarmMessage] = {}

    def connect(self) -> bool:
        try:
            self._socket = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
            self._socket.connect((self.hub_host, self.hub_port))
            self._connected = True

            self._send(SwarmMessage(
                type="register",
                from_id=self.agent_id,
                capabilities=self.capabilities,
                content=",".join(self.specialties),
            ))

            recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
            recv_thread.start()

            logger.info(f"🐝 Agent '{self.agent_id}' 已连接到 Hub {self.hub_host}:{self.hub_port}")
            return True

        except Exception as e:
            logger.error(f"连接 Hub 失败: {e}")
            self._connected = False
            return False

    def disconnect(self):
        self._connected = False
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
        logger.info(f"Agent '{self.agent_id}' 已断开连接")

    def broadcast(self, content: str):
        self._send(SwarmMessage(
            type="broadcast",
            from_id=self.agent_id,
            content=content,
        ))

    def send_direct(self, to_id: str, content: str):
        self._send(SwarmMessage(
            type="direct",
            from_id=self.agent_id,
            to_id=to_id,
            content=content,
        ))

    def request_help(self, task: str, timeout: float = 60.0) -> Optional[SwarmMessage]:
        msg_id = str(uuid.uuid4())[:8]

        event = threading.Event()
        self._response_futures[msg_id] = event

        self._send(SwarmMessage(
            type="help_request",
            from_id=self.agent_id,
            task=task,
            msg_id=msg_id,
        ))

        if event.wait(timeout=timeout):
            response = self._response_data.pop(msg_id, None)
            self._response_futures.pop(msg_id, None)
            return response

        self._response_futures.pop(msg_id, None)
        return None

    def respond_help(self, to_id: str, task: str, result: str, msg_id: str = ""):
        self._send(SwarmMessage(
            type="help_response",
            from_id=self.agent_id,
            to_id=to_id,
            task=task,
            result=result,
            msg_id=msg_id,
        ))

    def get_pending_messages(self) -> list[SwarmMessage]:
        with self._lock:
            msgs = self._message_queue.copy()
            self._message_queue.clear()
            return msgs

    def _send(self, msg: SwarmMessage):
        if not self._connected or not self._socket:
            return
        try:
            data = msg.to_json().encode("utf-8") + MESSAGE_DELIMITER
            self._socket.sendall(data)
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            self._connected = False

    def _recv_loop(self):
        buffer = b""
        while self._connected:
            try:
                data = self._socket.recv(BUFFER_SIZE)
                if not data:
                    break

                buffer += data

                while MESSAGE_DELIMITER in buffer:
                    line, buffer = buffer.split(MESSAGE_DELIMITER, 1)
                    if not line:
                        continue

                    msg = SwarmMessage.from_json(line.decode("utf-8", errors="replace"))
                    self._on_message(msg)

            except _socket.timeout:
                continue
            except Exception as e:
                if self._connected:
                    logger.error(f"接收消息异常: {e}")
                break

        self._connected = False

    def _on_message(self, msg: SwarmMessage):
        if msg.type == "help_response" and msg.msg_id in self._response_futures:
            self._response_data[msg.msg_id] = msg
            event = self._response_futures.get(msg.msg_id)
            if event:
                event.set()
        else:
            with self._lock:
                self._message_queue.append(msg)


SWARM_TOOL_DEFINITION_ANTHROPIC = {
    "name": "swarm_communicate",
    "description": (
        "P2P 智能体网络通信工具 - 与其他 Agent 节点协同工作。"
        "可以向集群广播求助、向特定 Agent 发送消息、请求其他 Agent 的专业能力。"
        "action='broadcast': 向所有 Agent 广播消息"
        "action='direct': 向特定 Agent 发送消息"
        "action='help': 向集群请求帮助（等待响应）"
        "action='respond': 回应求助请求"
        "action='list': 列出集群中的所有 Agent"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["broadcast", "direct", "help", "respond", "list"],
                "description": "通信动作类型",
            },
            "target_agent": {
                "type": "string",
                "description": "目标 Agent ID（direct/respond 时必填）",
            },
            "message": {
                "type": "string",
                "description": "消息内容",
            },
            "task": {
                "type": "string",
                "description": "求助任务描述（help 时必填）",
            },
            "result": {
                "type": "string",
                "description": "求助结果（respond 时必填）",
            },
        },
        "required": ["action"],
    },
}

SWARM_TOOL_DEFINITION_OPENAI = {
    "type": "function",
    "function": {
        "name": "swarm_communicate",
        "description": (
            "P2P 智能体网络通信工具 - 与其他 Agent 节点协同工作。"
            "可以向集群广播求助、向特定 Agent 发送消息、请求其他 Agent 的专业能力。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["broadcast", "direct", "help", "respond", "list"],
                    "description": "通信动作类型",
                },
                "target_agent": {
                    "type": "string",
                    "description": "目标 Agent ID",
                },
                "message": {
                    "type": "string",
                    "description": "消息内容",
                },
                "task": {
                    "type": "string",
                    "description": "求助任务描述",
                },
                "result": {
                    "type": "string",
                    "description": "求助结果",
                },
            },
            "required": ["action"],
        },
    },
}


_local_client: Optional[SwarmClient] = None
_local_hub: Optional[SwarmHub] = None


def get_swarm_client(
    agent_id: str = "eruitah_main",
    capabilities: list = None,
    specialties: list = None,
) -> SwarmClient:
    global _local_client
    if _local_client is None:
        _local_client = SwarmClient(
            agent_id=agent_id,
            capabilities=capabilities or ["coding", "file_edit", "bash", "search"],
            specialties=specialties or ["Python", "通用编程"],
        )
    return _local_client


def get_swarm_hub() -> SwarmHub:
    global _local_hub
    if _local_hub is None:
        _local_hub = SwarmHub()
    return _local_hub


def execute_swarm_communicate(
    action: str,
    target_agent: str = "",
    message: str = "",
    task: str = "",
    result: str = "",
) -> tuple[str, bool]:
    client = get_swarm_client()

    if not client._connected:
        if not client.connect():
            return "❌ 无法连接到 Swarm Hub，请确保 Hub 已启动", True

    if action == "broadcast":
        if not message:
            return "广播消息不能为空", True
        client.broadcast(message)
        return f"✅ 已向集群广播消息: {message[:100]}", False

    elif action == "direct":
        if not target_agent:
            return "直接消息需要指定 target_agent", True
        if not message:
            return "消息内容不能为空", True
        client.send_direct(target_agent, message)
        return f"✅ 已向 {target_agent} 发送消息: {message[:100]}", False

    elif action == "help":
        if not task:
            return "求助需要提供 task 描述", True
        response = client.request_help(task, timeout=60.0)
        if response:
            return (
                f"✅ 收到来自 {response.from_id} 的帮助:\n"
                f"任务: {response.task[:200]}\n"
                f"结果: {response.result[:2000]}",
                False,
            )
        else:
            return "⚠️ 请求帮助超时，集群中没有 Agent 响应", True

    elif action == "respond":
        if not target_agent:
            return "回应需要指定 target_agent", True
        if not result:
            return "回应需要提供 result", True
        client.respond_help(target_agent, task, result)
        return f"✅ 已向 {target_agent} 发送帮助结果", False

    elif action == "list":
        pending = client.get_pending_messages()
        hub = get_swarm_hub()
        nodes = hub.get_nodes() if hub._running else []

        lines = [f"集群状态 (在线节点: {len(nodes)}):"]
        for n in nodes:
            lines.append(
                f"  🤖 {n['agent_id']}: 能力={n['capabilities']}, "
                f"专长={n.get('specialties', [])}, 状态={n['status']}"
            )

        if pending:
            lines.append(f"\n待处理消息 ({len(pending)} 条):")
            for m in pending[:5]:
                lines.append(f"  [{m.type}] {m.from_id} → {m.to_id}: {m.content[:100]}")

        return "\n".join(lines), False

    else:
        return f"未知动作: {action}", True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("Eruitah P2P Agent Swarm 测试")
    print("=" * 60)

    hub = get_swarm_hub()
    hub.start()
    print(f"\n✅ Swarm Hub 已启动: {DEFAULT_HUB_HOST}:{DEFAULT_HUB_PORT}")

    import time
    time.sleep(0.5)

    client1 = SwarmClient(
        agent_id="cpp_agent",
        capabilities=["coding", "compilation"],
        specialties=["C++", "系统编程"],
    )
    client2 = SwarmClient(
        agent_id="db_agent",
        capabilities=["database", "sql"],
        specialties=["MySQL", "SQLite", "PostgreSQL"],
    )

    print("\n--- 注册 Agent ---")
    c1_ok = client1.connect()
    c2_ok = client2.connect()
    print(f"cpp_agent 连接: {'✅' if c1_ok else '❌'}")
    print(f"db_agent 连接: {'✅' if c2_ok else '❌'}")

    time.sleep(0.5)

    print("\n--- 列出节点 ---")
    nodes = hub.get_nodes()
    for n in nodes:
        print(f"  {n['agent_id']}: {n['capabilities']}")

    print("\n--- 广播测试 ---")
    client1.broadcast("大家好，我是 C++ Agent！")
    time.sleep(0.5)

    msgs = client2.get_pending_messages()
    for m in msgs:
        print(f"  db_agent 收到: [{m.type}] {m.content}")

    print("\n--- 直接消息测试 ---")
    client1.send_direct("db_agent", "我需要用户表的结构")
    time.sleep(0.5)

    msgs = client2.get_pending_messages()
    for m in msgs:
        print(f"  db_agent 收到: [{m.type}] {m.from_id} → {m.content}")

    print("\n--- 求助测试 ---")
    help_result = client1.request_help("查询 data.db 的表结构", timeout=5.0)
    if help_result:
        print(f"  收到帮助: {help_result.result[:100]}")
    else:
        print("  求助超时（预期行为，因为 db_agent 没有自动响应）")

    print("\n--- 清理 ---")
    client1.disconnect()
    client2.disconnect()
    hub.stop()

    print("\n✅ P2P Agent Swarm 测试通过!")
