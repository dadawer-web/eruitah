"""
Eruitah 智能编程沙盒 - 核心引擎 v4 (Agent Loop)

v4 完全重写: 对齐 Claude Code query.ts 的 runLoop 思想

核心架构:
┌─────────────────────────────────────────────────────────────────────┐
│  run_agent(user_input)  →  Generator[dict]                          │
│                                                                     │
│  ┌──────────┐    调用 LLM     ┌──────────────┐    yield event      │
│  │ messages │ ─────────────→  │  大模型回复   │ ─────────────→ 前端  │
│  └──────────┘                 └──────────────┘                     │
│       ↑                           │                                │
│       │                    有 Tool Call?                            │
│       │                     /         \\                            │
│       │                   是           否 (纯文本 → finish)          │
│       │                    │                                        │
│       │              执行 Python Tool                               │
│       │                    │                                        │
│       │              ┌─────┴─────┐                                  │
│       │              │ 成功/失败? │                                  │
│       │              └─────┬─────┘                                  │
│       │            成功 ↓     ↓ 失败(自愈!)                          │
│       │        追加 tool_result  追加错误消息作为 user 消息          │
│       │              ↓              ↓                              │
│       └──────────────┴──────────────┘  ← 回到循环顶部               │
│                                                                     │
│  最大 15 轮防止 Token 破产 + 死循环保护                              │
└─────────────────────────────────────────────────────────────────────┘

事件格式 (yield dict):
  {"type": "message", "content": "大模型的纯文本回复"}
  {"type": "tool_start", "tool_name": "bash", "args": {...}}
  {"type": "tool_end", "result": "..."}
  {"type": "status", "data": "Agent 正在思考..."}
  {"type": "error", "data": "..."}
  {"type": "finish", "data": "最终结果"}

自愈逻辑:
  工具执行抛出异常 → 不崩溃！
  将异常堆栈转为字符串 → 作为 user 消息喂回大模型
  大模型分析错误 → 更换策略或修复参数 → 重试

参考源码: claude-code-rev/src/query.ts (queryLoop 函数)
"""

import os
import json
import logging
import traceback
from typing import Generator, Optional, Any

logger = logging.getLogger(__name__)

# ============================================================================
# 常量定义
# ============================================================================

MAX_TURNS = 15

SYSTEM_PROMPT = """你是一个专业的编程助手，名为 Eruitah。

你可以使用以下工具来完成编程任务：

1. file_edit - 创建或编辑文件（必须使用此工具来写代码文件！）
2. bash - 执行 shell 命令（编译、运行、测试等）
3. file_read - 读取文件内容（支持行号范围）
4. glob - 文件模式匹配搜索
5. grep - 正则表达式代码搜索

⚠️ 重要规则：
- **必须使用 file_edit 工具来创建/修改文件，不要只在回复中输出代码！**
- 创建新文件时，search_text 设为空字符串即可
- 先理解需求，再动手编码
- 修改文件前先读取文件内容
- 遇到错误时分析原因并主动修复
- 每次只做一步操作，逐步推进任务

示例用法：
- 创建新文件 main.py: file_edit(file_path="main.py", search_text="", replace_text="# Python code...")
- 修改文件: file_edit(file_path="main.py", search_text="old code", replace_text="new code")
"""


# ============================================================================
# 工具注册表 - 内联定义，确保参数名与实际函数完全匹配
# ============================================================================

def _get_tools_definition(provider: str = "openai") -> list[dict]:
    """
    获取工具定义列表
    
    Args:
        provider: "openai" 或 "anthropic"
    
    Returns:
        工具定义列表
    """
    if provider == "anthropic":
        return [
            {
                "name": "bash",
                "description": "执行 shell 命令。用于编译代码、运行测试、查看文件等。",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "要执行的命令"},
                        "timeout_ms": {"type": "integer", "description": "超时时间（毫秒）", "default": 120000},
                        "work_dir": {"type": "string", "description": "工作目录"},
                    },
                    "required": ["command"],
                },
            },
            {
                "name": "file_edit",
                "description": "使用 SEARCH/REPLACE 模式编辑文件。",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "文件路径"},
                        "search_text": {"type": "string", "description": "要查找的文本"},
                        "replace_text": {"type": "string", "description": "替换为的文本"},
                        "replace_all": {"type": "boolean", "description": "是否替换所有匹配", "default": False},
                    },
                    "required": ["file_path", "search_text", "replace_text"],
                },
            },
            {
                "name": "file_read",
                "description": "读取文件内容，支持行号范围过滤。",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "文件路径"},
                        "start_line": {"type": "integer", "description": "起始行号（1-based）", "default": 1},
                        "end_line": {"type": "integer", "description": "结束行号"},
                        "work_dir": {"type": "string", "description": "工作目录"},
                    },
                    "required": ["file_path"],
                },
            },
            {
                "name": "glob",
                "description": "使用 glob 模式查找文件。",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "glob 模式，如 **/*.py"},
                        "work_dir": {"type": "string", "description": "工作目录"},
                    },
                    "required": ["pattern"],
                },
            },
            {
                "name": "grep",
                "description": "使用正则表达式搜索代码。",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "正则表达式模式"},
                        "work_dir": {"type": "string", "description": "工作目录"},
                        "file_pattern": {"type": "string", "description": "文件过滤模式，如 *.py"},
                        "case_insensitive": {"type": "boolean", "description": "是否忽略大小写", "default": False},
                    },
                    "required": ["pattern"],
                },
            },
        ]
    else:
        return [
            {
                "type": "function",
                "function": {
                    "name": "bash",
                    "description": "执行 shell 命令。用于编译代码、运行测试、查看文件等。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {"type": "string", "description": "要执行的命令"},
                            "timeout_ms": {"type": "integer", "description": "超时时间（毫秒）", "default": 120000},
                            "work_dir": {"type": "string", "description": "工作目录"},
                        },
                        "required": ["command"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "file_edit",
                    "description": "使用 SEARCH/REPLACE 模式编辑文件。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string", "description": "文件路径"},
                            "search_text": {"type": "string", "description": "要查找的文本"},
                            "replace_text": {"type": "string", "description": "替换为的文本"},
                            "replace_all": {"type": "boolean", "description": "是否替换所有匹配", "default": False},
                        },
                        "required": ["file_path", "search_text", "replace_text"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "file_read",
                    "description": "读取文件内容，支持行号范围过滤。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string", "description": "文件路径"},
                            "start_line": {"type": "integer", "description": "起始行号（1-based）", "default": 1},
                            "end_line": {"type": "integer", "description": "结束行号"},
                            "work_dir": {"type": "string", "description": "工作目录"},
                        },
                        "required": ["file_path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "glob",
                    "description": "使用 glob 模式查找文件。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pattern": {"type": "string", "description": "glob 模式，如 **/*.py"},
                            "work_dir": {"type": "string", "description": "工作目录"},
                        },
                        "required": ["pattern"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "grep",
                    "description": "使用正则表达式搜索代码。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pattern": {"type": "string", "description": "正则表达式模式"},
                            "work_dir": {"type": "string", "description": "工作目录"},
                            "file_pattern": {"type": "string", "description": "文件过滤模式，如 *.py"},
                            "case_insensitive": {"type": "boolean", "description": "是否忽略大小写", "default": False},
                        },
                        "required": ["pattern"],
                    },
                },
            },
        ]


# ============================================================================
# 工具执行器 - 直接调用实际函数，参数名完全匹配
# ============================================================================

def _execute_tool_local(name: str, args: dict, work_dir: str = ".") -> tuple[str, bool, dict]:
    """
    执行本地工具函数
    
    Args:
        name: 工具名称
        args: 工具参数（已与实际函数签名匹配）
        work_dir: 默认工作目录
    
    Returns:
        (result_string, is_error, extra_meta)
        - extra_meta: 额外元数据，如 file_updated 事件所需的新文件内容
    """
    meta = {}
    try:
        if name == "bash":
            from bash_executor import execute_bash
            result = execute_bash(
                command=args.get("command", ""),
                timeout_ms=args.get("timeout_ms", 120000),
                work_dir=args.get("work_dir", work_dir),
            )
            if result.blocked:
                return f"[安全拦截] {result.block_reason}", True, meta
            elif result.interrupted:
                return f"[超时] {result.stdout}", True, meta
            elif result.exit_code != 0:
                return f"{result.stdout}\n{result.stderr}".strip() or f"退出码: {result.exit_code}", True, meta
            else:
                return result.stdout or "(执行成功)", False, meta

        elif name == "file_edit":
            from file_editor import edit_file
            file_path = args.get("file_path", "")
            if file_path and not os.path.isabs(file_path):
                file_path = os.path.join(work_dir, file_path)

            result = edit_file(
                file_path=file_path,
                search_text=args.get("search_text", ""),
                replace_text=args.get("replace_text", ""),
                replace_all=args.get("replace_all", False),
            )

            if result.success:
                msg = f"已{'创建' if result.is_new_file else '更新'}文件: {result.file_path}"
                if result.diff_patch:
                    diff_preview = result.diff_patch[:1000]
                    if len(result.diff_patch) > 1000:
                        diff_preview += "\n... [diff 已截断]"
                    msg += f"\n变更:\n{diff_preview}"

                # 读取修改后的文件全内容，用于前端 Monaco Editor 实时展示
                try:
                    with open(result.file_path, 'r', encoding='utf-8', errors='replace') as f:
                        new_code = f.read()
                    ext = os.path.splitext(result.file_path)[1].lstrip('.')
                    meta["file_updated"] = {
                        "file_path": result.file_path,
                        "file_name": os.path.basename(result.file_path),
                        "new_code": new_code,
                        "language": ext,
                    }
                except Exception:
                    pass

                return msg, False, meta
            else:
                return f"编辑失败: {result.error}", True, meta

        elif name == "file_read":
            from file_read_tool import read_file
            file_path = args.get("file_path", "")
            if file_path and not os.path.isabs(file_path):
                file_path = os.path.join(work_dir, file_path)

            result = read_file(
                file_path=file_path,
                start_line=args.get("start_line", 1),
                end_line=args.get("end_line"),
                work_dir=args.get("work_dir", work_dir),
            )

            if result.error:
                return f"读取失败: {result.error}", True, meta

            content = result.content
            file_meta = f"[文件: {file_path} | 第{result.start_line}-{result.end_line}行/共{result.total_lines}行]"
            if result.truncated:
                file_meta += " [截断]"
            return f"{file_meta}\n{content}", False, meta

        elif name == "glob":
            from glob_tool import glob_search
            result = glob_search(
                pattern=args.get("pattern", "**/*"),
                work_dir=args.get("work_dir", work_dir),
            )

            if result.error:
                return f"搜索失败: {result.error}", True, meta
            elif not result.files:
                return f"未找到匹配 '{args.get('pattern')}' 的文件", False, meta
            else:
                lines = [f"匹配 '{args.get('pattern')}' ({result.total_matches} 个):"]
                for f in result.files:
                    lines.append(f"  {f}")
                if result.truncated:
                    lines.append(f"  ... (仅显示前 {len(result.files)} 个)")
                return "\n".join(lines), False, meta

        elif name == "grep":
            from grep_tool import grep_search
            result = grep_search(
                pattern=args.get("pattern", ""),
                work_dir=args.get("work_dir", work_dir),
                file_pattern=args.get("file_pattern"),
                case_insensitive=args.get("case_insensitive", False),
            )

            if result.error and not result.matches:
                return f"搜索失败: {result.error}", True, meta
            elif not result.matches:
                return f"未找到匹配 '{args.get('pattern')}' 的内容", False, meta
            else:
                lines = [f"搜索 '{args.get('pattern')}' ({result.total_matches} 行匹配):"]
                for m in result.matches:
                    lines.append(f"  {m.file_path}:{m.line_number}: {m.line_text}")
                if result.truncated:
                    lines.append(f"  ... (仅显示前 {len(result.matches)} 行)")
                return "\n".join(lines), False, meta

        else:
            return f"未知工具: {name}", True, meta

    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"工具 '{name}' 执行异常:\n{tb}")
        return f"工具执行异常 [{name}]: {str(e)}\n\n{tb[-1000:]}", True, meta


# ============================================================================
# 核心: run_agent() 生成器函数 - 自愈死循环
# ============================================================================

def run_agent(
    user_input: str,
    work_dir: str = ".",
    max_turns: int = MAX_TURNS,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    provider: str = "openai",
) -> Generator[dict, None, None]:
    """
    Agent 核心循环 - 对齐 Claude Code query.ts 的 queryLoop 思想
    
    这是一个生成器函数，通过 yield 实时推送事件给调用者（WebSocket/SSE）。
    
    循环流程:
    1. 初始化 messages (system + user)
    2. while turn < max_turns:
       a. 调用 LLM API (messages + tools)
       b. 如果返回纯文本 → yield message → break
       c. 如果有 Tool Call:
          - yield tool_start
          - 执行本地工具
          - 成功: 追加 tool_result 到 messages
          - 失败(异常): 将异常作为 user 消息喂回 LLM (自愈!)
          - yield tool_end
       d. 继续循环
    3. 超过 max_turns → yield error → 结束
    
    Args:
        user_input: 用户输入的任务描述
        work_dir: 工作目录（沙箱边界）
        max_turns: 最大循环轮数（防死循环+破产）
        api_key: API 密钥
        model: 模型名称
        base_url: API 基础 URL
        provider: "openai" 或 "anthropic"
    
    Yields:
        dict: 事件字典，格式如下:
        
        纯文本消息:
        {"type": "message", "content": "大模型回复的内容"}
        
        工具开始:
        {"type": "tool_start", "tool_name": "bash", "args": {"command": "ls"}}
        
        工具结束:
        {"type": "tool_end", "result": "执行结果...", "is_error": false}
        
        状态更新:
        {"type": "status", "data": "Agent 正在思考... (第 3 轮)"}
        
        错误:
        {"type": "error", "data": "错误信息..."}
        
        完成:
        {"type": "finish", "data": "最终结果"}
    """
    yield {"type": "status", "data": f"Agent 启动 (最大 {max_turns} 轮)"}

    # ------------------------------------------------------------------
    # 初始化消息列表
    # ------------------------------------------------------------------
    tools_def = _get_tools_definition(provider)

    if provider == "anthropic":
        messages = [{"role": "user", "content": user_input}]
    else:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_input},
        ]

    abs_work_dir = os.path.abspath(work_dir)
    os.makedirs(abs_work_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # 主循环 - 对应 TS 源码 queryLoop
    # ------------------------------------------------------------------
    for turn in range(1, max_turns + 1):
        yield {"type": "status", "data": f"Agent 正在思考... (第 {turn}/{max_turns} 轮)"}

        # --------------------------------------------------------------
        # Step 1: 调用 LLM API
        # --------------------------------------------------------------
        try:
            response_text, tool_calls = _call_llm(
                messages=messages,
                tools=tools_def,
                api_key=api_key,
                model=model,
                base_url=base_url,
                provider=provider,
            )
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"LLM API 调用失败 (第 {turn} 轮):\n{tb}")
            yield {"type": "error", "data": f"API 调用失败: {str(e)}"}
            return

        # --------------------------------------------------------------
        # Step 2: 处理大模型回复
        # --------------------------------------------------------------

        # Case A: 纯文本回复（没有工具调用）→ 任务完成
        if not tool_calls:
            if response_text.strip():
                yield {"type": "message", "content": response_text}
            yield {"type": "finish", "data": response_text}
            return

        # Case B: 有文本 + 工具调用 → 先推送文本
        if response_text.strip():
            yield {"type": "message", "content": response_text}

        # --------------------------------------------------------------
        # Step 3: 追加 assistant 消息（含工具调用声明）
        # --------------------------------------------------------------
        if provider == "anthropic":
            assistant_content = []
            if response_text.strip():
                assistant_content.append({"type": "text", "text": response_text})
            for tc in tool_calls:
                assistant_content.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["name"],
                    "input": tc["args"],
                })
            messages.append({"role": "assistant", "content": assistant_content})
        else:
            assistant_msg = {"role": "assistant", "content": response_text or None, "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": json.dumps(tc["args"], ensure_ascii=False)},
                }
                for tc in tool_calls
            ]}
            messages.append(assistant_msg)

        # 调试日志：显示工具调用
        if tool_calls:
            logger.info(f"Agent 决定调用 {len(tool_calls)} 个工具:")
            for tc in tool_calls:
                logger.info(f"  - {tc['name']}: {json.dumps(tc['args'], ensure_ascii=False)[:200]}")

        # --------------------------------------------------------------
        # Step 4: 逐个执行工具调用
        # --------------------------------------------------------------
        tool_results_for_api = []
        any_error = False

        for tc in tool_calls:
            tool_name = tc["name"]
            tool_args = tc["args"]

            # 通知前端: 开始执行工具
            yield {
                "type": "tool_start",
                "tool_name": tool_name,
                "args": tool_args,
            }

            # 执行本地工具
            result_str, is_error, tool_meta = _execute_tool_local(tool_name, tool_args, abs_work_dir)

            # 调试日志
            logger.info(f"工具执行完成: {tool_name}, is_error={is_error}, has_file_updated={'file_updated' in tool_meta}")

            # 通知前端: 工具执行结束
            yield {
                "type": "tool_end",
                "tool_name": tool_name,
                "result": result_str[:2000] if len(result_str) > 2000 else result_str,
                "is_error": is_error,
            }

            # 如果 file_edit 成功，yield file_updated 事件给前端 Monaco Editor
            if "file_updated" in tool_meta:
                file_info = tool_meta["file_updated"]
                
                logger.info(f"开始流式推送代码: {file_info['file_name']}, {len(file_info['new_code'])} 字符")
                
                # 流式推送代码内容 - 打字机效果
                new_code = file_info["new_code"]
                chunk_size = 50  # 每次推送的字符数
                
                for i in range(0, len(new_code), chunk_size):
                    chunk = new_code[i:i+chunk_size]
                    yield {
                        "type": "code_stream",
                        "content": chunk,
                    }
                
                logger.info(f"流式推送完成，发送 file_updated 事件")
                
                # 最后推送 file_updated 事件（用于保存到文件标签）
                yield {
                    "type": "file_updated",
                    "file_path": file_info["file_path"],
                    "file_name": file_info["file_name"],
                    "new_code": new_code,
                    "language": file_info["language"],
                }

            # 收集工具结果（追加到 messages）
            if provider == "anthropic":
                tool_results_for_api.append({
                    "type": "tool_result",
                    "tool_use_id": tc["id"],
                    "content": result_str,
                    "is_error": is_error,
                })
            else:
                tool_results_for_api.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result_str,
                })

            if is_error:
                any_error = True

        # --------------------------------------------------------------
        # Step 5: 自愈逻辑 - 对应 TS 源码中的错误恢复
        # --------------------------------------------------------------

        # 将工具结果追加到 messages
        if provider == "anthropic":
            messages.append({"role": "user", "content": tool_results_for_api})
        else:
            messages.extend(tool_results_for_api)

        # 🚨 关键: 如果有工具执行失败，追加自愈消息
        if any_error:
            error_summary = "\n".join(
                tr.get("content", "") for tr in tool_results_for_api
                if (tr.get("is_error") if isinstance(tr, dict) else False)
            )
            if len(error_summary) > 2000:
                error_summary = error_summary[:2000] + "\n... [截断]"

            healing_message = (
                f"⚠️ 执行工具时发生错误:\n\n{error_summary}\n\n"
                f"请分析以上错误原因，更换策略或修复参数后重试。"
                f" 不要重复相同的操作。"
            )

            if provider == "anthropic":
                messages.append({"role": "user", "content": healing_message})
            else:
                messages.append({"role": "user", "content": healing_message})

            yield {
                "type": "status",
                "data": f"检测到错误，Agent 正在尝试自愈... (第 {turn} 轮)",
            }
        else:
            yield {
                "type": "status",
                "data": f"工具执行成功，继续处理... (第 {turn} 轮)",
            }

    # 超过最大轮数
    yield {"type": "error", "data": f"已达到最大循环次数 ({max_turns} 轮)，强制终止。"}


# ============================================================================
# LLM API 调用层 - 支持 Anthropic 和 OpenAI 兼容接口
# ============================================================================

def _call_llm(
    messages: list[dict],
    tools: list[dict],
    api_key: Optional[str],
    model: Optional[str],
    base_url: Optional[str],
    provider: str,
) -> tuple[str, list[dict]]:
    """
    调用 LLM API
    
    Returns:
        (response_text, tool_calls)
        - response_text: 大模型纯文本回复
        - tool_calls: 工具调用列表 [{"id", "name", "args"}, ...]
    """
    if provider == "anthropic":
        return _call_anthropic(messages, tools, api_key, model, base_url)
    else:
        return _call_openai(messages, tools, api_key, model, base_url)


def _call_anthropic(
    messages: list[dict],
    tools: list[dict],
    api_key: Optional[str],
    model: Optional[str],
    base_url: Optional[str],
) -> tuple[str, list[dict]]:
    """调用 Anthropic Claude API"""
    import anthropic

    client_kwargs = {}
    if api_key:
        client_kwargs["api_key"] = api_key
    if base_url:
        client_kwargs["base_url"] = base_url

    client = anthropic.Anthropic(**client_kwargs)

    response = client.messages.create(
        model=model or "claude-sonnet-4-20250514",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=tools,
        messages=messages,
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
    api_key: Optional[str],
    model: Optional[str],
    base_url: Optional[str],
) -> tuple[str, list[dict]]:
    """调用 OpenAI 兼容 API"""
    from openai import OpenAI

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

    if hasattr(message, 'tool_calls') and message.tool_calls:
        for tc in message.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, TypeError):
                args = {}
            tool_calls.append({
                "id": tc.id,
                "name": tc.function.name,
                "args": args,
            })

    return "\n".join(text_parts), tool_calls


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    print("=" * 60)
    print("Eruitah Agent Engine v4 测试")
    print("=" * 60)

    test_input = "列出当前目录下的文件"
    print(f"\n测试输入: {test_input}")
    print(f"\n--- 事件流 ---")

    for event in run_agent(test_input, provider="openai"):
        event_type = event.get("type", "unknown")
        if event_type == "message":
            content = event.get("content", "")
            print(f"\n[MESSAGE] {content[:200]}...")
        elif event_type == "tool_start":
            print(f"\n[TOOL_START] {event.get('tool_name')}({event.get('args', {})})")
        elif event_type == "tool_end":
            result = event.get("result", "")
            print(f"[TOOL_END] {'ERROR' if event.get('is_error') else 'OK'}: {result[:150]}...")
        elif event_type == "status":
            print(f"[STATUS] {event.get('data', '')}")
        elif event_type == "finish":
            print(f"\n[FINISH] {event.get('data', '')[:200]}")
        elif event_type == "error":
            print(f"\n[ERROR] {event.get('data', '')}")
