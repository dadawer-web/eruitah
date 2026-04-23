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
└─────────────────────────────────────────────────────────────────────┘

参考源码: claude-code-rev/src/services/mcp/client.ts
"""

import os
import json
import asyncio
import logging
import subprocess
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)

MCP_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp.json")


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

    async def start(self):
        """启动 MCP Server 子进程"""
        try:
            full_env = {**os.environ, **self.env}

            self.process = await asyncio.create_subprocess_exec(
                self.command,
                *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=full_env,
            )

            # 发送 initialize 请求
            init_result = await self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "eruitah-agent", "version": "1.0.0"},
            })

            if init_result:
                # 发送 initialized 通知
                await self._send_notification("notifications/initialized", {})
                
                # 获取工具列表
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
            logger.info(f"MCP Server '{self.name}' 已停止")


class MCPClient:
    """MCP 客户端管理器"""

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
                config = json.load(f)

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
