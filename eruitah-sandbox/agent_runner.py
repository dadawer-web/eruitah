from typing import Optional, Dict, Any, Generator, List
import json
import uuid
import time
import os
import sys
import subprocess
import tempfile
import logging
import threading
import re
import asyncio
from pathlib import Path

from bash_executor import execute_bash
from file_editor import execute_file_edit
from file_read_tool import execute_file_read
from glob_tool import execute_glob
from grep_tool import execute_grep
from memory_manager import ConversationMemoryManager, estimate_tokens
from ask_user_tool import (
    register_question, resolve_question, cancel_all_questions,
    check_dangerous_command,
    ASK_USER_TOOL_DEFINITION_OPENAI,
    ASK_USER_TOOL_DEFINITION_ANTHROPIC,
)
from semantic_search_tool import (
    semantic_search,
    format_semantic_results,
    SEMANTIC_SEARCH_TOOL_DEFINITION_OPENAI,
    SEMANTIC_SEARCH_TOOL_DEFINITION_ANTHROPIC,
)
from computer_use_tool import (
    execute_computer_use,
    format_computer_use_result_for_anthropic,
    format_computer_use_result_for_openai,
    COMPUTER_USE_TOOL_DEFINITION_OPENAI,
    COMPUTER_USE_TOOL_DEFINITION_ANTHROPIC,
)
from meta_tool import (
    execute_meta_tool,
    execute_dynamic_tool,
    get_dynamic_tool_schemas,
    is_dynamic_tool,
    META_TOOL_DEFINITION_OPENAI,
    META_TOOL_DEFINITION_ANTHROPIC,
)
from shadow_sandbox import (
    execute_speculative,
    SPECULATIVE_TOOL_DEFINITION_OPENAI,
    SPECULATIVE_TOOL_DEFINITION_ANTHROPIC,
)
from agent_swarm import (
    execute_swarm_communicate,
    SWARM_TOOL_DEFINITION_OPENAI,
    SWARM_TOOL_DEFINITION_ANTHROPIC,
)
from self_distill import (
    execute_distill_tool,
    DISTILL_TOOL_DEFINITION_OPENAI,
    DISTILL_TOOL_DEFINITION_ANTHROPIC,
)
from theseus_rewrite import (
    execute_theseus_tool,
    THESEUS_TOOL_DEFINITION_OPENAI,
    THESEUS_TOOL_DEFINITION_ANTHROPIC,
)
from compute_autonomy import (
    execute_compute_tool,
    COMPUTE_TOOL_DEFINITION_OPENAI,
    COMPUTE_TOOL_DEFINITION_ANTHROPIC,
)
from token_budget import (
    check_output_length, check_budget_exhausted, consume_tokens, next_turn, reset_budget, get_budget_status,
)
from lsp_client import (
    execute_lsp_tool,
    LSP_TOOL_DEFINITION_OPENAI,
    LSP_TOOL_DEFINITION_ANTHROPIC,
)
from rewind_system import (
    execute_rewind_tool, get_rewind_system,
    REWIND_TOOL_DEFINITION_OPENAI,
    REWIND_TOOL_DEFINITION_ANTHROPIC,
)
from git_tool import (
    execute_git_tool,
    GIT_TOOL_DEFINITION_OPENAI,
    GIT_TOOL_DEFINITION_ANTHROPIC,
)
from notebook_tool import (
    execute_notebook_tool,
    NOTEBOOK_TOOL_DEFINITION_OPENAI,
    NOTEBOOK_TOOL_DEFINITION_ANTHROPIC,
)
from cost_guardrails import get_cost_tracker, reset_cost_tracker

logger = logging.getLogger(__name__)

MAX_TURNS = 15

BASE_SYSTEM_PROMPT = """你是一个专业的编程助手，名为 Eruitah。

你可以使用以下工具来完成编程任务：

1. file_edit - 创建或编辑文件（必须使用此工具来写代码文件！）
2. bash - 执行 shell 命令（编译、运行、测试等）
3. file_read - 读取文件内容（支持行号范围）
4. glob - 文件模式匹配搜索
5. grep - 正则表达式代码搜索
6. semantic_search - 语义代码搜索（基于 AST，比 grep 更精准）
7. computer_use - 控制虚拟桌面（截图、点击、输入）
8. meta_tool - 自我进化工具（创建新工具、热重载、扩展自己的能力！）
9. speculative_execute - 推测执行（同时启动多个影子沙盒并行尝试不同方案）
10. swarm_communicate - P2P 智能体网络通信（与其他 Agent 协同工作）
11. self_distill - 自我微调（轨迹收集、奖励建模、LoRA 蒸馏、模型切换）
12. theseus_rewrite - 忒修斯之船（核心自重构、C++ 重写、热切换）
13. compute_autonomy - 算力自治（云服务器扩缩容、成本控制）
14. lsp_tool - LSP 语言服务器（查找定义、引用、文件大纲）
15. rewind_tool - 时间机器（回退到之前的状态）
16. git_tool - Git 版本控制（查看状态、差异、日志、提交）
17. notebook_tool - Jupyter Notebook 原生手术刀（读取、编辑 Cell、添加 Cell）

⚠️ 重要规则：
- **必须使用 file_edit 工具来创建/修改文件，不要只在回复中输出代码！**
- 创建新文件时，search_text 设为空字符串即可
- 先理解需求，再动手编码
- 修改文件前先读取文件内容
- 遇到错误时分析原因并主动修复
- 每次只做一步操作，逐步推进任务
- 如果发现自己缺少某个工具能力，可以用 meta_tool 自我进化创建新工具！
- 遇到性能瓶颈时，可以用 theseus_rewrite 将 Python 模块重写为 C++
- 需要更多算力时，可以用 compute_autonomy 自动购买云服务器
- 代码分析时使用 lsp_tool 获得更精准的信息
- 修错代码时使用 rewind_tool 回退到之前的状态

示例用法：
- 创建新文件 main.py: file_edit(file_path="main.py", search_text="", replace_text="# Python code...")
- 修改文件: file_edit(file_path="main.py", search_text="old code", replace_text="new code")
- 查找定义: lsp_tool(action="find_definition", file_path="main.cpp", line=42, character=10)
- 回退: rewind_tool(action="rewind", session_id="session_001", steps=1)
"""

def build_system_prompt(workspace_dir: str) -> str:
    base_prompt = BASE_SYSTEM_PROMPT
    
    claude_md_path = os.path.join(workspace_dir, "CLAUDE.md")
    custom_instructions = ""
    if os.path.exists(claude_md_path):
        try:
            with open(claude_md_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if content.strip():
                    custom_instructions = f"\n\n=== 本项目的专属架构约束 (CLAUDE.md) ===\n{content}\n===================\n\n"
        except Exception:
            pass
    
    return custom_instructions + base_prompt

def _get_tools_definition(provider: str = "openai") -> list[dict]:
    """获取工具定义（根据不同提供商）"""
    if provider == "anthropic":
        return [
            {
                "name": "bash",
                "description": "执行 bash 命令",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "要执行的 bash 命令",
                        },
                    },
                    "required": ["command"],
                },
            },
            {
                "name": "file_edit",
                "description": "创建或编辑文件。使用 SEARCH/REPLACE 模式：查找文件中的特定文本并替换为新文本。如果要创建新文件，将 search_text 设为空字符串。",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "文件路径（必需）。可以是相对路径或绝对路径，例如 'src/main.py' 或 '/tmp/test.txt'",
                        },
                        "search_text": {
                            "type": "string",
                            "description": "要查找的文本。如果要创建新文件，请将此参数设为空字符串 ''",
                        },
                        "replace_text": {
                            "type": "string",
                            "description": "要替换为的新文本（必需）。如果是创建新文件，这里填写文件的全部内容",
                        },
                    },
                    "required": ["file_path", "replace_text"],
                },
            },
            {
                "name": "file_read",
                "description": "读取文件内容",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "文件路径",
                        },
                        "start_line": {
                            "type": "integer",
                            "description": "起始行号（可选）",
                        },
                        "end_line": {
                            "type": "integer",
                            "description": "结束行号（可选）",
                        },
                    },
                    "required": ["file_path"],
                },
            },
            {
                "name": "glob",
                "description": "文件模式匹配搜索",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "pattern": {
                            "type": "string",
                            "description": "文件模式（如 *.py, **/*.cpp）",
                        },
                    },
                    "required": ["pattern"],
                },
            },
            {
                "name": "grep",
                "description": "正则表达式代码搜索",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "pattern": {
                            "type": "string",
                            "description": "正则表达式",
                        },
                        "path": {
                            "type": "string",
                            "description": "搜索路径（可选）",
                        },
                    },
                    "required": ["pattern"],
                },
            },
            ASK_USER_TOOL_DEFINITION_ANTHROPIC,
            COMPUTER_USE_TOOL_DEFINITION_ANTHROPIC,
            SEMANTIC_SEARCH_TOOL_DEFINITION_ANTHROPIC,
            META_TOOL_DEFINITION_ANTHROPIC,
            SPECULATIVE_TOOL_DEFINITION_ANTHROPIC,
            SWARM_TOOL_DEFINITION_ANTHROPIC,
            DISTILL_TOOL_DEFINITION_ANTHROPIC,
            THESEUS_TOOL_DEFINITION_ANTHROPIC,
            COMPUTE_TOOL_DEFINITION_ANTHROPIC,
            LSP_TOOL_DEFINITION_ANTHROPIC,
            REWIND_TOOL_DEFINITION_ANTHROPIC,
            GIT_TOOL_DEFINITION_ANTHROPIC,
            NOTEBOOK_TOOL_DEFINITION_ANTHROPIC,
        ] + get_dynamic_tool_schemas("anthropic")
    else:
        return [
            {
                "type": "function",
                "function": {
                    "name": "bash",
                    "description": "执行 bash 命令",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "要执行的 bash 命令",
                            },
                        },
                        "required": ["command"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "file_edit",
                    "description": "创建或编辑文件。使用 SEARCH/REPLACE 模式：查找文件中的特定文本并替换为新文本。如果要创建新文件，将 search_text 设为空字符串。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "文件路径（必需）。可以是相对路径或绝对路径，例如 'src/main.py' 或 '/tmp/test.txt'",
                            },
                            "search_text": {
                                "type": "string",
                                "description": "要查找的文本。如果要创建新文件，请将此参数设为空字符串 ''",
                            },
                            "replace_text": {
                                "type": "string",
                                "description": "要替换为的新文本（必需）。如果是创建新文件，这里填写文件的全部内容",
                            },
                        },
                        "required": ["file_path", "replace_text"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "file_read",
                    "description": "读取文件内容",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "文件路径",
                            },
                            "start_line": {
                                "type": "integer",
                                "description": "起始行号（可选）",
                            },
                            "end_line": {
                                "type": "integer",
                                "description": "结束行号（可选）",
                            },
                        },
                        "required": ["file_path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "glob",
                    "description": "文件模式匹配搜索",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pattern": {
                                "type": "string",
                                "description": "文件模式（如 *.py, **/*.cpp）",
                            },
                        },
                        "required": ["pattern"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "grep",
                    "description": "正则表达式代码搜索",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pattern": {
                                "type": "string",
                                "description": "正则表达式",
                            },
                            "path": {
                                "type": "string",
                                "description": "搜索路径（可选）",
                            },
                        },
                        "required": ["pattern"],
                    },
                },
            },
            ASK_USER_TOOL_DEFINITION_OPENAI,
            COMPUTER_USE_TOOL_DEFINITION_OPENAI,
            SEMANTIC_SEARCH_TOOL_DEFINITION_OPENAI,
            META_TOOL_DEFINITION_OPENAI,
            SPECULATIVE_TOOL_DEFINITION_OPENAI,
            SWARM_TOOL_DEFINITION_OPENAI,
            DISTILL_TOOL_DEFINITION_OPENAI,
            THESEUS_TOOL_DEFINITION_OPENAI,
            COMPUTE_TOOL_DEFINITION_OPENAI,
            LSP_TOOL_DEFINITION_OPENAI,
            REWIND_TOOL_DEFINITION_OPENAI,
            GIT_TOOL_DEFINITION_OPENAI,
            NOTEBOOK_TOOL_DEFINITION_OPENAI,
        ] + get_dynamic_tool_schemas("openai")

def _execute_tool_local(
    name: str,
    args: dict,
    work_dir: str,
    session_id: str = "",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
) -> tuple[str, bool, dict]:
    """本地执行工具"""
    meta = {}
    
    # =======================================================
    # 🛡️ 终极防御墙：拦截大模型 JSON 幻觉与类型崩塌
    # =======================================================
    if not isinstance(args, dict):
        logger.warning(f"⚠️ 触发防幻觉拦截！期望 dict，实际收到 {type(args).__name__}: {args}")
        
        # 尝试抢救大模型的输出
        if isinstance(args, str):
            if name == "bash":
                # 如果是 bash 工具，大模型很可能直接吐了命令，我们帮它强行包成字典
                args = {"command": args}
            else:
                # 尝试二次解析 JSON
                try:
                    args = json.loads(args)
                    if not isinstance(args, dict):
                        args = {}
                except:
                    args = {}
        else:
            # 彻底烂掉的数据，直接给空字典，防止崩溃
            args = {}
    # =======================================================

    try:
        if name == "bash":
            command = args.get("command", "")
            if not command:
                return "命令不能为空", True, meta

            is_dangerous = check_dangerous_command(command)
            if is_dangerous:
                return f"危险命令，需要用户确认: {command}", True, meta

            bash_result = execute_bash(command, work_dir)
            
            if bash_result.needs_confirmation:
                meta["needs_confirmation"] = {
                    "command": bash_result.original_command,
                    "reason": bash_result.block_reason,
                }
                return f"需要用户授权: {bash_result.block_reason}", False, meta
            elif bash_result.blocked:
                result = f"命令被拦截: {bash_result.block_reason}"
                is_error = True
            elif bash_result.interrupted:
                result = f"命令超时 ({bash_result.elapsed_seconds:.1f}s)\n{bash_result.stdout}"
                is_error = True
            else:
                result_parts = []
                if bash_result.stdout:
                    result_parts.append(bash_result.stdout)
                if bash_result.stderr:
                    result_parts.append(f"[stderr]\n{bash_result.stderr}")
                result = "\n".join(result_parts) if result_parts else "命令执行成功（无输出）"
                is_error = bash_result.exit_code != 0
            
            result, truncated = check_output_length(result)
            if truncated:
                meta["truncated"] = True
            return result, is_error, meta

        elif name == "file_edit":
            file_path = args.get("file_path", "")
            search_text = args.get("search_text", "")
            replace_text = args.get("replace_text", "")

            if not file_path:
                return "文件路径不能为空", True, meta

            if session_id:
                rewind_system = get_rewind_system()
                rewind_system.add_file_snapshot(session_id, file_path, "edit")

            result, is_error = execute_file_edit(file_path, search_text, replace_text, work_dir)
            return result, is_error, meta

        elif name == "file_read":
            file_path = args.get("file_path", "")
            start_line = args.get("start_line")
            end_line = args.get("end_line")

            if not file_path:
                return "文件路径不能为空", True, meta

            result, is_error = execute_file_read(file_path, start_line, end_line)
            result, truncated = check_output_length(result)
            if truncated:
                meta["truncated"] = True
            return result, is_error, meta

        elif name == "glob":
            pattern = args.get("pattern", "")
            if not pattern:
                return "搜索模式不能为空", True, meta

            result, is_error = execute_glob(pattern, work_dir)
            result, truncated = check_output_length(result)
            if truncated:
                meta["truncated"] = True
            return result, is_error, meta

        elif name == "grep":
            pattern = args.get("pattern", "")
            path = args.get("path", work_dir)

            if not pattern:
                return "搜索模式不能为空", True, meta

            result, is_error = execute_grep(pattern, path)
            result, truncated = check_output_length(result)
            if truncated:
                meta["truncated"] = True
            return result, is_error, meta

        elif name == "ask_user":
            question = args.get("question", "")
            context = args.get("context", "")
            question_id = str(uuid.uuid4())[:8]

            meta["ask_user"] = {
                "question_id": question_id,
                "question": question,
                "context": context,
            }

            return f"[等待用户回答] {question}", False, meta

        elif name == "computer_use":
            action = args.get("action", "screenshot")
            cu_result = execute_computer_use(action, **args)

            if cu_result.success and cu_result.image_base64:
                meta["computer_use_image"] = {
                    "base64": cu_result.image_base64,
                    "action": cu_result.action,
                    "content": cu_result.content,
                }
                return f"[Computer Use] {cu_result.action}: {cu_result.content}", False, meta
            elif cu_result.success:
                return f"[Computer Use] {cu_result.action}: {cu_result.content}", False, meta
            else:
                return f"[Computer Use] 失败: {cu_result.error}", True, meta

        elif name == "semantic_search":
            query = args.get("query", "")
            kind = args.get("kind")
            search_file_path = args.get("file_path")
            parent = args.get("parent_name")
            search_lang = args.get("language")
            project_dir = args.get("project_dir", work_dir)

            result = semantic_search(
                query=query,
                kind=kind,
                file_path=search_file_path,
                parent_name=parent,
                language=search_lang,
                project_dir=project_dir,
            )
            formatted = format_semantic_results(result)
            is_err = not result.success
            return formatted, is_err, meta

        elif name == "meta_tool":
            action = args.get("action", "list")
            tool_name = args.get("tool_name", "")
            description = args.get("description", "")
            code = args.get("code", "")
            result_str, is_error = execute_meta_tool(action, tool_name, description, code)
            return result_str, is_error, meta

        elif name == "speculative_execute":
            task = args.get("task", "")
            strategies = args.get("strategies")
            max_shadows = args.get("max_shadows", 3)
            timeout = args.get("timeout", 300)
            result_str, is_error = execute_speculative(task, strategies, max_shadows, timeout, api_key, model, base_url)
            return result_str, is_error, meta

        elif name == "swarm_communicate":
            action = args.get("action", "list")
            target_agent = args.get("target_agent", "")
            message = args.get("message", "")
            task = args.get("task", "")
            result = args.get("result", "")
            result_str, is_error = execute_swarm_communicate(action, target_agent, message, task, result)
            return result_str, is_error, meta

        elif name == "self_distill":
            result_str, is_error = execute_distill_tool(**args)
            return result_str, is_error, meta

        elif name == "theseus_rewrite":
            result_str, is_error = execute_theseus_tool(**args)
            return result_str, is_error, meta

        elif name == "compute_autonomy":
            result_str, is_error = execute_compute_tool(**args)
            return result_str, is_error, meta

        elif name == "lsp_tool":
            result_str, is_error = execute_lsp_tool(**args)
            return result_str, is_error, meta

        elif name == "rewind_tool":
            result_str, is_error = execute_rewind_tool(**args)
            return result_str, is_error, meta

        elif name == "git_tool":
            args["workspace_dir"] = work_dir
            result_str, is_error = execute_git_tool(**args)
            return result_str, is_error, meta

        elif name == "notebook_tool":
            args["workspace_dir"] = work_dir
            result_str, is_error = execute_notebook_tool(**args)
            return result_str, is_error, meta

        elif is_dynamic_tool(name):
            result_str, is_error = execute_dynamic_tool(name, args)
            return result_str, is_error, meta

        else:
            return f"未知工具: {name}", True, meta

    except Exception as e:
        logger.error(f"工具执行异常 {name}: {e}")
        return f"工具执行异常: {str(e)}", True, meta

def run_agent(
    user_input: str,
    work_dir: str = ".",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    provider: str = "openai",
    max_turns: int = MAX_TURNS,
    session_id: Optional[str] = None,
) -> Generator[Dict[str, Any], None, None]:
    """Agent 主循环"""
    if not session_id:
        session_id = str(uuid.uuid4())

    reset_budget(session_id)
    cost_tracker = reset_cost_tracker(session_id, limit_usd=5.0)
    rewind_system = get_rewind_system()
    rewind_system.load_checkpoints(session_id)

    messages = []
    system_prompt = build_system_prompt(work_dir)
    if provider == "anthropic":
        messages.append({"role": "user", "content": user_input})
    else:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]

    summary_base_url = base_url if base_url else os.environ.get("OPENAI_BASE_URL")
    if summary_base_url and not summary_base_url.endswith("/v1"):
        summary_base_url = summary_base_url.rstrip("/") + "/v1"

    memory_manager = ConversationMemoryManager(
        summary_api_key=api_key,
        summary_model="qwen-turbo",
        summary_base_url=summary_base_url,
    )

    for turn in range(1, max_turns + 1):
        yield {"type": "status", "data": f"Agent 正在思考... (第 {turn}/{max_turns} 轮)"}

        ok, msg = check_budget_exhausted(session_id)
        if not ok:
            yield {"type": "error", "data": f"预算耗尽: {msg}"}
            break

        rewind_system.create_checkpoint(session_id, turn, messages, f"第 {turn} 轮")

        tools = _get_tools_definition(provider)

        try:
            if provider == "anthropic":
                text, tool_calls = _call_anthropic(
                    messages=messages,
                    tools=tools,
                    api_key=api_key,
                    model=model,
                    base_url=base_url,
                    system_prompt=system_prompt,
                )
            else:
                text, tool_calls = _call_openai(
                    messages=messages,
                    tools=tools,
                    api_key=api_key,
                    model=model,
                    base_url=base_url,
                )

            tokens = estimate_tokens(text)
            consume_tokens(session_id, tokens)
            
            try:
                turn_cost = cost_tracker.add_usage(
                    prompt_tokens=tokens,
                    completion_tokens=estimate_tokens(text),
                    model=model or "",
                )
                yield {
                    "type": "cost_update",
                    "data": cost_tracker.get_status(),
                }
            except Exception as cost_err:
                yield {"type": "error", "data": str(cost_err)}
                break

            if text:
                yield {"type": "assistant", "data": text}

            if not tool_calls:
                yield {"type": "finish", "data": text or "任务完成"}
                break

            tool_results_for_api = []
            any_error = False
            error_logs = []

            for tc in tool_calls:
                name = tc.get("name", "unknown")
                args = tc.get("args", {})
                
                if not isinstance(args, dict):
                    logger.warning(f"⚠️ 工具 {name} 的 args 不是字典: {type(args)}, 值: {args}")
                    args = {}
                
                if name == "file_edit" and not args.get("file_path"):
                    logger.error(f"🚨 file_edit 工具缺少 file_path 参数, args: {args}")
                    yield {
                        "type": "tool_start",
                        "tool_name": name,
                        "args": args,
                    }
                    yield {
                        "type": "tool_end",
                        "tool_name": name,
                        "result": "错误：file_edit 工具必须提供 file_path 参数",
                        "is_error": True,
                    }
                    continue

                yield {
                    "type": "tool_start",
                    "tool_name": name,
                    "args": args,
                }

                result_str, is_error, tool_meta = _execute_tool_local(
                    name=name,
                    args=args,
                    work_dir=work_dir,
                    session_id=session_id,
                    api_key=api_key,
                    model=model,
                    base_url=base_url,
                )

                yield {
                    "type": "tool_end",
                    "tool_name": name,
                    "result": result_str,
                    "is_error": is_error,
                }

                if name == "file_edit" and not is_error:
                    file_path = args.get("file_path", "")
                    if file_path:
                        try:
                            full_path = os.path.join(work_dir, file_path)
                            if os.path.exists(full_path):
                                with open(full_path, 'r', encoding='utf-8') as f:
                                    new_code = f.read()
                                yield {
                                    "type": "file_updated",
                                    "file_name": file_path,
                                    "new_code": new_code,
                                    "language": os.path.splitext(file_path)[1],
                                }
                        except Exception as e:
                            logger.error(f"读取更新后的文件失败: {e}")

                tokens = estimate_tokens(result_str)
                consume_tokens(session_id, tokens)

                if is_error:
                    any_error = True
                    error_logs.append(f"工具 [{name}] 报错: {result_str}")

                if "ask_user" in tool_meta:
                    yield {
                        "type": "ask_user",
                        "data": {
                            "question_id": tool_meta["ask_user"]["question_id"],
                            "question": tool_meta["ask_user"]["question"],
                            "context": tool_meta["ask_user"]["context"],
                        },
                    }
                    return

                if "needs_confirmation" in tool_meta:
                    yield {
                        "type": "command_confirmation",
                        "data": {
                            "command": tool_meta["needs_confirmation"]["command"],
                            "reason": tool_meta["needs_confirmation"]["reason"],
                        },
                    }
                    return

                if provider == "anthropic":
                    tool_result_content = result_str
                    if "computer_use_image" in tool_meta:
                        from computer_use_tool import format_computer_use_result_for_anthropic
                        cu_result = tool_meta["computer_use_image"]
                        from computer_use_tool import ComputerUseResult
                        cu_obj = ComputerUseResult(
                            success=True,
                            action=cu_result["action"],
                            content=cu_result["content"],
                            image_base64=cu_result["base64"],
                        )
                        tool_result_content = format_computer_use_result_for_anthropic(cu_obj)

                    tool_results_for_api.append({
                        "type": "tool_result",
                        "tool_use_id": tc["id"],
                        "content": tool_result_content,
                        "is_error": is_error,
                    })
                else:
                    tool_result_content = result_str
                    if "computer_use_image" in tool_meta:
                        from computer_use_tool import format_computer_use_result_for_openai
                        cu_result = tool_meta["computer_use_image"]
                        from computer_use_tool import ComputerUseResult
                        cu_obj = ComputerUseResult(
                            success=True,
                            action=cu_result["action"],
                            content=cu_result["content"],
                            image_base64=cu_result["base64"],
                        )
                        image_parts = format_computer_use_result_for_openai(cu_obj)
                        tool_result_content = json.dumps(image_parts, ensure_ascii=False)

                    tool_results_for_api.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": tool_result_content,
                    })

            # 只有在有工具调用结果时才添加到消息列表
            if tool_results_for_api:
                # 对于 OpenAI 格式，需要先添加 assistant 消息（带 tool_calls）
                if provider != "anthropic":
                    # 构造 assistant 消息
                    assistant_message = {
                        "role": "assistant",
                        "content": text if text else None,
                        "tool_calls": [
                            {
                                "id": tc["id"],
                                "type": "function",
                                "function": {
                                    "name": tc["name"],
                                    "arguments": json.dumps(tc["args"], ensure_ascii=False)
                                }
                            }
                            for tc in tool_calls
                        ]
                    }
                    messages.append(assistant_message)
                
                # 添加工具结果
                messages.extend(tool_results_for_api)

            if any_error:
                error_summary = "\n".join(error_logs)
                
                if len(error_summary) > 2000:
                    error_summary = error_summary[:2000] + "\n... [截断]"

                healing_message = (
                    f"⚠️ 执行工具时发生错误:\n\n{error_summary}\n\n"
                    f"请分析以上错误原因，更换策略或修复参数后重试。"
                    f" 不要重复相同的操作。"
                )
                messages.append({"role": "user", "content": healing_message})

            if not next_turn(session_id):
                yield {"type": "error", "data": "循环轮数超限"}
                break

        except Exception as e:
            import traceback
            logger.error(f"Agent 循环异常:\n{traceback.format_exc()}")
            yield {"type": "error", "data": f"Agent 执行异常: {str(e)}"}
            break

    yield {"type": "status", "data": f"Agent 任务完成 (共 {turn-1} 轮)"}

def _call_anthropic(
    messages: list[dict],
    tools: list[dict],
    api_key: Optional[str],
    model: Optional[str],
    base_url: Optional[str],
    system_prompt: str = "",
) -> tuple[str, list[dict]]:
    """调用 Anthropic Claude API"""
    import anthropic

    client_kwargs = {}
    if api_key:
        client_kwargs["api_key"] = api_key
    if base_url:
        client_kwargs["base_url"] = base_url

    client = anthropic.Anthropic(**client_kwargs)

    from prompt_caching import build_anthropic_cached_request
    cached_request = build_anthropic_cached_request(
        system_prompt=system_prompt,
        tools=tools,
        messages=messages,
    )

    cache_report = cached_request.pop("_cache_report", None)
    if cache_report and cache_report.has_break:
        logger.warning(f"⚠️ 缓存断层: {cache_report.reason}")
    elif cache_report:
        logger.info(
            f"💰 缓存前缀完整, 预估节省 {cache_report.cache_savings_estimate:.0f} tokens"
        )

    response = client.messages.create(
        model=model or "claude-sonnet-4-20250514",
        max_tokens=4096,
        system=cached_request["system"],
        tools=cached_request["tools"],
        messages=cached_request["messages"],
    )

    if hasattr(response, 'usage') and response.usage:
        cache_read = getattr(response.usage, 'cache_read_input_tokens', 0) or 0
        cache_creation = getattr(response.usage, 'cache_creation_input_tokens', 0) or 0
        if cache_read > 0 or cache_creation > 0:
            logger.info(
                f"📊 Prompt Cache: 读取 {cache_read} tokens, 创建 {cache_creation} tokens"
            )

    text_parts = []
    tool_calls = []

    for block in response.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use":
            tool_calls.append({
                "id": block.id,
                "name": block.name,
                "args": block.input if isinstance(block.input, dict) else {},
            })

    return "\n".join(text_parts), tool_calls

def _call_openai(
    messages: list[dict],
    tools: list[dict],
    api_key: str | None,
    model: str | None,
    base_url: str | None,
) -> tuple[str, list[dict]]:
    """调用 OpenAI 兼容 API (带 DashScope 终极防幻觉解析)"""
    from openai import OpenAI
    import json

    client_kwargs = {}
    if api_key:
        client_kwargs["api_key"] = api_key
    if base_url:
        client_kwargs["base_url"] = base_url

    client = OpenAI(**client_kwargs)

    response = client.chat.completions.create(
        model=model or "gpt-4o",
        messages=messages,
        tools=tools,
        max_tokens=4096,
    )

    choice = response.choices[0]
    message = choice.message

    text_parts = []
    tool_calls = []

    if message.content:
        text_parts.append(message.content)

    # ==========================================================
    # 🛡️ 终极防御墙：处理 DashScope 等国产模型的格式坍缩
    # ==========================================================
    raw_tool_calls = getattr(message, 'tool_calls', None)
    
    # 🚨 核心修复：如果大模型把整个 tool_calls 吐成了一个字符串！
    if isinstance(raw_tool_calls, str):
        try:
            raw_tool_calls = json.loads(raw_tool_calls)
        except Exception:
            logger.warning(f"⚠️ 无法解析的 tool_calls 字符串: {raw_tool_calls[:100]}")
            raw_tool_calls = []

    # 只有当它是真实的列表时，才开始遍历
    if isinstance(raw_tool_calls, list):
        for tc in raw_tool_calls:
            tc_name = "unknown_tool"
            args_dict = {}
            tc_id = "unknown_id"

            try:
                # 无论它是对象(Object)还是字典(Dict)，统统强转为字典
                if hasattr(tc, 'model_dump'):
                    tc_dict = tc.model_dump()
                elif hasattr(tc, '__dict__'):
                    tc_dict = tc.__dict__
                elif isinstance(tc, dict):
                    tc_dict = tc
                else:
                    tc_dict = {} # 单字符或者垃圾数据直接屏蔽

                tc_id = tc_dict.get('id', f"call_{hash(str(tc))}")
                
                # 提取 function
                func_obj = tc_dict.get('function', {})
                if isinstance(func_obj, dict):
                    tc_name = func_obj.get('name', 'unknown_tool')
                    args_raw = func_obj.get('arguments', '{}')
                else:
                    tc_name = getattr(func_obj, 'name', 'unknown_tool')
                    args_raw = getattr(func_obj, 'arguments', '{}')

                # 解析 arguments
                if isinstance(args_raw, str):
                    try:
                        args_dict = json.loads(args_raw)
                        if not isinstance(args_dict, dict):
                            args_dict = {}
                    except Exception:
                        args_dict = {}
                elif isinstance(args_raw, dict):
                    args_dict = args_raw

                # 强行抢救 bash
                if not args_dict and tc_name == "bash":
                    args_dict = {"command": str(args_raw)}

            except Exception as e:
                logger.error(f"🚨 解析单个 ToolCall 失败: {e}, 数据: {tc}")
                continue

            # 只有拿到合法工具名，才加入队列
            if tc_name != "unknown_tool":
                tool_calls.append({
                    "id": tc_id,
                    "name": tc_name,
                    "args": args_dict,
                })
    # ==========================================================

    return "\n".join(text_parts), tool_calls

def get_session_messages(session_id: str) -> list[dict]:
    """获取会话消息（用于回退工具）"""
    rewind_system = get_rewind_system()
    checkpoints = rewind_system.list_checkpoints(session_id)
    if not checkpoints:
        return []
    return checkpoints[-1].get("messages", [])

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Eruitah Agent")
    parser.add_argument("--input", type=str, required=True, help="用户输入")
    parser.add_argument("--work-dir", type=str, default=".", help="工作目录")
    parser.add_argument("--api-key", type=str, help="API 密钥")
    parser.add_argument("--model", type=str, help="模型名称")
    parser.add_argument("--base-url", type=str, help="API 基础 URL")
    parser.add_argument("--provider", type=str, default="openai", choices=["openai", "anthropic"])

    args = parser.parse_args()

    for event in run_agent(
        user_input=args.input,
        work_dir=args.work_dir,
        api_key=args.api_key,
        model=args.model,
        base_url=args.base_url,
        provider=args.provider,
    ):
        print(json.dumps(event, ensure_ascii=False))
