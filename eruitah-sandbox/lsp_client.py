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

    def initialize(self, root_uri: str = "", init_options: dict = None) -> bool:
        """执行 LSP 初始化握手"""
        root_path = root_uri or os.getcwd()
        uri = f"file://{root_path}"

        init_params = {
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
        }

        if init_options:
            init_params["initializationOptions"] = init_options

        result = self.send_request("initialize", init_params)

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
                init_opts = self.LSP_INIT_OPTIONS.get(language)
                server_init_opts = None
                if init_opts:
                    for server_name, opts in init_opts.items():
                        server_init_opts = opts
                        break

                if conn.initialize(root_uri, init_options=server_init_opts):
                    self.connections[language] = conn
                    return conn
                else:
                    conn.close()
            return None

    LSP_SERVERS = {
        'python': [
            ['pyright-langserver', '--stdio'],
            ['pylsp'],
            ['pyls'],
            ['basedpyright-langserver', '--stdio'],
        ],
        'cpp': [
            ['clangd', '--log=verbose'],
            ['clangd-18', '--log=verbose'],
            ['clangd-17', '--log=verbose'],
            ['clangd-16', '--log=verbose'],
            ['clangd-15', '--log=verbose'],
            ['clangd-14', '--log=verbose'],
            ['ccls'],
        ],
        'javascript': [
            ['./node_modules/.bin/typescript-language-server', '--stdio'],
            ['vscode-json-language-server', '--stdio'],
        ],
        'typescript': [
            ['./node_modules/.bin/typescript-language-server', '--stdio'],
        ],
        'java': [
            ['__jdtls__'],
        ],
        'rust': [
            ['rust-analyzer'],
        ],
        'go': [
            ['gopls'],
        ],
    }

    LSP_INIT_OPTIONS = {
        'cpp': {
            'clangd': {
                'fallbackFlags': ['-std=c++17'],
                'completion': {'allScopes': True},
            },
        },
    }

    LSP_AUTO_INSTALL = {
        'python': {
            'check': ['pyright-langserver', '--version'],
            'install': ['npm', 'install', '--no-save', 'pyright'],
            'name': 'pyright',
        },
        'typescript': {
            'check': ['./node_modules/.bin/typescript-language-server', '--version'],
            'install': ['npm', 'install', '--no-save', 'typescript-language-server', 'typescript'],
            'install_fallback': ['npm', 'install', '--no-save', 'typescript-language-server@3.3.2', 'typescript@4.9.5'],
            'name': 'typescript-language-server',
        },
        'javascript': {
            'check': ['./node_modules/.bin/typescript-language-server', '--version'],
            'install': ['npm', 'install', '--no-save', 'typescript-language-server', 'typescript'],
            'install_fallback': ['npm', 'install', '--no-save', 'typescript-language-server@3.3.2', 'typescript@4.9.5'],
            'name': 'typescript-language-server',
        },
        'cpp': {
            'check': ['clangd', '--version'],
            'install': ['apt-get', 'install', '-y', 'clangd'],
            'name': 'clangd',
        },
        'rust': {
            'check': ['rust-analyzer', '--version'],
            'install': ['bash', '-c', 'curl -L https://github.com/rust-lang/rust-analyzer/releases/latest/download/rust-analyzer-x86_64-unknown-linux-gnu.gz | gunzip -c > /usr/local/bin/rust-analyzer && chmod +x /usr/local/bin/rust-analyzer'],
            'name': 'rust-analyzer',
        },
        'go': {
            'check': ['gopls', 'version'],
            'install': ['bash', '-c', 'go install golang.org/x/tools/gopls@latest && mv ~/go/bin/gopls /usr/local/bin/'],
            'name': 'gopls',
        },
    }

    def _start_server(self, language: str) -> Optional[LSPConnection]:
        if language == 'java':
            return self._start_jdtls()

        commands_list = self.LSP_SERVERS.get(language, [])

        if not commands_list:
            return None

        for cmd in commands_list:
            try:
                # 容错：检查局部二进制文件是否存在（./node_modules/.bin/... 路径）
                binary_path = cmd[0]
                if binary_path.startswith('./') or binary_path.startswith('../'):
                    if not os.path.exists(binary_path):
                        logger.debug(f"LSP 二进制文件不存在: {binary_path}，跳过")
                        continue

                sock1, sock2 = socket.socketpair()

                init_opts = self.LSP_INIT_OPTIONS.get(language, {})

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
                    stderr_output = ""
                    try:
                        stderr_output = server_process.stderr.read(500).decode('utf-8', errors='replace')
                    except Exception:
                        pass
                    logger.debug(f"LSP 服务器 {cmd[0]} 启动失败 (exit={server_process.returncode}): {stderr_output[:200]}")
                    continue

                logger.info(f"✅ LSP 服务器启动成功: {language} → {cmd[0]}")
                return LSPConnection(server_process, sock1, language)
            except FileNotFoundError:
                logger.debug(f"LSP 服务器未安装: {cmd[0]}，尝试下一个后备方案...")
                continue
            except Exception as e:
                logger.debug(f"启动 LSP 服务器 {cmd[0]} 失败: {e}")
                continue

        install_info = self.LSP_AUTO_INSTALL.get(language)
        if install_info:
            logger.info(f"🔧 尝试自动安装 LSP 服务器: {install_info['name']}...")
            try:
                result = subprocess.run(
                    install_info['install'],
                    capture_output=True, text=True, timeout=120,
                )
                if result.returncode == 0:
                    logger.info(f"✅ LSP 服务器 {install_info['name']} 安装成功，重新启动...")
                else:
                    stderr_lower = (result.stderr or '').lower()
                    is_engine_error = 'ebadengine' in stderr_lower or 'unsupported engine' in stderr_lower
                    fallback_cmd = install_info.get('install_fallback')
                    if is_engine_error and fallback_cmd:
                        logger.warning(f"⚠️ LSP 安装遇到引擎版本不兼容 (EBADENGINE)，降级重试: {' '.join(fallback_cmd)}")
                        result = subprocess.run(
                            fallback_cmd,
                            capture_output=True, text=True, timeout=120,
                        )
                        if result.returncode == 0:
                            logger.info(f"✅ LSP 服务器 {install_info['name']} 降级安装成功，重新启动...")
                        else:
                            logger.warning(f"LSP 降级安装也失败: {result.stderr[:200]}")
                            result = None
                    elif not is_engine_error and fallback_cmd:
                        logger.warning(f"LSP 自动安装失败: {result.stderr[:200]}，尝试降级版本...")
                        result = subprocess.run(
                            fallback_cmd,
                            capture_output=True, text=True, timeout=120,
                        )
                        if result.returncode == 0:
                            logger.info(f"✅ LSP 服务器 {install_info['name']} 降级安装成功，重新启动...")
                        else:
                            logger.warning(f"LSP 降级安装也失败: {result.stderr[:200]}")
                            result = None
                    else:
                        logger.warning(f"LSP 自动安装失败: {result.stderr[:200]}")
                        result = None

                if result and result.returncode == 0:
                    for cmd in commands_list:
                        try:
                            # 容错：检查局部二进制文件是否存在
                            binary_path = cmd[0]
                            if binary_path.startswith('./') or binary_path.startswith('../'):
                                if not os.path.exists(binary_path):
                                    logger.debug(f"安装后二进制文件仍不存在: {binary_path}，跳过")
                                    continue

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
                                continue
                            logger.info(f"✅ LSP 服务器自动安装后启动成功: {language} → {cmd[0]}")
                            return LSPConnection(server_process, sock1, language)
                        except Exception:
                            continue
            except Exception as e:
                logger.warning(f"LSP 自动安装异常: {e}")

        logger.warning(f"⚠️ 所有 LSP 后备方案均失败: {language}")
        return None

    def _start_jdtls(self) -> Optional[LSPConnection]:
        """启动 Eclipse JDT Language Server (Java LSP)

        jdtls 的启动比较特殊，需要：
        1. 找到 jdtls 的安装路径（/opt/jdtls 或 PATH 中）
        2. 设置 JAVA_HOME
        3. 构建包含多个 JAR 的 classpath
        4. 使用特定的启动参数
        """
        jdtls_home = os.environ.get("JDTLS_HOME", "/opt/jdtls")
        java_home = os.environ.get("JAVA_HOME", "/usr/lib/jvm/default-java")

        jdtls_cmd = self._build_jdtls_command(jdtls_home, java_home)
        if not jdtls_cmd:
            logger.warning("⚠️ 未找到 jdtls 安装，Java LSP 不可用")
            logger.info("提示: 安装 jdtls: 下载 https://download.eclipse.org/jdtls/snapshots/ 解压到 /opt/jdtls")
            return None

        try:
            sock1, sock2 = socket.socketpair()
            env = os.environ.copy()
            env["JAVA_HOME"] = java_home

            server_process = subprocess.Popen(
                jdtls_cmd,
                stdin=sock2,
                stdout=sock2,
                stderr=subprocess.PIPE,
                text=False,
                env=env,
            )
            sock2.close()

            time.sleep(1.0)

            if server_process.poll() is not None:
                sock1.close()
                stderr_output = ""
                try:
                    stderr_output = server_process.stderr.read(1000).decode('utf-8', errors='replace')
                except Exception:
                    pass
                logger.error(f"jdtls 启动失败 (exit={server_process.returncode}): {stderr_output[:500]}")
                return None

            logger.info(f"✅ LSP 服务器启动成功: java → jdtls ({jdtls_home})")
            return LSPConnection(server_process, sock1, 'java')
        except Exception as e:
            logger.error(f"启动 jdtls 失败: {e}")
            return None

    def _build_jdtls_command(self, jdtls_home: str, java_home: str) -> Optional[list]:
        """构建 jdtls 启动命令"""
        jdtls_script = os.path.join(jdtls_home, "bin", "jdtls")
        if os.path.isfile(jdtls_script) and os.access(jdtls_script, os.X_OK):
            return [jdtls_script]

        plugins_dir = os.path.join(jdtls_home, "plugins")
        config_dir = os.path.join(jdtls_home, "config_linux")

        if not os.path.isdir(plugins_dir):
            return None

        java_bin = os.path.join(java_home, "bin", "java")
        if not os.path.isfile(java_bin):
            java_bin = "java"

        launcher_jar = None
        for f in sorted(os.listdir(plugins_dir)):
            if f.startswith("org.eclipse.equinox.launcher_") and f.endswith(".jar"):
                launcher_jar = os.path.join(plugins_dir, f)
                break

        if not launcher_jar:
            return None

        config_dir = config_dir if os.path.isdir(config_dir) else os.path.join(jdtls_home, "config_ss_linux")
        if not os.path.isdir(config_dir):
            config_dir = ""

        cmd = [
            java_bin,
            "-Declipse.application=org.eclipse.jdt.ls.core.id1",
            "-Dosgi.bundles.defaultStartLevel=4",
            "-Declipse.product=org.eclipse.jdt.ls.core.product",
            "-Dlog.level=ALL",
            "-Xmx1G",
            f"-javaagent:{launcher_jar}",
        ]

        if config_dir:
            cmd.extend([
                "--add-modules=ALL-SYSTEM",
                "--add-opens", "java.base/java.util=ALL-UNNAMED",
                "--add-opens", "java.base/java.lang=ALL-UNNAMED",
                "-jar", launcher_jar,
                "-configuration", config_dir,
                "-data", os.path.join(jdtls_home, "data"),
            ])
        else:
            cmd.extend(["-jar", launcher_jar])

        return cmd

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

    def get_diagnostics(self, file_path: str, root_uri: str = "") -> List[Dict[str, Any]]:
        language = self._get_language(file_path)
        if not language:
            return []

        conn = self.get_connection(language, root_uri)
        if not conn:
            return []

        self._ensure_file_open(file_path, conn)

        try:
            abs_path = os.path.abspath(file_path)
            uri = f"file://{abs_path}"

            with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            conn.did_change(abs_path, content, version=2)

            import time
            time.sleep(0.5)

            pushed_diags = self._try_read_pushed_diagnostics(conn, uri)
            if pushed_diags is not None:
                return pushed_diags

            result = conn.send_request("textDocument/diagnostic", {
                "textDocument": {"uri": uri}
            })

            diagnostics = []
            if result and "items" in result:
                for item in result["items"]:
                    diag = self._lsp_diag_to_json(item)
                    if diag:
                        diagnostics.append(diag)
            elif result and "relatedDocuments" in result:
                for doc_uri, doc_diags in result["relatedDocuments"].items():
                    if isinstance(doc_diags, list):
                        for item in doc_diags:
                            diag = self._lsp_diag_to_json(item)
                            if diag:
                                diagnostics.append(diag)

            return diagnostics
        except Exception as e:
            logger.error(f"获取 LSP 诊断失败: {e}")
            return []

    def _try_read_pushed_diagnostics(self, conn: LSPConnection, uri: str) -> Optional[List[Dict[str, Any]]]:
        try:
            if not conn.sock:
                return None
            conn.sock.settimeout(0.1)
            data = conn.sock.recv(65536)
            if not data:
                return None
            conn.buffer += data

            while True:
                header_end = conn.buffer.find(b'\r\n\r\n')
                if header_end == -1:
                    break
                header = conn.buffer[:header_end].decode('utf-8')
                content_length = 0
                for line in header.split('\r\n'):
                    if line.startswith('Content-Length:'):
                        content_length = int(line.split(':')[1].strip())
                        break
                if content_length == 0:
                    break
                total_length = header_end + 4 + content_length
                if len(conn.buffer) < total_length:
                    break
                body = conn.buffer[header_end + 4:total_length]
                conn.buffer = conn.buffer[total_length:]
                try:
                    msg = json.loads(body.decode('utf-8'))
                    if msg.get("method") == "textDocument/publishDiagnostics":
                        params = msg.get("params", {})
                        msg_uri = params.get("uri", "")
                        if msg_uri == uri or msg_uri.endswith(uri.replace("file://", "")):
                            diagnostics = []
                            for item in params.get("diagnostics", []):
                                diag = self._lsp_diag_to_json(item)
                                if diag:
                                    diagnostics.append(diag)
                            return diagnostics
                except json.JSONDecodeError:
                    pass
        except socket.timeout:
            pass
        except Exception:
            pass
        return None

    def _lsp_diag_to_json(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(item, dict):
            return None
        range_info = item.get("range", {})
        start = range_info.get("start", {})
        end = range_info.get("end", {})
        severity = item.get("severity", 3)
        severity_map = {1: "error", 2: "warning", 3: "info", 4: "hint"}
        return {
            "line": start.get("line", 0) + 1,
            "column": start.get("character", 0) + 1,
            "endLine": end.get("line", 0) + 1,
            "endColumn": end.get("character", 0) + 1,
            "message": item.get("message", ""),
            "severity": severity_map.get(severity, "info"),
        }

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
