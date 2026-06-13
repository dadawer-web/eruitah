"""
Eruitah 智能编程沙盒 - AskUser 工具 (Human-in-the-Loop)

当 Agent 遇到无法独立解决的问题时，通过 WebSocket 向用户求助。

核心流程:
┌─────────────────────────────────────────────────────────────────────┐
│  Agent 循环中:                                                       │
│    大模型决定调用 ask_user("数据库找不到，是否未初始化？")              │
│         │                                                            │
│         ▼                                                            │
│    Python 后端:                                                      │
│    1. yield {"type": "ask_user", "question": "..."} 给前端           │
│    2. 将 asyncio.Future 挂起，阻塞当前 Agent 循环                     │
│         │                                                            │
│         ▼                                                            │
│    前端:                                                             │
│    1. 收到 ask_user 事件                                             │
│    2. 弹出对话框: "🤖 Agent 遇到困难: ..."                            │
│    3. 用户输入回答                                                   │
│    4. 通过 WebSocket 发送 {"type": "user_answer", "answer": "..."}   │
│         │                                                            │
│         ▼                                                            │
│    Python 后端:                                                      │
│    1. 收到用户回答                                                   │
│    2. Future.set_result(answer)                                      │
│    3. Agent 循环恢复，将回答返回给大模型                               │
│    4. 大模型基于用户回答继续执行                                      │
│         │                                                            │
│         ▼                                                            │
│  交互式权限拦截（新增）:                                              │
│    危险命令（rm -rf /）→ 发送 require_confirm → 前端弹窗确认          │
│    → 用户确认 → 后端恢复执行                                         │
│    → 用户拒绝 → 后端取消命令                                         │
└─────────────────────────────────────────────────────────────────────┘

参考源码: claude-code-rev/src/tools/AskUserQuestionTool/
"""

import asyncio
import logging
import uuid
import re
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_pending_questions: dict[str, asyncio.Future] = {}

_pending_confirmations: dict[str, asyncio.Future] = {}


def register_question(question_id: str, future: asyncio.Future):
    _pending_questions[question_id] = future
    logger.info(f"注册等待问题: {question_id}")


def resolve_question(question_id: str, answer: str):
    future = _pending_questions.pop(question_id, None)
    if future and not future.done():
        future.set_result(answer)
        logger.info(f"用户回答了问题: {question_id} -> {answer[:100]}")
    else:
        logger.warning(f"未找到等待中的问题: {question_id}")


def register_confirmation(confirm_id: str, future: asyncio.Future):
    _pending_confirmations[confirm_id] = future
    logger.info(f"注册等待确认: {confirm_id}")


def resolve_confirmation(confirm_id: str, approved: bool, reason: str = ""):
    future = _pending_confirmations.pop(confirm_id, None)
    if future and not future.done():
        future.set_result({"approved": approved, "reason": reason})
        logger.info(f"用户确认: {confirm_id} -> {'批准' if approved else '拒绝'}")
    else:
        logger.warning(f"未找到等待中的确认: {confirm_id}")


def cancel_all_questions():
    for qid, future in _pending_questions.items():
        if not future.done():
            future.set_result("[用户未回答，已取消]")
    _pending_questions.clear()

    for cid, future in _pending_confirmations.items():
        if not future.done():
            future.set_result({"approved": False, "reason": "已取消"})
    _pending_confirmations.clear()


async def ask_user_async(question_id: str, question: str, timeout: float = 300) -> Optional[str]:
    """
    异步等待用户回答
    
    用法:
        answer = await ask_user_async("q123", "是否继续？")
        if answer == "yes":
            ...
    """
    loop = asyncio.get_event_loop()
    future = loop.create_future()
    register_question(question_id, future)
    
    try:
        answer = await asyncio.wait_for(future, timeout=timeout)
        return answer
    except asyncio.TimeoutError:
        _pending_questions.pop(question_id, None)
        logger.warning(f"等待用户回答超时: {question_id}")
        return None
    except Exception as e:
        _pending_questions.pop(question_id, None)
        logger.error(f"等待用户回答异常: {e}")
        return None


async def ask_confirmation_async(confirm_id: str, command: str, reason: str, timeout: float = 300) -> dict:
    """
    异步等待用户确认命令
    
    返回: {"approved": bool, "reason": str}
    """
    loop = asyncio.get_event_loop()
    future = loop.create_future()
    register_confirmation(confirm_id, future)
    
    try:
        result = await asyncio.wait_for(future, timeout=timeout)
        return result
    except asyncio.TimeoutError:
        _pending_confirmations.pop(confirm_id, None)
        logger.warning(f"等待用户确认超时: {confirm_id}")
        return {"approved": False, "reason": "超时"}
    except Exception as e:
        _pending_confirmations.pop(confirm_id, None)
        logger.error(f"等待用户确认异常: {e}")
        return {"approved": False, "reason": str(e)}


# ============================================================================
# 多级危险命令拦截 - 静态黑名单 + 动态风险评估
# ============================================================================

@dataclass
class CommandRisk:
    level: str  # "safe", "warning", "danger", "critical"
    reason: str
    requires_confirmation: bool = False
    auto_block: bool = False


DANGEROUS_PATTERNS = [
    (r"\brm\s+-rf\s+/", "递归删除根目录", "critical"),
    (r"\brm\s+-rf\s+~", "递归删除用户目录", "critical"),
    (r"\brm\s+-rf\s+\*", "递归删除所有文件", "critical"),
    (r"\brm\s+-rf\s+/home", "递归删除用户主目录", "critical"),
    (r"\brm\s+-rf\s+/etc", "递归删除系统配置", "critical"),
    (r"\brm\s+-rf\s+/var", "递归删除系统数据", "critical"),
    (r"\bchmod\s+777\s+/", "设置根目录危险权限", "danger"),
    (r"\bchmod\s+777", "设置危险权限 777", "warning"),
    (r"\bchown\s+.*\s+/", "修改根目录所有者", "danger"),
    (r"\bdd\s+if=", "磁盘写入操作", "critical"),
    (r"\bmkfs\.", "格式化文件系统", "critical"),
    (r"\bformat\s+[A-Z]:", "格式化磁盘", "critical"),
    (r"\breboot", "重启系统", "danger"),
    (r"\bshutdown", "关闭系统", "danger"),
    (r"\binit\s+[06]", "切换运行级别", "danger"),
    (r"\b:\(\)\{\s*:\|\:&\s*\}", "Fork 炸弹", "critical"),
    (r"\bwget\s+.*\|\s*sh", "下载并执行脚本", "danger"),
    (r"\bcurl\s+.*\|\s*sh", "下载并执行脚本", "danger"),
    (r"\bcurl\s+.*\|\s*bash", "下载并执行脚本", "danger"),
    (r"\bsudo\s+rm", "超级用户删除", "danger"),
    (r"\bapt\s+remove", "卸载系统包", "warning"),
    (r"\byum\s+remove", "卸载系统包", "warning"),
    (r"\bsystemctl\s+stop", "停止系统服务", "warning"),
    (r"\biptables\s+-F", "清空防火墙规则", "danger"),
    (r"\bsudo\s+chmod", "超级用户修改权限", "warning"),
    (r"\bkill\s+-9\s+1", "杀死 init 进程", "danger"),
    (r"\bmv\s+.*\s+/dev/null", "移动到黑洞设备", "danger"),
    (r"\b>\s*/dev/sd", "直接写入磁盘设备", "critical"),
]

WARNING_PATTERNS = [
    (r"\brm\s+-rf\s+", "递归删除操作", "warning"),
    (r"\bsudo\s+", "超级用户权限", "warning"),
    (r"\bgit\s+push\s+--force", "强制推送", "warning"),
    (r"\bgit\s+reset\s+--hard", "硬重置", "warning"),
    (r"\bdocker\s+rm", "删除容器", "warning"),
    (r"\bdocker\s+rmi", "删除镜像", "warning"),
    (r"\bpip\s+uninstall", "卸载 Python 包", "warning"),
    (r"\bnpm\s+uninstall", "卸载 Node 包", "warning"),
]


def assess_command_risk(command: str) -> CommandRisk:
    """
    多级风险评估：评估命令的危险等级

    返回:
        CommandRisk:
            level: "safe" | "warning" | "danger" | "critical"
            requires_confirmation: 是否需要用户确认
            auto_block: 是否自动拦截
    """
    for pattern, reason, level in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            if level == "critical":
                return CommandRisk(
                    level="critical",
                    reason=reason,
                    requires_confirmation=True,
                    auto_block=True,
                )
            elif level == "danger":
                return CommandRisk(
                    level="danger",
                    reason=reason,
                    requires_confirmation=True,
                    auto_block=False,
                )
            elif level == "warning":
                return CommandRisk(
                    level="warning",
                    reason=reason,
                    requires_confirmation=True,
                    auto_block=False,
                )

    for pattern, reason, level in WARNING_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return CommandRisk(
                level="warning",
                reason=reason,
                requires_confirmation=True,
                auto_block=False,
            )

    return CommandRisk(level="safe", reason="", requires_confirmation=False, auto_block=False)


def check_dangerous_command(command: str) -> Optional[str]:
    """
    检查命令是否危险（向后兼容接口）

    Args:
        command: 要检查的命令

    Returns:
        str: 危险原因，如果安全则返回 None
    """
    risk = assess_command_risk(command)
    if risk.level in ("danger", "critical"):
        return risk.reason
    return None


ASK_USER_TOOL_DEFINITION_OPENAI = {
    "type": "function",
    "function": {
        "name": "ask_user",
        "description": (
            "向用户提问以获取必要信息或授权。"
            "【必须调用的场景】1.用户需求极其模糊，你不知道该在哪几个文件中下手；"
            "2.准备执行删除大量文件、覆盖核心架构逻辑、修改数据库Schema等高危操作；"
            "3.测试代码反复报错超过3次，你无法理解为什么；"
            "4.需要用户提供密码、API Key等敏感信息；"
            "5.存在两种以上截然不同的技术方案，需要人类做决策。"
            "调用后静静等待人类指令，不要自己乱猜。"
            "【铁律】绝不提供 A/B/C/D 选项！请清晰列出选项，让用户明确说出他们想执行的动作"
            "（例如：请说出'删除文件夹'或'解释代码'）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "向用户提出的问题或确认信息（必须具体、明确，不能含糊。绝不使用A/B/C/D选项，而是让用户直接说出想执行的动作）"
                },
                "context": {
                    "type": "string",
                    "description": "问题的背景信息（为什么需要问用户，你目前遇到了什么困难）"
                }
            },
            "required": ["question"]
        }
    }
}

ASK_USER_TOOL_DEFINITION_ANTHROPIC = {
    "name": "ask_user",
    "description": (
        "向用户提问以获取必要信息或授权。"
        "【必须调用的场景】1.用户需求极其模糊，你不知道该在哪几个文件中下手；"
        "2.准备执行删除大量文件、覆盖核心架构逻辑、修改数据库Schema等高危操作；"
        "3.测试代码反复报错超过3次，你无法理解为什么；"
        "4.需要用户提供密码、API Key等敏感信息；"
        "5.存在两种以上截然不同的技术方案，需要人类做决策。"
        "调用后静静等待人类指令，不要自己乱猜。"
        "【铁律】绝不提供 A/B/C/D 选项！请清晰列出选项，让用户明确说出他们想执行的动作"
        "（例如：请说出'删除文件夹'或'解释代码'）。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "向用户提出的问题或确认信息（必须具体、明确，不能含糊。绝不使用A/B/C/D选项，而是让用户直接说出想执行的动作）"
            },
            "context": {
                "type": "string",
                "description": "问题的背景信息（为什么需要问用户，你目前遇到了什么困难）"
            }
        },
        "required": ["question"]
    }
}
