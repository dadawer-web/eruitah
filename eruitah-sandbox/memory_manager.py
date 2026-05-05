"""
Eruitah 智能编程沙盒 - 记忆管理器 (Memory Manager)

本模块实现了"记忆折叠"机制，防止 Agent 在长对话中 Token 破产。

核心思想（来自 Claude Code 的 compact 服务）:
┌─────────────────────────────────────────────────────────────────────┐
│  Agent 改 Bug 超过 20 轮后，对话历史越来越长:                        │
│    消息1: 用户需求 (100 token)                                      │
│    消息2: AI 思考 (500 token)                                       │
│    消息3: 工具结果 (2000 token)                                     │
│    消息4: AI 修复 (500 token)                                       │
│    消息5: 编译报错 (3000 token)                                     │
│    ... 重复 20 轮 ...                                               │
│    总计: ~100,000 token → API 费用爆炸 + 响应极慢                    │
│                                                                     │
│  折叠后:                                                            │
│    摘要: "用户要求写快速排序，已创建 main.cpp，当前编译报错:          │
│           缺少分号，已尝试修复2次仍未成功" (500 token)                │
│    消息19: 最新编译报错 (3000 token)                                 │
│    消息20: AI 最新修复 (500 token)                                   │
│    总计: ~4,000 token → 顺畅继续 Debug                               │
└─────────────────────────────────────────────────────────────────────┘

参考源码:
    claude-code-rev/src/services/compact/compact.ts     (核心折叠实现)
    claude-code-rev/src/services/compact/autoCompact.ts  (自动折叠触发)
    claude-code-rev/src/services/compact/prompt.ts       (摘要生成提示词)
    claude-code-rev/src/services/contextCollapse/        (上下文坍缩框架)
"""

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Optional
from collections import OrderedDict

logger = logging.getLogger(__name__)

SUMMARY_STORE_DIR = os.environ.get(
    "ERUITAH_SUMMARY_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".summaries")
)

# ============================================================================
# 常量定义 - 对齐 TS 源码 compact.ts 和 autoCompact.ts
# ============================================================================

# 折叠触发: 对话轮数阈值
# 超过此轮数触发折叠，对应用户需求"超过 15 轮触发折叠"
COMPACT_TURN_THRESHOLD = 30

# 折叠触发: Token 总量阈值
# 对应 TS 源码 autoCompactThreshold = effectiveContextWindow - AUTOCOMPACT_BUFFER_TOKENS
COMPACT_TOKEN_THRESHOLD = 30_000

# 折叠后摘要最大长度（字符数）
# 对应用户需求"压缩成 500 字以内的摘要"
MAX_SUMMARY_LENGTH = 3000

# 折叠时保留的最近对话轮数
# 保留最近几轮的完整上下文，只折叠更早的历史
# 对应 TS 源码 partialCompactConversation 的 'up_to' 模式
KEEP_RECENT_TURNS = 5

# 摘要生成提示词 - 对齐 TS 源码 prompt.ts 中的 BASE_COMPACT_PROMPT
COMPACT_PROMPT = """你的任务是创建对话的详细摘要，重点关注用户的明确请求和你之前的操作。
摘要应详尽地捕获技术细节、代码模式和架构决策，这些对于在不丢失上下文的情况下继续开发工作至关重要。

在提供最终摘要之前，请将你的分析过程放在 <analysis> 标签中，按时间顺序分析每条消息：
1. 用户的明确请求和意图
2. 你处理用户请求的方法
3. 关键决策、技术概念和代码模式
4. 具体细节：文件名、代码片段、函数签名、文件编辑
5. 遇到的错误及修复方法
6. 特别注意用户的反馈，尤其是用户要求改变做法时

你的摘要应包含以下 9 个部分：

1. 核心需求与意图：详细描述用户的所有明确请求和意图
2. 关键技术概念：列出所有重要的技术概念、技术和框架
3. 文件与代码：列出具体文件和代码段，包括文件名、修改原因和关键代码片段
4. 错误与修复：列出所有遇到的错误及修复方法，注意用户反馈
5. 问题解决：记录已解决的问题和正在进行的排查工作
6. 所有用户消息：列出所有非工具结果的用户消息
7. 待办任务：列出所有明确的待办任务
8. 当前工作：精确描述摘要请求前正在进行的工作，包括文件名和代码片段
9. 下一步建议：列出与最近工作直接相关的下一步操作，引用最近的对话内容

请按以下格式输出：

<analysis>
[你的分析过程，确保所有要点都被彻底准确地覆盖]
</analysis>

<summary>
1. 核心需求与意图：
   [详细描述]

2. 关键技术概念：
   - [概念1]
   - [概念2]

3. 文件与代码：
   - [文件名1]
      - [该文件的重要性]
      - [修改内容摘要]
      - [关键代码片段]

4. 错误与修复：
   - [错误描述]：
     - [修复方法]

5. 问题解决：
   [已解决问题和进行中的排查]

6. 所有用户消息：
   - [用户消息内容]

7. 待办任务：
   - [任务1]

8. 当前工作：
   [精确描述当前工作]

9. 下一步建议：
   [下一步操作]
</summary>

以下是对话历史：
{conversation}

请根据以上对话生成摘要："""


# ============================================================================
# 数据结构
# ============================================================================

@dataclass
class CompactStats:
    """
    折叠统计信息

    对应 TS 源码 compact.ts 中的 Stats 结构
    """
    # 当前对话轮数
    turn_count: int = 0
    # 估算的 Token 总量
    estimated_tokens: int = 0
    # 是否已触发过折叠
    has_compacted: bool = False
    # 折叠次数
    compact_count: int = 0
    # 当前摘要内容
    current_summary: str = ""


@dataclass
class CompactDecision:
    """
    折叠决策结果

    对应 TS 源码 shouldAutoCompact() 的返回值
    """
    # 是否需要折叠
    should_compact: bool = False
    # 触发原因
    reason: str = ""
    # 当前 Token 数
    current_tokens: int = 0
    # 当前轮数
    current_turns: int = 0


# ============================================================================
# Token 估算 - 对应 TS 源码中的 token 计数逻辑
# ============================================================================

def estimate_tokens(messages: list[dict]) -> int:
    """
    估算消息列表的 Token 总量

    对应 TS 源码中通过 API 返回的 usage.input_tokens 计算。
    在 Python 端，我们使用 tiktoken 库（如果可用）进行精确估算，
    否则使用简单的字符数/4 近似法。

    估算策略:
    - 优先使用 tiktoken（精确，与 OpenAI 计算方式一致）
    - 回退到字符数/4（粗略但快速，适用于所有模型）

    Args:
        messages: 消息列表，格式为 [{"role": "...", "content": "..."}]

    Returns:
        int: 估算的 Token 数
    """
    # =========================================================
    # 🚨 终极防御：包容各种奇葩传参（字符串、单字典、列表）
    # =========================================================
    if isinstance(messages, str):
        # 如果外面传进来的是纯字符串，我们把它包成标准的 message 格式
        messages = [{"role": "user", "content": messages}]
    elif isinstance(messages, dict):
        # 如果传进来的是单个字典，包成列表
        messages = [messages]
    elif not isinstance(messages, list):
        # 如果是烂数据（比如 None），直接返回 0
        return 0
    # =========================================================

    # 尝试使用 tiktoken
    try:
        import tiktoken
        encoding = tiktoken.get_encoding("cl100k_base")

        total_tokens = 0
        for msg in messages:
            # 消息格式开销（role 标记、分隔符等）
            # 对应 OpenAI 的消息格式: 每条消息约 4 token 开销
            total_tokens += 4

            content = msg.get("content", "")
            if isinstance(content, str):
                total_tokens += len(encoding.encode(content))
            elif isinstance(content, list):
                # 多模态内容（文本 + 工具调用等）
                for block in content:
                    if isinstance(block, dict):
                        block_text = block.get("text", "") or block.get("content", "") or json.dumps(block, ensure_ascii=False)
                        total_tokens += len(encoding.encode(block_text))
                    elif isinstance(block, str):
                        total_tokens += len(encoding.encode(block))

        return total_tokens

    except ImportError:
        # tiktoken 不可用，使用字符数/4 近似
        # 这是一个粗略估算: 英文约 4 字符/token，中文约 2 字符/token
        # 取平均 3 字符/token 作为折中
        total_chars = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        total_chars += len(json.dumps(block, ensure_ascii=False))
                    elif isinstance(block, str):
                        total_chars += len(block)

        # 每条消息约 4 token 格式开销
        format_overhead = len(messages) * 4
        return total_chars // 3 + format_overhead


# ============================================================================
# 折叠触发判断 - 对应 TS 源码 shouldAutoCompact()
# ============================================================================

def should_compact(
    messages: list[dict],
    turn_count: int = 0,
    token_threshold: int = COMPACT_TOKEN_THRESHOLD,
    turn_threshold: int = COMPACT_TURN_THRESHOLD,
) -> CompactDecision:
    """
    判断是否需要触发记忆折叠

    对应 TS 源码 shouldAutoCompact() 的核心逻辑:
    1. 计算 Token 总量
    2. 检查是否超过 Token 阈值
    3. 检查是否超过轮数阈值
    4. 返回折叠决策

    触发条件（满足任一即触发）:
    - Token 总量 >= 30,000
    - 对话轮数 >= 15

    Args:
        messages: 当前消息列表
        turn_count: 当前对话轮数
        token_threshold: Token 阈值
        turn_threshold: 轮数阈值

    Returns:
        CompactDecision: 折叠决策
    """
    estimated_tokens = estimate_tokens(messages)

    # 条件 1: Token 超过阈值
    if estimated_tokens >= token_threshold:
        return CompactDecision(
            should_compact=True,
            reason=f"Token 总量 ({estimated_tokens}) 超过阈值 ({token_threshold})",
            current_tokens=estimated_tokens,
            current_turns=turn_count,
        )

    # 条件 2: 轮数超过阈值
    if turn_count >= turn_threshold:
        return CompactDecision(
            should_compact=True,
            reason=f"对话轮数 ({turn_count}) 超过阈值 ({turn_threshold})",
            current_tokens=estimated_tokens,
            current_turns=turn_count,
        )

    return CompactDecision(
        should_compact=False,
        current_tokens=estimated_tokens,
        current_turns=turn_count,
    )


# ============================================================================
# 对话历史格式化 - 将消息列表转为可读文本
# ============================================================================

def _format_messages_for_summary(messages: list[dict]) -> str:
    """
    将消息列表格式化为可读文本，供摘要模型处理

    对应 TS 源码 compact.ts 中构建摘要请求前的消息格式化。

    格式:
        [user]: 帮我写一个快速排序
        [assistant]: 好的，我来创建一个快速排序文件...
        [tool_result(bash)]: 编译成功
        [assistant]: 我发现编译报错了...

    Args:
        messages: 消息列表

    Returns:
        str: 格式化后的对话文本
    """
    parts = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")

        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            # 处理多块内容（文本 + 工具调用 + 工具结果）
            text_parts = []
            for block in content:
                if isinstance(block, dict):
                    block_type = block.get("type", "")
                    if block_type == "text":
                        text_parts.append(block.get("text", ""))
                    elif block_type == "tool_use":
                        tool_name = block.get("name", "unknown")
                        tool_input = block.get("input", {})
                        text_parts.append(f"[调用工具: {tool_name}({json.dumps(tool_input, ensure_ascii=False)[:200]})]")
                    elif block_type == "tool_result":
                        result_text = block.get("content", "")
                        if isinstance(result_text, str) and len(result_text) > 300:
                            result_text = result_text[:300] + "..."
                        text_parts.append(f"[工具结果: {result_text}]")
                    else:
                        text_parts.append(json.dumps(block, ensure_ascii=False)[:200])
                elif isinstance(block, str):
                    text_parts.append(block)
            text = "\n".join(text_parts)
        else:
            text = str(content)

        # 截断过长的单条消息
        if len(text) > 2000:
            text = text[:2000] + "... [消息已截断]"

        parts.append(f"[{role}]: {text}")

    return "\n\n".join(parts)


# ============================================================================
# 摘要生成 - 对应 TS 源码 streamCompactSummary()
# ============================================================================

def _format_compact_summary(summary: str) -> str:
    """
    格式化折叠摘要 - 对标 claude-code prompt.ts 的 formatCompactSummary()

    1. 剥离 <analysis> 草稿区（仅用于提升摘要质量，无信息价值）
    2. 将 <summary> XML 标签替换为可读的节标题
    3. 清理多余空行
    """
    formatted = summary

    formatted = re.sub(r'<analysis>[\s\S]*?</analysis>', '', formatted)

    summary_match = re.search(r'<summary>([\s\S]*?)</summary>', formatted)
    if summary_match:
        content = summary_match.group(1) or ''
        formatted = formatted.replace(
            summary_match.group(0),
            f"摘要:\n{content.strip()}",
        )

    formatted = re.sub(r'\n\n+', '\n\n', formatted)

    return formatted.strip()


def generate_summary(
    messages: list[dict],
    api_key: Optional[str] = None,
    model: str = "mimo-v2.5-pro",
    base_url: Optional[str] = None,
) -> str:
    """
    调用小模型生成对话摘要

    对应 TS 源码 streamCompactSummary() 的核心逻辑:
    1. 格式化对话历史
    2. 构建摘要请求
    3. 调用 LLM 生成摘要
    4. 截断到最大长度

    使用子模型（如 mimo-v2.5-pro）而非主模型生成摘要，
    因为摘要生成不需要强推理能力，子模型更快更便宜。

    对应 TS 源码中的设计:
        - 使用独立的小模型调用（不占用主对话的上下文）
        - 摘要包含 9 个关键部分（Primary Request、Errors、Pending Tasks 等）

    Args:
        messages: 要折叠的消息列表
        api_key: API Key
        model: 用于生成摘要的模型名称
        base_url: API 基础 URL

    Returns:
        str: 生成的摘要文本（不超过 MAX_SUMMARY_LENGTH 字符）
    """
    conversation_text = _format_messages_for_summary(messages)

    # 如果对话文本本身就很短，不需要摘要
    if len(conversation_text) <= MAX_SUMMARY_LENGTH:
        return conversation_text

    prompt = COMPACT_PROMPT.format(conversation=conversation_text)

    # 尝试使用 OpenAI 兼容 API（支持通义千问、DeepSeek 等国产模型）
    try:
        from openai import OpenAI

        client_kwargs = {}
        if api_key:
            client_kwargs["api_key"] = api_key
        if base_url:
            client_kwargs["base_url"] = base_url

        client = OpenAI(**client_kwargs)

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一个对话摘要专家，擅长将长对话压缩为结构化的技术摘要。只输出文本，不要调用任何工具。"},
                {"role": "user", "content": prompt},
            ],
            max_tokens=4000,
            temperature=0.3,
        )

        raw_summary = response.choices[0].message.content or ""
        summary = _format_compact_summary(raw_summary)

    except ImportError:
        # OpenAI 库不可用，使用简单的截断策略
        logger.warning("openai 库不可用，使用简单截断策略生成摘要")
        summary = _simple_truncate_summary(messages)
    except Exception as e:
        logger.warning(f"摘要生成失败: {e}，使用简单截断策略")
        summary = _simple_truncate_summary(messages)

    # 确保摘要不超过最大长度
    if len(summary) > MAX_SUMMARY_LENGTH:
        summary = summary[:MAX_SUMMARY_LENGTH] + "..."

    return summary.strip()


def _simple_truncate_summary(messages: list[dict]) -> str:
    """
    简单截断策略 - 当 LLM 不可用时的回退方案

    提取每条消息的第一行，拼接成简要摘要。
    """
    parts = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    content = block.get("text", "")
                    break
            else:
                continue

        if isinstance(content, str) and content.strip():
            first_line = content.strip().split("\n")[0][:100]
            parts.append(f"[{role}] {first_line}")

    return "\n".join(parts[:20])


# ============================================================================
# 核心折叠函数 - 对应 TS 源码 compactConversation()
# ============================================================================

def compact_messages(
    messages: list[dict],
    keep_recent: int = KEEP_RECENT_TURNS,
    summary_api_key: Optional[str] = None,
    summary_model: str = "mimo-v2.5-pro",
    summary_base_url: Optional[str] = None,
) -> list[dict]:
    """
    执行记忆折叠 - 核心入口函数

    对应 TS 源码 compactConversation() 的核心逻辑:
    1. 将消息分为"待折叠"和"保留"两部分
    2. 对"待折叠"部分生成摘要
    3. 用摘要替换原有消息
    4. 返回折叠后的消息列表

    折叠策略（对应 TS 源码 partialCompactConversation 'up_to' 模式）:
    ┌──────────────────────────────────────────────────────────────┐
    │  原始消息列表:                                                │
    │    [消息1] [消息2] ... [消息10] | [消息11] ... [消息15]       │
    │    ←── 待折叠部分 ──────────→   ←── 保留部分 ──→             │
    │                                                                │
    │  折叠后:                                                      │
    │    [摘要消息] | [消息11] ... [消息15]                          │
    │    ← 500 token →  ←── 完整上下文 ──→                         │
    └──────────────────────────────────────────────────────────────┘

    保留最近几轮的完整上下文，因为:
    - 最近的对话包含当前工作状态
    - 编译报错等关键信息通常在最近几轮
    - Agent 需要完整上下文来决定下一步操作

    Args:
        messages: 当前消息列表
        keep_recent: 保留最近几轮对话（不折叠）
        summary_api_key: 摘要生成 API Key
        summary_model: 摘要生成模型
        summary_base_url: 摘要生成 API URL

    Returns:
        list[dict]: 折叠后的消息列表

    Example:
        >>> messages = [
        ...     {"role": "user", "content": "帮我写快速排序"},
        ...     {"role": "assistant", "content": "好的..."},
        ...     # ... 20 轮对话 ...
        ... ]
        >>> compacted = compact_messages(messages, keep_recent=5)
        >>> # compacted[0] 是摘要，后面是最近 5 轮的完整对话
    """
    if len(messages) <= keep_recent * 2:
        # 消息太少，不需要折叠
        logger.info(f"消息数 ({len(messages)}) 少于保留阈值 ({keep_recent * 2})，跳过折叠")
        return messages

    # ------------------------------------------------------------------
    # 第一步: 分割消息 - 对应 TS 源码中的 pivot 分割
    # ------------------------------------------------------------------
    # 保留最近 keep_recent 轮（一轮 = 一对 user + assistant 消息）
    # 计算分割点: 从后往前数，保留 keep_recent 对 user/assistant 消息
    split_index = len(messages)
    user_assistant_count = 0

    for i in range(len(messages) - 1, -1, -1):
        role = messages[i].get("role", "")
        if role in ("user", "assistant"):
            user_assistant_count += 1
            if user_assistant_count >= keep_recent * 2:
                split_index = i
                break

    # 确保分割点不越界
    split_index = max(0, split_index)

    old_messages = messages[:split_index]
    recent_messages = messages[split_index:]

    if not old_messages:
        return messages

    # ------------------------------------------------------------------
    # 第二步: 生成摘要 - 对应 TS 源码 streamCompactSummary()
    # ------------------------------------------------------------------
    logger.info(f"正在折叠 {len(old_messages)} 条历史消息...")

    summary = generate_summary(
        messages=old_messages,
        api_key=summary_api_key,
        model=summary_model,
        base_url=summary_base_url,
    )

    logger.info(f"摘要生成完成: {len(summary)} 字符")

    # ------------------------------------------------------------------
    # 第三步: 构建折叠后的消息列表
    # 对应 TS 源码中 getCompactUserSummaryMessage()
    # ------------------------------------------------------------------
    # 将摘要作为一条 user 消息插入，附带上下文说明
    # 这样大模型能理解之前的对话发生了什么
    summary_message = {
        "role": "user",
        "content": (
            f"[系统: 以下是对话历史的摘要，原始对话已被折叠以节省 Token]\n\n"
            f"{summary}\n\n"
            f"[系统: 以上为历史摘要，请基于此摘要和后续对话继续工作。"
            f"不要询问已折叠的内容，直接继续当前任务。]"
        ),
    }

    # 折叠后的消息列表: 摘要 + 最近对话
    compacted = [summary_message] + recent_messages

    logger.info(
        f"折叠完成: {len(messages)} 条消息 → {len(compacted)} 条消息 "
        f"(摘要 {len(summary)} 字符)"
    )

    return compacted


# ============================================================================
# 便捷类 - 对话管理器
# ============================================================================

class ConversationMemoryManager:
    """
    对话记忆管理器 - 封装折叠逻辑的便捷类

    对应 TS 源码中 autoCompactIfNeeded() 的封装逻辑。
    在 Agent 循环的每一步调用 check_and_compact()，
    自动判断是否需要折叠并执行。

    Usage:
        >>> manager = ConversationMemoryManager()
        >>> # 在 Agent 循环中:
        >>> messages = manager.check_and_compact(messages, turn_count=turn)
    """

    def __init__(
        self,
        token_threshold: int = COMPACT_TOKEN_THRESHOLD,
        turn_threshold: int = COMPACT_TURN_THRESHOLD,
        keep_recent: int = KEEP_RECENT_TURNS,
        summary_api_key: Optional[str] = None,
        summary_model: str = "mimo-v2.5-pro",
        summary_base_url: Optional[str] = None,
    ):
        self.token_threshold = token_threshold
        self.turn_threshold = turn_threshold
        self.keep_recent = keep_recent
        self.summary_api_key = summary_api_key
        self.summary_model = summary_model
        self.summary_base_url = summary_base_url
        self.stats = CompactStats()

    def check_and_compact(
        self,
        messages: list[dict],
        turn_count: int = 0,
    ) -> tuple[list[dict], bool]:
        """
        检查并执行记忆折叠

        对应 TS 源码 autoCompactIfNeeded() 的逻辑:
        1. 判断是否需要折叠
        2. 如果需要，执行折叠
        3. 返回折叠后的消息列表

        Args:
            messages: 当前消息列表
            turn_count: 当前对话轮数

        Returns:
            (折叠后的消息列表, 是否执行了折叠)
        """
        # 更新统计
        self.stats.turn_count = turn_count
        self.stats.estimated_tokens = estimate_tokens(messages)

        # 判断是否需要折叠
        decision = should_compact(
            messages=messages,
            turn_count=turn_count,
            token_threshold=self.token_threshold,
            turn_threshold=self.turn_threshold,
        )

        if not decision.should_compact:
            return messages, False

        logger.info(f"触发记忆折叠: {decision.reason}")

        # 执行折叠
        compacted = compact_messages(
            messages=messages,
            keep_recent=self.keep_recent,
            summary_api_key=self.summary_api_key,
            summary_model=self.summary_model,
            summary_base_url=self.summary_base_url,
        )

        # 更新统计
        self.stats.has_compacted = True
        self.stats.compact_count += 1
        self.stats.estimated_tokens = estimate_tokens(compacted)

        return compacted, True


# ============================================================================
# LRU 上下文缓存 - 模拟操作系统的 LRU 页面置换算法
# ============================================================================

class LRUContextCache:
    """
    LRU 上下文缓存 - 模拟操作系统的 LRU 页面置换算法

    核心思想（来自 408 操作系统知识）:
    ┌─────────────────────────────────────────────────────────────────────┐
    │  物理内存有限，不能把所有页面都加载进来。                             │
    │  LRU 算法: 最近最少使用的页面，优先被换出。                          │
    │                                                                     │
    │  映射到 Agent 上下文:                                               │
    │  - 物理内存 = Token 预算                                           │
    │  - 页面 = 对话轮次                                                  │
    │  - 换出 = 折叠/摘要                                                │
    │  - 访问 = Agent 引用该轮对话                                        │
    │                                                                     │
    │  实现:                                                              │
    │  ┌──────┬──────┬──────┬──────┬──────┬──────┐                       │
    │  │ Turn1│ Turn5│ Turn8│ Turn9│Turn12│Turn15│ ← 最近访问的轮次      │
    │  │ LRU  │      │      │      │      │ MRU  │                       │
    │  └──────┴──────┴──────┴──────┴──────┴──────┘                       │
    │    ↑                                                                │
    │    └── 最久未访问，优先折叠                                          │
    └─────────────────────────────────────────────────────────────────────┘
    """

    MAX_CACHE_ENTRIES = 32

    def __init__(self, max_entries: int = MAX_CACHE_ENTRIES):
        self._cache: OrderedDict[str, dict] = OrderedDict()
        self.max_entries = max_entries
        self._access_log: list[tuple[str, float]] = []

    def put(self, key: str, context: dict):
        """缓存一个上下文条目"""
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = {
            **context,
            "cached_at": time.time(),
            "access_count": context.get("access_count", 0) + 1,
        }
        self._cache.move_to_end(key)
        while len(self._cache) > self.max_entries:
            evicted_key, evicted_value = self._cache.popitem(last=False)
            logger.info(f"LRU 淘汰上下文: {evicted_key} (访问 {evicted_value.get('access_count', 0)} 次)")

    def get(self, key: str) -> Optional[dict]:
        """获取缓存条目（同时更新 LRU 顺序）"""
        if key in self._cache:
            self._cache.move_to_end(key)
            entry = self._cache[key]
            entry["access_count"] = entry.get("access_count", 0) + 1
            entry["last_accessed"] = time.time()
            return entry
        return None

    def touch(self, key: str):
        """标记访问（不返回数据，只更新 LRU 顺序）"""
        if key in self._cache:
            self._cache.move_to_end(key)
            self._cache[key]["access_count"] = self._cache[key].get("access_count", 0) + 1
            self._cache[key]["last_accessed"] = time.time()

    def evict(self, key: str) -> Optional[dict]:
        """手动淘汰一个条目"""
        return self._cache.pop(key, None)

    def get_lru_entries(self, count: int = 5) -> list[tuple[str, dict]]:
        """获取最久未访问的 N 个条目（用于折叠决策）"""
        entries = list(self._cache.items())
        return entries[:count]

    def get_stats(self) -> dict:
        """获取缓存统计"""
        total_access = sum(e.get("access_count", 0) for e in self._cache.values())
        return {
            "entries": len(self._cache),
            "max_entries": self.max_entries,
            "total_accesses": total_access,
            "hit_rate": 0.0,
        }


# ============================================================================
# 摘要持久化 - 将折叠后的摘要保存到磁盘
# ============================================================================

class SummaryStore:
    """
    摘要持久化存储

    当对话超过一定长度，调用大模型对前 10 轮对话进行"语义压缩"，
    将其转化为持久化的摘要节点，主上下文仅保留摘要。

    存储:
    ┌─────────────────────────────────────────────────────────────────────┐
    │  .summaries/                                                        │
    │    session_abc123/                                                   │
    │      compact_001.json  ← 第1次折叠的摘要                             │
    │      compact_002.json  ← 第2次折叠的摘要                             │
    │      index.json        ← 摘要索引                                   │
    └─────────────────────────────────────────────────────────────────────┘
    """

    def __init__(self, store_dir: str = SUMMARY_STORE_DIR):
        self.store_dir = store_dir

    def _session_dir(self, session_id: str) -> str:
        d = os.path.join(self.store_dir, session_id)
        os.makedirs(d, exist_ok=True)
        return d

    def save_summary(
        self,
        session_id: str,
        compact_index: int,
        summary: str,
        original_turn_range: tuple[int, int],
        token_saved: int = 0,
    ):
        """保存一个摘要节点"""
        sdir = self._session_dir(session_id)

        entry = {
            "compact_index": compact_index,
            "summary": summary,
            "original_turn_range": list(original_turn_range),
            "token_saved": token_saved,
            "created_at": time.time(),
        }

        filename = f"compact_{compact_index:03d}.json"
        filepath = os.path.join(sdir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False, indent=2)

        self._update_index(session_id, compact_index, entry)

        logger.info(
            f"摘要已持久化: session={session_id}, compact={compact_index}, "
            f"turns={original_turn_range}, saved={token_saved} tokens"
        )

    def load_summaries(self, session_id: str) -> list[dict]:
        """加载一个会话的所有摘要"""
        sdir = self._session_dir(session_id)
        summaries = []

        index_path = os.path.join(sdir, "index.json")
        if os.path.exists(index_path):
            try:
                with open(index_path, "r", encoding="utf-8") as f:
                    index = json.load(f)
                for entry in index.get("entries", []):
                    filename = f"compact_{entry['compact_index']:03d}.json"
                    filepath = os.path.join(sdir, filename)
                    if os.path.exists(filepath):
                        with open(filepath, "r", encoding="utf-8") as f:
                            summaries.append(json.load(f))
            except Exception as e:
                logger.error(f"加载摘要索引失败: {e}")

        return summaries

    def build_context_from_summaries(self, session_id: str) -> str:
        """从所有持久化摘要构建上下文"""
        summaries = self.load_summaries(session_id)
        if not summaries:
            return ""

        parts = ["[系统: 以下是之前对话的持久化摘要]\n"]
        for s in summaries:
            turn_range = s.get("original_turn_range", [0, 0])
            parts.append(
                f"--- 摘要 #{s['compact_index']} (第 {turn_range[0]}-{turn_range[1]} 轮) ---\n"
                f"{s['summary']}\n"
            )
        parts.append("[系统: 以上为历史摘要，请基于此继续工作。]")

        return "\n".join(parts)

    def _update_index(self, session_id: str, compact_index: int, entry: dict):
        """更新摘要索引"""
        sdir = self._session_dir(session_id)
        index_path = os.path.join(sdir, "index.json")

        index = {"entries": []}
        if os.path.exists(index_path):
            try:
                with open(index_path, "r", encoding="utf-8") as f:
                    index = json.load(f)
            except Exception:
                pass

        index_entry = {
            "compact_index": compact_index,
            "turn_range": entry.get("original_turn_range", []),
            "token_saved": entry.get("token_saved", 0),
            "created_at": entry.get("created_at", 0),
        }

        index["entries"].append(index_entry)
        index["total_compacts"] = len(index["entries"])
        index["total_tokens_saved"] = sum(e.get("token_saved", 0) for e in index["entries"])

        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

    def cleanup_session(self, session_id: str):
        """清理一个会话的所有摘要"""
        import shutil
        sdir = self._session_dir(session_id)
        if os.path.exists(sdir):
            shutil.rmtree(sdir)


_local_lru_cache: Optional[LRUContextCache] = None
_local_summary_store: Optional[SummaryStore] = None


def get_lru_cache() -> LRUContextCache:
    global _local_lru_cache
    if _local_lru_cache is None:
        _local_lru_cache = LRUContextCache()
    return _local_lru_cache


def get_summary_store() -> SummaryStore:
    global _local_summary_store
    if _local_summary_store is None:
        _local_summary_store = SummaryStore()
    return _local_summary_store


# ============================================================================
# 语义压缩引擎 - LRU 滑动窗口 + 小模型蒸馏
# ============================================================================

SUMMARY_COMPACT_THRESHOLD = 0.8
SUMMARY_COMPACT_TURNS = 10
SUMMARY_MAX_TARGET_TOKENS = 200


@dataclass
class LRUCompactDecision:
    should_compact: bool = False
    reason: str = ""
    turns_to_compact: int = 0
    current_usage_ratio: float = 0.0


def should_compact_context(
    messages: list[dict],
    token_budget: int = 100000,
    threshold: float = SUMMARY_COMPACT_THRESHOLD,
) -> LRUCompactDecision:
    """
    判断是否需要压缩上下文

    对应 408 操作系统的页面置换决策:
    - 当内存使用率达到阈值时，触发页面换出
    - 这里: 当 Token 使用率达到 80% 时，触发对话压缩

    Args:
        messages: 当前对话消息列表
        token_budget: Token 预算上限
        threshold: 触发压缩的使用率阈值

    Returns:
        CompactDecision: 压缩决策
    """
    total_chars = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    total_chars += len(str(block.get("text", "")))

    estimated_tokens = total_chars // 3
    usage_ratio = estimated_tokens / token_budget if token_budget > 0 else 0.0

    if usage_ratio >= threshold:
        turns_to_compact = min(SUMMARY_COMPACT_TURNS, len(messages) // 2)
        return LRUCompactDecision(
            should_compact=True,
            reason=f"Token 使用率 {usage_ratio:.0%} 超过阈值 {threshold:.0%}",
            turns_to_compact=turns_to_compact,
            current_usage_ratio=usage_ratio,
        )

    return LRUCompactDecision(
        should_compact=False,
        current_usage_ratio=usage_ratio,
    )


def compact_messages_with_lru(
    messages: list[dict],
    turns_to_compact: int = SUMMARY_COMPACT_TURNS,
    session_id: str = "",
) -> tuple[list[dict], str]:
    """
    基于 LRU 的滑动窗口压缩

    对应操作系统的 LRU 页面置换:
    ┌─────────────────────────────────────────────────────────────────────┐
    │  内存页:  [P1] [P2] [P3] [P4] [P5] [P6] [P7] [P8]               │
    │  访问时间:  1    3    5    7    9   11   13   15                   │
    │            ↑ LRU                                                 │
    │            └── 最久未访问，优先换出                                │
    │                                                                     │
    │  映射到对话:                                                        │
    │  对话轮:  [T1] [T2] [T3] [T4] [T5] [T6] [T7] [T8]               │
    │  时间戳:   1    2    3    4    5    6    7    8                    │
    │            ↑ LRU                                                   │
    │            └── 最早的对话，优先折叠                                  │
    │                                                                     │
    │  压缩后:                                                            │
    │  [摘要: T1-T5 的核心内容] [T6] [T7] [T8]                          │
    │   ↑ 持久化到磁盘                                      ↑ 保留原始  │
    └─────────────────────────────────────────────────────────────────────┘

    Args:
        messages: 当前对话消息列表
        turns_to_compact: 要压缩的轮数
        session_id: 会话 ID（用于持久化）

    Returns:
        (压缩后的消息列表, 摘要文本)
    """
    if len(messages) <= turns_to_compact + 2:
        return messages, ""

    system_messages = []
    compactable = []
    recent = []

    for msg in messages:
        role = msg.get("role", "")
        if role == "system":
            system_messages.append(msg)
        else:
            compactable.append(msg)

    if len(compactable) <= turns_to_compact:
        return messages, ""

    to_compact = compactable[:turns_to_compact]
    recent = compactable[turns_to_compact:]

    summary_text = _generate_summary_from_messages(to_compact)

    if session_id:
        store = get_summary_store()
        compact_index = len(store.load_summaries(session_id)) + 1
        start_turn = 1
        end_turn = turns_to_compact
        estimated_tokens = sum(
            len(str(m.get("content", ""))) // 3 for m in to_compact
        )
        store.save_summary(
            session_id=session_id,
            compact_index=compact_index,
            summary=summary_text,
            original_turn_range=(start_turn, end_turn),
            token_saved=estimated_tokens,
        )

    summary_message = {
        "role": "user",
        "content": f"[系统: 以下是对话历史的摘要]\n{summary_text}\n[系统: 以上为历史摘要，请基于此继续工作。]",
    }

    lru_cache = get_lru_cache()
    for msg in recent:
        content = msg.get("content", "")
        key = hashlib.md5(str(content).encode()).hexdigest()[:8]
        lru_cache.put(key, msg)

    result = system_messages + [summary_message] + recent
    return result, summary_text


def _generate_summary_from_messages(messages: list[dict]) -> str:
    """
    从消息列表生成摘要

    策略:
    1. 如果有 LLM 客户端可用，调用小模型进行语义蒸馏
    2. 否则，使用提取式摘要（提取关键信息）

    对应 408 知识点:
    - 生成式摘要 = 小模型蒸馏（Qwen-Turbo）
    - 提取式摘要 = 关键信息提取（正则匹配）
    """
    try:
        summary = _try_llm_summary(messages)
        if summary:
            return summary
    except Exception:
        pass

    return _extractive_summary(messages)


def _try_llm_summary(messages: list[dict]) -> Optional[str]:
    """尝试使用 LLM 生成摘要（子模型蒸馏）"""
    try:
        from openai import OpenAI

        api_key = os.environ.get("OPENAI_API_KEY")
        base_url = os.environ.get("OPENAI_BASE_URL")
        model = os.environ.get("ERUITAH_SUMMARY_MODEL", "mimo-v2.5-pro")

        if not api_key:
            return None

        if base_url and not base_url.endswith("/v1"):
            base_url = base_url.rstrip("/") + "/v1"

        client = OpenAI(api_key=api_key, base_url=base_url)

        conversation_text = _format_messages_for_summary(messages)

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是一个对话摘要助手。请将以下对话历史压缩为一段简洁的摘要，"
                        f"不超过 {SUMMARY_MAX_TARGET_TOKENS} 字。"
                        "保留关键决策、代码修改、文件路径和错误信息。"
                    ),
                },
                {"role": "user", "content": conversation_text},
            ],
            max_tokens=300,
            temperature=0.3,
        )

        summary = response.choices[0].message.content.strip()
        if summary:
            logger.info(f"LLM 语义蒸馏成功: {len(conversation_text)} → {len(summary)} 字符")
            return summary

    except Exception as e:
        logger.debug(f"LLM 摘要生成失败: {e}")

    return None


def _extractive_summary(messages: list[dict]) -> str:
    """提取式摘要：从消息中提取关键信息"""
    import hashlib as _hashlib

    key_points = []
    file_operations = []
    errors = []
    decisions = []

    for msg in messages:
        content = str(msg.get("content", ""))
        role = msg.get("role", "")

        if not content or len(content) < 10:
            continue

        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue

            if any(kw in line.lower() for kw in ["文件创建成功", "文件编辑成功", "file created", "file edited"]):
                file_operations.append(line[:150])
            elif any(kw in line.lower() for kw in ["error", "错误", "失败", "failed", "exception"]):
                errors.append(line[:150])
            elif any(kw in line.lower() for kw in ["决定", "选择", "方案", "approach", "decision"]):
                decisions.append(line[:150])

        if role == "user" and len(content) > 5:
            key_points.append(f"用户: {content[:100]}")
        elif role == "assistant" and len(content) > 20:
            first_line = content.splitlines()[0][:100]
            key_points.append(f"助手: {first_line}")

    parts = []
    if key_points:
        parts.append("关键对话:\n" + "\n".join(f"  - {p}" for p in key_points[:8]))
    if file_operations:
        parts.append("文件操作:\n" + "\n".join(f"  - {p}" for p in file_operations[:5]))
    if errors:
        parts.append("错误记录:\n" + "\n".join(f"  - {p}" for p in errors[:3]))
    if decisions:
        parts.append("决策记录:\n" + "\n".join(f"  - {p}" for p in decisions[:3]))

    if not parts:
        first_user_msg = ""
        for msg in messages:
            if msg.get("role") == "user":
                first_user_msg = str(msg.get("content", ""))[:200]
                break
        return f"对话摘要: 用户请求了 {first_user_msg[:100]}"

    return "\n".join(parts)


def _format_messages_for_summary(messages: list[dict]) -> str:
    """格式化消息列表用于摘要"""
    parts = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = str(msg.get("content", ""))

        if len(content) > 500:
            content = content[:500] + "..."

        parts.append(f"[{role}]: {content}")

    return "\n".join(parts)
