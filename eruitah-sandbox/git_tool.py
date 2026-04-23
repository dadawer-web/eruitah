import subprocess
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

MAX_DIFF_LENGTH = 20000

def git_status(workspace_dir: str) -> tuple[str, bool]:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=workspace_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return f"git status 失败: {result.stderr}", True
        
        if not result.stdout.strip():
            return "工作区干净，没有未提交的更改", False
        
        lines = result.stdout.strip().split("\n")
        output_lines = ["当前工作区状态:\n"]
        for line in lines:
            if len(line) >= 3:
                status_code = line[:2]
                file_path = line[3:]
                status_map = {
                    " M": "已修改(未暂存)",
                    "M ": "已修改(已暂存)",
                    "MM": "已修改(部分暂存)",
                    " A": "新增(未暂存)",
                    "A ": "新增(已暂存)",
                    " D": "已删除(未暂存)",
                    "D ": "已删除(已暂存)",
                    "??": "未跟踪",
                    "!!": "已忽略",
                }
                status_text = status_map.get(status_code, status_code)
                output_lines.append(f"  [{status_text}] {file_path}")
        
        return "\n".join(output_lines), False
    except subprocess.TimeoutExpired:
        return "git status 超时", True
    except Exception as e:
        return f"git status 异常: {str(e)}", True

def git_diff(workspace_dir: str, file_path: Optional[str] = None, staged: bool = False) -> tuple[str, bool]:
    try:
        cmd = ["git", "diff"]
        if staged:
            cmd.append("--staged")
        if file_path:
            cmd.append(file_path)
        
        result = subprocess.run(
            cmd,
            cwd=workspace_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return f"git diff 失败: {result.stderr}", True
        
        diff_output = result.stdout
        if not diff_output.strip():
            if staged:
                return "暂存区没有更改", False
            else:
                return "工作区没有更改", False
        
        if len(diff_output) > MAX_DIFF_LENGTH:
            diff_output = diff_output[:MAX_DIFF_LENGTH] + "\n... [Diff 过长已被截断，请指定具体文件查看]"
        
        return diff_output, False
    except subprocess.TimeoutExpired:
        return "git diff 超时", True
    except Exception as e:
        return f"git diff 异常: {str(e)}", True

def git_log(workspace_dir: str, count: int = 10, oneline: bool = True) -> tuple[str, bool]:
    try:
        cmd = ["git", "log", f"-{count}"]
        if oneline:
            cmd.append("--oneline")
        
        result = subprocess.run(
            cmd,
            cwd=workspace_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return f"git log 失败: {result.stderr}", True
        
        return result.stdout.strip(), False
    except subprocess.TimeoutExpired:
        return "git log 超时", True
    except Exception as e:
        return f"git log 异常: {str(e)}", True

def git_commit(workspace_dir: str, message: str) -> tuple[str, bool]:
    if not message.strip():
        return "提交信息不能为空", True
    
    try:
        result = subprocess.run(
            ["git", "add", "-A"],
            cwd=workspace_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=workspace_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            if "nothing to commit" in result.stdout:
                return "没有需要提交的更改", False
            return f"git commit 失败: {result.stderr}", True
        
        return f"提交成功: {message}\n{result.stdout.strip()}", False
    except subprocess.TimeoutExpired:
        return "git commit 超时", True
    except Exception as e:
        return f"git commit 异常: {str(e)}", True

def execute_git_tool(action: str, **kwargs) -> tuple[str, bool]:
    workspace_dir = kwargs.get("workspace_dir", ".")
    
    if action == "status":
        return git_status(workspace_dir)
    elif action == "diff":
        return git_diff(workspace_dir, kwargs.get("file_path"), kwargs.get("staged", False))
    elif action == "log":
        return git_log(workspace_dir, kwargs.get("count", 10), kwargs.get("oneline", True))
    elif action == "commit":
        return git_commit(workspace_dir, kwargs.get("message", ""))
    else:
        return f"未知 git 操作: {action}", True

GIT_TOOL_DEFINITION_OPENAI = {
    "type": "function",
    "function": {
        "name": "git_tool",
        "description": "Git 版本控制工具（查看状态、差异、日志、提交）",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "操作类型：status, diff, log, commit",
                    "enum": ["status", "diff", "log", "commit"]
                },
                "file_path": {
                    "type": "string",
                    "description": "文件路径（diff 操作可选，指定查看某个文件的差异）"
                },
                "staged": {
                    "type": "boolean",
                    "description": "是否查看暂存区的差异（diff 操作可选）"
                },
                "count": {
                    "type": "integer",
                    "description": "日志条数（log 操作可选，默认 10）"
                },
                "oneline": {
                    "type": "boolean",
                    "description": "是否使用单行格式（log 操作可选，默认 true）"
                },
                "message": {
                    "type": "string",
                    "description": "提交信息（commit 操作必填）"
                }
            },
            "required": ["action"]
        }
    }
}

GIT_TOOL_DEFINITION_ANTHROPIC = {
    "name": "git_tool",
    "description": "Git 版本控制工具（查看状态、差异、日志、提交）",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "操作类型：status, diff, log, commit",
                "enum": ["status", "diff", "log", "commit"]
            },
            "file_path": {
                "type": "string",
                "description": "文件路径（diff 操作可选，指定查看某个文件的差异）"
            },
            "staged": {
                "type": "boolean",
                "description": "是否查看暂存区的差异（diff 操作可选）"
            },
            "count": {
                "type": "integer",
                "description": "日志条数（log 操作可选，默认 10）"
            },
            "oneline": {
                "type": "boolean",
                "description": "是否使用单行格式（log 操作可选，默认 true）"
            },
            "message": {
                "type": "string",
                "description": "提交信息（commit 操作必填）"
            }
        },
        "required": ["action"]
    }
}
