"""
Eruitah 智能编程沙盒 - 交互式终端 (PTY)

提供真正的交互式 shell 体验，用户可以在终端中输入命令并实时看到输出。

核心流程:
┌─────────────────────────────────────────────────────────────────────┐
│  前端 Xterm.js:                                                      │
│    terminal.onData(data => ws.send({type: 'input', data}))          │
│         │                                                            │
│         ▼                                                            │
│  Python 后端:                                                        │
│    1. 创建 PTY 进程 (bash/zsh)                                       │
│    2. 收到前端输入 -> pty.write(data)                                │
│    3. pty 输出 -> ws.send({type: 'output', data})                   │
│         │                                                            │
│         ▼                                                            │
│  前端 Xterm.js:                                                      │
│    收到输出 -> terminal.write(data)                                  │
└─────────────────────────────────────────────────────────────────────┘
"""

import os
import sys
import select
import logging
import asyncio
import signal
import struct
import fcntl
import termios
import pty
import subprocess
import tempfile
import threading
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class BackgroundProcessManager:
    """后台进程管理器 - 让 Agent 能启动/监控/停止后台服务

    核心场景：Agent 写了一个 Web Server，需要：
    1. start_background_service: 后台启动服务（不阻塞 Agent）
    2. read_service_logs: 查看服务端日志
    3. kill_service: 关闭服务

    流程:
      Agent 写出 chat_server.py
        → start_background_service("python3 chat_server.py") → PID 12345
        → bash("curl http://localhost:8080") → 测试服务
        → read_service_logs(pid=12345) → 查看服务端日志
        → kill_service(pid=12345) → 关闭服务
    """

    def __init__(self):
        self._processes: Dict[int, subprocess.Popen] = {}
        self._log_files: Dict[int, str] = {}
        self._commands: Dict[int, str] = {}
        self._work_dirs: Dict[int, str] = {}
        self._lock = threading.Lock()
        self._cleanup_registered = False

    def start_service(self, command: str, work_dir: str = "", env: dict = None) -> dict:
        """启动后台服务

        Args:
            command: 要执行的命令
            work_dir: 工作目录
            env: 额外环境变量

        Returns:
            dict: {pid, log_file, command, status}
        """
        if not command.strip():
            return {"error": "命令不能为空", "pid": None}

        running_count = len(self._processes)
        if running_count >= 10:
            return {"error": f"后台进程数已达上限 ({running_count}/10)，请先 kill_service 清理", "pid": None}

        log_fd, log_path = tempfile.mkstemp(prefix=f"bgsvc_", suffix=".log", dir="/tmp")
        os.close(log_fd)

        full_env = os.environ.copy()
        if env:
            full_env.update(env)

        cwd = work_dir or os.environ.get("ERUITAH_SANDBOX_DIR", "/tmp/eruitah-sandbox")

        try:
            with open(log_path, 'w') as log_file:
                process = subprocess.Popen(
                    command,
                    shell=True,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    cwd=cwd,
                    env=full_env,
                    start_new_session=True,
                )
        except Exception as e:
            try:
                os.unlink(log_path)
            except Exception:
                pass
            return {"error": f"启动失败: {e}", "pid": None}

        pid = process.pid
        with self._lock:
            self._processes[pid] = process
            self._log_files[pid] = log_path
            self._commands[pid] = command
            self._work_dirs[pid] = cwd

        if not self._cleanup_registered:
            import atexit
            atexit.register(self.kill_all)
            self._cleanup_registered = True

        time.sleep(0.3)

        poll = process.poll()
        if poll is not None:
            log_content = ""
            try:
                with open(log_path, 'r', errors='replace') as f:
                    log_content = f.read(2000)
            except Exception:
                pass
            self._cleanup_pid(pid)
            return {
                "error": f"进程启动后立即退出 (exit code: {poll})",
                "pid": pid,
                "log": log_content,
            }

        logger.info(f"🚀 后台服务已启动: PID={pid}, command='{command[:80]}'")
        return {
            "pid": pid,
            "log_file": log_path,
            "command": command,
            "work_dir": cwd,
            "status": "running",
        }

    def read_logs(self, pid: int, lines: int = 50) -> dict:
        """读取后台服务的日志

        Args:
            pid: 进程 ID
            lines: 读取最后 N 行

        Returns:
            dict: {pid, status, logs, command}
        """
        with self._lock:
            log_path = self._log_files.get(pid)
            command = self._commands.get(pid, "")
            process = self._processes.get(pid)

        if not log_path:
            return {"error": f"未找到 PID={pid} 的后台进程", "pid": pid}

        status = "unknown"
        if process:
            poll = process.poll()
            if poll is None:
                status = "running"
            else:
                status = f"exited (code: {poll})"

        log_content = ""
        try:
            with open(log_path, 'r', errors='replace') as f:
                all_lines = f.readlines()
            log_content = "".join(all_lines[-lines:])
        except Exception as e:
            log_content = f"(读取日志失败: {e})"

        return {
            "pid": pid,
            "status": status,
            "logs": log_content,
            "command": command,
        }

    def kill_service(self, pid: int) -> dict:
        """关闭后台服务

        Args:
            pid: 进程 ID

        Returns:
            dict: {pid, status, command}
        """
        with self._lock:
            process = self._processes.get(pid)
            command = self._commands.get(pid, "")

        if not process:
            return {"error": f"未找到 PID={pid} 的后台进程", "pid": pid}

        try:
            import signal as sig
            try:
                os.killpg(os.getpgid(pid), sig.SIGTERM)
            except Exception:
                process.terminate()

            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(pid), sig.SIGKILL)
                except Exception:
                    process.kill()
                try:
                    process.wait(timeout=2)
                except Exception:
                    pass

        except Exception as e:
            logger.warning(f"终止进程 PID={pid} 时出错: {e}")

        exit_code = process.poll()
        self._cleanup_pid(pid)

        logger.info(f"🛑 后台服务已停止: PID={pid}, exit={exit_code}")
        return {
            "pid": pid,
            "status": f"killed (exit code: {exit_code})",
            "command": command,
        }

    def list_services(self) -> dict:
        """列出所有后台服务"""
        result = []
        with self._lock:
            for pid, process in list(self._processes.items()):
                poll = process.poll()
                status = "running" if poll is None else f"exited ({poll})"
                result.append({
                    "pid": pid,
                    "status": status,
                    "command": self._commands.get(pid, "")[:80],
                    "work_dir": self._work_dirs.get(pid, ""),
                })
        return {"services": result, "count": len(result)}

    def kill_all(self):
        """关闭所有后台服务"""
        with self._lock:
            pids = list(self._processes.keys())

        for pid in pids:
            try:
                self.kill_service(pid)
            except Exception:
                pass

    def _cleanup_pid(self, pid: int):
        """清理已停止进程的资源"""
        with self._lock:
            self._processes.pop(pid, None)
            self._commands.pop(pid, None)
            self._work_dirs.pop(pid, None)
            log_path = self._log_files.pop(pid, None)

        if log_path:
            try:
                os.unlink(log_path)
            except Exception:
                pass


_bg_manager: Optional[BackgroundProcessManager] = None

def get_bg_manager() -> BackgroundProcessManager:
    global _bg_manager
    if _bg_manager is None:
        _bg_manager = BackgroundProcessManager()
    return _bg_manager


BG_SERVICE_TOOL_DEFINITIONS = {
    "openai": [
        {
            "type": "function",
            "function": {
                "name": "start_background_service",
                "description": (
                    "在后台启动一个长驻服务进程（如 Web Server、数据库、消息队列），不会阻塞 Agent。"
                    "返回 PID，之后可以用 read_service_logs 查看日志，用 kill_service 关闭。"
                    "典型流程: start_background_service → bash(curl 测试) → read_service_logs → kill_service"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "要后台执行的命令，如 'python3 server.py' 或 'redis-server'",
                        },
                        "work_dir": {
                            "type": "string",
                            "description": "工作目录（可选，默认为当前沙盒目录）",
                        },
                    },
                    "required": ["command"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_service_logs",
                "description": (
                    "读取后台服务的日志输出。用于验证服务是否正常启动、查看请求处理情况、排查错误。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pid": {
                            "type": "integer",
                            "description": "后台服务的进程 ID（由 start_background_service 返回）",
                        },
                        "lines": {
                            "type": "integer",
                            "description": "读取最后 N 行日志（默认 50）",
                        },
                    },
                    "required": ["pid"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "kill_service",
                "description": (
                    "关闭后台服务进程。测试完成后必须调用此工具清理进程，释放端口。"
                    "会先发送 SIGTERM，5 秒后发送 SIGKILL 强制终止。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pid": {
                            "type": "integer",
                            "description": "要关闭的后台服务进程 ID",
                        },
                    },
                    "required": ["pid"],
                },
            },
        },
    ],
    "anthropic": [
        {
            "name": "start_background_service",
            "description": (
                "在后台启动一个长驻服务进程（如 Web Server、数据库、消息队列），不会阻塞 Agent。"
                "返回 PID，之后可以用 read_service_logs 查看日志，用 kill_service 关闭。"
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要后台执行的命令，如 'python3 server.py'",
                    },
                    "work_dir": {
                        "type": "string",
                        "description": "工作目录（可选）",
                    },
                },
                "required": ["command"],
            },
        },
        {
            "name": "read_service_logs",
            "description": "读取后台服务的日志输出，用于验证服务状态和排查错误。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "pid": {
                        "type": "integer",
                        "description": "后台服务的进程 ID",
                    },
                    "lines": {
                        "type": "integer",
                        "description": "读取最后 N 行日志（默认 50）",
                    },
                },
                "required": ["pid"],
            },
        },
        {
            "name": "kill_service",
            "description": "关闭后台服务进程，释放端口和资源。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "pid": {
                        "type": "integer",
                        "description": "要关闭的后台服务进程 ID",
                    },
                },
                "required": ["pid"],
            },
        },
    ],
}


def execute_bg_service_tool(tool_name: str, **kwargs) -> tuple:
    """执行后台服务管理工具"""
    manager = get_bg_manager()

    if tool_name == "start_background_service":
        command = kwargs.get("command", "")
        work_dir = kwargs.get("work_dir", "")
        result = manager.start_service(command, work_dir)

        if result.get("error"):
            return f"❌ {result['error']}", True

        lines = [
            f"🚀 后台服务已启动!",
            f"  PID: {result['pid']}",
            f"  命令: {result['command']}",
            f"  工作目录: {result.get('work_dir', '')}",
            f"  日志文件: {result.get('log_file', '')}",
            "",
            "下一步操作:",
            f"  - 测试服务: bash(command='curl http://localhost:端口')",
            f"  - 查看日志: read_service_logs(pid={result['pid']})",
            f"  - 关闭服务: kill_service(pid={result['pid']})",
        ]
        return "\n".join(lines), False

    elif tool_name == "read_service_logs":
        pid = kwargs.get("pid")
        lines_count = kwargs.get("lines", 50)
        if not pid:
            return "需要提供 pid 参数", True

        result = manager.read_logs(int(pid), int(lines_count))

        if result.get("error"):
            return f"❌ {result['error']}", True

        output = [
            f"📋 后台服务日志 (PID={result['pid']}, 状态={result['status']})",
            f"  命令: {result.get('command', '')}",
            "---",
        ]
        logs = result.get("logs", "")
        if logs.strip():
            output.append(logs)
        else:
            output.append("(暂无日志输出)")
        return "\n".join(output), False

    elif tool_name == "kill_service":
        pid = kwargs.get("pid")
        if not pid:
            return "需要提供 pid 参数", True

        result = manager.kill_service(int(pid))

        if result.get("error"):
            return f"❌ {result['error']}", True

        return f"🛑 后台服务已停止 (PID={result['pid']}, 状态={result['status']}, 命令={result.get('command', '')})", False

    else:
        return f"未知工具: {tool_name}", True

class InteractiveTerminal:
    """交互式终端会话"""
    
    def __init__(self, work_dir: str = None, shell: str = None, cols: int = 80, rows: int = 24):
        self.work_dir = work_dir or os.environ.get("ERUITAH_SANDBOX_DIR", "/tmp/eruitah-sandbox")
        self.shell = shell or os.environ.get("SHELL", "/bin/bash")
        self.cols = cols
        self.rows = rows
        self.master_fd = None
        self.slave_fd = None
        self.pid = None
        self.running = False
        
    def start(self):
        """启动 PTY 进程"""
        try:
            self.pid, self.master_fd = pty.fork()
            
            if self.pid == 0:
                os.chdir(self.work_dir)
                os.environ["TERM"] = "xterm-256color"
                os.environ["COLORTERM"] = "truecolor"
                os.execvp(self.shell, [self.shell])
            else:
                self.running = True
                self._set_winsize(self.master_fd, self.rows, self.cols)
                logger.info(f"PTY 进程已启动: pid={self.pid}, shell={self.shell}, cwd={self.work_dir}")
                return True
        except Exception as e:
            logger.error(f"启动 PTY 失败: {e}")
            return False
    
    def _set_winsize(self, fd, rows, cols):
        """设置终端窗口大小"""
        winsize = struct.pack('HHHH', rows, cols, 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
    
    def resize(self, cols: int, rows: int):
        """调整终端大小"""
        self.cols = cols
        self.rows = rows
        if self.master_fd is not None:
            try:
                self._set_winsize(self.master_fd, rows, cols)
            except Exception as e:
                logger.error(f"调整终端大小失败: {e}")
    
    def write(self, data: str):
        """向终端写入数据（用户输入）"""
        if self.master_fd is not None and self.running:
            try:
                os.write(self.master_fd, data.encode('utf-8'))
            except Exception as e:
                logger.error(f"写入 PTY 失败: {e}")
    
    def read(self, timeout: float = 0.1) -> str:
        """从终端读取数据（输出）"""
        if self.master_fd is None or not self.running:
            return ""
        
        try:
            r, _, _ = select.select([self.master_fd], [], [], timeout)
            if r:
                data = os.read(self.master_fd, 65536)
                return data.decode('utf-8', errors='replace')
        except Exception as e:
            if "resource temporarily unavailable" not in str(e).lower():
                logger.error(f"读取 PTY 失败: {e}")
        return ""
    
    def stop(self):
        """停止 PTY 进程"""
        self.running = False
        if self.pid:
            try:
                os.kill(self.pid, signal.SIGTERM)
                os.waitpid(self.pid, 0)
            except Exception:
                pass
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except Exception:
                pass
        if self.slave_fd is not None:
            try:
                os.close(self.slave_fd)
            except Exception:
                pass
        self.master_fd = None
        self.slave_fd = None
        self.pid = None
        logger.info("PTY 进程已停止")
    
    def is_alive(self) -> bool:
        """检查进程是否存活"""
        if self.pid is None:
            return False
        try:
            pid, status = os.waitpid(self.pid, os.WNOHANG)
            return pid == 0
        except Exception:
            return False
