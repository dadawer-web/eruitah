"""
Eruitah 智能编程沙盒 - 交互式调试器工具

基于 pexpect 接管 pdb，让 Agent 像用终端一样单步调试 Python 代码。
有状态设计：调试进程启动后保持存活，等待 Agent 下发后续指令。
"""

import os
import logging
import pexpect
from typing import Optional

logger = logging.getLogger(__name__)

PDB_PROMPT = r"\(Pdb\+\+\)|\(Pdb\)"

_active_sessions = {}


class DebugSession:
    def __init__(self, session_id: str, child: pexpect.spawn, script_path: str, work_dir: str):
        self.session_id = session_id
        self.child = child
        self.script_path = script_path
        self.work_dir = work_dir
        self.alive = True

    def is_alive(self) -> bool:
        if not self.alive:
            return False
        if self.child is None:
            self.alive = False
            return False
        if not self.child.isalive():
            self.alive = False
            return False
        return True

    def close(self):
        if self.child and self.child.isalive():
            try:
                self.child.sendline("quit")
                self.child.expect(pexpect.TIMEOUT, timeout=2)
            except Exception:
                pass
            try:
                self.child.close(force=True)
            except Exception:
                pass
        self.alive = False


def _get_session(session_id: str) -> Optional[DebugSession]:
    session = _active_sessions.get(session_id)
    if session and session.is_alive():
        return session
    if session_id in _active_sessions:
        del _active_sessions[session_id]
    return None


def _cleanup_dead_sessions():
    dead = [sid for sid, s in _active_sessions.items() if not s.is_alive()]
    for sid in dead:
        del _active_sessions[sid]


def execute_interactive_debugger(
    action: str,
    script_path: str = "",
    breakpoint_line: int = 0,
    breakpoint_func: str = "",
    cmd: str = "",
    work_dir: str = ".",
    session_id: str = "default",
    timeout: int = 15,
) -> dict:
    """
    交互式调试器工具

    Args:
        action: 操作类型
            - "start": 启动调试会话，加载脚本并设置断点
            - "command": 向运行中的 pdb 发送调试命令
            - "status": 查看当前调试会话状态
            - "stop": 终止调试会话
        script_path: 要调试的 Python 脚本路径（action=start 时必填）
        breakpoint_line: 断点行号（action=start 时可选）
        breakpoint_func: 断点函数名（action=start 时可选，与 breakpoint_line 二选一）
        cmd: pdb 调试命令（action=command 时必填，如 step/next/continue/p 变量名）
        work_dir: 工作目录
        session_id: 调试会话标识
        timeout: 命令超时时间（秒）

    Returns:
        dict: 包含 status 和 output 的字典
    """
    _cleanup_dead_sessions()

    if action == "start":
        return _action_start(script_path, breakpoint_line, breakpoint_func, work_dir, session_id, timeout)
    elif action == "command":
        return _action_command(cmd, session_id, timeout)
    elif action == "status":
        return _action_status(session_id)
    elif action == "stop":
        return _action_stop(session_id)
    else:
        return {"status": "error", "error": f"未知 action: {action}，可选: start, command, status, stop"}


def _action_start(script_path: str, breakpoint_line: int, breakpoint_func: str, work_dir: str, session_id: str, timeout: int) -> dict:
    existing = _get_session(session_id)
    if existing:
        existing.close()
        del _active_sessions[session_id]

    if not script_path:
        return {"status": "error", "error": "action=start 时必须提供 script_path"}

    full_path = os.path.join(work_dir, script_path) if not os.path.isabs(script_path) else script_path
    if not os.path.exists(full_path):
        return {"status": "error", "error": f"脚本不存在: {full_path}"}

    try:
        child = pexpect.spawn(
            "python3",
            ["-m", "pdb", script_path],
            cwd=work_dir,
            encoding="utf-8",
            timeout=timeout,
            echo=False,
        )

        idx = child.expect([PDB_PROMPT, pexpect.TIMEOUT, pexpect.EOF])
        if idx == 0:
            initial_output = child.before or ""
        elif idx == 1:
            child.close(force=True)
            return {"status": "error", "error": f"启动 pdb 超时（{timeout}s）"}
        else:
            output = child.before or ""
            child.close(force=True)
            return {"status": "error", "error": f"pdb 进程意外退出: {output[:500]}"}

        bp_commands = []
        if breakpoint_line > 0:
            bp_cmd = f"b {script_path}:{breakpoint_line}"
            child.sendline(bp_cmd)
            bp_commands.append(bp_cmd)
        elif breakpoint_func:
            bp_cmd = f"b {script_path}:{breakpoint_func}"
            child.sendline(bp_cmd)
            bp_commands.append(bp_cmd)

        if bp_commands:
            child.sendline("continue")
            idx = child.expect([PDB_PROMPT, pexpect.TIMEOUT, pexpect.EOF])
            run_output = child.before or ""
        else:
            run_output = ""

        session = DebugSession(session_id, child, script_path, work_dir)
        _active_sessions[session_id] = session

        full_output = initial_output
        if bp_commands:
            full_output += f"\n> {bp_commands[-1]}\n{run_output}"

        return {
            "status": "success",
            "action": "start",
            "output": full_output.strip(),
            "session_id": session_id,
            "script_path": script_path,
            "alive": True,
        }

    except Exception as e:
        logger.error(f"启动调试会话异常: {e}")
        return {"status": "error", "error": f"启动调试会话异常: {str(e)}"}


def _action_command(cmd: str, session_id: str, timeout: int) -> dict:
    if not cmd:
        return {"status": "error", "error": "action=command 时必须提供 cmd"}

    session = _get_session(session_id)
    if not session:
        return {"status": "error", "error": f"没有活跃的调试会话 (session_id={session_id})，请先 action=start"}

    try:
        session.child.sendline(cmd)

        idx = session.child.expect([PDB_PROMPT, pexpect.TIMEOUT, pexpect.EOF], timeout=timeout)

        if idx == 0:
            output = session.child.before or ""
            return {
                "status": "success",
                "action": "command",
                "output": output.strip(),
                "session_id": session_id,
                "alive": True,
            }
        elif idx == 1:
            output = session.child.before or ""
            return {
                "status": "timeout",
                "action": "command",
                "output": output.strip(),
                "session_id": session_id,
                "alive": session.is_alive(),
                "warning": f"命令执行超时（{timeout}s），程序可能在等待输入或长时间运行",
            }
        else:
            output = session.child.before or ""
            session.alive = False
            return {
                "status": "exited",
                "action": "command",
                "output": output.strip(),
                "session_id": session_id,
                "alive": False,
                "info": "被调试的程序已正常退出",
            }

    except Exception as e:
        logger.error(f"发送调试命令异常: {e}")
        session.alive = False
        return {"status": "error", "error": f"发送调试命令异常: {str(e)}", "alive": False}


def _action_status(session_id: str) -> dict:
    session = _get_session(session_id)
    if not session:
        return {"status": "info", "alive": False, "session_id": session_id, "info": "没有活跃的调试会话"}
    return {
        "status": "info",
        "alive": True,
        "session_id": session_id,
        "script_path": session.script_path,
        "work_dir": session.work_dir,
    }


def _action_stop(session_id: str) -> dict:
    session = _get_session(session_id)
    if not session:
        return {"status": "info", "alive": False, "session_id": session_id, "info": "没有活跃的调试会话"}

    session.close()
    if session_id in _active_sessions:
        del _active_sessions[session_id]

    return {"status": "success", "action": "stop", "session_id": session_id, "info": "调试会话已终止"}
