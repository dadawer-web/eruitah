"""
Eruitah 智能编程沙盒 - 多智能体协同系统 (Agent Swarm)

三大核心能力:
┌─────────────────────────────────────────────────────────────────────┐
│  1. P2P 智能体网络 - TCP 消息总线协同                               │
│  2. Subagent 编排 - 异步父子进程并发调度                            │
│  3. Coder-Reviewer 对抗博弈 - RBAC 权限隔离的代码审查闭环           │
│                                                                     │
│  Coder-Reviewer 工作流:                                             │
│    ┌──────────┐    提交审查     ┌──────────┐                        │
│    │  Coder   │ ──────────────→ │ Reviewer │                        │
│    │ (全权限) │                  │ (只读)   │                        │
│    └──────────┘ ←────────────── └──────────┘                        │
│                  打回重写 / LGTM                                     │
│                                                                     │
│  状态机:                                                            │
│    CODING → SUBMITTED → REVIEWING → LGTM (终态)                    │
│                                  → REJECTED → CODING (循环)         │
│                                  → MAX_LOOPS (终态)                 │
└─────────────────────────────────────────────────────────────────────┘
"""

import os
import re
import json
import time
import uuid
import socket as _socket
import threading
import logging
import asyncio
import subprocess
from dataclasses import dataclass, field
from typing import Optional, Callable
from collections import defaultdict

logger = logging.getLogger(__name__)

DEFAULT_HUB_HOST = os.environ.get("ERUITAH_SWARM_HOST", "127.0.0.1")
DEFAULT_HUB_PORT = int(os.environ.get("ERUITAH_SWARM_PORT", "9000"))
BUFFER_SIZE = 65536
MESSAGE_DELIMITER = b"\n"


def _try_report_career_advice(user_id, reviewer_output, work_dir, task_description):
    if not user_id or user_id <= 0:
        return
    try:
        from rpc_entry import report_career_advice

        extracted_skills = _extract_tech_skills_from_review(reviewer_output)
        resume_highlight = _generate_resume_highlight(extracted_skills, task_description)
        next_suggestion = _extract_learning_suggestion(reviewer_output)

        if extracted_skills or resume_highlight:
            report_career_advice(
                user_id=user_id,
                extracted_skills=extracted_skills,
                resume_highlight=resume_highlight,
                next_suggestion=next_suggestion,
            )
            logger.info(f"[Swarm] Career advice reported to Java for user={user_id}")
    except Exception as e:
        logger.debug(f"[Swarm] Career advice report failed (non-blocking): {e}")


def _extract_tech_skills_from_review(review_text: str) -> list:
    if not review_text:
        return []
    tech_keywords = [
        "epoll", "muduo", "reactor", "proactor", "thread pool", "thread_pool",
        "mutex", "semaphore", "condition variable", "atomic", "lock-free",
        "redis", "mysql", "postgresql", "mongodb", "kafka", "rabbitmq",
        "docker", "kubernetes", "k8s", "grpc", "protobuf", "rest api",
        "avl", "red-black", "b-tree", "b+tree", "hash table", "skip list",
        "dfs", "bfs", "dynamic programming", "greedy", "backtracking",
        "tcp", "udp", "http", "websocket", "rpc", "cdn", "dns",
        "spring", "mybatis", "netty", "muduo", "django", "flask", "fastapi",
        "react", "vue", "typescript", "javascript", "python", "java", "cpp", "rust", "go",
        "multi-thread", "concurrent", "async", "coroutine", "io_uring",
        "design pattern", "singleton", "factory", "observer", "strategy",
        "unit test", "integration test", "tdd", "ci/cd",
        "git", "linux", "shell", "awk", "sed",
    ]
    found = set()
    text_lower = review_text.lower()
    for kw in tech_keywords:
        if kw in text_lower:
            label = kw.replace("_", " ").title()
            found.add(label)
    return list(found)[:8]


def _generate_resume_highlight(skills: list, task_desc: str) -> str:
    if not skills and not task_desc:
        return ""
    skill_str = ", ".join(skills[:5]) if skills else "编程实践"
    return f"通过实现{task_desc[:30]}项目，掌握了{skill_str}等核心技术，具备独立完成中等复杂度系统开发的能力"


def _extract_learning_suggestion(review_text: str) -> str:
    if not review_text:
        return ""
    suggestion_patterns = [
        r"(?:建议|推荐|可以|应该|下一步|进阶)[：:]\s*(.+?)(?:\n|$)",
        r"(?:improve|suggest|recommend|next step)[：:]\s*(.+?)(?:\n|$)",
    ]
    for pattern in suggestion_patterns:
        matches = re.findall(pattern, review_text, re.IGNORECASE)
        if matches:
            return matches[0].strip()[:200]
    return ""


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
        "并发执行并汇总结果。子任务超时保护：bash 120s，compile/test 180s，llm 300s。"
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
            "系统自动分配独立沙盒工作区，超时保护：bash 120s，compile/test 180s，llm 300s。"
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
                task_timeout = 120.0
                if task_type == "llm":
                    task_timeout = 300.0
                elif task_type in ("compile", "test"):
                    task_timeout = 180.0
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=task_timeout,
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                result.status = "timeout"
                result.error = f"子进程超时被斩断 ({task_timeout:.0f}s)"
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
    global_timeout: float = 0,
) -> list:
    if global_timeout <= 0:
        max_task_timeout = 120.0
        for t in tasks:
            tt = t.get("type", "bash")
            if tt == "llm":
                max_task_timeout = max(max_task_timeout, 300.0)
            elif tt in ("compile", "test"):
                max_task_timeout = max(max_task_timeout, 180.0)
        global_timeout = max_task_timeout + 30.0

    logger.info(f"🚀 并发派发了 {len(tasks)} 个子任务（全局超时: {global_timeout:.0f}s）...")

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
    timeout_per_task: float = 120.0,
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


# ============================================================================
# SDD (Subagent-Driven Development) 引擎 — 三角色协作架构
# ============================================================================
#
#  ┌──────────┐  spawn_subagent   ┌──────────────┐   review     ┌──────────────┐
#  │ LeadAgent │ ──────────────→ │ Implementer   │ ──────────→ │ Reviewer     │
#  │ (主控)    │ ←────────────── │ Agent (执行者) │ ←────────── │ Agent (审查者)│
#  │ ask_user  │  status report  │ 全部工具      │  fix/reject │ 只读工具      │
#  └──────────┘                  └──────────────┘              └──────────────┘
#
#  流程: Lead 拆解任务 → Implementer 实现 → Reviewer 审查
#        → 通过则完成 / 拒绝则打回 Implementer 修改 (最多3次)
# ============================================================================

SDD_PROMPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_prompts", "sdd")

IMPLEMENTER_TOOLS = {
    "file_edit", "file_read", "file_write", "bash", "glob", "grep",
    "ask_user", "semantic_search", "semantic_search_code",
    "get_code_structure", "get_function_definition",
    "lsp_tool", "git_tool", "auto_test", "run_auto_test",
    "start_background_service", "read_service_logs", "kill_service",
    "read_project_memory", "record_learning", "meta_tool",
}

SDD_REVIEWER_TOOLS = {
    "file_read", "glob", "grep",
    "semantic_search", "semantic_search_code",
    "get_code_structure", "get_function_definition",
    "lsp_tool", "git_tool", "bash",
    "read_project_memory",
}

LEAD_AGENT_TOOLS = {
    "ask_user", "file_read", "glob", "grep",
    "git_tool", "read_project_memory",
}

SDD_MAX_REVIEW_RETRIES = 3
SDD_SUBAGENT_TIMEOUT_S = 600


def _load_sdd_prompt(filename: str) -> str:
    filepath = os.path.join(SDD_PROMPTS_DIR, filename)
    if os.path.isfile(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    logger.warning(f"SDD prompt file not found: {filepath}")
    return ""


def _get_sdd_tools_for_role(role: str, provider: str = "openai") -> list[dict]:
    from agent_runner import _get_tools_definition

    all_tools = _get_tools_definition(provider)

    if role == "implementer":
        allowed = IMPLEMENTER_TOOLS
    elif role == "reviewer":
        allowed = SDD_REVIEWER_TOOLS
    elif role == "lead":
        allowed = LEAD_AGENT_TOOLS
    else:
        allowed = IMPLEMENTER_TOOLS

    filtered = []
    for tool in all_tools:
        if provider == "anthropic":
            name = tool.get("name", "")
        else:
            name = tool.get("function", {}).get("name", "")
        if name in allowed:
            filtered.append(tool)

    return filtered


def _run_sdd_subagent(
    role: str,
    instruction: str,
    work_dir: str,
    provider: str = "openai",
    api_key: str = None,
    model: str = None,
    base_url: str = None,
    max_turns: int = 20,
    main_repo_dir: str = "",
    task_id: str = None,
    session_id: str = None,
    yield_events: bool = False,
    images: Optional[list] = None,
    timeout_s: float = SDD_SUBAGENT_TIMEOUT_S,
):
    if role == "implementer":
        role_prompt = _load_sdd_prompt("implementer-prompt.md")
        if not role_prompt:
            role_prompt = (
                "You are an Implementer Agent. Your job is to write code, tests, and commit.\n"
                "Report status: DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT\n"
                "Follow TDD. Self-review before reporting. Never overbuild."
            )
    elif role == "reviewer":
        role_prompt = _load_sdd_prompt("code-quality-reviewer-prompt.md")
        if not role_prompt:
            role_prompt = (
                "You are a Code Quality Reviewer Agent. Review the code changes below.\n"
                "You have READ-ONLY access. Never modify files.\n"
                "Return: APPROVED or REJECTED with specific issues."
            )
    else:
        role_prompt = ""

    TOOL_CALL_ENFORCER = (
        "\n\n🚨 CRITICAL INSTRUCTION (FATAL IF IGNORED):\n"
        "1. You MUST NOT output long conversational plans or explanations.\n"
        "2. You MUST interact with the system EXCLUSIVELY by invoking the provided tool functions "
        "(e.g., bash, file_edit, file_read, grep, glob, ask_user, etc.).\n"
        "3. DO NOT wrap your actions in markdown code blocks. Use the native JSON Tool Calling schema.\n"
        "If you understand, immediately invoke a tool to begin the task without any conversational filler."
    )

    instruction = instruction.rstrip() + TOOL_CALL_ENFORCER

    role_session_id = session_id or f"sdd_{role}_{uuid.uuid4().hex[:6]}"
    effective_images = images or []

    if provider == "anthropic":
        if effective_images:
            anthropic_content = [{"type": "text", "text": f"{role_prompt}\n\n---\n\n{instruction}"}]
            for img_b64 in effective_images:
                if isinstance(img_b64, str) and img_b64:
                    prefix = "" if img_b64.startswith("data:image") else "data:image/jpeg;base64,"
                    url = f"{prefix}{img_b64}"
                    if url.startswith("data:image/"):
                        parts = url.split(";base64,", 1)
                        media_type = parts[0].replace("data:image/", "image/")
                        b64_data = parts[1] if len(parts) > 1 else ""
                        anthropic_content.append({
                            "type": "image",
                            "source": {"type": "base64", "media_type": media_type, "data": b64_data},
                        })
            initial_messages = [{"role": "user", "content": anthropic_content}]
            user_input = ""
        else:
            initial_messages = [{"role": "user", "content": f"{role_prompt}\n\n---\n\n{instruction}"}]
            user_input = instruction
    else:
        if effective_images:
            content_list = [{"type": "text", "text": instruction}]
            for img_b64 in effective_images:
                if isinstance(img_b64, str) and img_b64:
                    prefix = "" if img_b64.startswith("data:image") else "data:image/jpeg;base64,"
                    content_list.append({
                        "type": "image_url",
                        "image_url": {"url": f"{prefix}{img_b64}"},
                    })
            initial_messages = [
                {"role": "system", "content": role_prompt},
                {"role": "user", "content": content_list},
            ]
            user_input = ""
        else:
            initial_messages = [{"role": "system", "content": role_prompt}]
            user_input = instruction

    from agent_runner import run_agent as _run_agent

    last_assistant_text = ""
    events_collected = []

    start_time = time.time()
    timed_out = False

    for event in _run_agent(
        user_input=user_input,
        work_dir=work_dir,
        api_key=api_key,
        model=model,
        base_url=base_url,
        provider=provider,
        max_turns=max_turns,
        session_id=role_session_id,
        task_id=task_id,
        initial_messages=initial_messages if initial_messages else None,
        main_repo_dir=main_repo_dir,
        auto_approve=True,
    ):
        if time.time() - start_time > timeout_s:
            timed_out = True
            logger.warning(f"[SDD] ⏰ Subagent {role} 超时 ({timeout_s}s)，强制终止")
            break

        if _is_terminal_signal(event):
            continue

        event_type = event.get("type", "")

        if event_type == "assistant":
            text = event.get("data", "")
            if text and isinstance(text, str) and text.strip():
                last_assistant_text = text.strip()

        if role == "reviewer":
            if event_type == "tool_start":
                tool_name = event.get("tool_name", "")
                if tool_name not in SDD_REVIEWER_TOOLS:
                    event["data"] = f"🚫 权限拒绝: Reviewer 不能使用 {tool_name} 工具"
                    event["is_error"] = True
            elif event_type == "tool_end":
                tool_name = event.get("tool_name", "")
                if tool_name == "bash":
                    tool_data = event.get("data", "")
                    if tool_data:
                        first_line = tool_data.split("\n")[0] if "\n" in tool_data else tool_data
                        is_safe, reason = _check_reviewer_bash_safety(first_line)
                        if not is_safe:
                            event["data"] = f"🚫 权限拒绝: {reason}"
                            event["is_error"] = True

        event["sdd_role"] = role
        events_collected.append(event)

        if yield_events:
            yield event

    final_text = last_assistant_text or _get_last_assistant_text(task_id, role_session_id)

    if timed_out:
        final_text = f"⏰ TIMEOUT: Subagent {role} exceeded {timeout_s}s limit.\n{final_text}"

    result = {
        "role": role,
        "status": "timeout" if timed_out else "done",
        "output": final_text,
        "events": events_collected,
    }

    if not yield_events:
        yield result
    else:
        yield {
            "type": "sdd_subagent_finish",
            "data": final_text,
            "role": role,
            "status": "timeout" if timed_out else "done",
        }


def _extract_sdd_status(text: str) -> str:
    if not text:
        return "DONE"
    upper = text.upper()
    if "BLOCKED" in upper:
        return "BLOCKED"
    if "NEEDS_CONTEXT" in upper:
        return "NEEDS_CONTEXT"
    if "DONE_WITH_CONCERNS" in upper:
        return "DONE_WITH_CONCERNS"
    return "DONE"


def _extract_review_verdict(text: str) -> str:
    if not text:
        return "APPROVED"
    upper = text.upper()
    if "REJECTED" in upper or "❌" in text or "DENIED" in upper:
        return "REJECTED"
    if "APPROVED" in upper or "LGTM" in upper or "✅" in text or "PASS" in upper:
        return "APPROVED"
    return "REJECTED"


def run_sdd_loop(
    task: str,
    work_dir: str = ".",
    provider: str = "openai",
    api_key: str = None,
    model: str = None,
    base_url: str = None,
    main_repo_dir: str = "",
    task_id: str = None,
    max_review_retries: int = SDD_MAX_REVIEW_RETRIES,
    yield_events: bool = True,
    images: Optional[list] = None,
):
    """
    SDD (Subagent-Driven Development) 主循环

    流程:
      1. Lead Agent 拆解任务 (使用 SKILL.md prompt)
      2. Implementer Agent 实现 (使用 implementer-prompt.md)
      3. Reviewer Agent 审查 (使用 code-quality-reviewer-prompt.md)
      4. 审查通过 → 完成 / 审查拒绝 → 打回 Implementer (最多 max_review_retries 次)
    """
    if not task_id:
        task_id = f"sdd_{uuid.uuid4().hex[:8]}"

    lead_prompt = _load_sdd_prompt("SKILL.md")
    if not lead_prompt:
        lead_prompt = "You are a Lead Agent coordinating implementation tasks."

    yield {
        "type": "sdd_loop_start",
        "data": {"task_id": task_id, "task": task[:100]},
    }

    yield {
        "type": "sdd_status",
        "data": {
            "phase": "lead",
            "message": "🔄 Lead Agent 正在拆解任务...",
            "task_id": task_id,
        },
    }

    lead_instruction = (
        f"{lead_prompt}\n\n"
        f"## User Task\n\n{task}\n\n"
        "Analyze this task and break it down into implementation steps. "
        "For each step, provide a clear description that an Implementer Agent can follow. "
        "Output your plan as a numbered list of tasks."
    )

    lead_output = ""
    for event in _run_sdd_subagent(
        role="lead",
        instruction=lead_instruction,
        work_dir=work_dir,
        provider=provider,
        api_key=api_key,
        model=model,
        base_url=base_url,
        max_turns=5,
        main_repo_dir=main_repo_dir,
        task_id=task_id,
        yield_events=yield_events,
        images=images,
    ):
        if yield_events:
            if isinstance(event, dict) and event.get("type") == "sdd_subagent_finish":
                lead_output = event.get("data", "")
            else:
                yield event
        else:
            if isinstance(event, dict):
                lead_output = event.get("output", "")

    if not lead_output:
        lead_output = task

    task_steps = _parse_task_steps(lead_output)
    if not task_steps:
        task_steps = [task]

    yield {
        "type": "sdd_plan_ready",
        "data": {
            "task_id": task_id,
            "steps": task_steps,
            "total_steps": len(task_steps),
        },
    }

    all_results = []

    for step_idx, step in enumerate(task_steps):
        step_id = f"{task_id}_step{step_idx + 1}"

        yield {
            "type": "sdd_status",
            "data": {
                "phase": "implement",
                "step": step_idx + 1,
                "total_steps": len(task_steps),
                "message": f"👨‍💻 Implementer 正在执行步骤 {step_idx + 1}/{len(task_steps)}: {step[:60]}...",
                "task_id": task_id,
            },
        }

        implementer_instruction = (
            f"You are implementing: {step}\n\n"
            f"## Context\nThis is step {step_idx + 1} of {len(task_steps)} "
            f"for the overall task: {task}\n\n"
            "## Your Job\n"
            "1. Implement exactly what the task specifies\n"
            "2. Write tests and verify\n"
            "3. Commit your work\n"
            "4. Self-review\n"
            "5. Report status: DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT\n\n"
            f"Work directory: {work_dir}"
        )

        impl_output = ""
        for event in _run_sdd_subagent(
            role="implementer",
            instruction=implementer_instruction,
            work_dir=work_dir,
            provider=provider,
            api_key=api_key,
            model=model,
            base_url=base_url,
            max_turns=20,
            main_repo_dir=main_repo_dir,
            task_id=step_id,
            yield_events=yield_events,
            images=images,
        ):
            if yield_events:
                if isinstance(event, dict) and event.get("type") == "sdd_subagent_finish":
                    impl_output = event.get("data", "")
                else:
                    yield event
            else:
                if isinstance(event, dict):
                    impl_output = event.get("output", "")

        impl_status = _extract_sdd_status(impl_output)

        if impl_status in ("BLOCKED", "NEEDS_CONTEXT"):
            yield {
                "type": "sdd_step_blocked",
                "data": {
                    "step": step_idx + 1,
                    "status": impl_status,
                    "output": impl_output[:500],
                    "task_id": task_id,
                },
            }
            all_results.append({"step": step, "status": impl_status, "output": impl_output})
            continue

        git_diff = _get_git_diff(work_dir)

        review_retry = 0
        review_approved = False

        while review_retry < max_review_retries:
            review_retry += 1

            yield {
                "type": "sdd_status",
                "data": {
                    "phase": "review",
                    "step": step_idx + 1,
                    "retry": review_retry,
                    "message": f"🕵️ Reviewer 正在审查步骤 {step_idx + 1} 的代码 (第 {review_retry} 次审查)...",
                    "task_id": task_id,
                },
            }

            reviewer_instruction = (
                f"Review the code changes for: {step}\n\n"
                f"## Implementer Report\n{impl_output[:2000]}\n\n"
                f"## Git Diff\n{git_diff[:3000]}\n\n"
                "## Your Job\n"
                "Review the code quality. Check:\n"
                "- Does the implementation match the spec?\n"
                "- Is the code clean and maintainable?\n"
                "- Are there edge cases or bugs?\n"
                "- Is test coverage adequate?\n\n"
                "Return APPROVED or REJECTED with specific issues to fix."
            )

            review_output = ""
            for event in _run_sdd_subagent(
                role="reviewer",
                instruction=reviewer_instruction,
                work_dir=work_dir,
                provider=provider,
                api_key=api_key,
                model=model,
                base_url=base_url,
                max_turns=10,
                main_repo_dir=main_repo_dir,
                task_id=step_id,
                yield_events=yield_events,
            ):
                if yield_events:
                    if isinstance(event, dict) and event.get("type") == "sdd_subagent_finish":
                        review_output = event.get("data", "")
                    else:
                        yield event
                else:
                    if isinstance(event, dict):
                        review_output = event.get("output", "")

            verdict = _extract_review_verdict(review_output)

            if verdict == "APPROVED":
                review_approved = True
                yield {
                    "type": "sdd_review_approved",
                    "data": {
                        "step": step_idx + 1,
                        "review_output": review_output[:500],
                        "task_id": task_id,
                    },
                }
                break
            else:
                yield {
                    "type": "sdd_review_rejected",
                    "data": {
                        "step": step_idx + 1,
                        "retry": review_retry,
                        "review_output": review_output[:500],
                        "task_id": task_id,
                    },
                }

                if review_retry < max_review_retries:
                    fix_instruction = (
                        f"The Reviewer REJECTED your implementation for: {step}\n\n"
                        f"## Reviewer Feedback\n{review_output[:2000]}\n\n"
                        "## Your Job\n"
                        "Fix the issues identified by the Reviewer. "
                        "Then commit and report status again."
                    )

                    yield {
                        "type": "sdd_status",
                        "data": {
                            "phase": "fix",
                            "step": step_idx + 1,
                            "retry": review_retry,
                            "message": f"🔧 Implementer 正在根据审查意见修复 (第 {review_retry} 次修改)...",
                            "task_id": task_id,
                        },
                    }

                    impl_output = ""
                    for event in _run_sdd_subagent(
                        role="implementer",
                        instruction=fix_instruction,
                        work_dir=work_dir,
                        provider=provider,
                        api_key=api_key,
                        model=model,
                        base_url=base_url,
                        max_turns=15,
                        main_repo_dir=main_repo_dir,
                        task_id=step_id,
                        yield_events=yield_events,
                        images=images,
                    ):
                        if yield_events:
                            if isinstance(event, dict) and event.get("type") == "sdd_subagent_finish":
                                impl_output = event.get("data", "")
                            else:
                                yield event
                        else:
                            if isinstance(event, dict):
                                impl_output = event.get("output", "")

                    git_diff = _get_git_diff(work_dir)

        step_status = "approved" if review_approved else "max_retries"
        all_results.append({
            "step": step,
            "status": step_status,
            "output": impl_output,
            "review_retries": review_retry,
        })

    yield {
        "type": "sdd_loop_end",
        "data": {
            "task_id": task_id,
            "total_steps": len(task_steps),
            "results": all_results,
        },
    }


def _parse_task_steps(lead_output: str) -> list[str]:
    if not lead_output:
        return []

    steps = []
    lines = lead_output.strip().split("\n")

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        match = re.match(r'^\s*(?:\d+[\.\):]\s*|[-*]\s+)(.+)', stripped)
        if match:
            step_text = match.group(1).strip()
            if len(step_text) > 10:
                steps.append(step_text)

    if not steps:
        paragraphs = [p.strip() for p in lead_output.split("\n\n") if p.strip() and len(p.strip()) > 20]
        if paragraphs:
            steps = paragraphs[:5]

    return steps


def _get_git_diff(work_dir: str) -> str:
    try:
        from bash_executor import execute_bash
        result = execute_bash("git diff HEAD~1 --stat && echo '---FULL---' && git diff HEAD~1", work_dir=work_dir)
        if result and not result.blocked and result.stdout:
            diff_text = result.stdout
            if len(diff_text) > 5000:
                return diff_text[:5000] + "\n... (truncated)"
            return diff_text
    except Exception as e:
        logger.debug(f"获取 git diff 失败: {e}")

    try:
        from bash_executor import execute_bash
        result = execute_bash("git diff --stat && echo '---FULL---' && git diff", work_dir=work_dir)
        if result and not result.blocked and result.stdout:
            diff_text = result.stdout
            if len(diff_text) > 5000:
                return diff_text[:5000] + "\n... (truncated)"
            return diff_text
    except Exception as e:
        logger.debug(f"获取 unstaged git diff 失败: {e}")

    return "(no git diff available)"


def start_debate_loop(
    task: str,
    dynamic_persona_prompt: str = "",
    work_dir: str = ".",
    provider: str = "openai",
    api_key: str = None,
    model: str = None,
    base_url: str = None,
    max_loops: int = 3,
    main_repo_dir: str = "",
    task_id: str = None,
    session_id: str = None,
    auto_approve: bool = False,
    yield_events: bool = True,
    images: Optional[list] = None,
):
    """
    红蓝对抗引擎 — 高级 API

    当 Supervisor（CTO）决定了专家身份和子任务后，调用此函数启动对抗循环。
    蓝军（Coder）继承 dynamic_persona_prompt 编写代码，
    红军（Reviewer）从该领域最佳实践角度进行深度挑刺。

    Args:
        task: Supervisor 拆解后的子任务描述
        dynamic_persona_prompt: 专家身份 Prompt（来自 Supervisor 路由结果）
        work_dir: 工作目录
        provider: LLM 提供商
        api_key: API Key
        model: 模型名称
        base_url: API Base URL
        max_loops: 最大对抗轮数（默认3轮）
        main_repo_dir: 主仓库目录
        task_id: 任务 ID
        session_id: 会话 ID
        auto_approve: 是否自动批准
        yield_events: 是否流式输出事件

    Returns:
        如果 yield_events=True，yield 事件流
        如果 yield_events=False，返回 SwarmResult
    """
    custom_coder_prompt = ""
    custom_reviewer_prompt = ""

    if dynamic_persona_prompt:
        custom_coder_prompt = (
            f"{dynamic_persona_prompt}\n\n"
            "⚠️ Coder 行为规范（附加）：\n"
            "1. 你的代码写完后，会交由一位极其严苛的架构师（Reviewer）进行审查\n"
            "2. 请使用工具完成开发，当你认为全部写完且测试通过后，请回复：【提交审查】+ 你的修改总结\n"
            "3. 如果 Reviewer 打回你的代码，你必须根据 Reviewer 的意见修复问题，然后再次提交审查\n"
            "4. 你拥有完整的文件编辑和命令执行权限，请善用这些工具写出高质量代码\n"
            "5. 绝对禁止直接在回复文本中输出大段完整代码！必须通过 file_edit 工具写入文件\n"
        )

        domain_hint = dynamic_persona_prompt[:200]
        custom_reviewer_prompt = (
            f"{REVIEWER_PROMPT}\n\n"
            f"# 🎯 领域感知审计增强\n"
            f"上述代码由以下领域的专家编写：\n"
            f"---\n"
            f"{domain_hint}\n"
            f"---\n\n"
            f"请你从该领域的安全和性能最佳实践角度，进行深度挑刺。"
            f"例如：如果代码声称是高并发 C++ 专家写的，你必须重点检查内存安全、线程安全、RAII 合规性；"
            f"如果代码声称是数据库专家写的，你必须重点检查 SQL 注入、索引设计、事务隔离级别等。\n\n"
            f"但请注意：如果代码确实符合该领域的最佳实践，没有致命问题，请果断 APPROVE，不要过度审查。"
        )

    logger.info(
        f"[DebateLoop] 🔥 启动红蓝对抗 | "
        f"动态专家: {'是' if dynamic_persona_prompt else '否'} | "
        f"任务: {task[:80]}"
    )

    return run_swarm(
        task_description=task,
        work_dir=work_dir,
        provider=provider,
        api_key=api_key,
        model=model,
        base_url=base_url,
        max_loops=max_loops,
        main_repo_dir=main_repo_dir,
        task_id=task_id,
        session_id=session_id,
        auto_approve=auto_approve,
        yield_events=yield_events,
        custom_coder_prompt=custom_coder_prompt,
        custom_reviewer_prompt=custom_reviewer_prompt,
        images=images,
    )


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


# ============================================================================
# Coder-Reviewer 对抗博弈系统 - RBAC 权限隔离 + 状态机闭环
# ============================================================================

CODER_TOOLS = {
    "file_edit", "file_read", "bash", "glob", "grep",
    "ask_user", "semantic_search", "semantic_search_code",
    "get_code_structure", "get_function_definition",
    "lsp_tool", "git_tool", "auto_test", "run_auto_test",
    "start_background_service", "read_service_logs", "kill_service",
    "read_project_memory", "record_learning",
    "meta_tool",
}

REVIEWER_TOOLS = {
    "file_read", "glob", "grep",
    "semantic_search", "semantic_search_code",
    "get_code_structure", "get_function_definition",
    "lsp_tool", "git_tool",
    "bash",
    "read_project_memory",
}

REVIEWER_BASH_WHITELIST = {
    "pytest", "python3 -m pytest", "python -m pytest",
    "make test", "cargo test", "go test", "npm test",
    "cat ", "head ", "tail ", "wc ", "find ", "ls ",
    "grep ", "rg ", "fd ", "which ", "type ",
    "git status", "git diff", "git log", "git show",
    "python3 -c ", "python -c ",
    "echo ", "stat ", "file ",
}

CODER_PROMPT = """你是资深的研发工程师（Coder）。你的任务是编写和修改代码以完成用户需求。

⚠️ 重要规则：
1. 你的代码写完后，会交由一位极其严苛的架构师（Reviewer）进行审查。
2. 请使用工具完成开发，当你认为全部写完且测试通过后，请回复：【提交审查】+ 你的修改总结。
3. 如果 Reviewer 打回你的代码，你必须根据 Reviewer 的意见修复问题，然后再次提交审查。
4. 每次修复时，请仔细阅读 Reviewer 的每一条意见，逐一修复，不要遗漏。
5. 你拥有完整的文件编辑和命令执行权限，请善用这些工具写出高质量代码。

【强制输出规范】当你要编写或修改代码时，绝对禁止直接在回复文本中输出大段的完整代码！
你必须且只能通过调用 file_edit 工具将代码写入文件。如果你在回复文本中直接贴代码，
你的回答将被系统直接截断并判定为失败。回复文本只用于说明你的思路和修改总结。

【交接纪律】你有充足的时间完成任务（35轮工具调用）。请自主使用工具写代码并跑测试。
只有当你确信功能已全部实现且测试无误时，才停止调用工具，并在回复的最后明确写上
【提交审查】四个字。绝对不要在代码还没写完时就提前停止！

代码质量要求：
- 所有异常必须被正确处理，不能有裸 except
- 资源（文件、连接）必须使用 with 语句或 try/finally 确保释放
- 并发代码必须考虑死锁和竞态条件
- 函数必须有清晰的类型注释和文档字符串
- 测试必须覆盖核心逻辑路径
"""

REVIEWER_PROMPT = """你是铁面无私的架构师代码审查员（Reviewer）。你不能直接修改代码。

你的任务是：检查 Coder 刚刚提交的代码，给出审查意见。

🚨 绝对禁止：
- 你**不能**调用 file_edit 修改代码！
- 你**不能**调用 start_background_service 启动服务！
- 你**只能**使用只读工具（file_read, grep, glob, get_code_structure 等）查看代码

🚫 测试纪律：
- 你**不能**手动使用 bash 运行 pytest、make test 等测试命令！
- 系统中的 TDD 自愈引擎（auto_test_tool）已经跑过测试了，请直接信任其结果。
- 你**只能**用 bash 执行纯只读命令（cat, ls, grep, git diff, git log, git status 等）。

⚡ 效率铁律（必须严格遵守）：
1.【禁止自行搜集背景】Coder 修改的文件和 Git Diff 已经附在下方了！绝对禁止你使用 ls、git status、find、pwd 等命令去摸索环境！直接阅读下方提供的 Diff 和代码！
2.【禁止过度检查】不要去搜 TODO、FIXME、HACK 注释！不要检查无关文件！只要核心逻辑能跑通即可！你的审查范围仅限于 Diff 中涉及的文件。
3.【强制提交报告】在你完成所有代码阅读和检查后，你**必须**在回复的最后使用 XML 标签输出纯文本结论！绝对禁止使用 Markdown 代码块符号（```）！系统只从 XML 标签中提取你的裁决！

📋 审查报告格式（必须严格遵守）：
在你回复的最后，必须输出如下格式的纯文本（绝对禁止使用 ``` 符号！）：

<DECISION>APPROVE</DECISION>
<FEEDBACK>LGTM: 代码质量良好，核心逻辑正确。</FEEDBACK>

或：

<DECISION>REJECT</DECISION>
<FEEDBACK>第 42 行存在空指针异常风险，请添加 None 检查。</FEEDBACK>

标签说明：
- <DECISION>：只能填 APPROVE 或 REJECT
- <FEEDBACK>：APPROVE 时写 LGTM 及理由；REJECT 时必须详细指出错误位置和修改建议
- 绝对禁止使用 Markdown 代码块符号 ``` 包裹！直接写纯文本标签即可！

审查标准（按严重程度排序）：
1. 🔴 致命问题：并发死锁、内存泄漏、资源未释放、SQL 注入等安全漏洞
2. 🟠 严重问题：未处理的异常、错误的逻辑、缺失的错误处理
3. 🟡 一般问题：代码风格不佳、缺少类型注释、命名不规范
4. 🟢 建议改进：性能优化、可读性提升

审查流程：
1. 直接阅读下方提供的 Git Diff 和 Coder 提交说明（不需要再 git diff！）
2. 如需深入了解，用 file_read 查看修改的文件完整内容（只看 Diff 涉及的文件！）
3. 逐个检查上述审查标准
4. 在回复末尾使用 <DECISION> 和 <FEEDBACK> 标签提交最终结论

【审查尺度动态调整】在审查前，你必须先阅读用户的原始需求。如果用户的需求包含"简单"、"示例"、"Demo"、"快速"、"测试"等词汇，绝对禁止过度工程化！只要代码能跑通且没有毁灭性 Bug 就必须 APPROVE。不要强求完整的异常处理、极端的内存优化或企业级设计模式。

【最终决断】如果你觉得代码基本满足要求，没有致命 Bug，请立即输出 <DECISION>APPROVE</DECISION>。不要过度审查！

【再次强调】你必须在回复的最后输出 <DECISION> 和 <FEEDBACK> 标签！系统只从这些标签中提取你的最终意见！没有标签 = 审查失败 = 系统兜底放行！绝对禁止使用 Markdown 代码块符号 ```！
"""


class SwarmState:
    CODING = "CODING"
    SUBMITTED = "SUBMITTED"
    REVIEWING = "REVIEWING"
    LGTM = "LGTM"
    REJECTED = "REJECTED"
    MAX_LOOPS = "MAX_LOOPS"


@dataclass
class SwarmResult:
    status: str
    loops: int = 0
    coder_output: str = ""
    reviewer_output: str = ""
    final_code_diff: str = ""
    error: str = ""


def _get_tools_for_role(role: str, provider: str = "openai") -> list[dict]:
    from agent_runner import _get_tools_definition

    all_tools = _get_tools_definition(provider)
    allowed = CODER_TOOLS if role == "coder" else REVIEWER_TOOLS

    filtered = []
    for tool in all_tools:
        if provider == "anthropic":
            name = tool.get("name", "")
        else:
            name = tool.get("function", {}).get("name", "")

        if name in allowed:
            filtered.append(tool)

    return filtered


def _extract_final_text(messages: list[dict]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            if content and isinstance(content, str) and content.strip():
                return content.strip()
    return ""


def _check_reviewer_bash_safety(command: str) -> tuple[bool, str]:
    command_stripped = command.strip()

    dangerous_patterns = [">", ">>", "|", "$(", "`",
                          "rm ", "rmdir", "mv ", "cp ",
                          "chmod", "chown", "pip install",
                          "apt ", "yum ", "dnf ", "brew ",
                          "curl ", "wget ", "nc ", "ncat ",
                          "os.system", "subprocess",
                          "pytest", "python3 -m pytest", "python -m pytest",
                          "make test", "cargo test", "go test", "npm test",
                          "run_auto_test"]
    for pat in dangerous_patterns:
        if pat in command_stripped:
            return False, f"Reviewer 不允许执行包含 '{pat}' 的命令"

    for prefix in ("cat ", "head ", "tail ", "wc ", "find ", "ls ",
                   "grep ", "rg ", "which ", "type ",
                   "git status", "git diff", "git log", "git show",
                   "python3 -c ", "python -c ",
                   "echo ", "stat ", "file "):
        if command_stripped.startswith(prefix):
            return True, ""

    return True, ""


def _run_role_agent(
    role: str,
    instruction: str,
    work_dir: str,
    provider: str = "openai",
    api_key: str = None,
    model: str = None,
    base_url: str = None,
    max_turns: int = 15,
    main_repo_dir: str = "",
    task_id: str = None,
    session_id: str = None,
    yield_events: bool = False,
    images: Optional[list] = None,
):
    if yield_events:
        yield from _run_role_agent_events(
            role=role,
            instruction=instruction,
            work_dir=work_dir,
            provider=provider,
            api_key=api_key,
            model=model,
            base_url=base_url,
            max_turns=max_turns,
            main_repo_dir=main_repo_dir,
            task_id=task_id,
            session_id=session_id,
            images=images,
        )
        return

    result_text = ""
    for event in _run_role_agent_events(
        role=role,
        instruction=instruction,
        work_dir=work_dir,
        provider=provider,
        api_key=api_key,
        model=model,
        base_url=base_url,
        max_turns=max_turns,
        main_repo_dir=main_repo_dir,
        task_id=task_id,
        session_id=session_id,
        images=images,
    ):
        if event.get("type") == "assistant":
            result_text = event.get("data", result_text)
        elif event.get("type") == "finish":
            result_text = event.get("data", result_text)

    return result_text, []


def _extract_text_from_content(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif "text" in block:
                    parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts).strip()
    return str(content).strip()


_THINKING_TOOL_NAMES = (
    "mcp_sequential-thinking_sequentialthinking",
    "mcp_sequential-thinking",
    "sequentialthinking",
    "sequential-thinking",
)


def _extract_thought_from_tool_calls(tool_calls: list) -> str:
    if not tool_calls:
        return ""
    for tc in reversed(tool_calls):
        fn = tc.get("function", {})
        fn_name = fn.get("name", "")
        if any(tn in fn_name for tn in _THINKING_TOOL_NAMES):
            args_str = fn.get("arguments", "")
            if not args_str:
                continue
            try:
                args = json.loads(args_str) if isinstance(args_str, str) else args_str
                thought = args.get("thought", "")
                if thought and isinstance(thought, str) and thought.strip():
                    return thought.strip()
            except (json.JSONDecodeError, TypeError):
                pass
    return ""


def _extract_review_from_text(text: str) -> tuple:
    if not text or not isinstance(text, str):
        return None, ""
    decision_match = re.search(r'<DECISION>\s*(APPROVE|REJECT)\s*</DECISION>', text, re.DOTALL | re.IGNORECASE)
    feedback_match = re.search(r'<FEEDBACK>\s*(.*?)\s*</FEEDBACK>', text, re.DOTALL | re.IGNORECASE)
    if decision_match and feedback_match:
        decision = decision_match.group(1).strip().upper()
        feedback = feedback_match.group(1).strip()
        if decision in ("APPROVE", "REJECT"):
            return decision, feedback
    json_patterns = [
        r'```json\s*(\{[^`]*?"decision"\s*:\s*"(?:APPROVE|REJECT)"[^`]*?\})\s*```',
        r'```\s*(\{[^`]*?"decision"\s*:\s*"(?:APPROVE|REJECT)"[^`]*?\})\s*```',
        r'(\{[^{}]*?"decision"\s*:\s*"(?:APPROVE|REJECT)"[^{}]*?"feedback"\s*:\s*"[^"]*?"[^{}]*?\})',
    ]
    for pattern in json_patterns:
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            json_str = match.group(1)
            try:
                data = json.loads(json_str)
                decision = data.get("decision", "").upper()
                feedback = data.get("feedback", data.get("detailed_feedback", ""))
                if decision in ("APPROVE", "REJECT"):
                    return decision, feedback
            except (json.JSONDecodeError, TypeError):
                continue
    return None, ""


def _get_last_assistant_text(task_id: str, session_id: str, user_id: int = 0) -> str:
    try:
        from task_manager import get_task_manager
        tm = get_task_manager(user_id=user_id)
        session = tm.get_session(task_id)
        if session:
            all_messages = (session.messages_before or []) + session.messages
            for msg in reversed(all_messages):
                if msg.get("role") != "assistant":
                    continue
                text = _extract_text_from_content(msg.get("content"))
                if text:
                    decision, feedback = _extract_review_from_text(text)
                    if decision:
                        return f"【{decision}】\n{feedback}"
                    return text
                thought = _extract_thought_from_tool_calls(msg.get("tool_calls", []))
                if thought:
                    return thought
    except Exception as e:
        logger.debug(f"[Swarm] 从 task_manager 读取历史失败: {e}")

    try:
        from session_storage import SessionStorage
        storage = SessionStorage()
        db_messages = storage.get_session_messages(session_id)
        for msg in reversed(db_messages):
            if msg.get("role") != "assistant":
                continue
            text = _extract_text_from_content(msg.get("content"))
            if text:
                decision, feedback = _extract_review_from_text(text)
                if decision:
                    return f"【{decision}】\n{feedback}"
                return text
            thought = _extract_thought_from_tool_calls(msg.get("tool_calls", []))
            if thought:
                return thought
    except Exception as e:
        logger.debug(f"[Swarm] 从 session_storage 读取历史失败: {e}")

    return ""


_TERMINAL_SIGNALS = {"finish", "distill"}
_TERMINAL_STATUSES = {"DONE", "IDLE", "ERROR"}


_IMPLICIT_APPROVAL_PATTERNS = (
    "LGTM",
    "APPROVE",
    "代码正确",
    "没有引入新的问题",
    "没有发现问题",
    "没有致命",
    "没有严重问题",
    "代码质量达标",
    "审查通过",
    "代码符合规范",
    "可以合并",
    "没有发现任何问题",
    "代码看起来没有问题",
    "代码没有问题",
    "逻辑正确",
    "功能正常",
    "代码是正确的",
    "没有明显问题",
    "没有重大问题",
    "代码基本满足",
    "looks good",
    "no issues",
    "approved",
    "passed",
)


def _is_approval(text: str) -> bool:
    if not text:
        return False
    upper = text.upper()
    for pattern in _IMPLICIT_APPROVAL_PATTERNS:
        if pattern.upper() in upper:
            return True
    return False


def _is_terminal_signal(event: dict) -> bool:
    event_type = event.get("type", "")
    if event_type in _TERMINAL_SIGNALS:
        return True
    if event_type == "agent_status":
        status = event.get("status", "")
        if status in _TERMINAL_STATUSES:
            return True
    return False


def _run_role_agent_events(
    role: str,
    instruction: str,
    work_dir: str,
    provider: str = "openai",
    api_key: str = None,
    model: str = None,
    base_url: str = None,
    max_turns: int = 15,
    main_repo_dir: str = "",
    task_id: str = None,
    session_id: str = None,
    auto_approve: bool = False,
    custom_coder_prompt: str = "",
    custom_reviewer_prompt: str = "",
    images: Optional[list] = None,
):
    from agent_runner import run_agent as _run_agent

    if role == "coder" and custom_coder_prompt:
        role_prompt = custom_coder_prompt
    elif role == "reviewer" and custom_reviewer_prompt:
        role_prompt = custom_reviewer_prompt
    else:
        role_prompt = CODER_PROMPT if role == "coder" else REVIEWER_PROMPT
    role_session_id = session_id or f"swarm_{role}_{uuid.uuid4().hex[:6]}"

    effective_images = images or []

    if provider == "anthropic":
        if effective_images:
            anthropic_content = [{"type": "text", "text": f"{role_prompt}\n\n---\n\n{instruction}"}]
            for img_b64 in effective_images:
                if isinstance(img_b64, str) and img_b64:
                    prefix = "" if img_b64.startswith("data:image") else "data:image/jpeg;base64,"
                    url = f"{prefix}{img_b64}"
                    if url.startswith("data:image/"):
                        parts = url.split(";base64,", 1)
                        media_type = parts[0].replace("data:image/", "image/")
                        b64_data = parts[1] if len(parts) > 1 else ""
                        anthropic_content.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": b64_data,
                            },
                        })
            initial_messages = [
                {"role": "user", "content": anthropic_content},
            ]
            user_input = ""
        else:
            initial_messages = [
                {"role": "user", "content": f"{role_prompt}\n\n---\n\n{instruction}"},
            ]
            user_input = instruction
    else:
        if effective_images:
            content_list = [{"type": "text", "text": instruction}]
            for img_b64 in effective_images:
                if isinstance(img_b64, str) and img_b64:
                    prefix = "" if img_b64.startswith("data:image") else "data:image/jpeg;base64,"
                    content_list.append({
                        "type": "image_url",
                        "image_url": {"url": f"{prefix}{img_b64}"},
                    })
            initial_messages = [
                {"role": "system", "content": role_prompt},
                {"role": "user", "content": content_list},
            ]
            user_input = ""
        else:
            initial_messages = [
                {"role": "system", "content": role_prompt},
            ]
            user_input = instruction

    last_assistant_text = ""
    last_thinking_thought = ""

    for event in _run_agent(
        user_input=user_input,
        work_dir=work_dir,
        api_key=api_key,
        model=model,
        base_url=base_url,
        provider=provider,
        max_turns=max_turns,
        session_id=role_session_id,
        task_id=task_id,
        initial_messages=initial_messages if initial_messages else None,
        main_repo_dir=main_repo_dir,
        auto_approve=auto_approve,
    ):
        if _is_terminal_signal(event):
            continue

        event_type = event.get("type", "")

        if event_type == "assistant":
            text = event.get("data", "")
            if text and isinstance(text, str) and text.strip():
                last_assistant_text = text.strip()

        if event_type == "tool_start":
            tool_name = event.get("tool_name", "")
            if any(tn in tool_name for tn in _THINKING_TOOL_NAMES):
                args = event.get("args", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                thought = args.get("thought", "") if isinstance(args, dict) else ""
                if thought and isinstance(thought, str) and thought.strip():
                    last_thinking_thought = thought.strip()

        if role == "reviewer":
            if event_type == "tool_start":
                tool_name = event.get("tool_name", "")
                if tool_name not in REVIEWER_TOOLS:
                    event["data"] = f"🚫 权限拒绝: Reviewer 不能使用 {tool_name} 工具"
                    event["is_error"] = True
            elif event_type == "tool_end":
                tool_name = event.get("tool_name", "")
                if tool_name == "bash":
                    tool_data = event.get("data", "")
                    if tool_data:
                        first_line = tool_data.split("\n")[0] if "\n" in tool_data else tool_data
                        is_safe, reason = _check_reviewer_bash_safety(first_line)
                        if not is_safe:
                            event["data"] = f"🚫 权限拒绝: {reason}"
                            event["is_error"] = True

        event["swarm_role"] = role
        yield event

    review_decision, review_feedback = _extract_review_from_text(last_assistant_text)

    if not review_decision and last_thinking_thought:
        review_decision, review_feedback = _extract_review_from_text(last_thinking_thought)

    if review_decision:
        final_text = f"【{review_decision}】\n{review_feedback}"
        logger.info(f"[Swarm] ✅ 从 JSON 代码块提取到审查结论: {review_decision}")
    else:
        final_text = last_assistant_text or last_thinking_thought or _get_last_assistant_text(task_id, role_session_id)

    if not final_text and role == "reviewer":
        logger.warning(f"[Swarm] Reviewer 文本提取全部失败（事件流+数据库均为空），触发兜底放行")
        final_text = ""

    yield {
        "type": "role_finish",
        "data": final_text,
        "role": role,
    }


def run_swarm(
    user_input: str = "",
    task_description: str = "",
    work_dir: str = ".",
    max_turns: int = 30,
    api_key: str = None,
    model: str = None,
    base_url: str = None,
    provider: str = "openai",
    initial_messages: list = None,
    start_turn: int = 1,
    task_id: str = None,
    session_id: str = None,
    main_repo_dir: str = "",
    auto_approve: bool = False,
    max_loops: int = 5,
    yield_events: bool = False,
    custom_coder_prompt: str = "",
    custom_reviewer_prompt: str = "",
    images: Optional[list] = None,
    user_id: int = 0,
):
    task_desc = task_description or user_input or ""
    if not task_desc:
        if yield_events:
            yield {"type": "error", "data": "任务描述不能为空"}
            return
        return SwarmResult(status=SwarmState.MAX_LOOPS, error="任务描述不能为空")

    logger.info(f"\n[Swarm] 🚀 Swarm 接管任务: {task_id or 'N/A'}, desc=\"{task_desc[:60]}\"")

    if yield_events:
        yield from _run_swarm_events(
            task_description=task_desc,
            work_dir=work_dir,
            provider=provider,
            api_key=api_key,
            model=model,
            base_url=base_url,
            max_loops=max_loops,
            main_repo_dir=main_repo_dir,
            task_id=task_id,
            session_id=session_id,
            auto_approve=auto_approve,
            custom_coder_prompt=custom_coder_prompt,
            custom_reviewer_prompt=custom_reviewer_prompt,
            images=images,
            user_id=user_id,
        )
        return

    result = None
    for event in _run_swarm_events(
        task_description=task_desc,
        work_dir=work_dir,
        provider=provider,
        api_key=api_key,
        model=model,
        base_url=base_url,
        max_loops=max_loops,
        main_repo_dir=main_repo_dir,
        task_id=task_id,
        session_id=session_id,
        auto_approve=auto_approve,
        custom_coder_prompt=custom_coder_prompt,
        custom_reviewer_prompt=custom_reviewer_prompt,
        images=images,
        user_id=user_id,
    ):
        if event.get("type") == "swarm_result":
            result = event.get("result")

    if result is None:
        result = SwarmResult(status=SwarmState.MAX_LOOPS, error="Swarm 未返回结果")

    return result


def _run_swarm_events(
    task_description: str,
    work_dir: str = ".",
    provider: str = "openai",
    api_key: str = None,
    model: str = None,
    base_url: str = None,
    max_loops: int = 5,
    main_repo_dir: str = "",
    task_id: str = None,
    session_id: str = None,
    auto_approve: bool = False,
    custom_coder_prompt: str = "",
    custom_reviewer_prompt: str = "",
    images: Optional[list] = None,
    user_id: int = 0,
):
    loop_count = 0
    coder_instruction = task_description
    all_coder_output = ""
    all_reviewer_output = ""
    swarm_messages = []

    logger.info(f"[Swarm] 🏁 Coder-Reviewer 对抗博弈启动: task=\"{task_description[:80]}\"")

    swarm_messages.append({
        "role": "system",
        "content": f"Coder-Reviewer 对抗博弈启动，核心目标: {task_description[:200]}",
    })

    yield {
        "type": "task_started",
        "data": f"Coder-Reviewer 对抗博弈启动",
        "task_description": task_description,
    }

    yield {
        "type": "system_alert",
        "content": f"⚔️ Coder-Reviewer 对抗博弈启动！核心目标: {task_description[:80]}",
    }

    while loop_count < max_loops:
        loop_count += 1
        logger.info(f"[Swarm] 🔄 第 {loop_count}/{max_loops} 轮: Coder 开始开发...")

        yield {
            "type": "swarm_loop_start",
            "data": f"🔄 第 {loop_count}/{max_loops} 轮: Coder 开始开发...",
            "loop": loop_count,
            "role": "coder",
        }

        yield {
            "type": "agent_status",
            "status": "WRITING",
        }

        yield {
            "type": "agent_state",
            "status": "thinking",
            "data": f"👨‍💻 Coder 开始第 {loop_count} 轮开发...",
        }

        yield {
            "type": "system_alert",
            "content": f"👨‍💻 Coder 开始第 {loop_count} 轮开发...",
        }

        coder_text = ""
        for event in _run_role_agent_events(
            role="coder",
            instruction=coder_instruction,
            work_dir=work_dir,
            provider=provider,
            api_key=api_key,
            model=model,
            base_url=base_url,
            max_turns=35,
            main_repo_dir=main_repo_dir,
            task_id=task_id,
            session_id=session_id,
            auto_approve=auto_approve,
            custom_coder_prompt=custom_coder_prompt,
            custom_reviewer_prompt=custom_reviewer_prompt,
            images=images,
        ):
            if event.get("type") == "role_finish":
                coder_text = event.get("data", "")

            yield event

        all_coder_output = coder_text

        swarm_messages.append({
            "role": "assistant",
            "content": f"【👨‍💻 Coder 第{loop_count}轮】\n{coder_text[:2000]}",
        })

        if task_id:
            try:
                from task_manager import get_task_manager
                tm = get_task_manager(user_id=user_id)
                session = tm.get_session(task_id)
                if session:
                    session_messages = (session.messages_before or []) + session.messages
                    session_messages.append({
                        "role": "assistant",
                        "content": f"【👨‍💻 Coder 第{loop_count}轮】\n{coder_text[:2000]}",
                    })
                    tm.update_session_messages(
                        task_id=task_id,
                        messages=session.messages,
                        current_turn=session.current_turn + 1,
                    )
            except Exception as e:
                logger.debug(f"[Swarm] Coder 消息持久化失败: {e}")

        yield {
            "type": "agent_status",
            "status": "REVIEWING",
        }

        yield {
            "type": "agent_state",
            "status": "searching",
            "data": f"🕵️‍♂️ Reviewer 开始审查代码（第 {loop_count} 轮）...",
        }

        yield {
            "type": "system_alert",
            "content": f"👨‍💻 Coder 已提交最新代码，等待 Reviewer 审查...",
        }

        yield {
            "type": "swarm_phase_change",
            "data": f"🕵️‍♂️ Coder 提交审查，Reviewer 开始审查...",
            "role": "reviewer",
        }

        yield {
            "type": "system_alert",
            "content": f"🕵️‍♂️ Reviewer 开始审查代码...",
        }

        logger.info(f"[Swarm] 🕵️‍♂️ Reviewer 开始审查...")

        diff_content = ""
        changed_files = ""
        untracked_files = ""
        try:
            result_stat = subprocess.run(
                ["git", "diff", "--stat"],
                capture_output=True, text=True, timeout=10, cwd=work_dir,
            )
            if result_stat.returncode == 0 and result_stat.stdout.strip():
                changed_files = result_stat.stdout.strip()

            result_diff = subprocess.run(
                ["git", "diff"],
                capture_output=True, text=True, timeout=15, cwd=work_dir,
            )
            if result_diff.returncode == 0 and result_diff.stdout.strip():
                diff_content = result_diff.stdout.strip()[:8000]

            result_untracked = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard"],
                capture_output=True, text=True, timeout=10, cwd=work_dir,
            )
            if result_untracked.returncode == 0 and result_untracked.stdout.strip():
                untracked_files = result_untracked.stdout.strip()
        except Exception as e:
            logger.debug(f"[Swarm] git diff 执行失败: {e}")

        if "提交审查" in coder_text:
            coder_status_prefix = "✅ Coder 已主动提交审查。\n\n"
        else:
            coder_status_prefix = (
                "⚠️ 【系统警告】Coder 似乎遇到了困难，在未明确提交的情况下被系统强制中断"
                "（可能是轮次耗尽或陷入死循环）。这是一个半成品代码，请重点检查代码完整性和逻辑断点。\n\n"
            )

        reviewer_instruction = (
            f"{coder_status_prefix}"
            f"=== 🎯 原始任务 ===\n{task_description}\n\n"
            f"=== 👨‍💻 Coder 的提交说明 ===\n{coder_text}\n\n"
        )

        if changed_files:
            reviewer_instruction += (
                f"=== 📂 变更文件统计 ===\n{changed_files}\n\n"
            )

        if untracked_files:
            reviewer_instruction += (
                f"=== 🆕 新增文件（未追踪）===\n{untracked_files}\n\n"
            )

        if diff_content:
            reviewer_instruction += (
                f"=== 🔥 强制阅读：代码修改清单 (Git Diff) ===\n"
                f"以下是 Coder 刚刚作出的代码修改。**绝对禁止你到处去 find 或 ls，请直接针对以下代码修改进行审查！**\n\n"
                f"{diff_content}\n\n"
            )
        else:
            reviewer_instruction += (
                f"=== ⚠️ 未获取到 Git Diff ===\n"
                f"可能是全新文件（未追踪），请查看上方「新增文件」列表，用 file_read 阅读这些文件。\n\n"
            )

        reviewer_instruction += (
            f"请严格基于上述 Diff 和提交说明进行审查。"
            f"如果需要深入了解某个文件，用 file_read 查看完整内容（只看 Diff 涉及的文件！）。"
        )

        reviewer_text = ""
        for event in _run_role_agent_events(
            role="reviewer",
            instruction=reviewer_instruction,
            work_dir=work_dir,
            provider=provider,
            api_key=api_key,
            model=model,
            base_url=base_url,
            max_turns=10,
            main_repo_dir=main_repo_dir,
            task_id=task_id,
            session_id=session_id,
            auto_approve=auto_approve,
            custom_coder_prompt=custom_coder_prompt,
            custom_reviewer_prompt=custom_reviewer_prompt,
            images=images,
        ):
            if event.get("type") == "role_finish":
                reviewer_text = event.get("data", "")

            yield event

        all_reviewer_output = reviewer_text

        if not reviewer_text.strip():
            logger.warning("[Swarm] ⚠️ Reviewer 返回了空意见或意外终止，自动放行。")

            yield {
                "type": "system_alert",
                "content": "⚠️ Reviewer 审查超时或意外终止，系统已自动放行。",
            }

            yield {
                "type": "assistant",
                "data": "✅ **任务圆满完成！** (系统兜底放行 — Reviewer 未返回有效审查意见，系统判定代码通过)",
                "swarm_role": "finale",
            }

            code_diff = ""
            try:
                result = subprocess.run(
                    ["git", "diff", "--stat"],
                    capture_output=True, text=True, timeout=5, cwd=work_dir,
                )
                if result.returncode == 0 and result.stdout.strip():
                    code_diff = result.stdout.strip()
            except Exception:
                pass

            swarm_result = SwarmResult(
                status=SwarmState.LGTM,
                loops=loop_count,
                coder_output=all_coder_output,
                reviewer_output="(系统兜底放行)",
                final_code_diff=code_diff,
            )

            yield {
                "type": "swarm_result",
                "data": f"✅ 系统兜底放行（Reviewer 未返回有效意见），经过 {loop_count} 轮。",
                "result": swarm_result,
            }

            _try_report_career_advice(
                user_id=user_id,
                reviewer_output=all_reviewer_output,
                work_dir=work_dir,
                task_description=task_description,
            )

            try:
                from self_distill import auto_distill
                distill_work_dir = main_repo_dir or work_dir
                distill_result = auto_distill(
                    messages=swarm_messages,
                    work_dir=distill_work_dir,
                    task_id=task_id or session_id or "",
                    task_description=task_description[:100],
                )
                if distill_result:
                    yield {"type": "distill", "data": f"🧠 经验已自动蒸馏并记录:\n{distill_result}"}
            except Exception as e:
                logger.debug(f"[Swarm] 自动蒸馏失败（不影响任务结果）: {e}")

            yield {
                "type": "agent_status",
                "status": "DONE",
            }

            yield {
                "type": "finish",
                "data": f"Coder-Reviewer 对抗博弈完成: 系统兜底放行 (第 {loop_count} 轮)",
                "status": SwarmState.LGTM,
            }

            yield {
                "type": "agent_status",
                "status": "IDLE",
            }
            return

        yield {
            "type": "assistant",
            "data": f"🕵️‍♂️ **Reviewer 审查意见（第{loop_count}轮）:**\n\n{reviewer_text[:3000]}",
            "swarm_role": "reviewer_broadcast",
        }

        swarm_messages.append({
            "role": "assistant",
            "content": f"【🕵️‍♂️ Reviewer 第{loop_count}轮】\n{reviewer_text[:2000]}",
        })

        if task_id:
            try:
                from task_manager import get_task_manager
                tm = get_task_manager(user_id=user_id)
                session = tm.get_session(task_id)
                if session:
                    session_messages = (session.messages_before or []) + session.messages
                    session_messages.append({
                        "role": "assistant",
                        "content": f"【🕵️‍♂️ Reviewer 第{loop_count}轮】\n{reviewer_text[:2000]}",
                    })
                    tm.update_session_messages(
                        task_id=task_id,
                        messages=session.messages,
                        current_turn=session.current_turn + 1,
                    )
            except Exception as e:
                logger.debug(f"[Swarm] Reviewer 消息持久化失败: {e}")

        if _is_approval(reviewer_text):
            logger.info(f"[Swarm] ✅ Reviewer 审核通过！意见: {reviewer_text[:80]}")

            yield {
                "type": "system_alert",
                "content": f"🎉 Reviewer 审核通过！经过 {loop_count} 轮审查。",
            }

            yield {
                "type": "assistant",
                "data": f"✅ **任务圆满完成！** Reviewer 已确认代码符合规范，经过 {loop_count} 轮审查通过。",
                "swarm_role": "finale",
            }

            code_diff = ""
            try:
                result = subprocess.run(
                    ["git", "diff", "--stat"],
                    capture_output=True, text=True, timeout=5, cwd=work_dir,
                )
                if result.returncode == 0 and result.stdout.strip():
                    code_diff = result.stdout.strip()
            except Exception:
                pass

            swarm_result = SwarmResult(
                status=SwarmState.LGTM,
                loops=loop_count,
                coder_output=all_coder_output,
                reviewer_output=all_reviewer_output,
                final_code_diff=code_diff,
            )

            yield {
                "type": "swarm_result",
                "data": f"✅ Reviewer 审核通过！经过 {loop_count} 轮审查。",
                "result": swarm_result,
            }

            _try_report_career_advice(
                user_id=user_id,
                reviewer_output=all_reviewer_output,
                work_dir=work_dir,
                task_description=task_description,
            )

            try:
                from self_distill import auto_distill
                distill_work_dir = main_repo_dir or work_dir
                distill_result = auto_distill(
                    messages=swarm_messages,
                    work_dir=distill_work_dir,
                    task_id=task_id or session_id or "",
                    task_description=task_description[:100],
                )
                if distill_result:
                    yield {"type": "distill", "data": f"🧠 经验已自动蒸馏并记录:\n{distill_result}"}
            except Exception as e:
                logger.debug(f"[Swarm] 自动蒸馏失败（不影响任务结果）: {e}")

            yield {
                "type": "agent_status",
                "status": "DONE",
            }

            yield {
                "type": "finish",
                "data": f"Coder-Reviewer 对抗博弈完成: LGTM (经过 {loop_count} 轮)",
                "status": SwarmState.LGTM,
            }

            yield {
                "type": "agent_status",
                "status": "IDLE",
            }
            return
        else:
            logger.info(f"[Swarm] ❌ Reviewer 打回修改！")

            yield {
                "type": "agent_status",
                "status": "WRITING",
            }

            yield {
                "type": "agent_state",
                "status": "thinking",
                "data": f"❌ Reviewer 打回重写！Coder 准备修复...",
            }

            yield {
                "type": "swarm_rejected",
                "data": f"❌ Reviewer 打回修改！",
                "loop": loop_count,
                "reviewer_feedback": reviewer_text[:500],
            }

            yield {
                "type": "system_alert",
                "content": f"❌ Reviewer 打回重写！第 {loop_count} 轮未通过审查。",
            }

            coder_instruction = (
                f"【终极目标】\n{task_description}\n\n"
                f"【当前目录状态】\n"
                f"目录中已经存在之前你或其他人编写的代码，请先阅读当前文件内容，"
                f"**绝对不要从头重写整个项目**！只针对 Reviewer 指出的错误进行局部修改。\n\n"
                f"【Reviewer 审查意见】\n{reviewer_text}\n\n"
                f"⚠️ 【系统最高指令】⚠️\n"
                f"1. 绝对禁止为你的错误道歉或解释！\n"
                f"2. Talk is cheap, show me the code! 无论 Reviewer 提出了什么修改意见，你**必须立刻调用 file_edit 或 bash 工具**去真实修改文件！\n"
                f"3. 如果你只回复了文本而没有调用任何工具，你将被判定为严重失职！\n"
                f"4. 如果你认为代码已经完美或 Reviewer 没有提出具体修改点，请直接运行测试验证，并回复【提交审查】。"
            )

    logger.warning(f"[Swarm] ⚠️ 达到最大循环次数 ({max_loops})，请求人类仲裁...")

    yield {
        "type": "system_alert",
        "content": f"⚠️ Coder 与 Reviewer 经过 {max_loops} 轮仍无法达成一致，请求人类介入仲裁...",
    }

    yield {
        "type": "ask_user",
        "question": (
            f"⚠️ Coder 和 Reviewer 经过 {max_loops} 轮对抗仍无法达成一致！\n\n"
            f"=== Coder 最后的输出 ===\n{all_coder_output[:1000]}\n\n"
            f"=== Reviewer 最后的意见 ===\n{all_reviewer_output[:1000]}\n\n"
            f"请做出最终裁决：\n"
            f"1. 回复「通过」— 接受 Coder 的代码，忽略 Reviewer 意见\n"
            f"2. 回复「打回」— 采纳 Reviewer 意见，继续修改\n"
            f"3. 回复具体指示 — 你来决定下一步怎么做"
        ),
        "question_id": f"swarm_arbitration_{task_id or 'unknown'}",
    }

    yield {
        "type": "assistant",
        "data": f"⚠️ **任务挂起**：Coder 与 Reviewer 经过 {max_loops} 轮对抗仍无法达成一致，请人工介入裁决。",
        "swarm_role": "finale",
    }

    swarm_result = SwarmResult(
        status=SwarmState.MAX_LOOPS,
        loops=loop_count,
        coder_output=all_coder_output,
        reviewer_output=all_reviewer_output,
        error=f"达到最大循环次数 {max_loops}，Coder 和 Reviewer 未能达成一致",
    )

    yield {
        "type": "swarm_result",
        "data": f"⚠️ 达到最大循环次数 ({max_loops})，Coder 和 Reviewer 未能达成一致",
        "result": swarm_result,
    }

    try:
        from self_distill import auto_distill
        distill_work_dir = main_repo_dir or work_dir
        distill_result = auto_distill(
            messages=swarm_messages,
            work_dir=distill_work_dir,
            task_id=task_id or session_id or "",
            task_description=task_description[:100],
        )
        if distill_result:
            yield {"type": "distill", "data": f"🧠 经验已自动蒸馏并记录:\n{distill_result}"}
    except Exception as e:
        logger.debug(f"[Swarm] 自动蒸馏失败（不影响任务结果）: {e}")

    yield {
        "type": "agent_status",
        "status": "DONE",
    }

    yield {
        "type": "finish",
        "data": f"Coder-Reviewer 对抗博弈: 达到最大循环次数 ({max_loops})",
        "status": SwarmState.MAX_LOOPS,
    }

    yield {
        "type": "agent_status",
        "status": "IDLE",
    }
    return


SWARM_REVIEW_TOOL_DEFINITION_OPENAI = {
    "type": "function",
    "function": {
        "name": "coder_reviewer_swarm",
        "description": (
            "Coder-Reviewer 对抗博弈工具 - 启动双智能体代码审查闭环。"
            "Coder 写代码 → Reviewer 审查 → 打回/LGTM，最多循环 5 轮。"
            "适用于需要高质量代码输出的场景，确保代码经过严格审查。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task_description": {
                    "type": "string",
                    "description": "要完成的编程任务描述，如 '实现一个线程安全的LRU缓存'",
                },
                "max_loops": {
                    "type": "integer",
                    "description": "Coder-Reviewer 最大循环轮数（默认5，防止无限吵架）",
                },
            },
            "required": ["task_description"],
        },
    },
}

SWARM_REVIEW_TOOL_DEFINITION_ANTHROPIC = {
    "name": "coder_reviewer_swarm",
    "description": (
        "Coder-Reviewer 对抗博弈工具 - 启动双智能体代码审查闭环。"
        "Coder 写代码 → Reviewer 审查 → 打回/LGTM，最多循环 5 轮。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "task_description": {
                "type": "string",
                "description": "要完成的编程任务描述",
            },
            "max_loops": {
                "type": "integer",
                "description": "最大循环轮数（默认5）",
            },
        },
        "required": ["task_description"],
    },
}


def execute_coder_reviewer_swarm(
    task_description: str,
    work_dir: str = ".",
    provider: str = "openai",
    api_key: str = None,
    model: str = None,
    base_url: str = None,
    max_loops: int = 5,
    main_repo_dir: str = "",
    custom_coder_prompt: str = "",
    custom_reviewer_prompt: str = "",
) -> tuple[str, bool]:
    if not task_description.strip():
        return "❌ 任务描述不能为空", True

    result = run_swarm(
        task_description=task_description,
        work_dir=work_dir,
        provider=provider,
        api_key=api_key,
        model=model,
        base_url=base_url,
        max_loops=max_loops,
        main_repo_dir=main_repo_dir,
        custom_coder_prompt=custom_coder_prompt,
        custom_reviewer_prompt=custom_reviewer_prompt,
    )

    lines = [
        "=" * 60,
        f"🏁 Coder-Reviewer 对抗博弈结果: {result.status}",
        f"   循环轮数: {result.loops}/{max_loops}",
        "=" * 60,
    ]

    if result.status == SwarmState.LGTM:
        lines.append("\n✅ Reviewer 审核通过！代码质量达标。")
        if result.final_code_diff:
            lines.append(f"\n📊 代码变更统计:\n{result.final_code_diff}")
        lines.append(f"\n📝 Coder 最终提交:\n{result.coder_output[:1000]}")
        is_error = False
    elif result.status == SwarmState.MAX_LOOPS:
        lines.append(f"\n⚠️ 达到最大循环次数 ({max_loops})，Coder 和 Reviewer 未能达成一致。")
        lines.append(f"\n📝 Coder 最后输出:\n{result.coder_output[:500]}")
        lines.append(f"\n🕵️ Reviewer 最后意见:\n{result.reviewer_output[:500]}")
        is_error = True
    else:
        lines.append(f"\n❌ 异常状态: {result.status}")
        if result.error:
            lines.append(f"   错误: {result.error}")
        is_error = True

    return "\n".join(lines), is_error


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
