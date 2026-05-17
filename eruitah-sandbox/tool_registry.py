"""
Eruitah 智能编程沙盒 - 工具注册表

按照 OpenAI Function Calling 格式定义 5 个工具的 JSON Schema，
并提供 execute_tool() 路由函数，将工具名反射到对应的 Python 函数。
"""

import json
import traceback
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# ============================================================================
# 工具定义列表 - OpenAI Function Calling 格式
# 参数名与实际 Python 函数签名完全匹配
# ============================================================================

tools: List[Dict[str, Any]] = [
    {
        "name": "bash",
        "description": "执行 bash 命令并返回输出",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的 bash 命令"
                },
                "timeout_ms": {
                    "type": "integer",
                    "description": "命令执行超时时间（毫秒）",
                    "default": 120000
                },
                "work_dir": {
                    "type": "string",
                    "description": "执行命令的工作目录"
                }
            },
            "required": ["command"]
        }
    },
    {
        "name": "file_edit",
        "description": "使用 SEARCH/REPLACE 模式编辑文件",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "要编辑的文件路径"
                },
                "search_text": {
                    "type": "string",
                    "description": "要查找的文本（必须与文件内容完全匹配）"
                },
                "replace_text": {
                    "type": "string",
                    "description": "替换为的文本"
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "是否替换所有匹配项（默认只替换第一个）",
                    "default": False
                }
            },
            "required": ["file_path", "search_text", "replace_text"]
        }
    },
    {
        "name": "file_read",
        "description": "读取文件内容，支持按行号范围读取。超过1000行的文件必须指定行号范围",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "要读取的文件路径"
                },
                "start_line": {
                    "type": "integer",
                    "description": "起始行号（从1开始）",
                    "default": 1
                },
                "end_line": {
                    "type": "integer",
                    "description": "结束行号"
                },
                "work_dir": {
                    "type": "string",
                    "description": "工作目录"
                }
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "glob",
        "description": "使用通配符搜索文件路径",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "文件匹配模式（支持 ** 递归匹配）"
                },
                "work_dir": {
                    "type": "string",
                    "description": "搜索的目录路径"
                }
            },
            "required": ["pattern"]
        }
    },
    {
        "name": "grep",
        "description": "搜索代码中的匹配内容，支持正则表达式",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "要搜索的正则表达式模式"
                },
                "work_dir": {
                    "type": "string",
                    "description": "搜索的目录路径"
                },
                "file_pattern": {
                    "type": "string",
                    "description": "文件过滤模式（如 *.py）"
                },
                "case_insensitive": {
                    "type": "boolean",
                    "description": "是否忽略大小写",
                    "default": False
                }
            },
            "required": ["pattern"]
        }
    },
    {
        "name": "browser_vision",
        "description": "访问指定 URL（本地或远程），使用无头浏览器渲染页面并返回截图。适用于检查网页视觉效果、验证前端布局、调试 Web 应用界面等场景。返回 Base64 编码的 PNG 截图。",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "要访问的 URL（如 http://localhost:3000 或 https://example.com）"
                },
                "wait_until": {
                    "type": "string",
                    "description": "页面加载等待策略：load（DOM完成）、domcontentloaded（HTML解析完成）、networkidle（网络空闲，默认）",
                    "enum": ["load", "domcontentloaded", "networkidle"],
                    "default": "networkidle"
                },
                "timeout_ms": {
                    "type": "integer",
                    "description": "页面加载超时时间（毫秒）",
                    "default": 30000
                }
            },
            "required": ["url"]
        }
    },
    {
        "name": "interactive_debugger",
        "description": "交互式 Python 调试器（pdb）。启动后保持进程存活，可逐步执行代码、检查变量、设置断点。适用于排查复杂的运行时 Bug，当代码阅读和 print 调试无法定位问题时使用。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["start", "command", "status", "stop"],
                    "description": "操作类型：start=启动调试会话，command=发送调试命令，status=查看会话状态，stop=终止会话"
                },
                "script_path": {
                    "type": "string",
                    "description": "要调试的 Python 脚本路径（action=start 时必填）"
                },
                "breakpoint_line": {
                    "type": "integer",
                    "description": "断点行号（action=start 时可选）"
                },
                "breakpoint_func": {
                    "type": "string",
                    "description": "断点函数名（action=start 时可选，与 breakpoint_line 二选一）"
                },
                "cmd": {
                    "type": "string",
                    "description": "pdb 调试命令（action=command 时必填，如 step/next/continue/p 变量名/where/list）"
                },
                "work_dir": {
                    "type": "string",
                    "description": "工作目录"
                },
                "session_id": {
                    "type": "string",
                    "description": "调试会话标识（默认 default）",
                    "default": "default"
                },
                "timeout": {
                    "type": "integer",
                    "description": "命令超时时间（秒）",
                    "default": 15
                }
            },
            "required": ["action"]
        }
    }
]


# ============================================================================
# 工具路由映射 - 懒加载避免循环导入
# ============================================================================

def _get_tool_function(name: str):
    """懒加载工具函数，避免模块级循环导入"""
    if name == "bash":
        from bash_executor import execute_bash
        return execute_bash
    elif name == "file_edit":
        from file_editor import edit_file
        return edit_file
    elif name == "file_read":
        from file_read_tool import read_file
        return read_file
    elif name == "glob":
        from glob_tool import glob_search
        return glob_search
    elif name == "grep":
        from grep_tool import grep_search
        return grep_search
    elif name == "browser_vision":
        from browser_vision_tool import execute_browser_vision
        return execute_browser_vision
    elif name == "interactive_debugger":
        from interactive_debugger_tool import execute_interactive_debugger
        return execute_interactive_debugger
    return None


# ============================================================================
# 执行路由函数
# ============================================================================

def execute_tool(name: str, args: Dict[str, Any]) -> str:
    """
    执行指定的工具函数

    当大模型决定调用某个工具时，此函数通过名字反射/分发到对应的 Python 函数，
    并捕获执行过程中的异常（Exception）转化为字符串返回。

    Args:
        name: 工具名称（如 "bash", "file_edit" 等）
        args: 工具参数字典

    Returns:
        str: 工具执行结果的字符串表示。
             如果执行失败，返回 "错误: ..." 格式的字符串。
    """
    try:
        func = _get_tool_function(name)
        if func is None:
            return f"错误: 未知工具 '{name}'"

        result = func(**args)

        if isinstance(result, dict):
            return json.dumps(result, ensure_ascii=False, indent=2)
        elif isinstance(result, list):
            return json.dumps(result, ensure_ascii=False, indent=2)
        elif hasattr(result, '__dataclass_fields__'):
            return _dataclass_to_string(result, name)
        else:
            return str(result)

    except TypeError as e:
        tb = traceback.format_exc()
        logger.error(f"工具 '{name}' 参数错误: {e}\n{tb}")
        return f"错误: 工具 '{name}' 参数不匹配 - {str(e)}"
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"工具 '{name}' 执行异常: {e}\n{tb}")
        return f"错误: {str(e)}"


def _dataclass_to_string(result, tool_name: str) -> str:
    """将 dataclass 结果转换为有意义的字符串"""
    if tool_name == "bash":
        if result.blocked:
            return f"[安全拦截] {result.block_reason}"
        elif result.interrupted:
            return f"[超时中断] {result.stdout}"
        elif result.exit_code != 0:
            return f"{result.stdout}\n{result.stderr}".strip() or f"退出码: {result.exit_code}"
        else:
            return result.stdout or "(执行成功)"

    elif tool_name == "file_edit":
        if result.success:
            msg = f"已{'创建' if result.is_new_file else '更新'}文件: {result.file_path}"
            if result.diff_patch:
                msg += f"\n变更:\n{result.diff_patch[:1000]}"
            return msg
        else:
            return f"编辑失败: {result.error}"

    elif tool_name == "file_read":
        if result.error:
            return f"读取失败: {result.error}"
        meta = f"[文件 | 第{result.start_line}-{result.end_line}行/共{result.total_lines}行]"
        if result.truncated:
            meta += " [截断]"
        return f"{meta}\n{result.content}"

    elif tool_name == "glob":
        if result.error:
            return f"搜索失败: {result.error}"
        elif not result.files:
            return "未找到匹配的文件"
        else:
            lines = [f"匹配结果 ({result.total_matches} 个):"]
            for f in result.files:
                lines.append(f"  {f}")
            if result.truncated:
                lines.append(f"  ... (仅显示前 {len(result.files)} 个)")
            return "\n".join(lines)

    elif tool_name == "grep":
        if result.error and not result.matches:
            return f"搜索失败: {result.error}"
        elif not result.matches:
            return "未找到匹配的内容"
        else:
            lines = [f"搜索结果 ({result.total_matches} 行匹配):"]
            for m in result.matches:
                lines.append(f"  {m.file_path}:{m.line_number}: {m.line_text}")
            if result.truncated:
                lines.append(f"  ... (仅显示前 {len(result.matches)} 行)")
            return "\n".join(lines)

    return str(result)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    print("=" * 60)
    print("Eruitah 工具注册表")
    print("=" * 60)
    print(f"注册的工具数量: {len(tools)}")
    for tool in tools:
        name = tool["name"]
        params = list(tool["parameters"]["properties"].keys())
        required = tool["parameters"].get("required", [])
        print(f"  {name}: params={params}, required={required}")

    print(f"\n--- 执行测试 ---")
    result = execute_tool("bash", {"command": "echo 'Hello from tool_registry!'"})
    print(f"bash: {result}")
