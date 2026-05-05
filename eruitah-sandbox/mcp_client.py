"""
Eruitah 智能编程沙盒 - MCP Client (Model Context Protocol)

让 Agent 支持 MCP 协议，动态加载第三方 MCP Server 提供的工具。

核心流程:
┌─────────────────────────────────────────────────────────────────────┐
│  mcp.json 配置文件:                                                  │
│  {                                                                   │
│    "mcpServers": {                                                   │
│      "postgres": {                                                   │
│        "command": "npx",                                             │
│        "args": ["-y", "@modelcontextprotocol/server-postgres"],     │
│        "env": {"DATABASE_URL": "..."}                                │
│      }                                                               │
│    }                                                                 │
│  }                                                                   │
│         │                                                            │
│         ▼                                                            │
│  Agent 启动时:                                                       │
│  1. 读取 mcp.json                                                    │
│  2. 为每个 Server 启动子进程 (stdio 通信)                             │
│  3. 发送 initialize + tools/list 请求                                │
│  4. 获取 Server 提供的 Tools                                         │
│  5. 合并到 Agent 的工具列表中                                        │
│         │                                                            │
│         ▼                                                            │
│  大模型调用 MCP Tool 时:                                             │
│  1. Agent 识别这是 MCP 工具                                          │
│  2. 通过 stdio 发送 tools/call 请求给对应 Server                     │
│  3. 获取结果返回给大模型                                             │
│         │                                                            │
│         ▼                                                            │
│  动态加载（新增）:                                                    │
│  Agent 运行时根据需求自主开启新的 MCP Server:                         │
│  用户: "查看我的 GitHub 提醒"                                        │
│  → Agent 调用 mcp_dynamic_load("github")                             │
│  → 后端拉起 GitHub MCP 容器                                         │
│  → Agent 获得 GitHub 工具能力                                       │
│  → 执行查询并返回结果                                                │
└─────────────────────────────────────────────────────────────────────┘

参考源码: claude-code-rev/src/services/mcp/client.ts
"""

import os
import json
import asyncio
import logging
import subprocess
import shutil
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)

MCP_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp.json")

MCP_DYNAMIC_REGISTRY = {
    "github": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": ""},
        "description": "GitHub MCP Server - 管理 Issues, PR, 代码搜索",
    },
    "postgres": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-postgres"],
        "env": {"DATABASE_URL": ""},
        "description": "PostgreSQL MCP Server - 查询和管理 PostgreSQL 数据库",
    },
    "sqlite": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-sqlite"],
        "env": {},
        "description": "SQLite MCP Server - 查询和管理 SQLite 数据库",
    },
    "filesystem": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", os.environ.get("ERUITAH_SANDBOX_DIR", "/tmp/eruitah-sandbox")],
        "env": {},
        "description": "Filesystem MCP Server - 安全的文件系统访问",
    },
    "brave-search": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-brave-search"],
        "env": {"BRAVE_API_KEY": ""},
        "description": "Brave Search MCP Server - 网络搜索",
    },
    "puppeteer": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-puppeteer"],
        "env": {},
        "description": "Puppeteer MCP Server - 浏览器自动化",
    },
    "slack": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-slack"],
        "env": {"SLACK_BOT_TOKEN": "", "SLACK_TEAM_ID": ""},
        "description": "Slack MCP Server - 发送和读取 Slack 消息",
    },
    "google-maps": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-google-maps"],
        "env": {"GOOGLE_MAPS_API_KEY": ""},
        "description": "Google Maps MCP Server - 地理位置和路线",
    },
    "memory": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-memory"],
        "env": {},
        "description": "Memory MCP Server - 知识图谱持久化记忆",
    },
    "sequential-thinking": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"],
        "env": {},
        "description": "Sequential Thinking MCP Server - 结构化推理",
    },
}


class MCPServer:
    """单个 MCP Server 连接"""

    def __init__(self, name: str, command: str, args: list = None, env: dict = None):
        self.name = name
        self.command = command
        self.args = args or []
        self.env = env or {}
        self.process = None
        self.tools = []
        self._request_id = 0
        self._initialized = False

    async def start(self):
        """启动 MCP Server 子进程"""
        try:
            if not shutil.which(self.command.split()[0] if ' ' not in self.command else self.command):
                logger.warning(f"MCP Server '{self.name}' 命令不可用: {self.command}")
                return

            full_env = {**os.environ, **self.env}

            self.process = await asyncio.create_subprocess_exec(
                self.command,
                *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=full_env,
            )

            init_result = await self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "eruitah-agent", "version": "1.0.0"},
            })

            if init_result:
                await self._send_notification("notifications/initialized", {})

                tools_result = await self._send_request("tools/list", {})
                if tools_result and "tools" in tools_result:
                    self.tools = []
                    for tool in tools_result["tools"]:
                        self.tools.append({
                            "name": f"mcp_{self.name}_{tool['name']}",
                            "description": tool.get("description", ""),
                            "parameters": tool.get("inputSchema", {}),
                            "_mcp_original_name": tool["name"],
                            "_mcp_server": self.name,
                        })
                    self._initialized = True
                    logger.info(f"MCP Server '{self.name}' 提供 {len(self.tools)} 个工具")
                else:
                    logger.warning(f"MCP Server '{self.name}' 未返回工具列表")
            else:
                logger.error(f"MCP Server '{self.name}' 初始化失败")

        except Exception as e:
            logger.error(f"启动 MCP Server '{self.name}' 失败: {e}")

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """调用 MCP 工具"""
        result = await self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })

        if result and "content" in result:
            contents = result["content"]
            texts = []
            for item in contents:
                if item.get("type") == "text":
                    texts.append(item.get("text", ""))
            return "\n".join(texts)

        return json.dumps(result, ensure_ascii=False) if result else "无返回结果"

    async def _send_request(self, method: str, params: dict) -> Optional[dict]:
        """发送 JSON-RPC 请求"""
        if not self.process or self.process.returncode is not None:
            return None

        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }

        try:
            message = json.dumps(request) + "\n"
            self.process.stdin.write(message.encode())
            await self.process.stdin.drain()

            response_line = await asyncio.wait_for(
                self.process.stdout.readline(), timeout=30
            )

            if response_line:
                response = json.loads(response_line.decode())
                return response.get("result")
        except asyncio.TimeoutError:
            logger.error(f"MCP 请求超时: {method}")
        except Exception as e:
            logger.error(f"MCP 请求失败: {method} -> {e}")

        return None

    async def _send_notification(self, method: str, params: dict):
        """发送 JSON-RPC 通知（无 id，不期望响应）"""
        if not self.process or self.process.returncode is not None:
            return

        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }

        try:
            message = json.dumps(notification) + "\n"
            self.process.stdin.write(message.encode())
            await self.process.stdin.drain()
        except Exception as e:
            logger.error(f"MCP 通知失败: {method} -> {e}")

    async def stop(self):
        """停止 MCP Server"""
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self.process.kill()
            self._initialized = False
            logger.info(f"MCP Server '{self.name}' 已停止")

    @property
    def is_running(self) -> bool:
        return self._initialized and self.process and self.process.returncode is None


class MCPClient:
    """MCP 客户端管理器 - 支持动态加载"""

    def __init__(self, config_path: str = MCP_CONFIG_PATH):
        self.config_path = config_path
        self.servers: dict[str, MCPServer] = {}
        self.all_tools: list[dict] = []

    def load_config(self) -> bool:
        """加载 mcp.json 配置"""
        if not os.path.exists(self.config_path):
            logger.info(f"MCP 配置文件不存在: {self.config_path}")
            return False

        try:
            with open(self.config_path, 'r') as f:
                content = f.read()

            sandbox_dir = os.environ.get("ERUITAH_SANDBOX_DIR", "/tmp/eruitah-sandbox")
            content = content.replace("${ERUITAH_SANDBOX_DIR}", sandbox_dir)
            config = json.loads(content)

            mcp_servers = config.get("mcpServers", {})
            for name, server_config in mcp_servers.items():
                self.servers[name] = MCPServer(
                    name=name,
                    command=server_config.get("command", ""),
                    args=server_config.get("args", []),
                    env=server_config.get("env", {}),
                )

            logger.info(f"加载了 {len(self.servers)} 个 MCP Server 配置")
            return True
        except Exception as e:
            logger.error(f"加载 MCP 配置失败: {e}")
            return False

    async def start_all(self):
        """启动所有 MCP Server"""
        for name, server in self.servers.items():
            await server.start()
            self.all_tools.extend(server.tools)

        if self.all_tools:
            logger.info(f"MCP 共提供 {len(self.all_tools)} 个工具")

    async def stop_all(self):
        """停止所有 MCP Server"""
        for server in self.servers.values():
            await server.stop()
        self.all_tools.clear()

    async def dynamic_load(self, server_name: str, env_overrides: dict = None) -> str:
        """
        动态加载 MCP Server

        Agent 运行时根据需求自主开启新的 MCP Server 容器。
        例如，当用户问"查看我的 GitHub 提醒"时，
        Agent 自主拉起 GitHub MCP 容器并完成调用。

        Args:
            server_name: 服务名称（来自 MCP_DYNAMIC_REGISTRY）
            env_overrides: 环境变量覆盖

        Returns:
            加载结果描述
        """
        if server_name in self.servers and self.servers[server_name].is_running:
            return f"MCP Server '{server_name}' 已在运行中，提供 {len(self.servers[server_name].tools)} 个工具"

        registry_entry = MCP_DYNAMIC_REGISTRY.get(server_name)
        if not registry_entry:
            available = ", ".join(MCP_DYNAMIC_REGISTRY.keys())
            return f"未知 MCP Server: '{server_name}'。可用的 Server: {available}"

        env = {**registry_entry["env"]}
        if env_overrides:
            env.update(env_overrides)

        missing_env = [k for k, v in env.items() if not v and k.endswith(("TOKEN", "KEY", "URL", "ID"))]
        if missing_env:
            return f"MCP Server '{server_name}' 缺少必要的环境变量: {', '.join(missing_env)}。请通过 env_overrides 参数提供。"

        server = MCPServer(
            name=server_name,
            command=registry_entry["command"],
            args=registry_entry.get("args", []),
            env=env,
        )

        await server.start()

        if server.is_running:
            self.servers[server_name] = server
            self.all_tools.extend(server.tools)
            tool_names = [t["name"] for t in server.tools]
            return f"✅ MCP Server '{server_name}' 动态加载成功！提供 {len(server.tools)} 个工具: {', '.join(tool_names[:5])}"
        else:
            return f"❌ MCP Server '{server_name}' 启动失败"

    def list_available_servers(self) -> str:
        """列出所有可用的 MCP Server（包括已加载和可动态加载的）"""
        lines = ["📋 MCP Server 状态:\n"]

        lines.append("已加载的 Server:")
        if self.servers:
            for name, server in self.servers.items():
                status = "🟢 运行中" if server.is_running else "🔴 已停止"
                tool_count = len(server.tools)
                lines.append(f"  {status} {name} ({tool_count} 个工具)")
        else:
            lines.append("  （无）")

        lines.append("\n可动态加载的 Server:")
        for name, entry in MCP_DYNAMIC_REGISTRY.items():
            loaded = "✅" if name in self.servers else "⬜"
            lines.append(f"  {loaded} {name}: {entry['description']}")

        return "\n".join(lines)

    def get_openai_tools(self) -> list[dict]:
        """获取 OpenAI 格式的工具定义"""
        tools = []
        for tool in self.all_tools:
            tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool.get("parameters", {}),
                },
            })
        return tools

    def get_anthropic_tools(self) -> list[dict]:
        """获取 Anthropic 格式的工具定义"""
        tools = []
        for tool in self.all_tools:
            tools.append({
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": tool.get("parameters", {}),
            })
        return tools

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """调用 MCP 工具"""
        for server in self.servers.values():
            for tool in server.tools:
                if tool["name"] == tool_name:
                    original_name = tool["_mcp_original_name"]
                    return await server.call_tool(original_name, arguments)

        return f"错误: 未找到 MCP 工具 '{tool_name}'"

    def is_mcp_tool(self, tool_name: str) -> bool:
        """判断是否是 MCP 工具"""
        return tool_name.startswith("mcp_")


# ============================================================================
# MCP 工具定义 - 供 agent_runner 注册
# ============================================================================

MCP_TOOL_DEFINITION_OPENAI = {
    "type": "function",
    "function": {
        "name": "mcp_manager",
        "description": (
            "MCP 服务管理工具 - 动态加载和管理第三方 MCP Server。"
            "action='dynamic_load': 动态加载一个 MCP Server（如 github, postgres, sqlite）"
            "action='list_available': 列出所有可用的 MCP Server"
            "action='list_loaded': 列出已加载的 MCP Server 及其工具"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["dynamic_load", "list_available", "list_loaded"],
                    "description": "操作类型",
                },
                "server_name": {
                    "type": "string",
                    "description": "MCP Server 名称（dynamic_load 时必填），如 github, postgres, sqlite",
                },
                "env_overrides": {
                    "type": "object",
                    "description": "环境变量覆盖（dynamic_load 时可选），如 {\"GITHUB_PERSONAL_ACCESS_TOKEN\": \"ghp_xxx\"}",
                },
            },
            "required": ["action"],
        },
    },
}

MCP_TOOL_DEFINITION_ANTHROPIC = {
    "name": "mcp_manager",
    "description": (
        "MCP 服务管理工具 - 动态加载和管理第三方 MCP Server。"
        "可以根据需求自主开启新的 MCP Server 容器，扩展 Agent 的工具能力。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["dynamic_load", "list_available", "list_loaded"],
                "description": "操作类型",
            },
            "server_name": {
                "type": "string",
                "description": "MCP Server 名称（dynamic_load 时必填）",
            },
            "env_overrides": {
                "type": "object",
                "description": "环境变量覆盖（dynamic_load 时可选）",
            },
        },
        "required": ["action"],
    },
}


_local_mcp_client: Optional[MCPClient] = None


def get_mcp_client() -> MCPClient:
    global _local_mcp_client
    if _local_mcp_client is None:
        _local_mcp_client = MCPClient()
    return _local_mcp_client


def execute_mcp_manager(action: str, server_name: str = "", env_overrides: dict = None) -> tuple[str, bool]:
    """执行 MCP 管理工具（同步包装）"""
    client = get_mcp_client()

    if action == "dynamic_load":
        if not server_name:
            return "必须提供 server_name 参数", True

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        client.dynamic_load(server_name, env_overrides)
                    )
                    result = future.result(timeout=60)
            else:
                result = loop.run_until_complete(client.dynamic_load(server_name, env_overrides))
            return result, False
        except Exception as e:
            return f"动态加载 MCP Server 失败: {e}", True

    elif action == "list_available":
        return client.list_available_servers(), False

    elif action == "list_loaded":
        lines = ["已加载的 MCP Server:"]
        for name, server in client.servers.items():
            status = "🟢 运行中" if server.is_running else "🔴 已停止"
            tool_names = [t["name"] for t in server.tools]
            lines.append(f"  {status} {name}: {', '.join(tool_names[:5])}")
        if not client.servers:
            lines.append("  （无已加载的 Server）")
        return "\n".join(lines), False

    else:
        return f"未知操作: {action}", True
