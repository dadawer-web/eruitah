"""
Eruitah 智能编程沙盒 - LSP Tool (Language Server Protocol)

让 Agent 拥有 IDE 级别的代码理解能力，不再依赖 grep 盲搜。

核心流程:
┌─────────────────────────────────────────────────────────────────────┐
│  Agent 调用 find_definition("User")                                 │
│         │                                                            │
│         ▼                                                            │
│  Python 后端:                                                        │
│  1. 构造 LSP JSON-RPC 请求: textDocument/definition                  │
│  2. 发送给后台的语言服务器 (clangd / pylsp)                           │
│  3. 解析返回的位置信息                                                │
│  4. 格式化为易读文本返回给大模型                                      │
│         │                                                            │
│         ▼                                                            │
│  返回: "User 类定义在 src/models/user.h:15"                          │
└─────────────────────────────────────────────────────────────────────┘

支持的工具:
  - find_definition: 查找符号定义
  - find_references: 查找所有引用
  - get_document_symbols: 获取文件大纲

参考源码: claude-code-rev/src/services/lsp/ 和 src/tools/LSPTool/
"""

import os
import json
import asyncio
import logging
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

LSP_SERVERS = {
    "cpp": {"command": "clangd", "args": []},
    "c": {"command": "clangd", "args": []},
    "python": {"command": "pylsp", "args": []},
    "js": {"command": "typescript-language-server", "args": ["--stdio"]},
    "ts": {"command": "typescript-language-server", "args": ["--stdio"]},
}


class LSPClient:
    """LSP 客户端 - 与语言服务器通信"""

    def __init__(self, work_dir: str = "."):
        self.work_dir = work_dir
        self.processes: dict[str, asyncio.subprocess.Process] = {}
        self._request_id = 0
        self._initialized: set[str] = set()

    def _get_language(self, file_path: str) -> Optional[str]:
        ext_map = {
            ".cpp": "cpp", ".c": "c", ".h": "cpp", ".hpp": "cpp",
            ".py": "python",
            ".js": "js", ".ts": "ts", ".jsx": "js", ".tsx": "ts",
            ".java": "java",
            ".go": "go",
            ".rs": "rust",
        }
        ext = os.path.splitext(file_path)[1].lower()
        return ext_map.get(ext)

    async def _ensure_server(self, language: str) -> Optional[asyncio.subprocess.Process]:
        """确保语言服务器已启动"""
        if language in self.processes:
            proc = self.processes[language]
            if proc.returncode is None:
                return proc

        server_config = LSP_SERVERS.get(language)
        if not server_config:
            return None

        try:
            proc = await asyncio.create_subprocess_exec(
                server_config["command"],
                *server_config["args"],
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.work_dir,
            )
            self.processes[language] = proc

            # 初始化
            if language not in self._initialized:
                await self._send_request(language, "initialize", {
                    "processId": os.getpid(),
                    "rootUri": f"file://{os.path.abspath(self.work_dir)}",
                    "capabilities": {
                        "textDocument": {
                            "definition": {"dynamicRegistration": False},
                            "references": {"dynamicRegistration": False},
                            "documentSymbol": {"dynamicRegistration": False},
                            # 显式关闭高级特性，防止前端发送不支持的请求
                            "codeLens": {"dynamicRegistration": False},
                            "documentLink": {"dynamicRegistration": False},
                            "semanticTokens": {
                                "dynamicRegistration": False,
                                "requests": {"full": False, "range": False},
                            },
                            "foldingRange": {"dynamicRegistration": False},
                            "documentHighlight": {"dynamicRegistration": False},
                            "colorProvider": {"dynamicRegistration": False},
                            "formatting": {"dynamicRegistration": False},
                            "rangeFormatting": {"dynamicRegistration": False},
                            "onTypeFormatting": {"dynamicRegistration": False},
                            "rename": {"dynamicRegistration": False},
                            "publishDiagnostics": {
                                "relatedInformation": False,
                                "tagSupport": {"valueSet": []},
                                "versionSupport": False,
                            },
                        },
                    },
                })
                await self._send_notification(language, "initialized", {})
                self._initialized.add(language)

            return proc
        except FileNotFoundError:
            logger.warning(f"语言服务器未安装: {server_config['command']}")
            return None
        except Exception as e:
            logger.error(f"启动语言服务器失败: {e}")
            return None

    async def _send_request(self, language: str, method: str, params: dict) -> Optional[dict]:
        """发送 LSP JSON-RPC 请求"""
        proc = self.processes.get(language)
        if not proc or proc.returncode is not None:
            return None

        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }

        try:
            content = json.dumps(request)
            header = f"Content-Length: {len(content)}\r\n\r\n"
            message = header + content

            proc.stdin.write(message.encode())
            await proc.stdin.drain()

            # 读取响应
            response = await self._read_response(proc)
            if response and 'error' in response:
                error_info = response['error']
                error_code = error_info.get('code', 0) if isinstance(error_info, dict) else 0
                if error_code == -32601:
                    # MethodNotFound: 服务器不支持该方法，静音处理
                    method_name = error_info.get('message', 'unknown') if isinstance(error_info, dict) else ''
                    logger.debug(f"LSP Server skipped unsupported method: {method_name}")
                    return {"result": None}
                else:
                    logger.error(f"LSP 错误: {error_info}")
                return None
            return response.get("result") if response else None
        except Exception as e:
            logger.error(f"LSP 请求失败: {method} -> {e}")
            return None

    async def _send_notification(self, language: str, method: str, params: dict):
        """发送 LSP 通知"""
        proc = self.processes.get(language)
        if not proc or proc.returncode is not None:
            return

        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }

        try:
            content = json.dumps(notification)
            header = f"Content-Length: {len(content)}\r\n\r\n"
            message = header + content
            proc.stdin.write(message.encode())
            await proc.stdin.drain()
        except Exception as e:
            logger.debug(f"LSP 通知发送失败 (fire-and-forget): {method} -> {e}")

    async def _read_response(self, proc: asyncio.subprocess.Process) -> Optional[dict]:
        """读取 LSP 响应"""
        try:
            # 读取 Content-Length 头
            headers = b""
            while True:
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=10)
                headers += line
                if line == b"\r\n":
                    break

            content_length = 0
            for header_line in headers.decode().split("\r\n"):
                if header_line.startswith("Content-Length:"):
                    content_length = int(header_line.split(":")[1].strip())

            if content_length == 0:
                return None

            # 读取内容
            body = await asyncio.wait_for(
                proc.stdout.readexactly(content_length), timeout=10
            )
            return json.loads(body.decode())
        except Exception as e:
            logger.error(f"读取 LSP 响应失败: {e}")
            return None

    async def find_definition(self, file_path: str, line: int, character: int) -> str:
        """查找符号定义"""
        language = self._get_language(file_path)
        if not language:
            return f"不支持的语言: {file_path}"

        proc = await self._ensure_server(language)
        if not proc:
            server_cmd = LSP_SERVERS.get(language, {}).get("command", "unknown")
            return f"语言服务器未启动 (需要安装 {server_cmd})"

        abs_path = os.path.abspath(file_path)
        uri = f"file://{abs_path}"

        result = await self._send_request(language, "textDocument/definition", {
            "textDocument": {"uri": uri},
            "position": {"line": line - 1, "character": character},
        })

        if not result:
            return "未找到定义"

        return self._format_locations(result)

    async def find_references(self, file_path: str, line: int, character: int) -> str:
        """查找所有引用"""
        language = self._get_language(file_path)
        if not language:
            return f"不支持的语言: {file_path}"

        proc = await self._ensure_server(language)
        if not proc:
            server_cmd = LSP_SERVERS.get(language, {}).get("command", "unknown")
            return f"语言服务器未启动 (需要安装 {server_cmd})"

        abs_path = os.path.abspath(file_path)
        uri = f"file://{abs_path}"

        result = await self._send_request(language, "textDocument/references", {
            "textDocument": {"uri": uri},
            "position": {"line": line - 1, "character": character},
            "context": {"includeDeclaration": True},
        })

        if not result:
            return "未找到引用"

        return self._format_locations(result)

    async def get_document_symbols(self, file_path: str) -> str:
        """获取文件大纲"""
        language = self._get_language(file_path)
        if not language:
            return f"不支持的语言: {file_path}"

        proc = await self._ensure_server(language)
        if not proc:
            server_cmd = LSP_SERVERS.get(language, {}).get("command", "unknown")
            return f"语言服务器未启动 (需要安装 {server_cmd})"

        abs_path = os.path.abspath(file_path)
        uri = f"file://{abs_path}"

        result = await self._send_request(language, "textDocument/documentSymbol", {
            "textDocument": {"uri": uri},
        })

        if not result:
            return "未获取到文件大纲"

        return self._format_symbols(result)

    def _format_locations(self, result) -> str:
        """格式化位置信息"""
        locations = []

        if isinstance(result, list):
            locations = result
        elif isinstance(result, dict):
            if "uri" in result:
                locations = [result]
            else:
                for key in result:
                    if isinstance(result[key], list):
                        locations = result[key]
                        break

        if not locations:
            return "未找到结果"

        lines = []
        for loc in locations[:20]:
            uri = loc.get("uri", "")
            path = uri.replace("file://", "")
            range_info = loc.get("range", {})
            start = range_info.get("start", {})
            line_num = start.get("line", 0) + 1
            lines.append(f"  {path}:{line_num}")

        if len(locations) > 20:
            lines.append(f"  ... (共 {len(locations)} 个结果)")

        return "\n".join(lines)

    def _format_symbols(self, symbols: list, indent: int = 0) -> str:
        """格式化符号信息"""
        lines = []
        for symbol in symbols[:30]:
            name = symbol.get("name", "")
            kind = symbol.get("kind", 0)
            kind_names = {
                1: "File", 2: "Module", 3: "Namespace", 4: "Package",
                5: "Class", 6: "Method", 7: "Property", 8: "Field",
                9: "Constructor", 10: "Enum", 11: "Interface", 12: "Function",
                13: "Variable", 14: "Constant", 15: "String", 16: "Number",
            }
            kind_name = kind_names.get(kind, "Unknown")
            prefix = "  " * indent
            lines.append(f"{prefix}{kind_name}: {name}")

            children = symbol.get("children", [])
            if children:
                lines.append(self._format_symbols(children, indent + 1))

        return "\n".join(lines)

    async def stop_all(self):
        """停止所有语言服务器"""
        for lang, proc in self.processes.items():
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    proc.kill()
        self.processes.clear()
        self._initialized.clear()
        logger.info("所有语言服务器已停止")


# LSP 工具定义
LSP_TOOL_DEFINITIONS_OPENAI = [
    {
        "type": "function",
        "function": {
            "name": "find_definition",
            "description": "查找符号的定义位置（需要语言服务器支持）",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "文件路径"},
                    "line": {"type": "integer", "description": "行号（1-based）"},
                    "character": {"type": "integer", "description": "列号（0-based）"},
                },
                "required": ["file_path", "line", "character"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_references",
            "description": "查找符号的所有引用位置（需要语言服务器支持）",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "文件路径"},
                    "line": {"type": "integer", "description": "行号（1-based）"},
                    "character": {"type": "integer", "description": "列号（0-based）"},
                },
                "required": ["file_path", "line", "character"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_document_symbols",
            "description": "获取文件的符号大纲（类、函数、变量等）（需要语言服务器支持）",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "文件路径"},
                },
                "required": ["file_path"],
            },
        },
    },
]

LSP_TOOL_DEFINITIONS_ANTHROPIC = [
    {
        "name": "find_definition",
        "description": "查找符号的定义位置（需要语言服务器支持）",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "文件路径"},
                "line": {"type": "integer", "description": "行号（1-based）"},
                "character": {"type": "integer", "description": "列号（0-based）"},
            },
            "required": ["file_path", "line", "character"],
        },
    },
    {
        "name": "find_references",
        "description": "查找符号的所有引用位置（需要语言服务器支持）",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "文件路径"},
                "line": {"type": "integer", "description": "行号（1-based）"},
                "character": {"type": "integer", "description": "列号（0-based）"},
            },
            "required": ["file_path", "line", "character"],
        },
    },
    {
        "name": "get_document_symbols",
        "description": "获取文件的符号大纲（类、函数、变量等）（需要语言服务器支持）",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "文件路径"},
            },
            "required": ["file_path"],
        },
    },
]
