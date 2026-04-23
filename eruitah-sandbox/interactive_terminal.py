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

logger = logging.getLogger(__name__)

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
