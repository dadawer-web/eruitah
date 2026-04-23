from typing import Dict, Any, Optional, List, Tuple
import json
import socket
import subprocess
import time
import os
import threading

class LSPConnection:
    """LSP 服务器连接"""
    
    def __init__(self, server_process, sock):
        self.server_process = server_process
        self.sock = sock
        self.buffer = b""
        self.closed = False
    
    def send_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """发送 LSP 请求"""
        request_id = 1
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params
        }
        
        data = json.dumps(request).encode('utf-8')
        header = f"Content-Length: {len(data)}\r\n\r\n"
        message = header.encode('utf-8') + data
        
        self.sock.sendall(message)
        return self._receive_response(request_id)
    
    def _receive_response(self, request_id: int) -> Dict[str, Any]:
        """接收 LSP 响应"""
        while not self.closed:
            data = self.sock.recv(4096)
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
                
                response = json.loads(body.decode('utf-8'))
                if 'id' in response and response['id'] == request_id:
                    return response
        
        return {"error": "Connection closed"}
    
    def close(self):
        """关闭连接"""
        if not self.closed:
            self.closed = True
            try:
                self.sock.close()
            except:
                pass
            try:
                if self.server_process:
                    self.server_process.terminate()
                    self.server_process.wait(timeout=1)
            except:
                pass

class LSPClient:
    """LSP 客户端"""
    
    def __init__(self):
        self.connections: Dict[str, LSPConnection] = {}
        self.lock = threading.Lock()
    
    def get_connection(self, language: str) -> Optional[LSPConnection]:
        """获取语言服务器连接"""
        with self.lock:
            if language in self.connections:
                conn = self.connections[language]
                if not conn.closed:
                    return conn
                del self.connections[language]
            
            conn = self._start_server(language)
            if conn:
                self.connections[language] = conn
                return conn
            return None
    
    def _start_server(self, language: str) -> Optional[LSPConnection]:
        """启动语言服务器"""
        if language == 'cpp':
            cmd = ['clangd']
        elif language == 'python':
            cmd = ['pyright-langserver', '--stdio']
        elif language == 'javascript' or language == 'typescript':
            cmd = ['typescript-language-server', '--stdio']
        else:
            return None
        
        try:
            # 创建 socket 对
            sock1, sock2 = socket.socketpair()
            
            # 启动服务器进程
            server_process = subprocess.Popen(
                cmd,
                stdin=sock2,
                stdout=sock2,
                stderr=subprocess.PIPE,
                text=False
            )
            sock2.close()
            
            # 等待服务器启动
            time.sleep(0.5)
            
            # 检查服务器是否启动成功
            if server_process.poll() is not None:
                sock1.close()
                return None
            
            return LSPConnection(server_process, sock1)
        except Exception as e:
            print(f"启动语言服务器失败: {e}")
            return None
    
    def _get_language(self, file_path: str) -> str:
        """根据文件路径获取语言"""
        ext = os.path.splitext(file_path)[1].lower()
        if ext in ['.cpp', '.cc', '.cxx', '.c++', '.h', '.hpp', '.hxx', '.h++']:
            return 'cpp'
        elif ext in ['.py']:
            return 'python'
        elif ext in ['.js', '.jsx']:
            return 'javascript'
        elif ext in ['.ts', '.tsx']:
            return 'typescript'
        return ''
    
    def find_definition(self, file_path: str, line: int, character: int) -> str:
        """查找定义"""
        language = self._get_language(file_path)
        if not language:
            return "不支持的文件类型"
        
        conn = self.get_connection(language)
        if not conn:
            return f"无法启动 {language} 语言服务器"
        
        try:
            uri = f"file://{os.path.abspath(file_path)}"
            result = conn.send_request(
                "textDocument/definition",
                {
                    "textDocument": {"uri": uri},
                    "position": {"line": line - 1, "character": character}
                }
            )
            return self._format_locations(result.get('result', []))
        except Exception as e:
            return f"查找定义失败: {e}"
    
    def find_references(self, file_path: str, line: int, character: int) -> str:
        """查找引用"""
        language = self._get_language(file_path)
        if not language:
            return "不支持的文件类型"
        
        conn = self.get_connection(language)
        if not conn:
            return f"无法启动 {language} 语言服务器"
        
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
            return self._format_locations(result.get('result', []))
        except Exception as e:
            return f"查找引用失败: {e}"
    
    def get_document_symbols(self, file_path: str) -> str:
        """获取文档符号"""
        language = self._get_language(file_path)
        if not language:
            return "不支持的文件类型"
        
        conn = self.get_connection(language)
        if not conn:
            return f"无法启动 {language} 语言服务器"
        
        try:
            uri = f"file://{os.path.abspath(file_path)}"
            result = conn.send_request(
                "textDocument/documentSymbol",
                {"textDocument": {"uri": uri}}
            )
            return self._format_symbols(result.get('result', []))
        except Exception as e:
            return f"获取文档符号失败: {e}"
    
    def search_workspace_symbols(self, query: str) -> str:
        """搜索工作区符号"""
        # 尝试使用不同的语言服务器
        for lang in ['cpp', 'python', 'javascript', 'typescript']:
            conn = self.get_connection(lang)
            if conn:
                try:
                    result = conn.send_request(
                        "workspace/symbol",
                        {"query": query}
                    )
                    symbols = result.get('result', [])
                    if symbols:
                        return self._format_symbols(symbols)
                except:
                    pass
        return "未找到匹配的符号"
    
    def _format_locations(self, locations: List[Dict[str, Any]]) -> str:
        """格式化位置信息"""
        if not locations:
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
        
        return "\n".join(lines)
    
    def _format_symbols(self, symbols: List[Dict[str, Any]]) -> str:
        """格式化符号信息"""
        if not symbols:
            return "未找到符号"
        
        lines = []
        for symbol in symbols:
            name = symbol.get('name', 'unknown')
            kind = self._get_symbol_kind(symbol.get('kind', 0))
            location = symbol.get('location', {})
            if location:
                uri = location.get('uri', '')
                range_info = location.get('range', {})
                start = range_info.get('start', {})
                file_path = uri.replace('file://', '')
                line = start.get('line', 0) + 1
                lines.append(f"{kind}: {name} at {file_path}:{line}")
            else:
                lines.append(f"{kind}: {name}")
        
        return "\n".join(lines)
    
    def _get_symbol_kind(self, kind: int) -> str:
        """获取符号类型名称"""
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

# 全局 LSP 客户端实例
_lsp_client = None
def get_lsp_client() -> LSPClient:
    """获取 LSP 客户端实例"""
    global _lsp_client
    if _lsp_client is None:
        _lsp_client = LSPClient()
    return _lsp_client

# 工具定义
LSP_TOOL_DEFINITION_OPENAI = {
    "type": "function",
    "function": {
        "name": "lsp_tool",
        "description": "LSP 语言服务器工具（查找定义、引用、文件大纲）",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "操作类型：find_definition, find_references, get_document_symbols, search_workspace_symbols",
                    "enum": ["find_definition", "find_references", "get_document_symbols", "search_workspace_symbols"]
                },
                "file_path": {
                    "type": "string",
                    "description": "文件路径（find_definition, find_references, get_document_symbols 需要）"
                },
                "line": {
                    "type": "integer",
                    "description": "行号（find_definition, find_references 需要）"
                },
                "character": {
                    "type": "integer",
                    "description": "字符位置（find_definition, find_references 需要）"
                },
                "query": {
                    "type": "string",
                    "description": "搜索查询（search_workspace_symbols 需要）"
                }
            },
            "required": ["action"]
        }
    }
}

LSP_TOOL_DEFINITION_ANTHROPIC = {
    "name": "lsp_tool",
    "description": "LSP 语言服务器工具（查找定义、引用、文件大纲）",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "操作类型：find_definition, find_references, get_document_symbols, search_workspace_symbols",
                "enum": ["find_definition", "find_references", "get_document_symbols", "search_workspace_symbols"]
            },
            "file_path": {
                "type": "string",
                "description": "文件路径（find_definition, find_references, get_document_symbols 需要）"
            },
            "line": {
                "type": "integer",
                "description": "行号（find_definition, find_references 需要）"
            },
            "character": {
                "type": "integer",
                "description": "字符位置（find_definition, find_references 需要）"
            },
            "query": {
                "type": "string",
                "description": "搜索查询（search_workspace_symbols 需要）"
            }
        },
        "required": ["action"]
    }
}

def execute_lsp_tool(action: str, **kwargs) -> Tuple[str, bool]:
    """执行 LSP 工具"""
    client = get_lsp_client()
    
    try:
        if action == "find_definition":
            file_path = kwargs.get("file_path")
            line = kwargs.get("line", 1)
            character = kwargs.get("character", 0)
            if not file_path:
                return "缺少 file_path 参数", True
            result = client.find_definition(file_path, line, character)
        
        elif action == "find_references":
            file_path = kwargs.get("file_path")
            line = kwargs.get("line", 1)
            character = kwargs.get("character", 0)
            if not file_path:
                return "缺少 file_path 参数", True
            result = client.find_references(file_path, line, character)
        
        elif action == "get_document_symbols":
            file_path = kwargs.get("file_path")
            if not file_path:
                return "缺少 file_path 参数", True
            result = client.get_document_symbols(file_path)
        
        elif action == "search_workspace_symbols":
            query = kwargs.get("query", "")
            result = client.search_workspace_symbols(query)
        
        else:
            return f"未知操作: {action}", True
        
        return result, False
    
    except Exception as e:
        return f"LSP 工具执行失败: {str(e)}", True

# 清理函数
def cleanup_lsp():
    """清理 LSP 连接"""
    global _lsp_client
    if _lsp_client:
        _lsp_client.close_all()
        _lsp_client = None

# 退出时清理
import atexit
atexit.register(cleanup_lsp)
