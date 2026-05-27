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
    semantic_search_code,
    SEMANTIC_SEARCH_CODE_TOOL_DEFINITION_OPENAI,
    SEMANTIC_SEARCH_CODE_TOOL_DEFINITION_ANTHROPIC,
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
    execute_coder_reviewer_swarm,
    SWARM_REVIEW_TOOL_DEFINITION_OPENAI,
    SWARM_REVIEW_TOOL_DEFINITION_ANTHROPIC,
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
    get_mcp_client,
)
from auto_test_tool import (
    execute_auto_test,
    AUTO_TEST_TOOL_DEFINITION_OPENAI,
    AUTO_TEST_TOOL_DEFINITION_ANTHROPIC,
    execute_run_auto_test,
    RUN_AUTO_TEST_TOOL_DEFINITION_OPENAI,
    RUN_AUTO_TEST_TOOL_DEFINITION_ANTHROPIC,
)
from memory_store import (
    search_memory as memory_search,
    record_learning as memory_record,
    init_memory_store,
    load_all_memory_files,
)
from ast_tool import (
    execute_get_code_structure,
    execute_get_function_definition,
    AST_CODE_STRUCTURE_TOOL_DEFINITION_OPENAI,
    AST_CODE_STRUCTURE_TOOL_DEFINITION_ANTHROPIC,
    AST_FUNCTION_DEFINITION_TOOL_DEFINITION_OPENAI,
    AST_FUNCTION_DEFINITION_TOOL_DEFINITION_ANTHROPIC,
)
from interactive_terminal import (
    execute_bg_service_tool,
    BG_SERVICE_TOOL_DEFINITIONS,
)

logger = logging.getLogger(__name__)

MAX_TURNS = 30


def sanitize_llm_args(args):
    """全局智能洗白中间件：递归遍历字典，纠正大模型乱加双引号的坏毛病

    大模型经常把 JSON 中的数字和布尔值加上引号变成字符串：
      {"totalThoughts": "2"} → {"totalThoughts": 2}
      {"nextThoughtNeeded": "False"} → {"nextThoughtNeeded": false}
      {"count": "3", "staged": "true"} → {"count": 3, "staged": true}

    此函数递归遍历整个参数树，自动修正类型漂移。
    安全机制：只转换"纯数字字符串"和"纯布尔字符串"，
    不会误伤文件路径 ("/home/test.py") 等合法字符串。
    """
    if isinstance(args, dict):
        for k, v in args.items():
            args[k] = sanitize_llm_args(v)
        return args
    elif isinstance(args, list):
        return [sanitize_llm_args(item) for item in args]
    elif isinstance(args, str):
        lower_val = args.lower()
        if lower_val == "true":
            return True
        if lower_val == "false":
            return False
        if args.isdigit() or (args.startswith('-') and len(args) > 1 and args[1:].isdigit()):
            return int(args)
        try:
            if '.' in args and args.replace('.', '', 1).lstrip('-').isdigit():
                return float(args)
        except ValueError:
            pass
    return args


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

🚨🚨🚨 【绝对铁律 #0 - 禁止盲目行动，必须先问人！】🚨🚨🚨
你拥有 ask_user 工具。这是你最重要的工具，没有之一。
当用户的指令模糊不清时，你**绝对禁止**自己猜测意图并直接动手写代码！
你必须**第一时间**调用 ask_user 工具向用户提问，明确需求后再行动。

**必须调用 ask_user 的典型场景（举例）：**
- 用户说"重构一下" → 你必须问："重构哪个文件？重构目标是什么？"
- 用户说"优化" → 你必须问："优化性能还是代码结构？针对哪个模块？"
- 用户说"修个bug" → 你必须问："什么bug？报错信息是什么？哪个文件出的问题？"
- 用户说"加个功能" → 你必须问："具体什么功能？加在哪个文件？有什么交互要求？"
- 用户说"改一下" → 你必须问："改什么？改成什么样？"
- 项目中有多个文件，用户没有指定操作哪个 → 你必须问清楚具体文件
- 你准备执行 rm -rf、git push --force、覆盖核心逻辑等高危操作 → 你必须请求确认
- 你的代码连续报错超过 3 次 → 你必须向人类求助，不要盲目试错

**判断标准：如果你无法 100% 确定用户想要什么，就调用 ask_user！宁可多问一句，也不要做错方向！**
调用 ask_user 后，静静等待人类回答，不要自己乱猜。人类的回答会作为工具返回值传回给你。

⚠️ 【最高执行军规 - 角色设定隔离】
你是一个在全自动隔离沙盒中运行的高级 AI 智能体，你 **不是** 普通的聊天助手！
当你需要写代码、创建文件、运行命令时，**必须且只能**通过发起 tool_calls（比如调用 bash 或 file_edit 工具）来完成。
**绝对禁止**在普通的 content 文本回复中直接输出几千行的代码段！这会导致系统崩溃！
如果任务代码非常长，请分步骤调用 file_edit 工具将代码写入硬盘，每次写入一个文件或一个函数。
**你的每一次回复，要么调用工具，要么简短汇报进度。绝不允许输出超过 500 字的纯文本！**

# 🧠 最高执行法则：强制深度思考

你现在已经装配了 `sequentialthinking` 工具（通过 MCP 加载，工具名格式为 `mcp_sequential-thinking_*`）。
在面对任何复杂的 Bug 修复、架构设计或多文件修改任务时，你**绝对禁止**直接调用 `file_edit` 或 `bash` 工具！
你必须首先调用 `sequentialthinking` 工具，输出你的思维链。
你的思考过程必须包含：
1. **现状分析**（目前的报错是什么，系统结构是怎样的）
2. **假设与验证方案**（我猜哪里出了问题，我需要搜什么文件来验证）
3. **行动计划**（确认原因后，我将分几步修改哪几个文件）

只有当你的思考过程足够清晰后，你才能开始执行实际的文件修改。
简单任务（如创建单文件、修改一行代码）可以跳过深度思考，直接执行。

# 🛠️ 可用工具

0. 🚨 **ask_user** - 【最重要！】向用户提问！当指令模糊、需求不清、操作高危、连续失败时，必须先调用此工具问清楚再动手！
1. file_edit - 创建或编辑文件（必须使用此工具来写代码文件！）
2. bash - 执行 shell 命令（编译、运行、测试等）
3. file_read - 读取文件内容（支持行号范围）
4. glob - 文件模式匹配搜索（用 ** 递归搜索子目录，如 'src/**/*.py'）
5. grep - 正则表达式代码搜索
6. **get_code_structure** - 🔭 AST 代码结构透视（获取文件的类名、函数签名、行号）
7. **get_function_definition** - 🎯 AST 函数精准定位（直接获取函数完整代码块）
8. semantic_search - 语义代码搜索（基于 AST，比 grep 更精准）
15. **semantic_search_code** - 🔍 Codebase RAG 语义搜索（用自然语言描述功能，返回最相关的代码片段！不确定功能在哪个文件时优先使用）
9. lsp_tool - LSP 语言服务器（查找定义、引用、文件大纲）
10. git_tool - Git 版本控制（查看状态、差异、日志、提交）
11. auto_test - 自动化测试（scan_and_test 可递归扫描目录下所有代码文件）
14. **run_auto_test** - 🧪 TDD 自愈测试引擎（修改代码后必须调用！自动运行测试，报错则自己修复，直到全绿）
10. read_project_memory - 搜索项目记忆库（查找以前踩过的坑和解决方案）
11. record_learning - 记录经验教训（成功修复 Bug 后，用一句话总结经验写入记忆库）
12. dispatch_subtasks - 🚀 子任务并发派发（多智能体协同！将任务拆分为多个子任务并发执行）
13. mcp_manager - 🔌 MCP 服务管理（动态加载第三方 MCP Server，如 GitHub、数据库、浏览器自动化等）
14. **coder_reviewer_swarm** - ⚔️ Coder-Reviewer 对抗博弈（双智能体代码审查闭环！Coder写代码→Reviewer审查→打回/LGTM）
16. **start_background_service** - 🚀 后台启动长驻服务（Web Server、数据库等，不阻塞 Agent！返回 PID）
17. **read_service_logs** - 📋 读取后台服务日志（查看服务端输出，排查启动错误）
18. **kill_service** - 🛑 关闭后台服务（测试完成后必须调用，释放端口和资源）
19. **interactive_debugger** - 🔬 交互式 Python 调试器（pdb）。启动后进程保持存活，可单步执行、检查变量、设置断点。当 print 调试无法定位 Bug 时使用。
20. **computer_use** - 🖥️ OS 级别电脑控制！控制鼠标键盘、截取屏幕截图。支持：take_screenshot、mouse_move、left_click、right_click、type_text、press_key、scroll、mouse_drag、hotkey。每次操作后自动返回最新截图。
21. **browser_vision** - 🌐 浏览器视觉截图！访问 URL 并返回渲染后的网页截图（Base64 PNG）。适用于检查网页视觉效果、验证前端布局。

**MCP 动态工具**: 当你通过 mcp_manager 动态加载了一个 MCP Server 后，该 Server 提供的所有工具会自动出现在你的工具列表中，工具名格式为 `mcp_{server}_{tool}`（如 `mcp_github_list_issues`）。你可以像调用本地工具一样直接调用它们。

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

# 🚀 后台服务管理 (长驻进程联调)

当你需要测试自己写的服务端代码（如 Web Server、数据库、消息队列）时，**绝对不能**直接用 `bash` 运行，因为那会阻塞 Agent！
你必须使用后台服务管理工具：

**典型流程：**
1. `start_background_service(command="python3 server.py")` → 后台启动服务，返回 PID
2. `bash(command="curl http://localhost:8080/health")` → 模拟客户端发请求测试
3. `read_service_logs(pid=返回的PID)` → 查看服务端日志，验证请求是否被正确处理
4. `kill_service(pid=返回的PID)` → 测试完毕，关闭服务释放端口

**重要规则：**
- 启动服务后，等待 1-2 秒再发请求（服务需要初始化时间）
- 测试完成后**必须**调用 `kill_service` 关闭服务，否则端口会被占用
- 最多同时运行 10 个后台服务
- 如果服务启动后立即退出，`start_background_service` 会返回错误日志，请根据日志排查

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

## 4. 【最高安全与协同指令】Human-in-the-Loop (人机协同) — 铁律重申！
这条规则在系统提示词开头已经强调过，这里再次重申：你**绝对禁止**在需求不明确时自己猜测并动手！
遇到以下情况，你**必须**调用 `ask_user` 工具，**没有任何例外**：

1. **需求模糊**：用户的指令不够具体，你无法 100% 确定该做什么、改哪个文件、改成什么样。
2. **高危操作**：你准备执行删除大量文件、覆盖核心架构逻辑、修改数据库 Schema、提交 Git 等不可逆操作。
3. **连续失败**：你的测试代码反复报错超过 3 次，你无法理解为什么，陷入了盲目试错的循环。
4. **权限不足**：需要用户提供密码、API Key、数据库连接串等敏感信息。
5. **方向分歧**：存在两种以上截然不同的技术方案，需要人类做决策。

**违反此规则的后果：你会浪费大量 Token 做错误的事情，用户会非常不满意。每次动手前，先问自己："我 100% 确定用户想要什么吗？"如果不确定，就调用 ask_user！**

## 3.5 🧪 TDD 自愈闭环（最高优先级死命令！）
- **在执行修改代码的任务后，绝对不要立刻告诉我任务完成！你必须先调用 `run_auto_test` 工具运行测试。**
- 如果 `run_auto_test` 返回 `[Test Failed]`，你必须自己阅读报错信息，分析原因，然后调用 `file_edit` 修改代码，再次调用 `run_auto_test`，直到返回 `[Test Passed]`。
- 自愈循环最多 3 轮。如果 3 轮后测试仍然失败，请停止并报告错误给用户。
- 如果项目中没有现成的测试文件，你可以用 `bash` 工具直接运行代码来验证（如 `python3 main.py`），或用 `auto_test(action='generate_and_run')` 自动生成测试。
- **只有当 `run_auto_test` 返回 `[Test Passed]`，或者你用 bash 直接运行代码验证通过后，你才能宣布任务完成。**

## 4. 自愈机制 (Auto-Healing)
- 如果终端执行报错，允许你在当前任务上下文中进行最多 3 次的尝试修改。超过 3 次请停止尝试并报告错误。

## 4.1 🔬 高级调试策略 (Interactive Debugger Protocol)
你现在拥有了一个 Interactive Debugger 工具（interactive_debugger）。这是一个有状态的 pdb 调试器，启动后进程保持存活，你可以像在终端中一样逐步调试代码。

**强制触发条件：当你在尝试修复一个复杂的运行时 Bug，且连续两次通过阅读代码和修改未解决问题时，你必须停止盲目猜测。你应当使用 Debugger 在出错的行设置断点，运行代码，并通过发送调试命令来检查实时的内存状态，然后再进行修复。**

**典型调试流程：**
1. `interactive_debugger(action="start", script_path="main.py", breakpoint_line=42)` → 在第 42 行设置断点并运行到断点处
2. `interactive_debugger(action="command", cmd="p variable_name")` → 打印变量值
3. `interactive_debugger(action="command", cmd="p locals()")` → 查看当前作用域所有局部变量
4. `interactive_debugger(action="command", cmd="step")` → 单步进入函数
5. `interactive_debugger(action="command", cmd="next")` → 单步跳过（不进入函数）
6. `interactive_debugger(action="command", cmd="continue")` → 继续运行到下一个断点
7. `interactive_debugger(action="command", cmd="where")` → 查看调用栈
8. `interactive_debugger(action="command", cmd="list")` → 查看当前代码上下文
9. `interactive_debugger(action="stop")` → 调试完毕，终止会话

**关键原则：**
- **禁止盲目修改**：连续 2 次修改代码后 Bug 仍未解决 → 必须启动 Debugger 观察运行时状态
- **先观察后行动**：用 `p locals()` 或 `p 变量名` 检查实际值，而非猜测变量内容
- **断点精准**：在报错行或可疑函数入口设断点，不要在无关代码处浪费时间
- **及时清理**：调试完成后必须调用 `action="stop"` 终止会话，释放进程资源

## 4.2 🖥️ 手眼协调策略 (Hand-Eye Coordination Protocol)
你现在运行在一个拥有 GUI 的虚拟桌面系统中（Xvfb 虚拟显示器，分辨率 1024x768）。你拥有 `computer_use` 工具，可以控制鼠标键盘并截取屏幕截图。

**核心原则：先看后动，每动必看。**

当你需要操作 GUI 应用（如浏览器、IDE、终端模拟器）时，必须遵循以下闭环：

1. **观察**：先调用 `computer_use(action="take_screenshot")` 观察当前屏幕状态
2. **定位**：通过视觉能力分析截图，估算目标元素（按钮/图标/输入框）在 1024x768 屏幕上的 (x, y) 坐标
3. **操作**：调用 `computer_use(action="mouse_move", x=..., y=...)` 移动鼠标，然后 `computer_use(action="left_click", x=..., y=...)` 点击
4. **确认**：每次操作后你都会自动获得一张新的截图，检查操作是否生效
5. **循环**：如果操作未生效，重新分析截图并调整坐标，重复上述步骤

**典型场景：**
- 测试 Web 应用：先用 `browser_vision` 看网页，再用 `computer_use` 操作桌面浏览器
- 操作 GUI 程序：截图 → 找按钮 → 点击 → 再截图确认
- 输入文本：先点击输入框 → `computer_use(action="type_text", text="...")` → 截图确认
- 按键操作：`computer_use(action="press_key", key="enter")` → 截图确认

**坐标估算技巧：**
- 屏幕左上角为 (0, 0)，右下角为 (1023, 767)
- 屏幕中心约为 (512, 384)
- 典型按钮高度约 30-40px，标题栏约 30px
- 如果第一次点击不准确，根据截图偏差调整坐标重试

**重要规则：**
- 绝对不要在没看屏幕的情况下盲目点击！先 take_screenshot 再操作
- 每次操作后你都会收到最新截图，必须仔细检查再决定下一步
- 如果连续 3 次点击未命中目标，停下来用 ask_user 请求帮助

## 5. 记忆系统 (Memory System)
- 遇到 Bug 时，先调用 read_project_memory 搜索是否有类似的历史经验。
- 成功修复 Bug 并验证通过后，必须调用 record_learning 记录经验，格式：record_learning(category="Bug修复", lesson="一句话总结", related_files=["相关文件路径"])
- 记忆会自动写入 .agent_memory/learnings.md 并 Git 提交，永久保存。

## 6. AST 代码透视优先策略 (AST-First Strategy)
- **当你想了解一个文件的结构（有哪些类、函数、方法）时，绝对优先使用 `get_code_structure`，而不是 grep。**
  - grep "class" 会匹配注释、字符串、模板参数，产生大量垃圾结果。
  - get_code_structure 基于 AST 语法树，只返回真正的代码结构，精准率提升 100 倍。
- **当你想查看某个函数/方法的具体实现时，绝对优先使用 `get_function_definition`，而不是 grep + file_read 手动拼凑。**
  - get_function_definition 直接返回函数完整代码块，包含行号和签名。
  - 如果存在多个同名函数（重载/多类同名），会列出所有匹配项供你选择。
- **典型使用流程**：
  1. 先用 `get_code_structure(file_path)` 鸟瞰文件结构
  2. 再用 `get_function_definition(file_path, function_name)` 精准定位感兴趣的函数
  3. 只有在 AST 工具无法覆盖的场景（如搜索变量名、字符串常量）才回退到 grep

## 6.5 🔍 Codebase RAG 语义搜索优先策略
- **当你不确定某个功能在哪个文件，或者需要理解业务逻辑时，优先使用 `semantic_search_code`。**
  - 示例：semantic_search_code(query="数据库连接初始化")
  - 示例：semantic_search_code(query="用户认证逻辑")
  - 它会返回最相关的代码片段（含文件路径、行号、签名和源码）
- **如果你知道极其确切的函数名或变量名，使用 `grep` 进行精准搜索。**
- **搜索策略优先级**：semantic_search_code（不确定在哪）> get_code_structure（已知文件）> get_function_definition（已知函数名）> grep（已知确切字符串）

## 5. 基本操作规则
- 必须使用 file_edit 工具来创建/修改文件，不要只在回复中输出代码！
- 创建新文件时，old_string 设为空字符串即可
- 编辑文件时，old_string 必须精确匹配文件中的原代码片段，且在文件中唯一
- 先理解需求，再动手编码
- 修改文件前先读取文件内容
- 每次只做一步操作，逐步推进任务

示例用法：
- 创建新文件 main.py: file_edit(file_path="main.py", old_string="", new_string="# Python code...")
- 修改文件: file_edit(file_path="main.py", old_string="old code", new_string="new code")
- 递归搜索文件: glob(pattern="src/**/*.py") 或 glob(pattern="monopoly_game/**/*.*")

📝 备用方案：如果工具调用失败，你也可以直接在回复中使用 Markdown 代码块：
```python filepath=文件名.py
# 你的代码
```
系统会自动识别并写入文件。

⚠️ 工具调用格式警告：你当前拥有 40+ 个工具。请必须严格按照 JSON 格式发起 tool_calls。绝不要把命令直接写在回复的文本内容里！不要在文本中输出类似 bash("xxx") 或 file_edit(...) 的伪调用，必须使用标准的 function call 格式！

⚠️ 【JSON 数据类型强制警告】调用工具时，必须严格遵守参数的 JSON 数据类型！
- 数字参数（如 thoughtNumber, totalThoughts, count, line）必须是整数，绝不能加引号！正确: {"totalThoughts": 2}  错误: {"totalThoughts": "2"}
- 布尔参数（如 nextThoughtNeeded, staged）必须是原生 true/false，绝不能输出字符串！正确: {"nextThoughtNeeded": false}  错误: {"nextThoughtNeeded": "False"}
- 违反类型会导致 MCP Server 校验失败，工具调用被拒绝！

🚫 【铁律一：工作区锁定约束】
你必须且只能在当前分配的工作区目录（即运行环境的根目录）下创建和修改文件。严禁使用 `cd /tmp` 或使用绝对路径去其他地方创建项目！所有文件操作（file_edit、file_write、bash）的目标路径必须是工作区内的相对路径。否则系统将无法保存你的代码，你的工作将丢失！

🚫 【铁律二：视觉工具使用规范】
如果需要截图或查看网页，严禁使用 `browser_vision` 工具（该工具不存在且已被废弃）。你必须使用 MCP 提供的真实工具：先调用 `mcp_puppeteer_puppeteer_navigate` 打开网址，然后调用 `mcp_puppeteer_puppeteer_screenshot` 获取截图。如果你尝试调用 `browser_vision`，系统将返回错误并要求你重新使用正确的 MCP 工具。
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
    file_edit(file_path="player.py", old_string="", new_string="class Player:...")
    ```
    
    Returns:
        [{"name": "file_edit", "args": {"file_path": "player.py", ...}}, ...]
    """
    import re
    results = []
    
    # 匹配 file_edit(file_path="xxx", old_string="xxx", new_string="xxx")
    file_edit_pattern = r'file_edit\s*\(\s*file_path\s*=\s*["\']([^"\']+)["\']\s*,\s*(?:old_string|search_text)\s*=\s*["\']([^"\']*)["\']\s*,\s*(?:new_string|replace_text)\s*=\s*["\'](.+?)["\']\s*\)'
    
    for match in re.finditer(file_edit_pattern, text, re.DOTALL):
        file_path = match.group(1)
        old_string = match.group(2)
        new_string = match.group(3)
        
        new_string = new_string.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"')
        
        results.append({
            "name": "file_edit",
            "args": {
                "file_path": file_path,
                "old_string": old_string,
                "new_string": new_string,
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

    project_manual = ""
    manual_file = None
    for candidate in [".eruitah.md", "CLAUDE.md"]:
        candidate_path = os.path.join(workspace_dir, candidate)
        if os.path.exists(candidate_path):
            manual_file = candidate
            break

    if manual_file:
        try:
            with open(os.path.join(workspace_dir, manual_file), 'r', encoding='utf-8') as f:
                content = f.read()
                if content.strip():
                    project_manual = (
                        f"\n\n<project_manual>\n{content}\n</project_manual>\n"
                        "请在接下来的任务中，严格遵守上述 <project_manual> 中的项目架构与编码规范。\n"
                    )
                    logger.info(f"📖 成功加载项目专属说明书：{manual_file}")
        except Exception:
            pass

    return project_rules + project_manual + memory_section + base_prompt

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
                    "创建或编辑文件（精准 Diff 替换模式）。\n"
                    "使用方法：\n"
                    "1. 创建新文件：file_path='文件名', old_string='', new_string='文件内容'\n"
                    "2. 编辑文件：file_path='文件名', old_string='要被替换的原代码片段（必须精确匹配）', new_string='新的代码片段'\n"
                    "规则：old_string 必须在文件中唯一匹配（出现 0 次报错，出现 >1 次需提供更多上下文）。\n"
                    "示例：file_edit(file_path='hello.py', old_string='print(1)', new_string='print(2)')"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "【必需】文件路径，如 'main.py' 或 'src/app.js'",
                        },
                        "old_string": {
                            "type": "string",
                            "description": "要被替换的原代码片段，必须精确匹配文件中的内容。创建新文件时设为空字符串 ''",
                        },
                        "new_string": {
                            "type": "string",
                            "description": "【必需】替换后的新代码片段",
                        },
                    },
                    "required": ["file_path", "new_string"],
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
            SEMANTIC_SEARCH_CODE_TOOL_DEFINITION_ANTHROPIC,
            META_TOOL_DEFINITION_ANTHROPIC,
            SPECULATIVE_TOOL_DEFINITION_ANTHROPIC,
            SWARM_TOOL_DEFINITION_ANTHROPIC,
            DISPATCH_SUBTASKS_TOOL_DEFINITION_ANTHROPIC,
            SWARM_REVIEW_TOOL_DEFINITION_ANTHROPIC,
            DISTILL_TOOL_DEFINITION_ANTHROPIC,
            THESEUS_TOOL_DEFINITION_ANTHROPIC,
            COMPUTE_TOOL_DEFINITION_ANTHROPIC,
            LSP_TOOL_DEFINITION_ANTHROPIC,
            GIT_TOOL_DEFINITION_ANTHROPIC,
            NOTEBOOK_TOOL_DEFINITION_ANTHROPIC,
            MCP_TOOL_DEFINITION_ANTHROPIC,
            AUTO_TEST_TOOL_DEFINITION_ANTHROPIC,
            RUN_AUTO_TEST_TOOL_DEFINITION_ANTHROPIC,
            AST_CODE_STRUCTURE_TOOL_DEFINITION_ANTHROPIC,
            AST_FUNCTION_DEFINITION_TOOL_DEFINITION_ANTHROPIC,
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
        ] + BG_SERVICE_TOOL_DEFINITIONS["anthropic"] + get_dynamic_tool_schemas("anthropic")
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
                        "创建或编辑文件（精准 Diff 替换模式）。\n"
                        "使用方法：\n"
                        "1. 创建新文件：file_path='文件名', old_string='', new_string='文件内容'\n"
                        "2. 编辑文件：file_path='文件名', old_string='要被替换的原代码片段（必须精确匹配）', new_string='新的代码片段'\n"
                        "规则：old_string 必须在文件中唯一匹配（出现 0 次报错，出现 >1 次需提供更多上下文）。\n"
                        "示例：file_edit(file_path='hello.py', old_string='print(1)', new_string='print(2)')"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "【必需】文件路径，如 'main.py' 或 'src/app.js'",
                            },
                            "old_string": {
                                "type": "string",
                                "description": "要被替换的原代码片段，必须精确匹配文件中的内容。创建新文件时设为空字符串 ''",
                            },
                            "new_string": {
                                "type": "string",
                                "description": "【必需】替换后的新代码片段",
                            },
                        },
                        "required": ["file_path", "new_string"],
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
            SEMANTIC_SEARCH_CODE_TOOL_DEFINITION_OPENAI,
            META_TOOL_DEFINITION_OPENAI,
            SPECULATIVE_TOOL_DEFINITION_OPENAI,
            SWARM_TOOL_DEFINITION_OPENAI,
            DISPATCH_SUBTASKS_TOOL_DEFINITION_OPENAI,
            SWARM_REVIEW_TOOL_DEFINITION_OPENAI,
            DISTILL_TOOL_DEFINITION_OPENAI,
            THESEUS_TOOL_DEFINITION_OPENAI,
            COMPUTE_TOOL_DEFINITION_OPENAI,
            LSP_TOOL_DEFINITION_OPENAI,
            GIT_TOOL_DEFINITION_OPENAI,
            NOTEBOOK_TOOL_DEFINITION_OPENAI,
            MCP_TOOL_DEFINITION_OPENAI,
            AUTO_TEST_TOOL_DEFINITION_OPENAI,
            RUN_AUTO_TEST_TOOL_DEFINITION_OPENAI,
            AST_CODE_STRUCTURE_TOOL_DEFINITION_OPENAI,
            AST_FUNCTION_DEFINITION_TOOL_DEFINITION_OPENAI,
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
        ] + BG_SERVICE_TOOL_DEFINITIONS["openai"] + get_dynamic_tool_schemas("openai")


def _get_mcp_tools(provider: str = "openai") -> list[dict]:
    client = get_mcp_client()
    if not client.servers:
        return []
    try:
        if provider == "anthropic":
            return client.get_anthropic_tools()
        else:
            return client.get_openai_tools()
    except Exception as e:
        logger.warning(f"获取 MCP 工具列表失败: {e}")
        return []


def _build_tools_with_mcp(provider: str = "openai") -> list[dict]:
    base_tools = _get_tools_definition(provider)
    mcp_tools = _get_mcp_tools(provider)
    if mcp_tools:
        logger.info(f"🔀 合并 {len(mcp_tools)} 个 MCP 外部工具到 {provider} 工具列表")
        base_tools.extend(mcp_tools)

    if provider == "openai":
        for tool_def in base_tools:
            func = tool_def.get("function", {})
            if "strict" not in func:
                func["strict"] = True
            params = func.get("parameters", {})
            if isinstance(params, dict):
                if "additionalProperties" not in params:
                    params["additionalProperties"] = False
                if "properties" in params and "required" not in params:
                    params["required"] = list(params["properties"].keys())
                for prop_schema in params.get("properties", {}).values():
                    if isinstance(prop_schema, dict) and prop_schema.get("type") == "object":
                        if "additionalProperties" not in prop_schema:
                            prop_schema["additionalProperties"] = False

    return base_tools

def _auto_commit_worktree(
    work_dir: str,
    session_id: str,
    summary: str,
    model: Optional[str] = None,
    main_repo_dir: Optional[str] = None,
    current_turn: int = 0,
) -> str:
    try:
        commit_hash = ""

        git_dir = os.path.join(work_dir, ".git")
        if os.path.exists(git_dir):
            import subprocess
            status_result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True, text=True, timeout=5, cwd=work_dir,
            )
            if status_result.stdout.strip():
                commit_msg = f"turn {current_turn}: {summary[:80]}" if current_turn > 0 else summary[:80]
                subprocess.run(
                    ["git", "add", "-A"],
                    capture_output=True, timeout=5, cwd=work_dir,
                )
                subprocess.run(
                    ["git", "commit", "-m", commit_msg],
                    capture_output=True, timeout=10, cwd=work_dir,
                )
                rev_result = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    capture_output=True, text=True, timeout=5, cwd=work_dir,
                )
                if rev_result.returncode == 0:
                    commit_hash = rev_result.stdout.strip()
                    logger.debug(f"auto-commit worktree: {commit_hash[:8]} in {work_dir}")

        if not commit_hash:
            from sandbox_manager import get_sandbox, _sandboxes
            repo_dir = main_repo_dir or work_dir
            abs_repo = os.path.abspath(repo_dir)
            if abs_repo in _sandboxes:
                sandbox = get_sandbox(repo_dir)
                commit_hash = sandbox.commit_agent_changes(session_id, summary, model_name=model or "unknown")

        return commit_hash or ""
    except Exception as e:
        logger.warning(f"Git auto-commit 失败: {e}")
        return ""


def _safe_run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result(timeout=60)
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            pass


def _run_lsp_check(file_path: str, work_dir: str) -> tuple:
    try:
        from lsp_client import get_lsp_client
        client = get_lsp_client()

        abs_path = file_path
        if work_dir and not os.path.isabs(file_path):
            abs_path = os.path.join(work_dir, file_path)
        abs_path = os.path.abspath(abs_path)

        if not os.path.isfile(abs_path):
            return "", []

        diagnostics = client.get_diagnostics(abs_path, work_dir)
        if not diagnostics:
            return "", []

        errors = [d for d in diagnostics if d.get("severity") == "error"]
        warnings = [d for d in diagnostics if d.get("severity") == "warning"]

        if not errors and not warnings:
            return "", []

        lines = []
        if errors:
            lines.append(f"⚠️ LSP 静态分析检测到 {len(errors)} 个错误，请立即修复：")
            for e in errors[:8]:
                lines.append(f"  - Line {e['line']}: {e['message']}")
            if len(errors) > 8:
                lines.append(f"  ... 还有 {len(errors) - 8} 个错误")
        if warnings:
            lines.append(f"⚡ LSP 检测到 {len(warnings)} 个警告：")
            for w in warnings[:4]:
                lines.append(f"  - Line {w['line']}: {w['message']}")
            if len(warnings) > 4:
                lines.append(f"  ... 还有 {len(warnings) - 4} 个警告")

        return "\n".join(lines), diagnostics

    except Exception as e:
        logger.debug(f"LSP 检查跳过: {e}")
        return "", []


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
    current_turn: int = 0,
    plan_mode: bool = False,
) -> tuple[str, bool, dict]:
    """本地执行工具"""
    meta = {}
    
    # =======================================================
    # 🛡️ 终极防御墙：拦截大模型 JSON 幻觉与类型崩塌
    # =======================================================
    if plan_mode:
        from prompt_builder import PLAN_MODE_TOOLS
        if name not in PLAN_MODE_TOOLS and not name.startswith("mcp_"):
            logger.warning(f"🔒 PM模式拦截: 禁止工具 '{name}'，仅允许 {PLAN_MODE_TOOLS}")
            return (
                f"Error: Tool '{name}' is blocked in PM mode. "
                f"You can only use: {', '.join(sorted(PLAN_MODE_TOOLS))}. "
                f"Please use ask_user to discuss requirements, or file_edit to write SPEC.md.",
                True,
                meta,
            )

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

            command_stripped = command.strip()
            _webcontainer_run_patterns = (
                "npm start", "npm run dev", "npm run start", "npm run serve",
                "npm run build", "npm run preview",
                "npx serve", "npx vite", "npx next dev", "npx nuxt dev",
                "yarn start", "yarn dev", "yarn serve", "yarn build",
                "pnpm start", "pnpm dev", "pnpm serve", "pnpm build",
                "bun start", "bun dev", "bun run dev", "bun run start",
                "vite", "vite dev", "vite serve",
                "next dev", "nuxt dev",
            )
            _is_webcontainer_run = any(
                command_stripped.startswith(p) or command_stripped == p
                for p in _webcontainer_run_patterns
            )

            if _is_webcontainer_run:
                try:
                    from artifact_builder import detect_execution_env
                    _env = detect_execution_env(work_dir)
                    if _env == "webcontainer":
                        meta["webcontainer_intercept"] = True
                        meta["intercepted_command"] = command_stripped
                        return (
                            f"✅ 命令已拦截: `{command_stripped}`\n"
                            f"本项目被判定为 WebContainer 前端项目，运行命令将由前端 WebContainer 接管执行，"
                            f"无需在后端 Docker 中运行。请继续完成代码编写工作。",
                            False,
                            meta,
                        )
                except Exception:
                    pass

            try:
                from main import check_stop_flag
                if check_stop_flag(session_id):
                    return "用户已停止 Agent 执行", False, meta
            except ImportError:
                pass

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

            if is_error and bash_result.stderr:
                from bash_executor import parse_compiler_errors
                diagnostics = parse_compiler_errors(bash_result.stderr, work_dir)
                if diagnostics:
                    meta["diagnostics"] = diagnostics

            if not is_error and session_id:
                pass

            return result, is_error, meta

        elif name == "file_edit":
            file_path = args.get("file_path", "")
            old_string = args.get("old_string", args.get("search_text", ""))
            new_string = args.get("new_string", args.get("replace_text", ""))

            if not file_path:
                return "文件路径不能为空", True, meta

            result, is_error = execute_file_edit(file_path, old_string, new_string, work_dir)

            if not is_error:
                lsp_diag_text, lsp_diagnostics = _run_lsp_check(file_path, work_dir)
                if lsp_diag_text:
                    result = result + "\n\n" + lsp_diag_text
                if lsp_diagnostics:
                    meta["diagnostics"] = lsp_diagnostics

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
            cu_args = {k: v for k, v in args.items() if k != 'action'}
            cu_result = execute_computer_use(args.get("action", "screenshot"), **cu_args)

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

        elif name == "semantic_search_code":
            query = args.get("query", "")
            top_k = args.get("top_k", 3)
            project_dir = args.get("project_dir", work_dir)
            result_str, is_err = semantic_search_code(query, top_k, project_dir)
            return result_str, is_err, meta

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

        elif name == "coder_reviewer_swarm":
            task_desc = args.get("task_description", "")
            max_loops = args.get("max_loops", 5)
            if not task_desc:
                return "❌ task_description 不能为空", True, meta
            result_str, is_error = execute_coder_reviewer_swarm(
                task_description=task_desc,
                work_dir=work_dir,
                provider=provider,
                api_key=api_key,
                model=model,
                base_url=base_url,
                max_loops=int(max_loops),
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

        elif name.startswith("mcp_") and name != "mcp_manager":
            try:
                client = get_mcp_client()
                if not client.is_mcp_tool(name):
                    return f"未知的 MCP 工具: {name}", True, meta

                try:
                    result_str = client.sync_call_tool(name, args)
                except Exception as e:
                    result_str = f"MCP 工具调用失败: {e}"

                is_error = result_str.startswith("错误:")
                return result_str, is_error, meta
            except Exception as e:
                return f"MCP 路由异常: {e}", True, meta

        elif name == "auto_test":
            action = args.get("action", "run")
            test_file = args.get("test_file", "")
            source_file = args.get("source_file", "")
            directory = args.get("directory", "")
            result_str, is_error = execute_auto_test(action, test_file, source_file, directory, work_dir)
            return result_str, is_error, meta

        elif name == "browser_vision":
            from browser_vision_tool import execute_browser_vision
            url = args.get("url", "")
            if not url:
                return "URL 不能为空", True, meta
            wait_until = args.get("wait_until", "networkidle")
            timeout_ms = args.get("timeout_ms", 30000)
            bv_result = execute_browser_vision(url, wait_until, timeout_ms)
            if bv_result.get("status") == "success" and bv_result.get("base64_image"):
                meta["browser_vision_image"] = {
                    "base64": bv_result["base64_image"],
                    "url": bv_result.get("url", url),
                    "title": bv_result.get("title", ""),
                }
                return f"[Browser Vision] 已截取页面截图: {bv_result.get('title', url)}", False, meta
            else:
                return f"[Browser Vision] 截图失败: {bv_result.get('error', '未知错误')}", True, meta

        elif name == "interactive_debugger":
            from interactive_debugger_tool import execute_interactive_debugger
            dbg_action = args.get("action", "")
            if not dbg_action:
                return "action 不能为空", True, meta
            dbg_result = execute_interactive_debugger(
                action=dbg_action,
                script_path=args.get("script_path", ""),
                breakpoint_line=args.get("breakpoint_line", 0),
                breakpoint_func=args.get("breakpoint_func", ""),
                cmd=args.get("cmd", ""),
                work_dir=work_dir,
                session_id=args.get("session_id", "default"),
                timeout=args.get("timeout", 15),
            )
            is_error = dbg_result.get("status") == "error"
            result_str = json.dumps(dbg_result, ensure_ascii=False, indent=2)
            return result_str, is_error, meta

        elif name == "run_auto_test":
            test_command = args.get("test_command", "")
            test_file = args.get("test_file", "")
            result_str, is_error = execute_run_auto_test(test_command, test_file, work_dir)
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

        elif name == "get_code_structure":
            file_path = args.get("file_path", "")
            if not file_path:
                return "文件路径不能为空", True, meta
            result_str, is_error = execute_get_code_structure(file_path, work_dir)
            return result_str, is_error, meta

        elif name == "get_function_definition":
            file_path = args.get("file_path", "")
            function_name = args.get("function_name", "")
            if not file_path:
                return "文件路径不能为空", True, meta
            if not function_name:
                return "函数名不能为空", True, meta
            result_str, is_error = execute_get_function_definition(file_path, function_name, work_dir)
            return result_str, is_error, meta

        elif name in ("start_background_service", "read_service_logs", "kill_service"):
            result_str, is_error = execute_bg_service_tool(name, **args)
            return result_str, is_error, meta

        elif is_dynamic_tool(name):
            result_str, is_error = execute_dynamic_tool(name, args)
            return result_str, is_error, meta

        else:
            return f"未知工具: {name}", True, meta

    except Exception as e:
        logger.error(f"工具执行异常 {name}: {e}")
        return f"工具执行异常: {str(e)}", True, meta


def route_task(
    user_message: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    provider: str = "openai",
    images: Optional[list] = None,
) -> dict:
    """
    Supervisor（CTO）路由：调用 LLM 分析用户请求，决定路由给预设专家或动态生成专家。
    支持多模态：当 images 存在时，CTO LLM 也能看到用户上传的图片。

    Returns:
        dict: {
            "is_predefined": bool,
            "target_agent_name": str,
            "dynamic_system_prompt": str,
            "sub_task": str
        }
        如果路由失败，返回兜底结果 {"is_predefined": True, "target_agent_name": "general_coder", ...}
    """
    from agent_prompts import ROUTER_PROMPT, PREDEFINED_AGENTS

    router_messages = [
        {"role": "system", "content": ROUTER_PROMPT},
    ]

    effective_images = images or []

    if effective_images:
        content_list = [{"type": "text", "text": user_message}]
        for img_b64 in effective_images:
            if isinstance(img_b64, str) and img_b64:
                prefix = "" if img_b64.startswith("data:image") else "data:image/jpeg;base64,"
                content_list.append({
                    "type": "image_url",
                    "image_url": {"url": f"{prefix}{img_b64}"},
                })

        if provider == "anthropic":
            anthropic_content = []
            for item in content_list:
                if item["type"] == "text":
                    anthropic_content.append({"type": "text", "text": item["text"]})
                elif item["type"] == "image_url":
                    url = item["image_url"]["url"]
                    if url.startswith("data:image/"):
                        parts = url.split(";base64,", 1)
                        media_type = parts[0].replace("data:image/", "image/")
                        b64_data = parts[1] if len(parts) > 1 else ""
                        anthropic_content.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": b64_data,
                            },
                        })
            router_messages.append({"role": "user", "content": anthropic_content})
        else:
            router_messages.append({"role": "user", "content": content_list})

        logger.info(f"📷 route_task: CTO 接收到 {len(effective_images)} 张图片")
    else:
        router_messages.append({"role": "user", "content": user_message})

    try:
        if provider == "anthropic":
            text, _, _ = _call_anthropic(
                messages=router_messages,
                tools=[],
                api_key=api_key,
                model=model,
                base_url=base_url,
            )
        else:
            text, _, _ = _call_openai(
                messages=router_messages,
                tools=[],
                api_key=api_key,
                model=model,
                base_url=base_url,
            )

        text = text.strip()

        json_str = text
        if "```json" in text:
            json_str = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            json_str = text.split("```")[1].split("```")[0].strip()

        result = json.loads(json_str)

        if not isinstance(result, dict):
            raise ValueError("路由结果不是 JSON 对象")

        if "is_predefined" not in result:
            if "target_agent" in result:
                result["is_predefined"] = True
                result["target_agent_name"] = result.pop("target_agent")
                result.setdefault("dynamic_system_prompt", "")
            else:
                raise ValueError("路由结果缺少 is_predefined 字段")

        is_predefined = result.get("is_predefined", True)

        if is_predefined:
            agent_name = result.get("target_agent_name", "general_coder")
            if agent_name not in PREDEFINED_AGENTS:
                logger.warning(f"⚠️ 路由返回未知预设专家 '{agent_name}'，降级为 general_coder")
                result["target_agent_name"] = "general_coder"
            result["dynamic_system_prompt"] = ""
            logger.info(f"🔀 路由结果 [预设]: {result['target_agent_name']} | 子任务: {result.get('sub_task', 'N/A')[:80]}")
        else:
            dynamic_prompt = result.get("dynamic_system_prompt", "")
            if not dynamic_prompt or len(dynamic_prompt.strip()) < 20:
                logger.warning("⚠️ 动态专家的 system_prompt 过短，降级为 general_coder")
                result["is_predefined"] = True
                result["target_agent_name"] = "general_coder"
                result["dynamic_system_prompt"] = ""
            else:
                result["target_agent_name"] = "dynamic_expert"
                logger.info(f"🔀 路由结果 [动态生成]: dynamic_expert | Prompt 长度: {len(dynamic_prompt)} | 子任务: {result.get('sub_task', 'N/A')[:80]}")

        if "sub_task" not in result or not result["sub_task"]:
            result["sub_task"] = user_message

        result.setdefault("execution_env", "native")

        return result

    except json.JSONDecodeError as e:
        logger.warning(f"⚠️ 路由结果 JSON 解析失败: {e}, 原始输出: {text[:200]}")
        return {
            "is_predefined": True,
            "target_agent_name": "general_coder",
            "dynamic_system_prompt": "",
            "sub_task": user_message,
            "execution_env": "native",
        }
    except Exception as e:
        logger.error(f"路由任务异常: {e}")
        return {
            "is_predefined": True,
            "target_agent_name": "general_coder",
            "dynamic_system_prompt": "",
            "sub_task": user_message,
            "execution_env": "native",
        }


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
    user_id: int = 0,
    override_system_prompt: Optional[str] = None,
    images: Optional[list] = None,
    plan_mode: bool = False,
) -> Generator[Dict[str, Any], None, None]:
    """Agent 主循环"""
    if not task_id:
        task_id = f"task_{uuid.uuid4().hex[:8]}"

    session_id = task_id

    reset_budget(session_id)
    cost_tracker = reset_cost_tracker(session_id, limit_usd=5.0)
    rewind_system = get_rewind_system(user_id=user_id, session_id=session_id)
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
                tm = get_task_manager(user_id=user_id)
                session = tm.get_session(task_id)
                if session:
                    task_data = session.to_dict()
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
        if override_system_prompt:
            system_prompt = override_system_prompt
        else:
            system_prompt = build_system_prompt(work_dir)

        effective_images = images or []

        if effective_images:
            content_list = [{"type": "text", "text": user_input}]
            for img_b64 in effective_images:
                if isinstance(img_b64, str) and img_b64:
                    prefix = "" if img_b64.startswith("data:image") else "data:image/jpeg;base64,"
                    content_list.append({
                        "type": "image_url",
                        "image_url": {"url": f"{prefix}{img_b64}"},
                    })

            if provider == "anthropic":
                anthropic_content = []
                for item in content_list:
                    if item["type"] == "text":
                        anthropic_content.append({"type": "text", "text": item["text"]})
                    elif item["type"] == "image_url":
                        url = item["image_url"]["url"]
                        if url.startswith("data:image/"):
                            parts = url.split(";base64,", 1)
                            media_type = parts[0].replace("data:image/", "image/")
                            b64_data = parts[1] if len(parts) > 1 else ""
                            anthropic_content.append({
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": b64_data,
                                },
                            })
                messages.append({"role": "user", "content": anthropic_content})
            else:
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content_list},
                ]
            logger.info(f"📷 视觉消息已组装: {len(effective_images)} 张图片, provider={provider}")
        else:
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
    sm = get_session_manager(user_id=user_id)
    session = sm.get_or_create_session(
        task_id=task_id,
        first_prompt=user_input or task_name,
        work_dir=work_dir,
        existing_messages=messages.copy(),
    )
    task_id = session.id
    task_name = session.summary

    if session.worktree_dir and os.path.isdir(session.worktree_dir):
        work_dir = os.path.abspath(session.worktree_dir)
        logger.info(f"🔒 路径强制重定向: work_dir → worktree {work_dir}")

    logger.info(f"📦 任务 {task_id} 已注册，物理快照已创建: {work_dir}")

    mcp_client = get_mcp_client()
    if not mcp_client.servers:
        mcp_config = os.path.join(work_dir, "mcp.json")
        if not os.path.exists(mcp_config):
            mcp_config = MCP_CONFIG_PATH if 'MCP_CONFIG_PATH' in dir() else os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp.json")
        mcp_client.config_path = mcp_config
        if mcp_client.load_config():
            import threading
            def _mcp_bg_init():
                try:
                    mcp_client.sync_start_all()
                    if mcp_client.all_tools:
                        logger.info(f"🔌 MCP 后台加载完成: {len(mcp_client.all_tools)} 个外部工具")
                except Exception as e:
                    logger.warning(f"MCP 后台初始化失败（不影响核心功能）: {e}")
            t = threading.Thread(target=_mcp_bg_init, daemon=True)
            t.start()
            logger.info(f"🔌 MCP 后台初始化已启动（不阻塞 Agent）")

    _lsp_languages_for_workdir = set()
    try:
        from lsp_client import get_lsp_client
        lsp_client = get_lsp_client()

        lsp_indicators = {
            'cpp': ['CMakeLists.txt', 'compile_commands.json', 'Makefile', '.clang-format'],
            'python': ['requirements.txt', 'setup.py', 'pyproject.toml', 'Pipfile'],
            'typescript': ['tsconfig.json', 'package.json'],
            'javascript': ['package.json', '.eslintrc.js'],
            'go': ['go.mod', 'go.sum'],
            'rust': ['Cargo.toml', 'Cargo.lock'],
            'java': ['pom.xml', 'build.gradle', 'build.gradle.kts'],
        }

        for lang, indicators in lsp_indicators.items():
            for indicator in indicators:
                if os.path.exists(os.path.join(work_dir, indicator)):
                    _lsp_languages_for_workdir.add(lang)
                    break

        ext_map = {'.cpp': 'cpp', '.cc': 'cpp', '.h': 'cpp', '.hpp': 'cpp', '.c': 'cpp',
                   '.py': 'python', '.js': 'javascript', '.ts': 'typescript',
                   '.rs': 'rust', '.go': 'go', '.java': 'java'}
        for f in os.listdir(work_dir):
            ext = os.path.splitext(f)[1].lower()
            if ext in ext_map:
                _lsp_languages_for_workdir.add(ext_map[ext])

        if _lsp_languages_for_workdir:
            for lang in _lsp_languages_for_workdir:
                try:
                    conn = lsp_client.get_connection(lang, work_dir)
                    if conn:
                        logger.info(f"🔬 LSP 预初始化成功: {lang}")
                except Exception as e:
                    logger.debug(f"LSP {lang} 预初始化跳过: {e}")
    except Exception as e:
        logger.debug(f"LSP 预初始化跳过: {e}")

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
    format_error_count = 0
    thinking_mode_detected = False
    has_code_changes = False

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

        blackboard.update_from_messages(messages, work_dir)
        injected_messages = blackboard.inject_anchor(messages, provider)

        from prompt_caching import truncate_messages_with_budget
        injected_messages = truncate_messages_with_budget(
            injected_messages,
            max_tokens=100000,
            keep_recent=6,
        )

        tools = _build_tools_with_mcp(provider)

        if plan_mode:
            from prompt_builder import PLAN_MODE_TOOLS
            filtered_tools = []
            for t in tools:
                func_info = t.get("function", t)
                name = func_info.get("name", "")
                if name in PLAN_MODE_TOOLS:
                    filtered_tools.append(t)
            logger.info(f"🔒 PM模式: 工具列表已过滤 {len(tools)} → {len(filtered_tools)} (仅保留: {PLAN_MODE_TOOLS})")
            tools = filtered_tools

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

            api_messages = _sanitize_messages_for_api(injected_messages, thinking_mode_detected)

            if provider == "anthropic":
                text, tool_calls, reasoning_content = _call_anthropic(
                    messages=api_messages,
                    tools=tools,
                    api_key=api_key,
                    model=model,
                    base_url=base_url,
                    system_prompt=anchor_system,
                    force_tool_call=format_error_count >= 2,
                )
            else:
                text, tool_calls, reasoning_content = _call_openai(
                    messages=api_messages,
                    tools=tools,
                    api_key=api_key,
                    model=model,
                    base_url=base_url,
                    force_tool_call=format_error_count >= 2,
                )

            if reasoning_content is not None and not thinking_mode_detected:
                thinking_mode_detected = True
                logger.info("🧠 检测到思维链模式 (reasoning_content)，后续请求将保留推理内容")

            logger.info(f"🤖 LLM 返回: text 长度={len(text) if text else 0}, tool_calls 数量={len(tool_calls)}")
            if tool_calls:
                logger.info(f"🔧 工具调用: {[tc.get('name', 'unknown') for tc in tool_calls]}")
                file_related = any(tc.get('name', '') in ('file_edit', 'file_write', 'bash', 'theseus_rewrite') for tc in tool_calls)
                if file_related:
                    has_code_changes = True
                search_tools = ('semantic_search_code', 'semantic_search', 'glob', 'file_read', 'grep', 'lsp_tool', 'get_code_structure', 'get_function_definition')
                thinking_tools = ('mcp_sequential-thinking_sequentialthinking', 'mcp_sequential-thinking', 'ask_user')
                is_searching = any(tc.get('name', '') in search_tools or tc.get('name', '').startswith('mcp_sequential') for tc in tool_calls)
                is_deep_thinking = any(tc.get('name', '') in thinking_tools or 'sequential' in tc.get('name', '').lower() or 'thinking' in tc.get('name', '').lower() for tc in tool_calls)
                if is_deep_thinking:
                    yield {"type": "agent_state", "status": "thinking", "data": "深度推理中..."}
                    yield {"type": "agent_status", "status": "THINKING"}
                elif is_searching:
                    search_desc = "正在检索代码库..."
                    for tc in tool_calls:
                        tc_name = tc.get('name', '')
                        tc_args = tc.get('args', {})
                        if tc_name == 'semantic_search_code' and tc_args.get('query'):
                            search_desc = f"语义搜索: {tc_args['query'][:60]}"
                        elif tc_name == 'grep' and tc_args.get('pattern'):
                            search_desc = f"正则搜索: {tc_args['pattern'][:60]}"
                        elif tc_name == 'glob' and tc_args.get('pattern'):
                            search_desc = f"文件匹配: {tc_args['pattern'][:60]}"
                        elif tc_name == 'file_read' and tc_args.get('file_path'):
                            search_desc = f"读取文件: {tc_args['file_path'][:60]}"
                    yield {"type": "agent_state", "status": "searching", "data": search_desc}
                    yield {"type": "agent_status", "status": "THINKING"}
                elif file_related:
                    yield {"type": "agent_status", "status": "WRITING"}
                else:
                    yield {"type": "agent_status", "status": "THINKING"}

            # 🚨 检测乱码：如果文本主要是空格和引号，可能是模型崩溃
            if text and len(text) > 100:
                non_space_chars = len([c for c in text if c not in ' \t\n\r"\''])
                if non_space_chars < len(text) * 0.3:  # 有效字符少于 30%
                    logger.warning(f"⚠️ 检测到模型返回乱码，有效字符比例: {non_space_chars/len(text):.2%}")
                    messages.append(_build_assistant_msg(text, reasoning_content=reasoning_content))
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
                            has_code_changes = True
                            
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
                messages.append(_build_assistant_msg(text, reasoning_content=reasoning_content))
                messages.append({
                    "role": "user",
                    "content": f"✅ 已通过 Markdown 降级模式写入文件。请继续执行任务，如果还有更多文件需要创建或修改，请继续。"
                })
                _cp_desc = f"第 {turn} 轮 (Markdown写入)"
                try:
                    from rewind_system import get_rewind_system as _get_rewind
                    _rewind = _get_rewind(user_id=user_id, session_id=session_id)
                    _cp = _rewind.create_checkpoint(session_id, turn, messages, _cp_desc, work_dir=work_dir)
                    if _cp:
                        yield {
                            "type": "checkpoint_created",
                            "session_id": session_id,
                            "turn": turn,
                            "description": _cp_desc,
                            "code_diff": _cp.code_diff or "",
                            "diff_stat": _cp.diff_stat or "",
                            "git_commit": _cp.git_commit or "",
                        }
                except Exception:
                    pass
                logger.info("🔄 Markdown 降级成功，继续下一轮循环...")
                continue

            if not tool_calls:
                format_error_count += 1
                if text and len(text) > 2000:
                    logger.warning(f"🚨 [系统拦截] 模型输出了 {len(text)} 字符的纯文本，无工具调用！强制截断！")
                    yield {"type": "system_alert", "content": "检测到模型输出大量纯文本（无工具调用），正在自动拦截并重试..."}
                    truncated_text = text[:500] + f"\n\n... [系统截断：原文 {len(text)} 字符被丢弃]"
                    messages.append(_build_assistant_msg(truncated_text, reasoning_content=reasoning_content))
                    messages.append({
                        "role": "user",
                        "content": (
                            "🚨 [系统拦截] 你刚刚试图在聊天回复中直接输出大量代码！\n\n"
                            "重复一遍：**严禁在文本中直接写代码！**\n"
                            "你必须调用 `file_edit` 工具将代码写入文件系统！\n"
                            "如果代码很长，请分多次调用 file_edit，每次写入一个文件或一个函数。\n\n"
                            "正确做法示例：\n"
                            '```json\n'
                            '{"name": "file_edit", "arguments": {"file_path": "main.py", "old_string": "", "new_string": "def hello():\\n    print(\\"hello\\")"}}\n'
                            '```\n\n'
                            "请立即重新执行你的操作，这次必须使用标准工具调用格式！"
                        )
                    })
                    _cp_desc = f"第 {turn} 轮 (长文本拦截)"
                    try:
                        from rewind_system import get_rewind_system as _get_rewind
                        _rewind = _get_rewind(user_id=user_id, session_id=session_id)
                        _cp = _rewind.create_checkpoint(session_id, turn, messages, _cp_desc, work_dir=work_dir)
                        if _cp:
                            yield {
                                "type": "checkpoint_created",
                                "session_id": session_id,
                                "turn": turn,
                                "description": _cp_desc,
                                "code_diff": _cp.code_diff or "",
                                "diff_stat": _cp.diff_stat or "",
                                "git_commit": _cp.git_commit or "",
                            }
                    except Exception:
                        pass
                    continue

                if text and ('file_edit' in text or '```' in text or 'def ' in text or 'class ' in text):
                    logger.warning("⚠️ 检测到文本中可能包含代码或工具调用，但格式不正确")
                    yield {"type": "system_alert", "content": "检测到格式错误（代码混入文本），正在自动修正并重试..."}
                    messages.append(_build_assistant_msg(text[:2000], reasoning_content=reasoning_content))
                    messages.append({
                        "role": "user",
                        "content": (
                            "⚠️ 严重格式错误！你刚才的回复中包含了代码或工具调用，"
                            "但你没有使用标准的 function call 格式！\n\n"
                            "你当前拥有 40+ 个工具。你必须严格按照 JSON 格式发起 tool_calls，"
                            "绝不要把命令直接写在回复的文本内容里！\n\n"
                            "正确做法：\n"
                            "- 写代码 → 必须调用 file_edit 工具\n"
                            "- 执行命令 → 必须调用 bash 工具\n"
                            "- 读取文件 → 必须调用 file_read 工具\n\n"
                            "请立即重新执行你的操作，这次必须使用标准工具调用格式！"
                        )
                    })
                    _cp_desc = f"第 {turn} 轮 (格式错误重试)"
                    try:
                        from rewind_system import get_rewind_system as _get_rewind
                        _rewind = _get_rewind(user_id=user_id, session_id=session_id)
                        _cp = _rewind.create_checkpoint(session_id, turn, messages, _cp_desc, work_dir=work_dir)
                        if _cp:
                            yield {
                                "type": "checkpoint_created",
                                "session_id": session_id,
                                "turn": turn,
                                "description": _cp_desc,
                                "code_diff": _cp.code_diff or "",
                                "diff_stat": _cp.diff_stat or "",
                                "git_commit": _cp.git_commit or "",
                            }
                    except Exception:
                        pass
                    continue

                _cp_desc = f"第 {turn} 轮 (完成)"
                try:
                    from rewind_system import get_rewind_system as _get_rewind
                    _rewind = _get_rewind(user_id=user_id, session_id=session_id)
                    _cp = _rewind.create_checkpoint(session_id, turn, messages, _cp_desc, work_dir=work_dir)
                    if _cp:
                        yield {
                            "type": "checkpoint_created",
                            "session_id": session_id,
                            "turn": turn,
                            "description": _cp_desc,
                            "code_diff": _cp.code_diff or "",
                            "diff_stat": _cp.diff_stat or "",
                            "git_commit": _cp.git_commit or "",
                        }
                except Exception:
                    pass

                if has_code_changes and user_id > 0:
                    try:
                        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "protobuf-rpc-bridge", "python"))
                        from career_analyzer import analyze_career_sync
                        analysis = analyze_career_sync(
                            user_id=user_id,
                            work_dir=work_dir,
                            session_messages=None,
                        )
                        if analysis and (analysis.get("skills") or analysis.get("resume_highlight")):
                            from rpc_entry import report_career_advice
                            report_career_advice(
                                user_id=user_id,
                                extracted_skills=analysis.get("skills", []),
                                resume_highlight=analysis.get("resume_highlight", ""),
                                next_suggestion=analysis.get("next_suggestion", ""),
                            )
                    except Exception as e:
                        logger.warning(f"⚠️ 职业档案分析触发失败: {e}")

                try:
                    from artifact_builder import build_artifact_payload
                    artifact_payload = build_artifact_payload(work_dir)
                    execution_env = artifact_payload.get("execution_env", "native")
                    logger.info(
                        f"📦 任务结算: execution_env={execution_env}, "
                        f"files={artifact_payload.get('file_count', 0)}, "
                        f"size={artifact_payload.get('total_size_bytes', 0) // 1024}KB"
                    )
                    yield {
                        "type": "artifacts_ready",
                        "data": artifact_payload,
                    }
                except Exception as e:
                    logger.warning(f"⚠️ 构建产物打包失败（不影响任务结果）: {e}")

                yield {"type": "finish", "data": text or "任务完成"}
                break

            tool_results_for_api = []
            any_error = False
            error_logs = []
            turn_tool_summary = []
            format_error_count = 0

            for tc in tool_calls:
                name = tc.get("name", "unknown")
                args = tc.get("args", {})
                tc_id = tc.get("id", f"call_{hash(str(tc))}")
                
                if not isinstance(args, dict):
                    logger.warning(f"⚠️ 工具 {name} 的 args 不是字典: {type(args)}, 值: {args}")
                    args = {}
                
                # ==========================================================
                # 🔄 全局参数类型洗白 (Global Type Sanitizer)
                # 大模型经常把 JSON 中的数字和布尔值加上引号变成字符串，
                # 导致 MCP Server 的 Zod/JSON Schema 校验失败。
                # sanitize_llm_args 递归遍历整个参数树，自动修正类型漂移：
                #   "2" → 2, "False" → false, "3.14" → 3.14
                # 安全：不会误伤文件路径等合法字符串
                # ==========================================================
                args = sanitize_llm_args(args)
                
                if name == "__invalid_tool__":
                    error_msg = args.get("_error", f"Error: Tool '{args.get('_original_name', 'unknown')}' is invalid or not found.")
                    logger.warning(f"⚠️ 无效工具调用反馈: {error_msg}")
                    yield {"type": "tool_start", "tool_name": args.get("_original_name", "unknown"), "args": args.get("_original_args", {})}
                    yield {"type": "tool_end", "tool_name": args.get("_original_name", "unknown"), "result": error_msg, "is_error": True}
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
                    continue
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
                            "old_string": "",
                            "new_string": markdown_file["content"],
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
                            current_turn=turn,
                            plan_mode=plan_mode,
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
                        '  "old_string": "",\n'
                        '  "new_string": "你的代码内容"\n'
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
                    current_turn=turn,
                    plan_mode=plan_mode,
                )

                tool_end_event = {
                    "type": "tool_end",
                    "tool_name": name,
                    "result": result_str,
                    "is_error": is_error,
                }
                if tool_meta.get("diagnostics"):
                    tool_end_event["diagnostics"] = tool_meta["diagnostics"]

                if "ask_user" not in tool_meta:
                    yield tool_end_event

                if not is_error:
                    tool_desc = name
                    if name == "file_edit" and args.get("file_path"):
                        tool_desc = f"file_edit: {args['file_path']}"
                    elif name == "bash" and args.get("command"):
                        tool_desc = f"bash: {args['command'][:60]}"
                    elif name == "file_read" and args.get("file_path"):
                        tool_desc = f"file_read: {args['file_path']}"
                    elif name == "grep" and args.get("pattern"):
                        tool_desc = f"grep: {args['pattern'][:40]}"
                    turn_tool_summary.append(tool_desc)

                if name == "file_edit" and not is_error:
                    file_path = args.get("file_path", "")
                    if file_path:
                        yield {"type": "context_update", "files": [file_path]}
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

                if not is_error:
                    active_files_from_tool = []
                    if name == "file_read" and args.get("file_path"):
                        active_files_from_tool.append(args.get("file_path"))
                    elif name in ("semantic_search_code", "semantic_search") and result_str:
                        import re as _re
                        _found = _re.findall(r'(?:^|\n)\s*[\w./-]+\.(?:py|js|ts|vue|go|rs|java|cpp|c|h|hpp|rb|php|jsx|tsx|css|html|sql|sh|yaml|yml|toml|json|md)\b', result_str[:2000])
                        for _f in _found:
                            _f = _f.strip()
                            if _f and len(_f) < 200:
                                active_files_from_tool.append(_f)
                    elif name == "grep" and args.get("file_path"):
                        active_files_from_tool.append(args.get("file_path"))
                    elif name == "glob" and result_str:
                        import re as _re
                        _found = _re.findall(r'[\w./-]+\.(?:py|js|ts|vue|go|rs|java|cpp|c|h|hpp|rb|php|jsx|tsx|css|html|sql|sh|yaml|yml|toml|json|md)\b', result_str[:1000])
                        for _f in _found[:5]:
                            if _f and len(_f) < 200:
                                active_files_from_tool.append(_f)
                    elif name == "get_code_structure" and args.get("file_path"):
                        active_files_from_tool.append(args.get("file_path"))
                    elif name == "get_function_definition" and args.get("file_path"):
                        active_files_from_tool.append(args.get("file_path"))
                    if active_files_from_tool:
                        yield {"type": "context_update", "files": active_files_from_tool}

                tokens = estimate_tokens(result_str)
                consume_tokens(session_id, tokens)

                if is_error:
                    any_error = True
                    error_logs.append(f"工具 [{name}] 报错: {result_str}")
                    yield {"type": "agent_status", "status": "ERROR"}

                if "ask_user" in tool_meta:
                    if provider != "anthropic":
                        tc_list = [
                            {
                                "id": tc_item["id"],
                                "type": "function",
                                "function": {
                                    "name": tc_item["name"],
                                    "arguments": json.dumps(tc_item["args"], ensure_ascii=False)
                                }
                            }
                            for tc_item in tool_calls
                        ]
                        messages.append(_build_assistant_msg(
                            text if text else None,
                            tool_calls=tc_list,
                            reasoning_content=reasoning_content,
                        ))
                    else:
                        tc_list_anthropic = [
                            {
                                "id": tc_item["id"],
                                "type": "function",
                                "function": {
                                    "name": tc_item["name"],
                                    "arguments": json.dumps(tc_item["args"], ensure_ascii=False)
                                }
                            }
                            for tc_item in tool_calls
                        ] if tool_calls else None
                        messages.append(_build_assistant_msg(
                            text if text else "",
                            tool_calls=tc_list_anthropic,
                            reasoning_content=reasoning_content,
                        ))

                    if task_id:
                        try:
                            from task_manager import get_task_manager
                            tm = get_task_manager(user_id=user_id)
                            tm.update_session_messages(
                                task_id=task_id,
                                messages=messages,
                                current_turn=turn,
                            )
                        except Exception as e:
                            logger.debug(f"保存 ask_user 挂起状态失败: {e}")

                    yield {
                        "type": "ask_user",
                        "data": {
                            "question_id": tool_meta["ask_user"]["question_id"],
                            "question": tool_meta["ask_user"]["question"],
                            "context": tool_meta["ask_user"]["context"],
                            "tool_call_id": tc_id,
                            "task_id": task_id,
                            "provider": provider,
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
                    elif "browser_vision_image" in tool_meta:
                        bv_result = tool_meta["browser_vision_image"]
                        bv_text = result_str
                        tool_result_content = [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": bv_result["base64"],
                                },
                            },
                            {
                                "type": "text",
                                "text": bv_text,
                            },
                        ]

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
                        tool_result_content = image_parts
                    elif "browser_vision_image" in tool_meta:
                        bv_result = tool_meta["browser_vision_image"]
                        bv_text = result_str
                        tool_result_content = [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{bv_result['base64']}",
                                    "detail": "auto",
                                },
                            },
                            {
                                "type": "text",
                                "text": bv_text,
                            },
                        ]

                    tool_results_for_api.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": tool_result_content,
                    })

            # 只有在有工具调用结果时才添加到消息列表
            if tool_results_for_api:
                # 对于 OpenAI 格式，需要先添加 assistant 消息（带 tool_calls）
                if provider != "anthropic":
                    tc_list_main = []
                    for tc in tool_calls:
                        tc_name_for_api = tc["name"]
                        tc_args_for_api = tc["args"]
                        if tc_name_for_api == "__invalid_tool__":
                            tc_name_for_api = tc_args_for_api.get("_original_name", "unknown_tool")
                            tc_args_for_api = tc_args_for_api.get("_original_args", {})
                        tc_list_main.append({
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc_name_for_api,
                                "arguments": json.dumps(tc_args_for_api, ensure_ascii=False)
                            }
                        })
                    messages.append(_build_assistant_msg(
                        text if text else None,
                        tool_calls=tc_list_main,
                        reasoning_content=reasoning_content,
                    ))
                
                # 添加工具结果
                messages.extend(tool_results_for_api)

            checkpoint_desc = " | ".join(turn_tool_summary[:5]) if turn_tool_summary else f"第 {turn} 轮 (思考)"
            _cp_code_diff = ""
            _cp_diff_stat = ""
            _cp_git_commit = ""
            try:
                from rewind_system import get_rewind_system as _get_rewind
                _rewind = _get_rewind(user_id=user_id, session_id=session_id)
                _cp = _rewind.create_checkpoint(session_id, turn, messages, checkpoint_desc, work_dir=work_dir)
                if _cp:
                    _cp_code_diff = _cp.code_diff or ""
                    _cp_diff_stat = _cp.diff_stat or ""
                    _cp_git_commit = _cp.git_commit or ""
            except Exception as e:
                logger.debug(f"创建轮次检查点失败: {e}")

            yield {
                "type": "checkpoint_created",
                "session_id": session_id,
                "turn": turn,
                "description": checkpoint_desc,
                "code_diff": _cp_code_diff,
                "diff_stat": _cp_diff_stat,
                "git_commit": _cp_git_commit,
            }

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
                yield {"type": "system_alert", "content": f"检测到执行错误，正在自动重试... (第 {consecutive_errors}/{MAX_CONSECUTIVE_ERRORS} 次)"}
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
                    tm = get_task_manager(user_id=user_id)
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

    try:
        from self_distill import auto_distill
        distill_work_dir = main_repo_dir or work_dir
        distill_result = auto_distill(
            messages=messages,
            work_dir=distill_work_dir,
            task_id=task_id or session_id,
            task_description=user_input[:100] if user_input else "",
        )
        if distill_result:
            yield {"type": "distill", "data": f"🧠 经验已自动蒸馏并记录:\n{distill_result}"}
    except Exception as e:
        logger.debug(f"自动蒸馏失败（不影响任务结果）: {e}")

    final_checkpoints = []
    try:
        final_checkpoints = rewind_system.list_checkpoints(session_id)
    except Exception:
        pass
    yield {
        "type": "finish",
        "data": f"任务已完成 (共 {turn-1} 轮)",
        "checkpoints": final_checkpoints,
    }

def _build_assistant_msg(
    content: str | None,
    tool_calls: list[dict] | None = None,
    reasoning_content: str | None = None,
) -> dict:
    """
    构建 assistant 消息，兼容思维链模型和非思维链模型。
    
    - 思维链模型 (DeepSeek-R1, QwQ 等): reasoning_content 非空时自动保留，
      API 要求在后续请求中原样传回，否则报 400。
    - 非思维链模型 (GPT-4o, Claude 等): reasoning_content 为 None，
      不会添加该字段，不会影响 API 调用。
    - 空字符串 reasoning_content: 使用 is not None 判断，
      确保思维链模型即使推理内容为空也会传回（部分 API 强制要求）。
    """
    msg: dict = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    if reasoning_content is not None:
        msg["reasoning_content"] = reasoning_content
    return msg


def _sanitize_messages_for_api(
    messages: list[dict],
    thinking_mode: bool,
) -> list[dict]:
    """
    清理消息数组中的 reasoning_content 字段，兼容不支持思维链的模型。
    
    安全策略:
    - thinking_mode=True: 保留 reasoning_content
    - 消息中存在 reasoning_content: 自动保留（说明当前/历史模型是思维链模型，
      清理会导致 API 400 报错 "reasoning_content must be passed back"）
    - 仅当 thinking_mode=False 且消息中无 reasoning_content 时: 无需处理
    """
    has_reasoning = any("reasoning_content" in m for m in messages)
    if not has_reasoning:
        return messages
    if thinking_mode:
        return messages
    logger.warning("⚠️ 消息中存在 reasoning_content 但 thinking_mode=False，为安全起见保留 reasoning_content（清理会导致思维链模型 400 报错）")
    return messages


def _call_anthropic(
    messages: list[dict],
    tools: list[dict],
    api_key: str | None,
    model: str | None,
    base_url: str | None,
    system_prompt: str = "",
    force_tool_call: bool = False,
) -> tuple[str, list[dict], str | None]:
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
        model=model or "claude-sonnet-4-20250514",
    )

    cache_report = cached_request.pop("_cache_report", None)
    if cache_report and cache_report.has_break:
        logger.warning(f"⚠️ 缓存断层: {cache_report.reason}")
    elif cache_report:
        logger.info(
            f"💰 缓存前缀完整, 预估节省 {cache_report.cache_savings_estimate:.0f} tokens"
        )

    tool_choice_val = {"type": "auto"}
    if force_tool_call and tools:
        tool_choice_val = {"type": "any"}
        logger.warning("🔒 强制工具调用模式已激活 (连续格式错误 ≥ 2)")

    response = client.messages.create(
        model=model or "claude-sonnet-4-20250514",
        max_tokens=4096,
        system=cached_request["system"],
        tools=cached_request["tools"],
        messages=cached_request["messages"],
        tool_choice=tool_choice_val,
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
    thinking_content = None

    for block in response.content:
        if block.type == "thinking":
            thinking_text = getattr(block, 'thinking', None) or getattr(block, 'text', '')
            if thinking_text:
                thinking_content = thinking_text
        elif block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use":
            tool_calls.append({
                "id": block.id,
                "name": block.name,
                "args": block.input if isinstance(block.input, dict) else {},
            })

    return "\n".join(text_parts), tool_calls, thinking_content

def _call_openai(
    messages: list[dict],
    tools: list[dict],
    api_key: str | None,
    model: str | None,
    base_url: str | None,
    max_retries: int = 3,
    force_tool_call: bool = False,
) -> tuple[str, list[dict], str | None]:
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
        request_kwargs = {
            "model": model_name,
            "messages": messages,
            "tools": tools,
            "max_tokens": 4096,
        }

        if tools:
            if force_tool_call:
                request_kwargs["tool_choice"] = "required"
                logger.warning(f"🔒 强制工具调用模式已激活 (连续格式错误 ≥ 2)")
            else:
                request_kwargs["tool_choice"] = "auto"

        return client.chat.completions.create(**request_kwargs)

    def _parse_response(response):
        """解析响应"""
        choice = response.choices[0]
        message = choice.message

        reasoning_content = getattr(message, 'reasoning_content', None)
        logger.info(f"📥 LLM 原始响应: content 存在={message.content is not None}, tool_calls={message.tool_calls}, reasoning_content 存在={reasoning_content is not None}")

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
                    "code_structure": "get_code_structure",
                    "get_structure": "get_code_structure",
                    "file_structure": "get_code_structure",
                    "function_def": "get_function_definition",
                    "get_function": "get_function_definition",
                    "find_function": "get_function_definition",
                    "start_service": "start_background_service",
                    "background_service": "start_background_service",
                    "start_bg_service": "start_background_service",
                    "read_logs": "read_service_logs",
                    "service_logs": "read_service_logs",
                    "kill_bg_service": "kill_service",
                    "stop_service": "kill_service",
                    "swarm_review": "coder_reviewer_swarm",
                    "code_review": "coder_reviewer_swarm",
                    "review_code": "coder_reviewer_swarm",
                }

                VALID_TOOLS = {
                    "file_edit", "file_read", "bash", "glob", "grep",
                    "ask_user", "semantic_search", "semantic_search_code", "meta_tool",
                    "speculative_execute", "swarm_communicate", "dispatch_subtasks",
                    "self_distill",
                    "theseus_rewrite", "compute_autonomy", "lsp_tool",
                    "git_tool", "notebook_tool", "mcp_tool",
                    "auto_test", "run_auto_test", "computer_use",
                    "read_project_memory", "record_learning",
                    "get_code_structure", "get_function_definition",
                    "start_background_service", "read_service_logs", "kill_service",
                    "coder_reviewer_swarm",
                }

                if tc_name not in VALID_TOOLS:
                    if tc_name in TOOL_NAME_ALIASES:
                        original_name = tc_name
                        tc_name = TOOL_NAME_ALIASES[tc_name]
                        logger.info(f"🔄 工具名映射: {original_name} → {tc_name}")
                    elif tc_name.startswith("mcp_"):
                        pass
                    else:
                        logger.warning(f"⚠️ 无效的工具名: {tc_name}, 尝试从参数推断...")
                        if "command" in args_dict:
                            tc_name = "bash"
                            logger.info(f"🔄 根据参数推断工具名: bash")
                        elif "file_path" in args_dict and ("content" in args_dict or "new_string" in args_dict or "replace_text" in args_dict):
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
                            logger.warning(f"⚠️ 无法推断工具名: {tc_name}, 将错误反馈给模型以触发自我纠正")
                            invalid_tool_hints = {
                                "browser_vision": "browser_vision 不存在且已废弃。如需截图请使用 MCP 工具: mcp_puppeteer_puppeteer_navigate 打开网页, mcp_puppeteer_puppeteer_screenshot 获取截图",
                                "browser_screenshot": "browser_screenshot 不存在。如需截图请使用 MCP 工具: mcp_puppeteer_puppeteer_navigate + mcp_puppeteer_puppeteer_screenshot",
                                "web_screenshot": "web_screenshot 不存在。如需截图请使用 MCP 工具: mcp_puppeteer_puppeteer_navigate + mcp_puppeteer_puppeteer_screenshot",
                                "screenshot": "screenshot 不存在。如需截图请使用 MCP 工具: mcp_puppeteer_puppeteer_navigate + mcp_puppeteer_puppeteer_screenshot",
                                "navigate": "navigate 不存在。如需打开网页请使用 MCP 工具: mcp_puppeteer_puppeteer_navigate",
                                "open_browser": "open_browser 不存在。如需打开网页请使用 MCP 工具: mcp_puppeteer_puppeteer_navigate",
                            }
                            hint = invalid_tool_hints.get(tc_name, f"该工具不存在。可用工具: bash, file_edit, file_read, glob, grep, ask_user, mcp_puppeteer_puppeteer_navigate, mcp_puppeteer_puppeteer_screenshot 等")
                            error_msg = f"Error: Tool '{tc_name}' is invalid or not found. {hint}"
                            tool_calls.append({
                                "id": tc_id,
                                "name": "__invalid_tool__",
                                "args": {"_original_name": tc_name, "_original_args": args_dict, "_error": error_msg},
                            })

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

        return "\n".join(text_parts), tool_calls, reasoning_content

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
                return f"❌ LLM 服务不可用: {str(e)}", [], None
    
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
        return "❌ 大模型服务暂时不可用，请稍后重试", [], None

def get_session_messages(session_id: str, user_id: int = 0) -> list[dict]:
    """获取会话消息（用于回退工具）"""
    rewind_system = get_rewind_system(user_id=user_id, session_id=session_id)
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
