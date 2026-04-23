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
└─────────────────────────────────────────────────────────────────────┘

参考源码: claude-code-rev/src/tools/AskUserQuestionTool/
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ============================================================================
# 全局等待表 - 存储所有等待用户回答的 Future
# ============================================================================

_pending_questions: dict[str, asyncio.Future] = {}


def register_question(question_id: str, future: asyncio.Future):
    """注册一个等待用户回答的问题"""
    _pending_questions[question_id] = future
    logger.info(f"注册等待问题: {question_id}")


def resolve_question(question_id: str, answer: str):
    """用户回答了问题，解除阻塞"""
    future = _pending_questions.pop(question_id, None)
    if future and not future.done():
        future.set_result(answer)
        logger.info(f"用户回答了问题: {question_id} -> {answer[:100]}")
    else:
        logger.warning(f"未找到等待中的问题: {question_id}")


def cancel_all_questions():
    """取消所有等待中的问题"""
    for qid, future in _pending_questions.items():
        if not future.done():
            future.set_result("[用户未回答，已取消]")
    _pending_questions.clear()


# ============================================================================
# AskUser 工具定义
# ============================================================================

ASK_USER_TOOL_DEFINITION_OPENAI = {
    "type": "function",
    "function": {
        "name": "ask_user",
        "description": "向用户提问以获取必要信息。当遇到无法独立解决的逻辑问题、需要用户提供密码/前置条件、或连续失败需要人类指导时使用此工具。",
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "向用户提出的问题"
                },
                "context": {
                    "type": "string",
                    "description": "问题的背景信息（为什么需要问用户）"
                }
            },
            "required": ["question"]
        }
    }
}

ASK_USER_TOOL_DEFINITION_ANTHROPIC = {
    "name": "ask_user",
    "description": "向用户提问以获取必要信息。当遇到无法独立解决的逻辑问题、需要用户提供密码/前置条件、或连续失败需要人类指导时使用此工具。",
    "input_schema": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "向用户提出的问题"
            },
            "context": {
                "type": "string",
                "description": "问题的背景信息（为什么需要问用户）"
            }
        },
        "required": ["question"]
    }
}


# ============================================================================
# 安全拦截 - 危险命令黑名单
# ============================================================================

DANGEROUS_PATTERNS = [
    (r"\brm\s+-rf\s+/", "递归删除根目录"),
    (r"\brm\s+-rf\s+~", "递归删除用户目录"),
    (r"\brm\s+-rf\s+\*", "递归删除所有文件"),
    (r"\bchmod\s+777", "设置危险权限 777"),
    (r"\bchown\s+.*\s+/", "修改根目录所有者"),
    (r"\bdd\s+if=", "磁盘写入操作"),
    (r"\bmkfs\.", "格式化文件系统"),
    (r"\bformat\s+[A-Z]:", "格式化磁盘"),
    (r"\breboot", "重启系统"),
    (r"\bshutdown", "关闭系统"),
    (r"\binit\s+[06]", "切换运行级别"),
    (r"\b:\(\)\{\s*:\|\:&\s*\}", "Fork 炸弹"),
    (r"\bwget\s+.*\|\s*sh", "下载并执行脚本"),
    (r"\bcurl\s+.*\|\s*sh", "下载并执行脚本"),
    (r"\bsudo\s+rm", "超级用户删除"),
    (r"\bapt\s+remove", "卸载系统包"),
    (r"\byum\s+remove", "卸载系统包"),
    (r"\bsystemctl\s+stop", "停止系统服务"),
    (r"\biptables\s+-F", "清空防火墙规则"),
]

import re

def check_dangerous_command(command: str) -> Optional[str]:
    """
    检查命令是否危险
    
    Args:
        command: 要检查的命令
    
    Returns:
        str: 危险原因，如果安全则返回 None
    """
    for pattern, reason in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return reason
    return None
