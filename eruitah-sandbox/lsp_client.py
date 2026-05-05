from typing import Dict, Any, Optional, List, Tuple
import json
import socket
import subprocess
import time
import os
import threading
import logging

logger = logging.getLogger(__name__)


class LSPConnection:
    """LSP 服务器连接"""

    def __init__(self, server_process, sock, language: str = ""):
        self.server_process = server_process
        self.sock = sock
        self.buffer = b""
        self.closed = False
        self.language = language
        self._request_id = 0
        self._initialized = False
        self._lock = threading.Lock()

    def initialize(self, root_uri: str = "") -> bool:
        """执行 LSP 初始化握手"""
        root_path = root_uri or os.getcwd()
        uri = f"file://{root_path}"

        result = self.send_request("initialize", {
            "processId": os.getpid(),
            "rootUri": uri,
            "rootPath": root_path,
            "capabilities": {
                "textDocument": {
                    "definition": {"dynamicRegistration": False},
                    "references": {"dynamicRegistration": False},
                    "documentSymbol": {"dynamicRegistration": False},
                    "hover": {"dynamicRegistration": False},
                    "completion": {
                        "dynamicRegistration": False,
                        "completionItem": {"snippetSupport": False},
                    },
                },
                "workspace": {
                    "symbol": {"dynamicRegistration": False},
                },
            },
        })

        if result is None:
            logger.error(f"LSP 初始化失败: {self.language}")
            return False

        self.send_notification("initialized", {})

        self._initialized = True
        logger.info(f"LSP 初始化成功: {self.language}, root={uri}")
        return True

    def did_open(self, file_path: str, content: str, version: int = 1):
        """通知 LSP 服务器文件打开"""
        language_id = self._get_language_id(file_path)
        uri = f"file://{os.path.abspath(file_path)}"

        self.send_notification("textDocument/didOpen", {
            "textDocument": {
                "uri": uri,
                "languageId": language_id,
                "version": version,
                "text": content,
            }
        })

    def did_change(self, file_path: str, content: str, version: int = 2):
        """通知 LSP 服务器文件变更"""
        uri = f"file://{os.path.abspath(file_path)}"

        self.send_notification("textDocument/didChange", {
            "textDocument": {"uri": uri, "version": version},
            "contentChanges": [{"text": content}],
        })

    def _get_language_id(self, file_path: str) -> str:
        ext = os.path.splitext(file_path)[1].lower()
        lang_map = {
            '.py': 'python', '.cpp': 'cpp', '.cc': 'cpp', '.cxx': 'cpp',
            '.h': 'c', '.hpp': 'cpp', '.c': 'c', '.java': 'java',
            '.js': 'javascript', '.ts': 'typescript', '.tsx': 'typescriptreact',
            '.rs': 'rust', '.go': 'go', '.rb': 'ruby',
        }
        return lang_map.get(ext, 'plaintext')

    def send_request(self, method: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """发送 LSP 请求"""
        with self._lock:
            self._request_id += 1
            request_id = self._request_id

        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params
        }

        data = json.dumps(request).encode('utf-8')
        header = f"Content-Length: {len(data)}\r\n\r\n"
        message = header.encode('utf-8') + data

        try:
            self.sock.sendall(message)
        except Exception as e:
            logger.error(f"LSP 发送失败: {e}")
            return None

        return self._receive_response(request_id)

    def send_notification(self, method: str, params: Dict[str, Any]):
        """发送 LSP 通知（无 id，不期望响应）"""
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }

        data = json.dumps(notification).encode('utf-8')
        header = f"Content-Length: {len(data)}\r\n\r\n"
        message = header.encode('utf-8') + data

        try:
            self.sock.sendall(message)
        except Exception as e:
            logger.error(f"LSP 通知失败: {e}")

    def _receive_response(self, request_id: int, timeout: float = 10.0) -> Optional[Dict[str, Any]]:
        """接收 LSP 响应"""
        deadline = time.time() + timeout

        while time.time() < deadline and not self.closed:
            try:
                self.sock.settimeout(max(0.1, deadline - time.time()))
                data = self.sock.recv(65536)
                if not data:
                    break

                self.buffer += data
                while True:
                    header_end = self.buffer.find(b'\r\n\r\n')
                    if header_end == -1:
                        break

                    header = self.buffer[:header_end].decode('utf-8')
                    content_length = 0
                    for line in header.split('\r\n'):
                        if line.startswith('Content-Length:'):
                            content_length = int(line.split(':')[1].strip())
                            break

                    if content_length == 0:
                        break

                    total_length = header_end + 4 + content_length
                    if len(self.buffer) < total_length:
                        break

                    body = self.buffer[header_end + 4:total_length]
                    self.buffer = self.buffer[total_length:]

                    try:
                        response = json.loads(body.decode('utf-8'))
                        if 'id' in response and response['id'] == request_id:
                            if 'error' in response:
                                logger.error(f"LSP 错误: {response['error']}")
                                return None
                            return response.get('result', {})
                        elif 'method' in response:
                            pass
                    except json.JSONDecodeError:
                        pass

            except socket.timeout:
                continue
            except Exception as e:
                logger.error(f"LSP 接收异常: {e}")
                break

        return None

    def close(self):
        """关闭连接"""
        if not self.closed:
            self.closed = True
            try:
                self.sock.close()
            except Exception:
                pass
            try:
                if self.server_process:
                    self.server_process.terminate()
                    self.server_process.wait(timeout=2)
            except Exception:
                pass


class LSPClient:
    """LSP 客户端 - 支持初始化握手和文件追踪"""

    def __init__(self):
        self.connections: Dict[str, LSPConnection] = {}
        self.lock = threading.Lock()
        self._open_files: Dict[str, str] = {}

    def get_connection(self, language: str, root_uri: str = "") -> Optional[LSPConnection]:
        """获取语言服务器连接（带初始化握手）"""
        with self.lock:
            if language in self.connections:
                conn = self.connections[language]
                if not conn.closed and conn._initialized:
                    return conn
                else:
                    try:
                        conn.close()
                    except Exception:
                        pass
                    del self.connections[language]

            conn = self._start_server(language)
            if conn:
                if conn.initialize(root_uri):
                    self.connections[language] = conn
                    return conn
                else:
                    conn.close()
            return None

    def _start_server(self, language: str) -> Optional[LSPConnection]:
        """启动语言服务器"""
        commands = {
            'cpp': ['clangd'],
            'python': ['pyright-langserver', '--stdio'],
            'javascript': ['typescript-language-server', '--stdio'],
            'typescript': ['typescript-language-server', '--stdio'],
            'java': ['jdtls'],
            'rust': ['rust-analyzer'],
            'go': ['gopls'],
        }

        cmd = commands.get(language)
        if not cmd:
            return None

        try:
            sock1, sock2 = socket.socketpair()

            server_process = subprocess.Popen(
                cmd,
                stdin=sock2,
                stdout=sock2,
                stderr=subprocess.PIPE,
                text=False,
            )
            sock2.close()

            time.sleep(0.3)

            if server_process.poll() is not None:
                sock1.close()
                logger.error(f"LSP 服务器启动失败: {language}")
                return None

            return LSPConnection(server_process, sock1, language)
        except FileNotFoundError:
            logger.warning(f"LSP 服务器未安装: {language} ({cmd[0]})")
            return None
        except Exception as e:
            logger.error(f"启动 LSP 服务器失败: {e}")
            return None

    def _get_language(self, file_path: str) -> str:
        ext = os.path.splitext(file_path)[1].lower()
        lang_map = {
            '.cpp': 'cpp', '.cc': 'cpp', '.cxx': 'cpp', '.c++': 'cpp',
            '.h': 'cpp', '.hpp': 'cpp', '.hxx': 'cpp', '.h++': 'cpp',
            '.c': 'cpp',
            '.py': 'python',
            '.js': 'javascript', '.jsx': 'javascript',
            '.ts': 'typescript', '.tsx': 'typescript',
            '.java': 'java',
            '.rs': 'rust',
            '.go': 'go',
        }
        return lang_map.get(ext, '')

    def _ensure_file_open(self, file_path: str, conn: LSPConnection):
        """确保文件已在 LSP 服务器中打开"""
        abs_path = os.path.abspath(file_path)
        cache_key = f"{conn.language}:{abs_path}"

        if cache_key not in self._open_files:
            try:
                with open(abs_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                conn.did_open(abs_path, content)
                self._open_files[cache_key] = content
            except Exception as e:
                logger.warning(f"无法打开文件给 LSP: {e}")

    def find_definition(self, file_path: str, line: int, character: int, root_uri: str = "") -> str:
        """查找定义"""
        language = self._get_language(file_path)
        if not language:
            return "不支持的文件类型"

        conn = self.get_connection(language, root_uri)
        if not conn:
            return f"无法启动 {language} 语言服务器（可能未安装）"

        self._ensure_file_open(file_path, conn)

        try:
            uri = f"file://{os.path.abspath(file_path)}"
            result = conn.send_request(
                "textDocument/definition",
                {
                    "textDocument": {"uri": uri},
                    "position": {"line": line - 1, "character": character}
                }
            )
            return self._format_locations(result if result else [])
        except Exception as e:
            return f"查找定义失败: {e}"

    def find_references(self, file_path: str, line: int, character: int, root_uri: str = "") -> str:
        """查找引用"""
        language = self._get_language(file_path)
        if not language:
            return "不支持的文件类型"

        conn = self.get_connection(language, root_uri)
        if not conn:
            return f"无法启动 {language} 语言服务器（可能未安装）"

        self._ensure_file_open(file_path, conn)

        try:
            uri = f"file://{os.path.abspath(file_path)}"
            result = conn.send_request(
                "textDocument/references",
                {
                    "textDocument": {"uri": uri},
                    "position": {"line": line - 1, "character": character},
                    "context": {"includeDeclaration": True}
                }
            )
            return self._format_locations(result if result else [])
        except Exception as e:
            return f"查找引用失败: {e}"

    def get_document_symbols(self, file_path: str, root_uri: str = "") -> str:
        """获取文档符号"""
        language = self._get_language(file_path)
        if not language:
            return "不支持的文件类型"

        conn = self.get_connection(language, root_uri)
        if not conn:
            return f"无法启动 {language} 语言服务器（可能未安装）"

        self._ensure_file_open(file_path, conn)

        try:
            uri = f"file://{os.path.abspath(file_path)}"
            result = conn.send_request(
                "textDocument/documentSymbol",
                {"textDocument": {"uri": uri}}
            )
            return self._format_symbols(result if result else [])
        except Exception as e:
            return f"获取文档符号失败: {e}"

    def get_hover(self, file_path: str, line: int, character: int, root_uri: str = "") -> str:
        """获取悬停信息（类型、文档）"""
        language = self._get_language(file_path)
        if not language:
            return "不支持的文件类型"

        conn = self.get_connection(language, root_uri)
        if not conn:
            return f"无法启动 {language} 语言服务器"

        self._ensure_file_open(file_path, conn)

        try:
            uri = f"file://{os.path.abspath(file_path)}"
            result = conn.send_request(
                "textDocument/hover",
                {
                    "textDocument": {"uri": uri},
                    "position": {"line": line - 1, "character": character}
                }
            )
            if result and "contents" in result:
                contents = result["contents"]
                if isinstance(contents, dict):
                    return contents.get("value", str(contents))
                elif isinstance(contents, list):
                    parts = []
                    for item in contents:
                        if isinstance(item, dict):
                            parts.append(item.get("value", ""))
                        elif isinstance(item, str):
                            parts.append(item)
                    return "\n".join(parts)
                return str(contents)
            return "无悬停信息"
        except Exception as e:
            return f"获取悬停信息失败: {e}"

    def search_workspace_symbols(self, query: str, root_uri: str = "") -> str:
        """搜索工作区符号"""
        for lang in ['cpp', 'python', 'typescript', 'javascript']:
            conn = self.get_connection(lang, root_uri)
            if conn:
                try:
                    result = conn.send_request(
                        "workspace/symbol",
                        {"query": query}
                    )
                    if result:
                        formatted = self._format_symbols(result)
                        if "未找到" not in formatted:
                            return formatted
                except Exception:
                    pass
        return "未找到匹配的符号"

    def _format_locations(self, locations) -> str:
        """格式化位置信息"""
        if not locations:
            return "未找到定义/引用"

        if isinstance(locations, dict):
            if "uri" in locations:
                locations = [locations]
            elif "ranges" in locations:
                results = []
                for range_item in locations.get("ranges", []):
                    start = range_item.get("start", {})
                    results.append(f"{locations.get('uri', '').replace('file://', '')}:{start.get('line', 0) + 1}")
                return "\n".join(results) if results else "未找到定义/引用"
            else:
                return "未找到定义/引用"

        lines = []
        for loc in locations:
            if isinstance(loc, dict):
                uri = loc.get('uri', '')
                range_info = loc.get('range', {})
                start = range_info.get('start', {})
                file_path = uri.replace('file://', '')
                line = start.get('line', 0) + 1
                character = start.get('character', 0)
                lines.append(f"{file_path}:{line}:{character}")

        return "\n".join(lines) if lines else "未找到定义/引用"

    def _format_symbols(self, symbols) -> str:
        """格式化符号信息"""
        if not symbols:
            return "未找到符号"

        lines = []
        for symbol in symbols[:30]:
            if isinstance(symbol, dict):
                name = symbol.get('name', 'unknown')
                kind = self._get_symbol_kind(symbol.get('kind', 0))

                if 'location' in symbol:
                    location = symbol['location']
                    uri = location.get('uri', '')
                    range_info = location.get('range', {})
                    start = range_info.get('start', {})
                    file_path = uri.replace('file://', '')
                    line = start.get('line', 0) + 1
                    lines.append(f"{kind}: {name} at {file_path}:{line}")
                elif 'range' in symbol:
                    range_info = symbol.get('range', {})
                    start = range_info.get('start', {})
                    line = start.get('line', 0) + 1
                    children_count = len(symbol.get('children', []))
                    child_info = f" (+{children_count} children)" if children_count else ""
                    lines.append(f"{kind}: {name} at line {line}{child_info}")
                else:
                    lines.append(f"{kind}: {name}")

        return "\n".join(lines) if lines else "未找到符号"

    def _get_symbol_kind(self, kind: int) -> str:
        kinds = {
            1: "File", 2: "Module", 3: "Namespace", 4: "Package",
            5: "Class", 6: "Method", 7: "Property", 8: "Field",
            9: "Constructor", 10: "Enum", 11: "Interface", 12: "Function",
            13: "Variable", 14: "Constant", 15: "String", 16: "Number",
            17: "Boolean", 18: "Array", 19: "Object", 20: "Key",
            21: "Null", 22: "EnumMember", 23: "Struct", 24: "Event",
            25: "Operator", 26: "TypeParameter"
        }
        return kinds.get(kind, "Unknown")

    def close_all(self):
        """关闭所有连接"""
        with self.lock:
            for conn in self.connections.values():
                conn.close()
            self.connections.clear()
            self._open_files.clear()


_lsp_client = None

def get_lsp_client() -> LSPClient:
    global _lsp_client
    if _lsp_client is None:
        _lsp_client = LSPClient()
    return _lsp_client


LSP_TOOL_DEFINITION_OPENAI = {
    "type": "function",
    "function": {
        "name": "lsp_tool",
        "description": (
            "LSP 语言服务器工具 - 精准的语义级代码分析。"
            "比 grep 更强大：能理解代码结构、查找定义和引用、获取类型信息。"
            "action='find_definition': 跳转到定义（如：这个函数在哪里定义的？）"
            "action='find_references': 查找所有引用（如：这个变量在哪些地方被使用？）"
            "action='get_document_symbols': 获取文件大纲（如：这个文件有哪些类和函数？）"
            "action='get_hover': 获取类型和文档信息"
            "action='search_workspace_symbols': 在整个项目中搜索符号"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "操作类型",
                    "enum": ["find_definition", "find_references", "get_document_symbols", "get_hover", "search_workspace_symbols"]
                },
                "file_path": {
                    "type": "string",
                    "description": "文件路径（find_definition, find_references, get_document_symbols, get_hover 需要）"
                },
                "line": {
                    "type": "integer",
                    "description": "行号（find_definition, find_references, get_hover 需要）"
                },
                "character": {
                    "type": "integer",
                    "description": "字符位置（find_definition, find_references, get_hover 需要）"
                },
                "query": {
                    "type": "string",
                    "description": "搜索查询（search_workspace_symbols 需要）"
                },
                "root_uri": {
                    "type": "string",
                    "description": "项目根目录（可选，默认为当前工作目录）"
                }
            },
            "required": ["action"]
        }
    }
}

LSP_TOOL_DEFINITION_ANTHROPIC = {
    "name": "lsp_tool",
    "description": (
        "LSP 语言服务器工具 - 精准的语义级代码分析。"
        "比 grep 更强大：能理解代码结构、查找定义和引用、获取类型信息。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "操作类型",
                "enum": ["find_definition", "find_references", "get_document_symbols", "get_hover", "search_workspace_symbols"]
            },
            "file_path": {
                "type": "string",
                "description": "文件路径"
            },
            "line": {
                "type": "integer",
                "description": "行号"
            },
            "character": {
                "type": "integer",
                "description": "字符位置"
            },
            "query": {
                "type": "string",
                "description": "搜索查询"
            },
            "root_uri": {
                "type": "string",
                "description": "项目根目录"
            }
        },
        "required": ["action"]
    }
}


def execute_lsp_tool(action: str, **kwargs) -> Tuple[str, bool]:
    """执行 LSP 工具"""
    client = get_lsp_client()

    try:
        root_uri = kwargs.get("root_uri", "")

        if action == "find_definition":
            file_path = kwargs.get("file_path")
            line = kwargs.get("line", 1)
            character = kwargs.get("character", 0)
            if not file_path:
                return "缺少 file_path 参数", True
            result = client.find_definition(file_path, line, character, root_uri)

        elif action == "find_references":
            file_path = kwargs.get("file_path")
            line = kwargs.get("line", 1)
            character = kwargs.get("character", 0)
            if not file_path:
                return "缺少 file_path 参数", True
            result = client.find_references(file_path, line, character, root_uri)

        elif action == "get_document_symbols":
            file_path = kwargs.get("file_path")
            if not file_path:
                return "缺少 file_path 参数", True
            result = client.get_document_symbols(file_path, root_uri)

        elif action == "get_hover":
            file_path = kwargs.get("file_path")
            line = kwargs.get("line", 1)
            character = kwargs.get("character", 0)
            if not file_path:
                return "缺少 file_path 参数", True
            result = client.get_hover(file_path, line, character, root_uri)

        elif action == "search_workspace_symbols":
            query = kwargs.get("query", "")
            result = client.search_workspace_symbols(query, root_uri)

        else:
            return f"未知操作: {action}", True

        return result, False

    except Exception as e:
        return f"LSP 工具执行失败: {str(e)}", True


def cleanup_lsp():
    global _lsp_client
    if _lsp_client:
        _lsp_client.close_all()
        _lsp_client = None


import atexit
atexit.register(cleanup_lsp)
