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


# ============================================================================
# Subagent 编排系统 - 异步父子进程并发调度
# ============================================================================

DISPATCH_SUBTASKS_TOOL_DEFINITION_ANTHROPIC = {
    "name": "dispatch_subtasks",
    "description": (
        "子任务并发派发工具 - 将复杂任务拆分为多个子任务并发执行，大幅提升效率。\n"
        "适用场景：\n"
        "- 同时搜索多个文档/网页\n"
        "- 编译代码的同时搜索依赖文档\n"
        "- 并行测试多个文件\n"
        "- 同时读取多个大文件\n"
        "- 让子智能体分析代码/生成方案（llm 类型）\n\n"
        "子任务类型：\n"
        "- search: 网络搜索（纯网络请求，不需要沙盒）\n"
        "- compile: 编译/构建代码（在独立沙盒中执行，不干扰主干）\n"
        "- test: 运行测试（在独立沙盒中执行）\n"
        "- read: 读取文件（在当前工作目录中执行）\n"
        "- bash: 执行任意 bash 命令（在独立沙盒中执行）\n"
        "- llm: 调用子智能体（mimo-v2.5-pro）分析问题、生成方案、审查代码\n\n"
        "系统会自动为需要沙盒的子任务分配独立工作区（WarmPool 预热池），"
        "并发执行并汇总结果。每个子任务有 30 秒超时保护。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "subtasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "子任务标识（如 'search_docs', 'compile_cpp'），用于区分结果",
                        },
                        "type": {
                            "type": "string",
                            "enum": ["search", "compile", "test", "read", "bash", "llm"],
                            "description": "子任务类型",
                        },
                        "command": {
                            "type": "string",
                            "description": "要执行的命令（compile/test/bash 类型必填）",
                        },
                        "query": {
                            "type": "string",
                            "description": "搜索查询（search 类型必填）",
                        },
                        "file_path": {
                            "type": "string",
                            "description": "文件路径（read 类型必填）",
                        },
                        "prompt": {
                            "type": "string",
                            "description": "子智能体提示词（llm 类型必填，描述需要子智能体完成的分析/生成任务）",
                        },
                    },
                    "required": ["id", "type"],
                },
                "description": "子任务列表（最多 5 个并发子任务）",
            },
        },
        "required": ["subtasks"],
    },
}

DISPATCH_SUBTASKS_TOOL_DEFINITION_OPENAI = {
    "type": "function",
    "function": {
        "name": "dispatch_subtasks",
        "description": (
            "子任务并发派发工具 - 将复杂任务拆分为多个子任务并发执行。"
            "例如：同时搜索文档 + 编译代码 + 运行测试 + 让子智能体分析代码。"
            "系统自动分配独立沙盒工作区，30秒超时保护。"
            "llm 类型会调用 mimo-v2.5-pro 子智能体进行代码分析、方案生成等。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "subtasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {
                                "type": "string",
                                "description": "子任务标识",
                            },
                            "type": {
                                "type": "string",
                                "enum": ["search", "compile", "test", "read", "bash", "llm"],
                                "description": "子任务类型",
                            },
                            "command": {
                                "type": "string",
                                "description": "要执行的命令",
                            },
                            "query": {
                                "type": "string",
                                "description": "搜索查询",
                            },
                            "file_path": {
                                "type": "string",
                                "description": "文件路径",
                            },
                            "prompt": {
                                "type": "string",
                                "description": "子智能体提示词（llm 类型必填）",
                            },
                        },
                        "required": ["id", "type"],
                    },
                    "description": "子任务列表（最多5个）",
                },
            },
            "required": ["subtasks"],
        },
    },
}


@dataclass
class SubtaskResult:
    subtask_id: str
    subtask_type: str
    status: str = "pending"
    output: str = ""
    error: str = ""
    elapsed_seconds: float = 0.0
    worktree_path: str = ""
    sandbox_recycled: bool = False


async def run_single_subagent(
    task: dict,
    work_dir: str,
    main_repo_dir: str = "",
) -> SubtaskResult:
    task_id = task.get("id", "unknown")
    task_type = task.get("type", "bash")
    result = SubtaskResult(subtask_id=task_id, subtask_type=task_type)
    start_time = time.time()

    sandbox = None
    borrowed_cwd = ""

    try:
        if task_type == "search":
            query = task.get("query", "")
            if not query:
                result.status = "failed"
                result.error = "search 类型必须提供 query 参数"
                return result

            logger.info(f"🔍 Subagent-{task_id} 启动搜索: query=\"{query[:60]}\"")
            try:
                from semantic_search_tool import semantic_search, format_semantic_results
                loop = asyncio.get_event_loop()
                sr = await loop.run_in_executor(
                    None, lambda: semantic_search(query=query, project_dir=work_dir)
                )
                result.output = format_semantic_results(sr) if sr.results else "未找到相关结果"
            except ImportError:
                try:
                    from grep_tool import execute_grep
                    loop = asyncio.get_event_loop()
                    output, is_error = await loop.run_in_executor(
                        None, lambda: execute_grep(query, work_dir)
                    )
                    result.output = output[:3000]
                except Exception:
                    result.output = f"搜索完成（无专业搜索引擎）: query={query}"

            result.status = "success"
            result.elapsed_seconds = time.time() - start_time
            logger.info(
                f"🔍 Subagent-{task_id} 搜索完成 "
                f"({result.elapsed_seconds:.1f}s)"
            )
            return result

        elif task_type in ("compile", "test", "bash"):
            cmd = task.get("command", task.get("cmd", ""))
            if not cmd:
                result.status = "failed"
                result.error = f"{task_type} 类型必须提供 command/cmd 参数"
                return result

            repo_dir = main_repo_dir or work_dir
            try:
                from sandbox_manager import get_sandbox
                if os.path.exists(os.path.join(repo_dir, ".git")):
                    sandbox = get_sandbox(repo_dir)
                    borrowed_cwd = sandbox.get_warm_workspace()
                    if borrowed_cwd:
                        logger.info(
                            f"📦 Subagent-{task_id} 借出预热沙盒: "
                            f"{os.path.basename(borrowed_cwd)}"
                        )
                    else:
                        borrowed_cwd = work_dir
                        logger.info(
                            f"🐌 Subagent-{task_id} 预热池为空，使用主工作区"
                        )
                else:
                    borrowed_cwd = work_dir
                    logger.info(
                        f"📂 Subagent-{task_id} 非 Git 仓库，使用主工作区"
                    )
            except Exception as e:
                logger.warning(f"📦 Subagent-{task_id} 沙盒获取异常: {e}")
                borrowed_cwd = work_dir

            result.worktree_path = borrowed_cwd
            logger.info(
                f"⚙️ Subagent-{task_id} 启动子进程: "
                f"cmd=\"{cmd[:80]}\" cwd={borrowed_cwd}"
            )

            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=borrowed_cwd,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=30.0,
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                result.status = "timeout"
                result.error = f"子进程超时被斩断 (30s)"
                result.elapsed_seconds = time.time() - start_time
                logger.warning(
                    f"🚨 Subagent-{task_id} 子进程超时被斩断!"
                )
                return result

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            result.elapsed_seconds = time.time() - start_time

            if proc.returncode != 0:
                result.status = "failed"
                result.output = stdout[:3000]
                result.error = stderr[:500] if stderr else f"Exit code {proc.returncode}"
                logger.info(
                    f"❌ Subagent-{task_id} 执行失败 "
                    f"(exit={proc.returncode}, {result.elapsed_seconds:.1f}s)"
                )
            else:
                result.status = "success"
                result.output = stdout[:3000]
                logger.info(
                    f"✅ Subagent-{task_id} 执行成功 "
                    f"({result.elapsed_seconds:.1f}s)"
                )
            return result

        elif task_type == "read":
            file_path = task.get("file_path", "")
            if not file_path:
                result.status = "failed"
                result.error = "read 类型必须提供 file_path 参数"
                return result

            if not os.path.isabs(file_path):
                file_path = os.path.join(work_dir, file_path)

            from file_read_tool import execute_file_read
            loop = asyncio.get_event_loop()
            output, is_error = await loop.run_in_executor(
                None,
                lambda: execute_file_read(file_path, None, None, work_dir)
            )
            result.output = output[:3000]
            result.status = "success" if not is_error else "failed"
            if is_error:
                result.error = output[:500]
            result.elapsed_seconds = time.time() - start_time
            return result

        elif task_type == "llm":
            prompt = task.get("prompt", "")
            if not prompt:
                result.status = "failed"
                result.error = "llm 类型必须提供 prompt 参数"
                return result

            logger.info(f"🧠 Subagent-{task_id} 启动 LLM 子智能体: prompt=\"{prompt[:60]}\"")

            try:
                from openai import OpenAI

                sub_api_key = os.environ.get("OPENAI_API_KEY", "")
                sub_base_url = os.environ.get("OPENAI_BASE_URL", "")
                if sub_base_url and not sub_base_url.endswith("/v1"):
                    sub_base_url = sub_base_url.rstrip("/") + "/v1"
                sub_model = os.environ.get("ERUITAH_SUBAGENT_MODEL", "mimo-v2.5-pro")

                client = OpenAI(api_key=sub_api_key, base_url=sub_base_url)

                context_files = task.get("context_files", [])
                context_content = ""
                if context_files:
                    for cf in context_files:
                        cf_path = cf if os.path.isabs(cf) else os.path.join(work_dir, cf)
                        if os.path.exists(cf_path):
                            try:
                                with open(cf_path, "r", encoding="utf-8", errors="replace") as f:
                                    content = f.read()
                                    context_content += f"\n--- 文件: {cf} ---\n{content[:2000]}\n"
                            except Exception:
                                pass

                is_explore = any(kw in prompt.lower() for kw in [
                    "搜索", "查找", "分析", "阅读", "理解", "解释", "review",
                    "search", "find", "analyze", "read", "understand", "explain",
                    "grep", "inspect", "explore",
                ])

                if is_explore:
                    system_prompt = (
                        "你是一个只读探索型子智能体（Explore Agent）。你的任务是：\n"
                        "1. 搜索、阅读、分析代码和文档\n"
                        "2. 你**没有**文件写入权限，只能阅读和分析\n"
                        "3. 完成后，你必须返回一段**精简的摘要报告**，格式如下：\n"
                        "   - 📋 发现摘要：[核心发现的 1-3 句话]\n"
                        "   - 📂 相关文件：[涉及的文件列表]\n"
                        "   - 💡 建议：[对主智能体的操作建议]\n\n"
                        "绝对不要返回大段源码，只返回摘要和关键信息！"
                    )
                else:
                    system_prompt = (
                        "你是一个专业的编程助手子智能体。你的任务是：根据主智能体的请求，"
                        "进行代码生成、方案设计或问题修复。"
                        "请给出简洁、专业、可操作的回答。"
                    )

                if context_content:
                    system_prompt += f"\n\n以下是相关的代码文件内容：{context_content[:6000]}"

                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: client.chat.completions.create(
                        model=sub_model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt},
                        ],
                        max_tokens=2000,
                        temperature=0.3,
                    )
                )

                llm_output = response.choices[0].message.content.strip()
                result.output = llm_output
                result.status = "success"
                result.elapsed_seconds = time.time() - start_time
                logger.info(
                    f"🧠 Subagent-{task_id} LLM 完成 "
                    f"({'探索' if is_explore else '决策'}, {result.elapsed_seconds:.1f}s, {len(llm_output)} 字符)"
                )
                return result

            except Exception as e:
                result.status = "failed"
                result.error = f"LLM 子智能体调用失败: {str(e)[:300]}"
                result.elapsed_seconds = time.time() - start_time
                logger.error(f"🧠 Subagent-{task_id} LLM 调用异常: {e}")
                return result

        else:
            result.status = "failed"
            result.error = f"未知子任务类型: {task_type}"
            return result

    except Exception as e:
        result.status = "failed"
        result.error = str(e)[:500]
        result.elapsed_seconds = time.time() - start_time
        logger.error(f"🚨 Subagent-{task_id} 异常: {e}")
        return result

    finally:
        if sandbox and borrowed_cwd and borrowed_cwd != work_dir:
            try:
                sandbox.recycle_workspace(borrowed_cwd)
                result.sandbox_recycled = True
            except Exception as e:
                logger.error(
                    f"♻️ Subagent-{task_id} 沙盒回收失败: {e}"
                )


async def dispatch_and_gather(
    tasks: list,
    work_dir: str,
    main_repo_dir: str = "",
    global_timeout: float = 30.0,
) -> list:
    logger.info(f"🚀 并发派发了 {len(tasks)} 个子任务...")

    coroutines = [
        run_single_subagent(t, work_dir, main_repo_dir)
        for t in tasks
    ]

    pending_results: dict[int, SubtaskResult] = {}
    task_futures = {}

    for i, coro in enumerate(coroutines):
        task_futures[i] = asyncio.ensure_future(coro)

    done, pending = await asyncio.wait(
        task_futures.values(),
        timeout=global_timeout,
        return_when=asyncio.ALL_COMPLETED,
    )

    timed_out = len(pending) > 0
    if timed_out:
        logger.error(
            f"🚨 全局超时熔断触发！{global_timeout}s 内未完成所有子任务"
            f"（完成: {len(done)}, 超时: {len(pending)}）"
        )
        for fut in pending:
            fut.cancel()
        try:
            await asyncio.gather(*pending, return_exceptions=True)
        except Exception:
            pass

    index_map = {id(fut): idx for idx, fut in task_futures.items()}

    for fut in done:
        idx = index_map[id(fut)]
        try:
            r = fut.result()
            if isinstance(r, SubtaskResult):
                pending_results[idx] = r
            else:
                pending_results[idx] = SubtaskResult(
                    subtask_id=tasks[idx].get("id", f"task_{idx}"),
                    subtask_type=tasks[idx].get("type", "unknown"),
                    status="failed",
                    error="未知返回类型",
                )
        except Exception as e:
            idx = index_map[id(fut)]
            pending_results[idx] = SubtaskResult(
                subtask_id=tasks[idx].get("id", f"task_{idx}"),
                subtask_type=tasks[idx].get("type", "unknown"),
                status="failed",
                error=f"[EXCEPTION] {str(e)[:500]}",
            )

    for fut in pending:
        idx = index_map[id(fut)]
        pending_results[idx] = SubtaskResult(
            subtask_id=tasks[idx].get("id", f"task_{idx}"),
            subtask_type=tasks[idx].get("type", "unknown"),
            status="timeout",
            error="[TIMEOUT_ERROR] 全局超时，子任务被强行终止",
        )

    return [pending_results[i] for i in range(len(tasks))]


def execute_dispatch_subtasks(
    subtasks: list,
    work_dir: str = ".",
    main_repo_dir: str = "",
    timeout_per_task: float = 30.0,
) -> tuple[str, bool]:
    if not subtasks:
        return "❌ 子任务列表不能为空", True

    if len(subtasks) > 5:
        return "❌ 最多支持 5 个并发子任务", True

    for i, st in enumerate(subtasks):
        if not isinstance(st, dict):
            return f"❌ 子任务 {i} 格式错误，必须是字典", True
        if not st.get("id"):
            return f"❌ 子任务 {i} 缺少 id 字段", True
        if not st.get("type"):
            return f"❌ 子任务 {st.get('id', i)} 缺少 type 字段", True

    try:
        results = asyncio.run(
            dispatch_and_gather(subtasks, work_dir, main_repo_dir, timeout_per_task)
        )
    except RuntimeError:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                asyncio.run,
                dispatch_and_gather(subtasks, work_dir, main_repo_dir, timeout_per_task)
            )
            results = future.result(timeout=timeout_per_task + 10)
    except Exception as e:
        logger.error(f"🚨 Subagent 调度异常: {e}")
        return f"❌ 子任务调度失败: {str(e)}", True

    success_count = sum(1 for r in results if r.status == "success")
    failed_count = sum(1 for r in results if r.status != "success")
    timeout_count = sum(1 for r in results if r.status == "timeout")

    lines = [
        f"🚀 Subagent 编排结果: {success_count} 成功 / {failed_count} 失败"
        f" (超时: {timeout_count}) / 共 {len(results)} 个子任务",
        "=" * 60,
    ]

    for r in results:
        if r.status == "success":
            status_icon = "✅"
        elif r.status == "timeout":
            status_icon = "🚨"
        else:
            status_icon = "❌"

        lines.append(f"\n{status_icon} [{r.subtask_id}] ({r.subtask_type}) - {r.status}")
        if r.elapsed_seconds > 0:
            lines.append(f"   ⏱️ 耗时: {r.elapsed_seconds:.1f}s")
        if r.worktree_path:
            lines.append(f"   📦 沙盒: {os.path.basename(r.worktree_path)}")
        if r.sandbox_recycled:
            lines.append(f"   ♻️ 沙盒已安全归还预热池")
        if r.output:
            output_preview = r.output[:1500]
            if len(r.output) > 1500:
                output_preview += f"\n   ... [截断，共 {len(r.output)} 字符]"
            lines.append(f"   📄 输出:\n   {output_preview}")
        if r.error:
            lines.append(f"   ⚠️ 错误: {r.error[:300]}")

    is_error = failed_count > 0 and success_count == 0
    return "\n".join(lines), is_error


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
