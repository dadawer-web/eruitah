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
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ============================================================================
# 常量定义 - 对齐 TS 源码 compact.ts 和 autoCompact.ts
# ============================================================================

# 折叠触发: 对话轮数阈值
# 超过此轮数触发折叠，对应用户需求"超过 15 轮触发折叠"
COMPACT_TURN_THRESHOLD = 15

# 折叠触发: Token 总量阈值
# 对应 TS 源码 autoCompactThreshold = effectiveContextWindow - AUTOCOMPACT_BUFFER_TOKENS
COMPACT_TOKEN_THRESHOLD = 30_000

# 折叠后摘要最大长度（字符数）
# 对应用户需求"压缩成 500 字以内的摘要"
MAX_SUMMARY_LENGTH = 500

# 折叠时保留的最近对话轮数
# 保留最近几轮的完整上下文，只折叠更早的历史
# 对应 TS 源码 partialCompactConversation 的 'up_to' 模式
KEEP_RECENT_TURNS = 5

# 摘要生成提示词 - 对齐 TS 源码 prompt.ts 中的 BASE_COMPACT_PROMPT
COMPACT_PROMPT = """你是一个对话摘要专家。请将以下对话历史压缩成一段简洁的摘要。

要求:
1. 摘要不超过 500 字
2. 必须包含: 用户的核心需求、已完成的操作、当前的错误状态、未完成的任务
3. 保留关键文件路径和函数名
4. 保留编译/运行错误的关键信息
5. 省略冗余的中间过程，只保留对后续工作有参考价值的信息

对话历史:
{conversation}

请生成摘要:"""


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

def generate_summary(
    messages: list[dict],
    api_key: Optional[str] = None,
    model: str = "qwen-turbo",
    base_url: Optional[str] = None,
) -> str:
    """
    调用小模型生成对话摘要

    对应 TS 源码 streamCompactSummary() 的核心逻辑:
    1. 格式化对话历史
    2. 构建摘要请求
    3. 调用 LLM 生成摘要
    4. 截断到最大长度

    使用小模型（如 qwen-turbo）而非主模型生成摘要，
    因为摘要生成不需要强推理能力，小模型更快更便宜。

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
                {"role": "system", "content": "你是一个对话摘要专家，擅长将长对话压缩为简洁的摘要。"},
                {"role": "user", "content": prompt},
            ],
            max_tokens=800,
            temperature=0.3,
        )

        summary = response.choices[0].message.content or ""

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
    summary_model: str = "qwen-turbo",
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
        summary_model: str = "qwen-turbo",
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
