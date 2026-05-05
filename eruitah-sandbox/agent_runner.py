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
from memory_manager import (
    ConversationMemoryManager,
    estimate_tokens,
    get_summary_store,
)
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
    execute_dispatch_subtasks,
    DISPATCH_SUBTASKS_TOOL_DEFINITION_OPENAI,
    DISPATCH_SUBTASKS_TOOL_DEFINITION_ANTHROPIC,
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
from rewind_system import get_rewind_system
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
from mcp_client import (
    execute_mcp_manager,
    MCP_TOOL_DEFINITION_OPENAI,
    MCP_TOOL_DEFINITION_ANTHROPIC,
)
from auto_test_tool import (
    execute_auto_test,
    AUTO_TEST_TOOL_DEFINITION_OPENAI,
    AUTO_TEST_TOOL_DEFINITION_ANTHROPIC,
)
from memory_store import (
    search_memory as memory_search,
    record_learning as memory_record,
    init_memory_store,
    load_all_memory_files,
)

logger = logging.getLogger(__name__)

MAX_TURNS = 30


class StateBlackboard:
    """
    动态锚点记忆 (Dynamic State Anchoring)
    
    解决问题：大模型滑动窗口裁剪导致"失忆"
    原理：提取核心状态，钉在每次请求的最前面，确保不可被裁剪遗忘
    """
    
    def __init__(self):
        self.current_goal = ""
        self.active_files = set()
        self.key_decisions = []
        self.error_history = []
        self.work_dir = ""
    
    def update_from_messages(self, messages: list, work_dir: str = ""):
        if work_dir:
            self.work_dir = work_dir
        
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            
            if role == "user" and content and not self.current_goal:
                self.current_goal = content[:500]
            
            if role == "assistant":
                tool_calls = msg.get("tool_calls", [])
                for tc in tool_calls:
                    if isinstance(tc, dict):
                        fn = tc.get("function", tc)
                        if isinstance(fn, dict):
                            name = fn.get("name", "")
                            args_str = fn.get("arguments", "{}")
                            try:
                                args = json.loads(args_str) if isinstance(args_str, str) else args_str
                            except (json.JSONDecodeError, TypeError):
                                args = {}
                            
                            if name in ("file_edit", "file_read", "file_write"):
                                fp = args.get("file_path", "")
                                if fp:
                                    self.active_files.add(fp)
                                    if len(self.active_files) > 20:
                                        self.active_files = set(list(self.active_files)[-15:])
                            
                            if name == "bash" and args.get("command", ""):
                                cmd = args["command"][:200]
                                if any(kw in cmd for kw in ["mkdir", "touch", "cp ", "mv "]):
                                    self.key_decisions.append(f"执行: {cmd}")
                                    if len(self.key_decisions) > 10:
                                        self.key_decisions = self.key_decisions[-8:]
            
            if role == "tool" and content:
                content_str = str(content)
                if "error" in content_str.lower() or "失败" in content_str:
                    err_summary = content_str[:200]
                    self.error_history.append(err_summary)
                    if len(self.error_history) > 5:
                        self.error_history = self.error_history[-3:]
    
    def inject_anchor(self, messages: list, provider: str) -> list:
        if not self.current_goal and not self.active_files:
            return messages
        
        parts = ["【系统强制状态备忘录 - 绝对不可遗忘】"]
        
        if self.current_goal:
            parts.append(f"🎯 当前核心任务: {self.current_goal}")
        
        if self.active_files:
            files_str = ", ".join(sorted(self.active_files))
            parts.append(f"📂 正在操作的文件: [{files_str}]")
        
        if self.work_dir:
            parts.append(f"📁 工作目录: {self.work_dir}")
        
        if self.key_decisions:
            parts.append("🔑 关键决策:")
            for d in self.key_decisions[-5:]:
                parts.append(f"  - {d}")
        
        if self.error_history:
            parts.append("⚠️ 近期错误记录:")
            for e in self.error_history[-3:]:
                parts.append(f"  - {e}")
        
        parts.append("请始终基于上述目标和文件上下文进行思考，不要遗忘任务目标！")
        
        anchor_text = "\n".join(parts)
        
        if provider == "anthropic":
            return messages
        
        has_system = messages and messages[0].get("role") == "system"
        if has_system:
            existing = messages[0]["content"]
            if "【系统强制状态备忘录" in existing:
                import re as _re
                existing = _re.sub(
                    r"【系统强制状态备忘录.*?请始终基于上述目标.*?】",
                    "",
                    existing,
                    flags=_re.DOTALL,
                ).strip()
            messages[0]["content"] = existing + "\n\n" + anchor_text
            return messages
        else:
            return [{"role": "system", "content": anchor_text}] + messages

BASE_SYSTEM_PROMPT = """你是一个受限沙盒中的「任务型 AI 编码智能体」，名为 Eruitah。
你的生命周期严格绑定于用户当前下发的【单一任务】。你没有系统级的上下文管理权限。

# 🛠️ 可用工具

1. file_edit - 创建或编辑文件（必须使用此工具来写代码文件！）
2. bash - 执行 shell 命令（编译、运行、测试等）
3. file_read - 读取文件内容（支持行号范围）
4. glob - 文件模式匹配搜索（用 ** 递归搜索子目录，如 'src/**/*.py'）
5. grep - 正则表达式代码搜索
6. semantic_search - 语义代码搜索（基于 AST，比 grep 更精准）
7. lsp_tool - LSP 语言服务器（查找定义、引用、文件大纲）
8. git_tool - Git 版本控制（查看状态、差异、日志、提交）
9. auto_test - 自动化测试（scan_and_test 可递归扫描目录下所有代码文件）
10. read_project_memory - 搜索项目记忆库（查找以前踩过的坑和解决方案）
11. record_learning - 记录经验教训（成功修复 Bug 后，用一句话总结经验写入记忆库）
12. dispatch_subtasks - 🚀 子任务并发派发（多智能体协同！将任务拆分为多个子任务并发执行）

# 🚀 多智能体协同 (dispatch_subtasks)

当你遇到需要多线并行的复杂任务时，请不要自己一步步串行做！使用 dispatch_subtasks 工具并发执行：
- 同时搜索多个文档/网页 → search 类型子任务
- 编译代码的同时搜索依赖文档 → compile + search 并发
- 并行测试多个文件 → 多个 test 类型子任务
- 同时读取多个大文件 → 多个 read 类型子任务

示例调用：
dispatch_subtasks(subtasks=[
  {"id": "search_muduo", "type": "search", "query": "muduo TCP server example"},
  {"id": "compile_code", "type": "compile", "command": "make"},
  {"id": "read_config", "type": "read", "file_path": "CMakeLists.txt"}
])

系统会自动为需要沙盒的子任务分配独立工作区（WarmPool 预热池），并发执行并汇总结果。
每个子任务有 30 秒超时保护，卡死的子任务会被自动斩断。

# ⚠️ 任务执行与边界规范（严格遵守）

## 1. 任务的原子性 (Atomicity)
- 每次用户下发的需求，都是一个独立的「任务」。你只需专注于当前任务所需的代码修改、文件读写和终端测试。
- 绝对禁止越权修改与当前任务无关的底层基础设施代码。

## 2. 上帝权限隔离 (System Commands Isolation)
- 任务的【快照备份 (Checkpoint)】和【物理回滚 (Rollback)】由外部的"系统网关"在后台自动管理，你完全不知道它们的存在。
- 你不需要、也绝对不允许尝试使用任何工具去"创建检查点"、"读取历史快照"或"还原文件"。
- 如果你发现代码被改得一塌糊涂、彻底无法自愈，请不要自己尝试删除文件来回退！你只需直接向用户报告错误，等待人类用户从外部触发物理回滚。

## 3. 验证与交付规范 (Verification Policy)
- 编写代码后，优先使用直接运行（如 python x.py 或编译执行），通过 print 输出结果来验证正确性。
- 仅当修改核心复杂算法逻辑（如红黑树插入、复杂正则匹配），或用户明确要求时，才使用 pytest 框架。
- 如果 pytest 连续两次执行失败，立刻退回到使用 print() 进行快速验证。绝对不要在测试框架本身上浪费超过 2 轮迭代。

## 4. 自愈机制 (Auto-Healing)
- 如果终端执行报错，允许你在当前任务上下文中进行最多 3 次的尝试修改。超过 3 次请停止尝试并报告错误。

## 5. 记忆系统 (Memory System)
- 遇到 Bug 时，先调用 read_project_memory 搜索是否有类似的历史经验。
- 成功修复 Bug 并验证通过后，必须调用 record_learning 记录经验，格式：record_learning(category="Bug修复", lesson="一句话总结", related_files=["相关文件路径"])
- 记忆会自动写入 .agent_memory/learnings.md 并 Git 提交，永久保存。

## 5. 基本操作规则
- 必须使用 file_edit 工具来创建/修改文件，不要只在回复中输出代码！
- 创建新文件时，search_text 设为空字符串即可
- 先理解需求，再动手编码
- 修改文件前先读取文件内容
- 每次只做一步操作，逐步推进任务

示例用法：
- 创建新文件 main.py: file_edit(file_path="main.py", search_text="", replace_text="# Python code...")
- 修改文件: file_edit(file_path="main.py", search_text="old code", replace_text="new code")
- 递归搜索文件: glob(pattern="src/**/*.py") 或 glob(pattern="monopoly_game/**/*.*")

📝 备用方案：如果工具调用失败，你也可以直接在回复中使用 Markdown 代码块：
```python filepath=文件名.py
# 你的代码
```
系统会自动识别并写入文件。
"""

# ============================================================================
# Markdown 正则拦截器 - 当 Function Calling 失败时的备用方案
# ============================================================================

MARKDOWN_FILE_PATTERN = re.compile(
    r'```(?:\w+)?\s*'
    r'(?:filepath|file|path)[:=]\s*["\']?([^\s"\']+)["\']?'
    r'\s*\n'
    r'(.*?)'
    r'\n```',
    re.DOTALL | re.IGNORECASE
)

MARKDOWN_FILE_PATTERN_V2 = re.compile(
    r'```(\w+)\s+'
    r'(["\']?)([^\s"\']+)\2'
    r'\s*\n'
    r'(.*?)'
    r'\n```',
    re.DOTALL
)

def parse_markdown_code_blocks(text: str) -> list[dict]:
    """
    从 Markdown 文本中解析文件代码块
    
    支持的格式：
    1. ```python filepath=main.py
    2. ```python file="main.py"
    3. ```python path:main.py
    4. ```python main.py
    
    Returns:
        [{"file_path": "main.py", "content": "...", "language": "python"}, ...]
    """
    results = []
    
    try:
        for match in MARKDOWN_FILE_PATTERN.finditer(text):
            try:
                file_path = match.group(1).strip()
                content = match.group(2)
                if file_path and content is not None:
                    results.append({
                        "file_path": file_path,
                        "content": content,
                        "language": "unknown",
                    })
            except (IndexError, AttributeError):
                continue
    except Exception as e:
        logger.warning(f"Markdown 代码块解析 (V1) 异常: {e}")
    
    try:
        for match in MARKDOWN_FILE_PATTERN_V2.finditer(text):
            try:
                language = match.group(1)
                file_path = match.group(3).strip()
                content = match.group(4)
                
                if file_path and content is not None and '.' in file_path and not file_path.startswith('http'):
                    if not any(r["file_path"] == file_path for r in results):
                        results.append({
                            "file_path": file_path,
                            "content": content,
                            "language": language,
                        })
            except (IndexError, AttributeError):
                continue
    except Exception as e:
        logger.warning(f"Markdown 代码块解析 (V2) 异常: {e}")
    
    return results


def parse_pseudo_tool_calls(text: str) -> list[dict]:
    """
    解析模型"幻觉"出的伪工具调用格式
    
    例如：
    ```python
    file_edit(file_path="player.py", search_text="", replace_text="class Player:...")
    ```
    
    Returns:
        [{"name": "file_edit", "args": {"file_path": "player.py", ...}}, ...]
    """
    import re
    results = []
    
    # 匹配 file_edit(file_path="xxx", search_text="xxx", replace_text="xxx")
    file_edit_pattern = r'file_edit\s*\(\s*file_path\s*=\s*["\']([^"\']+)["\']\s*,\s*search_text\s*=\s*["\']([^"\']*)["\']\s*,\s*replace_text\s*=\s*["\'](.+?)["\']\s*\)'
    
    for match in re.finditer(file_edit_pattern, text, re.DOTALL):
        file_path = match.group(1)
        search_text = match.group(2)
        replace_text = match.group(3)
        
        # 处理转义字符
        replace_text = replace_text.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"')
        
        results.append({
            "name": "file_edit",
            "args": {
                "file_path": file_path,
                "search_text": search_text,
                "replace_text": replace_text,
            }
        })
        logger.info(f"🔍 解析伪工具调用: file_edit(file_path={file_path})")
    
    # 匹配 bash(command="xxx")
    bash_pattern = r'bash\s*\(\s*command\s*=\s*["\']([^"\']+)["\']\s*\)'
    for match in re.finditer(bash_pattern, text):
        command = match.group(1)
        results.append({
            "name": "bash",
            "args": {"command": command}
        })
        logger.info(f"🔍 解析伪工具调用: bash(command={command[:50]}...)")
    
    # 🚨 新增：匹配 JSON 格式的工具调用（SiliconFlow 模型有时会把工具调用当作 JSON 文本返回）
    # 格式: "name": "file_edit" "arguments": {"file_path": "xxx", ...}
    json_tool_pattern = r'"name"\s*:\s*"([^"]+)"\s*"arguments"\s*:\s*\{([^}]+)\}'
    for match in re.finditer(json_tool_pattern, text):
        tool_name = match.group(1)
        args_str = match.group(2)
        
        if tool_name in ["file_edit", "bash", "file_read", "glob", "grep"]:
            try:
                # 尝试解析参数
                args = {}
                # 简单解析 "key": "value" 格式
                arg_pattern = r'"([^"]+)"\s*:\s*"([^"]*)"'
                for arg_match in re.finditer(arg_pattern, args_str):
                    args[arg_match.group(1)] = arg_match.group(2)
                
                if args:
                    results.append({
                        "name": tool_name,
                        "args": args
                    })
                    logger.info(f"🔍 解析 JSON 格式工具调用: {tool_name}({args})")
            except Exception as e:
                logger.warning(f"解析 JSON 工具调用失败: {e}")
    
    return results


def extract_first_file_from_markdown(text: str) -> Optional[dict]:
    """从 Markdown 文本中提取第一个文件代码块"""
    blocks = parse_markdown_code_blocks(text)
    return blocks[0] if blocks else None

def build_system_prompt(workspace_dir: str) -> str:
    base_prompt = BASE_SYSTEM_PROMPT

    init_memory_store(workspace_dir)

    memory_content = load_all_memory_files(workspace_dir)
    memory_section = ""
    if memory_content:
        memory_section = f"\n\n=== 📚 项目记忆库 (.agent_memory/) ===\n{memory_content}===================\n"

    project_rules = ""

    agent_md_path = os.path.join(workspace_dir, "AGENT.md")
    if os.path.exists(agent_md_path):
        try:
            with open(agent_md_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if content.strip():
                    project_rules = f"\n\n=== 🤖 项目团队规范 (AGENT.md) ===\n{content}\n===================\n"
        except Exception:
            pass

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

    return project_rules + custom_instructions + memory_section + base_prompt

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
                "description": (
                    "创建或编辑文件。【重要】必须提供 file_path 参数！\n"
                    "使用方法：\n"
                    "1. 创建新文件：file_path='文件名', search_text='', replace_text='文件内容'\n"
                    "2. 编辑文件：file_path='文件名', search_text='旧内容', replace_text='新内容'\n"
                    "示例：file_edit(file_path='hello.py', search_text='', replace_text='print(1)')"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "【必需】文件路径，如 'main.py' 或 'src/app.js'",
                        },
                        "search_text": {
                            "type": "string",
                            "description": "要查找的文本。创建新文件时必须设为空字符串 ''",
                        },
                        "replace_text": {
                            "type": "string",
                            "description": "【必需】要写入的新内容",
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
                "description": "文件模式匹配搜索。重要：使用 ** 递归搜索子目录，如 'monopoly_game/**/*.py' 会搜索所有子目录下的 Python 文件。单层搜索用 'monopoly_game/*.py'，递归搜索用 'monopoly_game/**/*.*'",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "pattern": {
                            "type": "string",
                            "description": "文件模式。单层: *.py, src/*.js；递归: **/*.py, src/**/*.ts, monopoly_game/**/*.*",
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
            DISPATCH_SUBTASKS_TOOL_DEFINITION_ANTHROPIC,
            DISTILL_TOOL_DEFINITION_ANTHROPIC,
            THESEUS_TOOL_DEFINITION_ANTHROPIC,
            COMPUTE_TOOL_DEFINITION_ANTHROPIC,
            LSP_TOOL_DEFINITION_ANTHROPIC,
            GIT_TOOL_DEFINITION_ANTHROPIC,
            NOTEBOOK_TOOL_DEFINITION_ANTHROPIC,
            MCP_TOOL_DEFINITION_ANTHROPIC,
            AUTO_TEST_TOOL_DEFINITION_ANTHROPIC,
            {
                "name": "read_project_memory",
                "description": "搜索项目记忆库，查找以前踩过的坑和解决方案。遇到 Bug 时先查记忆，避免重复踩坑。",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "搜索关键词，如 'pthread 链接失败' 或 'CMake 配置'",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "record_learning",
                "description": "记录经验教训到项目记忆库。成功修复 Bug 后必须调用此工具，用一句话总结经验。记忆会自动 Git 提交，永久保存。",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "description": "经验分类，如 'Bug修复', '性能优化', '配置技巧'",
                        },
                        "lesson": {
                            "type": "string",
                            "description": "一句话总结经验，如 'Muduo 库链接失败是因为 CMakeLists 漏了 pthread'",
                        },
                        "related_files": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "相关文件路径列表（可选）",
                        },
                    },
                    "required": ["category", "lesson"],
                },
            },
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
                    "description": (
                        "创建或编辑文件。【重要】必须提供 file_path 参数！\n"
                        "使用方法：\n"
                        "1. 创建新文件：file_path='文件名', search_text='', replace_text='文件内容'\n"
                        "2. 编辑文件：file_path='文件名', search_text='旧内容', replace_text='新内容'\n"
                        "示例：file_edit(file_path='hello.py', search_text='', replace_text='print(1)')"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "【必需】文件路径，如 'main.py' 或 'src/app.js'",
                            },
                            "search_text": {
                                "type": "string",
                                "description": "要查找的文本。创建新文件时必须设为空字符串 ''",
                            },
                            "replace_text": {
                                "type": "string",
                                "description": "【必需】要写入的新内容",
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
                    "description": "文件模式匹配搜索。重要：使用 ** 递归搜索子目录，如 'monopoly_game/**/*.py' 会搜索所有子目录下的 Python 文件。单层搜索用 'monopoly_game/*.py'，递归搜索用 'monopoly_game/**/*.*'",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pattern": {
                                "type": "string",
                                "description": "文件模式。单层: *.py, src/*.js；递归: **/*.py, src/**/*.ts, monopoly_game/**/*.*",
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
            DISPATCH_SUBTASKS_TOOL_DEFINITION_OPENAI,
            DISTILL_TOOL_DEFINITION_OPENAI,
            THESEUS_TOOL_DEFINITION_OPENAI,
            COMPUTE_TOOL_DEFINITION_OPENAI,
            LSP_TOOL_DEFINITION_OPENAI,
            GIT_TOOL_DEFINITION_OPENAI,
            NOTEBOOK_TOOL_DEFINITION_OPENAI,
            MCP_TOOL_DEFINITION_OPENAI,
            AUTO_TEST_TOOL_DEFINITION_OPENAI,
            {
                "type": "function",
                "function": {
                    "name": "read_project_memory",
                    "description": "搜索项目记忆库，查找以前踩过的坑和解决方案。遇到 Bug 时先查记忆，避免重复踩坑。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "搜索关键词，如 'pthread 链接失败' 或 'CMake 配置'",
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "record_learning",
                    "description": "记录经验教训到项目记忆库。成功修复 Bug 后必须调用此工具，用一句话总结经验。记忆会自动 Git 提交，永久保存。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "category": {
                                "type": "string",
                                "description": "经验分类，如 'Bug修复', '性能优化', '配置技巧'",
                            },
                            "lesson": {
                                "type": "string",
                                "description": "一句话总结经验，如 'Muduo 库链接失败是因为 CMakeLists 漏了 pthread'",
                            },
                            "related_files": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "相关文件路径列表（可选）",
                            },
                        },
                        "required": ["category", "lesson"],
                    },
                },
            },
        ] + get_dynamic_tool_schemas("openai")

def _auto_commit_worktree(
    work_dir: str,
    session_id: str,
    summary: str,
    model: Optional[str] = None,
    main_repo_dir: Optional[str] = None,
):
    try:
        from sandbox_manager import get_sandbox, _sandboxes
        repo_dir = main_repo_dir or work_dir
        abs_repo = os.path.abspath(repo_dir)
        if abs_repo not in _sandboxes:
            logger.debug(f"直通模式: 跳过 auto-commit (目录 {abs_repo} 不在 sandbox 管理中)")
            return
        sandbox = get_sandbox(repo_dir)
        sandbox.commit_agent_changes(session_id, summary, model_name=model or "unknown")
    except Exception as e:
        logger.warning(f"Git auto-commit 失败: {e}")


def _execute_tool_local(
    name: str,
    args: dict,
    work_dir: str,
    session_id: str = "",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    main_repo_dir: Optional[str] = None,
    auto_approve: bool = False,
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
            if is_dangerous and not auto_approve:
                return f"危险命令，需要用户确认: {command}", True, meta

            bash_result = execute_bash(command, work_dir, allow_warnings=auto_approve)
            
            if bash_result.needs_confirmation and not auto_approve:
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

            if not is_error and session_id:
                file_modifying_cmds = (
                    "sed", "awk", "cat >", "cat >>", "echo >", "echo >>",
                    "tee", "cp ", "mv ", "install ", "pip install",
                    "npm install", "curl -o", "wget -o",
                    "python -c", "python3 -c", "node -e",
                    "mkdir", "touch", "chmod", "chown",
                )
                cmd_lower = command.strip().lower()
                should_commit = any(kw in cmd_lower for kw in file_modifying_cmds)
                if should_commit:
                    _auto_commit_worktree(work_dir, session_id, f"bash: {command[:80]}", model, main_repo_dir)

            return result, is_error, meta

        elif name == "file_edit":
            file_path = args.get("file_path", "")
            search_text = args.get("search_text", "")
            replace_text = args.get("replace_text", "")

            if not file_path:
                return "文件路径不能为空", True, meta

            result, is_error = execute_file_edit(file_path, search_text, replace_text, work_dir)

            if not is_error and session_id:
                _auto_commit_worktree(work_dir, session_id, f"file_edit: {file_path}", model, main_repo_dir)

            return result, is_error, meta

        elif name == "file_read":
            file_path = args.get("file_path", "")
            start_line = args.get("start_line")
            end_line = args.get("end_line")

            if not file_path:
                return "文件路径不能为空", True, meta

            result, is_error = execute_file_read(file_path, start_line, end_line, work_dir)
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

        elif name == "dispatch_subtasks":
            subtasks = args.get("subtasks", [])
            if not subtasks:
                return "❌ subtasks 列表不能为空", True, meta
            result_str, is_error = execute_dispatch_subtasks(
                subtasks=subtasks,
                work_dir=work_dir,
                main_repo_dir=main_repo_dir,
            )
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

        elif name == "git_tool":
            args["workspace_dir"] = work_dir
            result_str, is_error = execute_git_tool(**args)
            return result_str, is_error, meta

        elif name == "notebook_tool":
            args["workspace_dir"] = work_dir
            result_str, is_error = execute_notebook_tool(**args)
            return result_str, is_error, meta

        elif name == "mcp_manager":
            action = args.get("action", "list_available")
            server_name = args.get("server_name", "")
            env_overrides = args.get("env_overrides")
            result_str, is_error = execute_mcp_manager(action, server_name, env_overrides)
            return result_str, is_error, meta

        elif name == "auto_test":
            action = args.get("action", "run")
            test_file = args.get("test_file", "")
            source_file = args.get("source_file", "")
            directory = args.get("directory", "")
            result_str, is_error = execute_auto_test(action, test_file, source_file, directory, work_dir)
            return result_str, is_error, meta

        elif name == "read_project_memory":
            query = args.get("query", "")
            if not query:
                return "搜索关键词不能为空", True, meta
            result_str = memory_search(query, work_dir)
            return result_str, False, meta

        elif name == "record_learning":
            category = args.get("category", "通用")
            lesson = args.get("lesson", "")
            related_files = args.get("related_files", [])
            if not lesson:
                return "经验内容不能为空", True, meta
            result_str = memory_record(category, lesson, work_dir, related_files)
            return result_str, False, meta

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
    initial_messages: Optional[list] = None,
    start_turn: int = 1,
    task_id: Optional[str] = None,
    main_repo_dir: Optional[str] = None,
    auto_approve: bool = False,
) -> Generator[Dict[str, Any], None, None]:
    """Agent 主循环"""
    if not task_id:
        task_id = f"task_{uuid.uuid4().hex[:8]}"

    session_id = task_id

    reset_budget(session_id)
    cost_tracker = reset_cost_tracker(session_id, limit_usd=5.0)
    rewind_system = get_rewind_system()
    rewind_system.load_checkpoints(session_id)

    blackboard = StateBlackboard()

    if initial_messages:
        messages = initial_messages.copy()
        if user_input:
            messages.append({"role": "user", "content": user_input})
        if task_id:
            task_data = None
            try:
                from task_manager import get_task_manager
                tm = get_task_manager()
                task_data = tm.load_task(task_id)
            except Exception:
                pass
            if task_data and task_data.get("blackboard"):
                bb = task_data["blackboard"]
                blackboard.current_goal = bb.get("current_goal", "")
                blackboard.active_files = set(bb.get("active_files", []))
                blackboard.key_decisions = bb.get("key_decisions", [])
                blackboard.error_history = bb.get("error_history", [])
                blackboard.work_dir = bb.get("work_dir", work_dir)
    else:
        messages = []
        system_prompt = build_system_prompt(work_dir)
        if provider == "anthropic":
            messages.append({"role": "user", "content": user_input})
        else:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ]

    rewind_system.create_checkpoint(session_id, 0, messages, f"任务开始前快照 [task={task_id}]")
    logger.info(f"📦 任务 {task_id} 开启，已创建任务前快照 (turn=0)")

    task_name = user_input[:50] + ("..." if len(user_input) > 50 else "") if user_input else f"任务 {task_id[:8]}"

    from task_manager import get_session_manager
    sm = get_session_manager()
    session = sm.get_or_create_session(
        task_id=task_id,
        first_prompt=user_input or task_name,
        work_dir=work_dir,
        existing_messages=messages.copy(),
    )
    task_id = session.id
    task_name = session.summary
    logger.info(f"📦 任务 {task_id} 已注册，物理快照已创建: {work_dir}")

    yield {"type": "task_started", "task_id": task_id, "task_name": task_name}

    summary_base_url = base_url if base_url else os.environ.get("OPENAI_BASE_URL")
    if summary_base_url and not summary_base_url.endswith("/v1"):
        summary_base_url = summary_base_url.rstrip("/") + "/v1"

    summary_api_key_to_use = api_key
    summary_base_url_to_use = summary_base_url
    summary_model_to_use = "mimo-v2.5-pro"

    memory_manager = ConversationMemoryManager(
        summary_api_key=summary_api_key_to_use,
        summary_model=summary_model_to_use,
        summary_base_url=summary_base_url_to_use,
    )

    consecutive_errors = 0
    MAX_CONSECUTIVE_ERRORS = 5

    for turn in range(start_turn, max_turns + 1):
        try:
            from main import check_stop_flag, clear_stop_flag
            if check_stop_flag(session_id):
                logger.info(f"🛑 检测到停止信号，终止 Agent 循环: session={session_id}")
                clear_stop_flag(session_id)
                yield {"type": "agent_status", "status": "IDLE"}
                yield {"type": "stopped", "data": "用户已停止 Agent 执行"}
                return
        except ImportError:
            pass

        yield {"type": "status", "data": f"Agent 正在思考... (第 {turn}/{max_turns} 轮)"}
        yield {"type": "agent_status", "status": "THINKING"}

        ok, msg = check_budget_exhausted(session_id)
        if not ok:
            yield {"type": "agent_status", "status": "IDLE"}
            yield {"type": "finish", "data": f"预算耗尽: {msg}"}
            break

        messages, is_compacted = memory_manager.check_and_compact(messages, turn_count=turn)
        if is_compacted:
            yield {
                "type": "context_compact",
                "data": {
                    "reason": f"弹性折叠触发 (轮数={turn}, 估算Token={memory_manager.stats.estimated_tokens})",
                    "summary_preview": memory_manager.stats.current_summary[:200] if memory_manager.stats.current_summary else "",
                    "remaining_messages": len(messages),
                },
            }

        rewind_system.create_checkpoint(session_id, turn, messages, f"第 {turn} 轮")

        blackboard.update_from_messages(messages, work_dir)
        injected_messages = blackboard.inject_anchor(messages, provider)

        tools = _get_tools_definition(provider)

        try:
            if provider == "anthropic":
                anchor_system = system_prompt
                if blackboard.current_goal or blackboard.active_files:
                    anchor_parts = ["【系统强制状态备忘录 - 绝对不可遗忘】"]
                    if blackboard.current_goal:
                        anchor_parts.append(f"🎯 当前核心任务: {blackboard.current_goal}")
                    if blackboard.active_files:
                        anchor_parts.append(f"📂 正在操作的文件: [{', '.join(sorted(blackboard.active_files))}]")
                    if blackboard.work_dir:
                        anchor_parts.append(f"📁 工作目录: {blackboard.work_dir}")
                    if blackboard.key_decisions:
                        anchor_parts.append("🔑 关键决策:")
                        for d in blackboard.key_decisions[-5:]:
                            anchor_parts.append(f"  - {d}")
                    anchor_parts.append("请始终基于上述目标和文件上下文进行思考，不要遗忘任务目标！")
                    anchor_system = system_prompt + "\n\n" + "\n".join(anchor_parts)
                text, tool_calls = _call_anthropic(
                    messages=injected_messages,
                    tools=tools,
                    api_key=api_key,
                    model=model,
                    base_url=base_url,
                    system_prompt=anchor_system,
                )
            else:
                text, tool_calls = _call_openai(
                    messages=injected_messages,
                    tools=tools,
                    api_key=api_key,
                    model=model,
                    base_url=base_url,
                )

            logger.info(f"🤖 LLM 返回: text 长度={len(text) if text else 0}, tool_calls 数量={len(tool_calls)}")
            if tool_calls:
                logger.info(f"🔧 工具调用: {[tc.get('name', 'unknown') for tc in tool_calls]}")
                file_related = any(tc.get('name', '') in ('file_edit', 'file_write', 'bash', 'theseus_rewrite') for tc in tool_calls)
                yield {"type": "agent_status", "status": "WRITING" if file_related else "THINKING"}

            # 🚨 检测乱码：如果文本主要是空格和引号，可能是模型崩溃
            if text and len(text) > 100:
                non_space_chars = len([c for c in text if c not in ' \t\n\r"\''])
                if non_space_chars < len(text) * 0.3:  # 有效字符少于 30%
                    logger.warning(f"⚠️ 检测到模型返回乱码，有效字符比例: {non_space_chars/len(text):.2%}")
                    # 添加一个提示让模型重试
                    messages.append({"role": "assistant", "content": text})
                    messages.append({
                        "role": "user", 
                        "content": "⚠️ 你的上一次回复格式异常，请重新组织语言并继续执行任务。如果需要创建或修改文件，请使用 file_edit 工具或 Markdown 代码块格式。"
                    })
                    continue

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

            # ==========================================================
            # 🦍 Markdown 降级调用 - 当大模型没有调用工具时
            # 检查文本中是否包含 Markdown 代码块，自动提取并写入文件
            # ==========================================================
            markdown_files_written = False
            if not tool_calls and text:
                markdown_files = parse_markdown_code_blocks(text)
                
                if markdown_files:
                    logger.info(f"🔥 检测到 Markdown 降级写入指令，找到 {len(markdown_files)} 个代码块")
                    
                    for mf in markdown_files:
                        file_path = mf["file_path"]
                        content = mf["content"]
                        
                        # 确保路径在沙盒目录下
                        if not file_path.startswith("/"):
                            file_path = os.path.join(work_dir, file_path)
                        
                        # 确保目标文件夹存在
                        dir_path = os.path.dirname(file_path)
                        if dir_path:
                            os.makedirs(dir_path, exist_ok=True)
                        
                        # 真正写入硬盘！
                        try:
                            with open(file_path, "w", encoding="utf-8") as f:
                                f.write(content)
                            
                            logger.info(f"✅ [Markdown 拦截成功] 已写入文件: {file_path}")
                            markdown_files_written = True
                            
                            yield {
                                "type": "tool_start",
                                "tool_name": "file_edit (markdown auto)",
                                "args": {"file_path": file_path},
                            }
                            yield {
                                "type": "tool_end",
                                "tool_name": "file_edit (markdown auto)",
                                "result": f"✅ 文件创建成功: {file_path}",
                                "is_error": False,
                            }
                            
                            # 刷新文件树
                            yield {
                                "type": "file_updated",
                                "file_name": os.path.relpath(file_path, work_dir),
                                "new_code": content,
                                "language": os.path.splitext(file_path)[1],
                            }
                            
                        except Exception as e:
                            logger.error(f"❌ [Markdown 拦截失败] 写入文件 {file_path} 时报错: {e}")
                            yield {
                                "type": "error",
                                "data": f"写入文件失败: {file_path} - {str(e)}",
                            }

            # 🚨 关键修复：如果 Markdown 降级成功写入文件，构造 tool_result 并继续循环
            if markdown_files_written:
                _auto_commit_worktree(work_dir, session_id, "markdown auto-write", model, main_repo_dir)
                # 将 assistant 消息加入 messages
                messages.append({"role": "assistant", "content": text})
                # 加入一个 tool_result 告诉 LLM 文件已写入
                messages.append({
                    "role": "user",
                    "content": f"✅ 已通过 Markdown 降级模式写入文件。请继续执行任务，如果还有更多文件需要创建或修改，请继续。"
                })
                logger.info("🔄 Markdown 降级成功，继续下一轮循环...")
                continue

            if not tool_calls:
                # 🚨 检查文本中是否包含代码块或工具调用关键字，但格式不正确
                if text and ('file_edit' in text or '```' in text or 'def ' in text or 'class ' in text):
                    logger.warning("⚠️ 检测到文本中可能包含代码或工具调用，但格式不正确")
                    messages.append({"role": "assistant", "content": text[:2000]})  # 截断避免太长
                    messages.append({
                        "role": "user",
                        "content": "⚠️ 你的回复中似乎包含代码或工具调用，但格式不正确。请使用以下格式之一：\n1. 使用 file_edit 工具：file_edit(file_path=\"文件名\", search_text=\"\", replace_text=\"内容\")\n2. 使用 Markdown 代码块：```python\\n# 代码\\n```\n请重新格式化你的回复并继续执行任务。"
                    })
                    continue
                
                yield {"type": "finish", "data": text or "任务完成"}
                break

            tool_results_for_api = []
            any_error = False
            error_logs = []

            for tc in tool_calls:
                name = tc.get("name", "unknown")
                args = tc.get("args", {})
                tc_id = tc.get("id", f"call_{hash(str(tc))}")
                
                if not isinstance(args, dict):
                    logger.warning(f"⚠️ 工具 {name} 的 args 不是字典: {type(args)}, 值: {args}")
                    args = {}
                
                # ==========================================================
                # 🛡️ 终极防线：提示词补偿机制 (Prompt Compensation)
                # 当大模型调用工具参数缺失时：
                # 1. 先尝试从文本中解析 Markdown 代码块
                # 2. 如果找到，自动执行文件操作
                # 3. 如果没找到，返回详细错误让大模型重试
                # ==========================================================
                if name == "file_edit" and not args.get("file_path"):
                    # 🦍 Markdown 降级调用：尝试从文本中解析代码块
                    markdown_file = extract_first_file_from_markdown(text or "")
                    
                    if markdown_file:
                        # 找到了 Markdown 代码块，自动转换为 file_edit 参数
                        logger.info(f"🔄 Markdown 降级调用成功: 从文本中提取到文件 {markdown_file['file_path']}")
                        args = {
                            "file_path": markdown_file["file_path"],
                            "search_text": "",
                            "replace_text": markdown_file["content"],
                        }
                        
                        yield {
                            "type": "tool_start",
                            "tool_name": "file_edit (from markdown)",
                            "args": args,
                        }
                        
                        result_str, is_error, tool_meta = _execute_tool_local(
                            name="file_edit",
                            args=args,
                            work_dir=work_dir,
                            session_id=session_id,
                            api_key=api_key,
                            model=model,
                            base_url=base_url,
                            main_repo_dir=main_repo_dir,
                            auto_approve=auto_approve,
                        )
                        
                        yield {
                            "type": "tool_end",
                            "tool_name": "file_edit (from markdown)",
                            "result": f"✅ Markdown 降级调用成功！\n{result_str}",
                            "is_error": is_error,
                        }
                        
                        # 添加到上下文
                        if provider == "anthropic":
                            tool_results_for_api.append({
                                "type": "tool_result",
                                "tool_use_id": tc_id,
                                "content": f"✅ Markdown 降级调用成功！\n{result_str}",
                                "is_error": is_error,
                            })
                        else:
                            tool_results_for_api.append({
                                "role": "tool",
                                "tool_call_id": tc_id,
                                "content": f"✅ Markdown 降级调用成功！\n{result_str}",
                            })
                        
                        continue
                    
                    # 没找到 Markdown，返回详细错误
                    error_msg = (
                        "🚨 严重错误：调用 file_edit 失败！\n"
                        f"原因：你输出的参数为空或缺少 file_path: {args}\n\n"
                        "【强制指令】：你必须严格按照以下 JSON 格式提供参数，绝对不允许为空！\n\n"
                        "正确的调用格式：\n"
                        "```json\n"
                        "{\n"
                        '  "file_path": "文件名.py",\n'
                        '  "search_text": "",\n'
                        '  "replace_text": "你的代码内容"\n'
                        "}\n"
                        "```\n\n"
                        "或者使用 Markdown 格式：\n"
                        "```python filepath=文件名.py\n"
                        "# 你的代码\n"
                        "```\n\n"
                        "请立即按上述格式重新调用 file_edit 工具！"
                    )
                    logger.error(f"🚨 file_edit 工具参数缺失, args: {args}")
                    
                    yield {
                        "type": "tool_start",
                        "tool_name": name,
                        "args": args,
                    }
                    yield {
                        "type": "tool_end",
                        "tool_name": name,
                        "result": error_msg,
                        "is_error": True,
                    }
                    
                    # 关键：将错误信息作为 tool_result 添加到上下文，让大模型看到并重试
                    if provider == "anthropic":
                        tool_results_for_api.append({
                            "type": "tool_result",
                            "tool_use_id": tc_id,
                            "content": error_msg,
                            "is_error": True,
                        })
                    else:
                        tool_results_for_api.append({
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": error_msg,
                        })
                    
                    any_error = True
                    error_logs.append(f"工具 [{name}] 参数缺失，已触发提示词补偿")
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
                    main_repo_dir=main_repo_dir,
                    auto_approve=auto_approve,
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
                    yield {"type": "agent_status", "status": "ERROR"}

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
                    conf = tool_meta["needs_confirmation"]
                    yield {
                        "type": "command_confirmation",
                        "data": {
                            "command": conf.get("command", ""),
                            "reason": conf.get("reason", ""),
                            "tool_call_id": tc.get("id", ""),
                            "pending_async": True,
                            "messages": messages.copy(),
                            "turn": turn,
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
                consecutive_errors += 1
                error_summary = "\n".join(error_logs)
                
                if len(error_summary) > 2000:
                    error_summary = error_summary[:2000] + "\n... [截断]"

                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    logger.error(f"🚨 连续 {consecutive_errors} 次错误，触发熔断！终止 Agent 循环。")
                    yield {"type": "agent_status", "status": "IDLE"}
                    yield {"type": "finish", "data": f"🚨 连续 {MAX_CONSECUTIVE_ERRORS} 次执行错误，已强制终止任务。请检查代码或调整策略后重试。"}
                    break

                healing_message = (
                    f"⚠️ 执行工具时发生错误 (连续第 {consecutive_errors} 次，最多允许 {MAX_CONSECUTIVE_ERRORS} 次):\n\n{error_summary}\n\n"
                    f"请分析以上错误原因，更换策略或修复参数后重试。"
                    f" 不要重复相同的操作。"
                )
                messages.append({"role": "user", "content": healing_message})
                yield {"type": "agent_status", "status": "THINKING"}
            else:
                consecutive_errors = 0

            if not next_turn(session_id):
                budget_status = get_budget_status(session_id)
                actual_turns = budget_status.get("turns", turn)
                actual_max = budget_status.get("max_turns", max_turns)
                yield {"type": "agent_status", "status": "IDLE"}
                yield {"type": "finish", "data": f"已达到最大轮数限制 ({actual_turns}/{actual_max} 轮)，任务自动结束。如需继续，请在对话框中输入新的指令。"}
                break

            if task_id:
                try:
                    from task_manager import get_task_manager
                    tm = get_task_manager()
                    tm.update_session_messages(
                        task_id=task_id,
                        messages=messages,
                        current_turn=turn,
                    )
                except Exception as e:
                    logger.debug(f"自动保存任务状态失败: {e}")

        except Exception as e:
            import traceback
            logger.error(f"Agent 循环异常:\n{traceback.format_exc()}")
            yield {"type": "agent_status", "status": "ERROR"}
            yield {"type": "error", "data": f"Agent 执行异常: {str(e)}"}
            break

    yield {"type": "status", "data": f"Agent 任务完成 (共 {turn-1} 轮)"}
    yield {"type": "agent_status", "status": "DONE"}
    yield {"type": "finish", "data": f"任务已完成 (共 {turn-1} 轮)"}

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
    max_retries: int = 3,
) -> tuple[str, list[dict]]:
    """
    调用 OpenAI 兼容 API (带主备双活 + 指数退避重试 + DashScope 终极防幻觉解析)
    
    主节点：用户指定的模型
    备用节点：FALLBACK_MODEL（当主节点限流时自动切换）
    """
    from openai import OpenAI, RateLimitError, APIConnectionError, APITimeoutError
    import json
    import time
    import os

    # 备用模型配置
    fallback_api_key = os.environ.get("FALLBACK_API_KEY", api_key)
    fallback_base_url = os.environ.get("FALLBACK_BASE_URL", base_url)
    fallback_model = os.environ.get("FALLBACK_MODEL", "qwen/qwen3-next-80b-a3b-instruct:free")

    def _make_request(client, model_name, attempt_label="主节点"):
        """内部请求函数"""
        return client.chat.completions.create(
            model=model_name,
            messages=messages,
            tools=tools,
            max_tokens=4096,
        )

    def _parse_response(response):
        """解析响应"""
        choice = response.choices[0]
        message = choice.message

        logger.info(f"📥 LLM 原始响应: content 存在={message.content is not None}, tool_calls={message.tool_calls}")

        text_parts = []
        tool_calls = []

        if message.content:
            text_parts.append(message.content)

        raw_tool_calls = getattr(message, 'tool_calls', None)

        # 🛡️ 终极防御墙：处理 DashScope 等国产模型的格式坍缩
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
                    if hasattr(tc, 'model_dump'):
                        tc_dict = tc.model_dump()
                    elif hasattr(tc, '__dict__'):
                        tc_dict = tc.__dict__
                    elif isinstance(tc, dict):
                        tc_dict = tc
                    else:
                        tc_dict = {}

                    tc_id = tc_dict.get('id', f"call_{hash(str(tc))}")
                    
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
                        except Exception as parse_err:
                            # 尝试修复不完整的 JSON
                            logger.warning(f"⚠️ 解析 arguments 失败: {parse_err}, 尝试修复...")
                            
                            fixed_args = args_raw
                            if not fixed_args.endswith('}'):
                                open_braces = fixed_args.count('{') - fixed_args.count('}')
                                open_brackets = fixed_args.count('[') - fixed_args.count(']')
                                missing = ']' * open_brackets + '}' * open_braces
                                fixed_args = fixed_args + missing
                            
                            quote_count = fixed_args.count('"') - fixed_args.count('\\"')
                            if quote_count % 2 == 1:
                                fixed_args = fixed_args + '"'
                            
                            try:
                                args_dict = json.loads(fixed_args)
                                logger.info(f"✅ JSON 修复成功: {args_dict}")
                            except Exception:
                                import re
                                fp_match = re.search(r'"file_path"\s*:\s*"([^"]+)"', args_raw)
                                if fp_match:
                                    args_dict = {"file_path": fp_match.group(1)}
                                    logger.info(f"✅ 提取到 file_path: {args_dict}")
                                else:
                                    args_dict = {}
                    elif isinstance(args_raw, dict):
                        args_dict = args_raw

                    if not args_dict and tc_name == "bash":
                        args_dict = {"command": str(args_raw)}

                except Exception as e:
                    logger.error(f"🚨 解析单个 ToolCall 失败: {e}, 数据: {tc}")
                    continue

                TOOL_NAME_ALIASES = {
                    "run_shell_command": "bash",
                    "execute_command": "bash",
                    "shell": "bash",
                    "run_command": "bash",
                    "execute_shell": "bash",
                    "cmd": "bash",
                    "terminal": "bash",
                    "write_file": "file_edit",
                    "create_file": "file_edit",
                    "edit_file": "file_edit",
                    "save_file": "file_edit",
                    "read_file": "file_read",
                    "get_file": "file_read",
                    "search": "grep",
                    "find": "glob",
                    "find_files": "glob",
                    "list_files": "glob",
                    "test": "auto_test",
                    "run_test": "auto_test",
                    "search_memory": "read_project_memory",
                    "query_memory": "read_project_memory",
                    "save_learning": "record_learning",
                    "write_learning": "record_learning",
                }

                VALID_TOOLS = {
                    "file_edit", "file_read", "bash", "glob", "grep",
                    "ask_user", "semantic_search", "meta_tool",
                    "speculative_execute", "swarm_communicate", "dispatch_subtasks",
                    "self_distill",
                    "theseus_rewrite", "compute_autonomy", "lsp_tool",
                    "git_tool", "notebook_tool", "mcp_tool",
                    "auto_test", "computer_use",
                    "read_project_memory", "record_learning",
                }

                if tc_name not in VALID_TOOLS:
                    if tc_name in TOOL_NAME_ALIASES:
                        original_name = tc_name
                        tc_name = TOOL_NAME_ALIASES[tc_name]
                        logger.info(f"🔄 工具名映射: {original_name} → {tc_name}")
                    else:
                        logger.warning(f"⚠️ 无效的工具名: {tc_name}, 尝试从参数推断...")
                        if "command" in args_dict:
                            tc_name = "bash"
                            logger.info(f"🔄 根据参数推断工具名: bash")
                        elif "file_path" in args_dict and ("content" in args_dict or "replace_text" in args_dict):
                            tc_name = "file_edit"
                            logger.info(f"🔄 根据参数推断工具名: file_edit")
                        elif "file_path" in args_dict:
                            tc_name = "file_read"
                            logger.info(f"🔄 根据参数推断工具名: file_read")
                        elif "pattern" in args_dict:
                            if "path" in args_dict:
                                tc_name = "grep"
                            else:
                                tc_name = "glob"
                            logger.info(f"🔄 根据参数推断工具名: {tc_name}")
                        elif "query" in args_dict and "category" not in args_dict:
                            tc_name = "read_project_memory"
                            logger.info(f"🔄 根据参数推断工具名: read_project_memory")
                        elif "lesson" in args_dict or "category" in args_dict:
                            tc_name = "record_learning"
                            logger.info(f"🔄 根据参数推断工具名: record_learning")
                        else:
                            logger.warning(f"⚠️ 无法推断工具名，忽略此工具调用")
                            continue

                if tc_name != "unknown_tool":
                    tool_calls.append({
                        "id": tc_id,
                        "name": tc_name,
                        "args": args_dict,
                    })

        # 终极补救：如果 tool_calls 为空，尝试从文本中解析伪工具调用
        if not tool_calls and text_parts:
            full_text = "\n".join(text_parts)
            pseudo_calls = parse_pseudo_tool_calls(full_text)
            if pseudo_calls:
                logger.info(f"🔧 从文本中解析出 {len(pseudo_calls)} 个伪工具调用")
                for pc in pseudo_calls:
                    tool_calls.append({
                        "id": f"pseudo_{hash(str(pc))}",
                        "name": pc["name"],
                        "args": pc["args"],
                    })

        return "\n".join(text_parts), tool_calls

    # ==========================================================
    # 主节点调用逻辑
    # ==========================================================
    client_kwargs = {}
    if api_key:
        client_kwargs["api_key"] = api_key
    if base_url:
        client_kwargs["base_url"] = base_url

    client = OpenAI(**client_kwargs)
    current_model = model or "gpt-4o"
    
    retry_delay = 2  # 初始等待 2 秒
    rate_limit_count = 0
    
    for attempt in range(max_retries):
        try:
            response = _make_request(client, current_model, "主节点")
            return _parse_response(response)
            
        except RateLimitError as e:
            rate_limit_count += 1
            logger.warning(f"🚨 主节点触发 429 限流 (尝试 {attempt+1}/{max_retries})")
            
            # 如果连续 2 次限流，切换到备用节点
            if rate_limit_count >= 2:
                logger.info("🔄 主节点连续限流，启动降级路由切换到备用节点...")
                time.sleep(0.5)
                
                try:
                    fallback_client = OpenAI(
                        api_key=fallback_api_key,
                        base_url=fallback_base_url,
                    )
                    logger.info(f"🔄 正在使用备用节点 {fallback_model} 抢救...")
                    response = _make_request(fallback_client, fallback_model, "备用节点")
                    logger.info("✅ 降级抢救成功！")
                    return _parse_response(response)
                    
                except Exception as fallback_error:
                    logger.error(f"❌ 备用节点也失败: {fallback_error}")
                    # 继续尝试主节点重试
            
            time.sleep(retry_delay)
            retry_delay *= 2
            
        except (APIConnectionError, APITimeoutError) as e:
            logger.warning(f"⚠️ 网络波动异常: {e}，等待 2 秒后重试...")
            time.sleep(2)
            
        except Exception as e:
            logger.error(f"❌ LLM API 调用异常: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
            else:
                return f"❌ LLM 服务不可用: {str(e)}", []
    
    # ==========================================================
    # 最后尝试备用节点
    # ==========================================================
    logger.warning("🚨 主节点彻底不可用，最后尝试备用节点...")
    try:
        fallback_client = OpenAI(
            api_key=fallback_api_key,
            base_url=fallback_base_url,
        )
        response = _make_request(fallback_client, fallback_model, "备用节点")
        logger.info("✅ 备用节点抢救成功！")
        return _parse_response(response)
    except Exception as e:
        logger.error(f"❌ 所有节点都不可用: {e}")
        return "❌ 大模型服务暂时不可用，请稍后重试", []

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
