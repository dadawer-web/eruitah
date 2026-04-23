"""
Eruitah 智能编程沙盒 - 提示词缓存 (Prompt Caching)

核心思想（来自 Claude Code 的 promptCacheBreakDetection.ts + tokenBudget.ts）:
┌─────────────────────────────────────────────────────────────────────┐
│  大模型的缓存基于前缀匹配:                                           │
│                                                                     │
│  请求1: [System Prompt][Tools Schema][对话1][对话2]                  │
│          ─── 缓存边界 ──→ 缓存命中！只计费变化部分                    │
│                                                                     │
│  请求2: [System Prompt][Tools Schema][对话1][对话2][对话3]            │
│          ─── 缓存命中 ──→ ─── 缓存命中 ──→ 只计费 [对话3]            │
│                                                                     │
│  缓存命中后:                                                        │
│    - Token 价格直降 90% (Anthropic: input $3/MTok → $0.3/MTok)     │
│    - 响应延迟从 10s 缩短到 1s                                       │
│                                                                     │
│  关键规则:                                                          │
│    1. 缓存是基于前缀的，必须保证前缀不变                              │
│    2. 静态内容放前面（System Prompt, Tools Schema）                   │
│    3. 动态内容放后面（最新对话、Terminal 报错）                        │
│    4. 在静态块的末尾注入 cache_control: {"type": "ephemeral"}        │
│    5. 缓存 TTL 为 5 分钟，超时自动失效                                │
│                                                                     │
│  断层检测 (Cache Break Detection):                                   │
│    如果消息顺序被打乱（如插入新消息到中间），缓存会断裂。              │
│    本模块会检测并重新排序消息，确保缓存前缀最大化。                    │
└─────────────────────────────────────────────────────────────────────┘

参考源码:
    claude-code-rev/src/services/api/promptCacheBreakDetection.ts
    claude-code-rev/src/utils/tokenBudget.ts
"""

import json
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

CACHE_CONTROL_EPHEMERAL = {"cache_control": {"type": "ephemeral"}}


@dataclass
class CacheBreakReport:
    has_break: bool = False
    break_position: int = -1
    reason: str = ""
    static_prefix_hash: str = ""
    dynamic_suffix_count: int = 0
    cache_savings_estimate: float = 0.0


@dataclass
class CacheStats:
    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    tokens_saved: int = 0
    money_saved: float = 0.0
    last_cache_hit_time: float = 0.0

    @property
    def hit_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.cache_hits / self.total_requests


_cache_stats = CacheStats()

STATIC_PREFIX_HASH_KEY = "_eruitah_static_prefix_hash"


def compute_content_hash(content) -> str:
    if isinstance(content, str):
        raw = content.encode("utf-8")
    elif isinstance(content, list):
        raw = json.dumps(content, sort_keys=True, ensure_ascii=False).encode("utf-8")
    elif isinstance(content, dict):
        raw = json.dumps(content, sort_keys=True, ensure_ascii=False).encode("utf-8")
    else:
        raw = str(content).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def build_anthropic_cached_system(system_prompt: str) -> list[dict]:
    return [
        {
            "type": "text",
            "text": system_prompt,
            **CACHE_CONTROL_EPHEMERAL,
        }
    ]


def build_anthropic_cached_tools(tools: list[dict]) -> list[dict]:
    if not tools:
        return tools

    cached_tools = []
    for i, tool in enumerate(tools):
        t = dict(tool)
        if i == len(tools) - 1:
            if "input_schema" in t:
                schema = dict(t["input_schema"])
                schema.update(CACHE_CONTROL_EPHEMERAL)
                t["input_schema"] = schema
            else:
                t.update(CACHE_CONTROL_EPHEMERAL)
        cached_tools.append(t)

    return cached_tools


def build_openai_cached_messages(
    system_prompt: str,
    messages: list[dict],
) -> list[dict]:
    cached_system = {
        "role": "system",
        "content": system_prompt,
        **CACHE_CONTROL_EPHEMERAL,
    }

    result = [cached_system]
    result.extend(messages)
    return result


def detect_cache_break(
    messages: list[dict],
    static_prefix_hash: Optional[str] = None,
) -> CacheBreakReport:
    if not messages:
        return CacheBreakReport()

    current_hash = _compute_static_prefix_hash(messages)

    if static_prefix_hash and current_hash != static_prefix_hash:
        break_pos = _find_break_position(messages, static_prefix_hash)
        return CacheBreakReport(
            has_break=True,
            break_position=break_pos,
            reason=f"静态前缀哈希变化: {static_prefix_hash} → {current_hash}",
            static_prefix_hash=current_hash,
            dynamic_suffix_count=len(messages) - break_pos if break_pos >= 0 else len(messages),
        )

    dynamic_count = _count_dynamic_messages(messages)
    static_tokens = _estimate_static_tokens(messages)
    savings = static_tokens * 0.9

    return CacheBreakReport(
        has_break=False,
        static_prefix_hash=current_hash,
        dynamic_suffix_count=dynamic_count,
        cache_savings_estimate=savings,
    )


def reorder_messages_for_cache(messages: list[dict]) -> list[dict]:
    if not messages:
        return messages

    static_messages = []
    dynamic_messages = []

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if _is_static_message(msg):
            static_messages.append(msg)
        else:
            dynamic_messages.append(msg)

    if not dynamic_messages:
        return static_messages

    if static_messages and dynamic_messages:
        last_static = static_messages[-1]
        if not _has_cache_control(last_static):
            static_messages[-1] = _inject_cache_control(last_static)

    return static_messages + dynamic_messages


def build_anthropic_cached_request(
    system_prompt: str,
    tools: list[dict],
    messages: list[dict],
) -> dict:
    cached_system = build_anthropic_cached_system(system_prompt)
    cached_tools = build_anthropic_cached_tools(tools)

    ordered_messages = reorder_messages_for_cache(messages)

    static_hash = compute_content_hash(system_prompt) + compute_content_hash(tools)
    report = detect_cache_break(ordered_messages, static_hash)

    _update_stats(report, ordered_messages)

    if report.has_break:
        logger.warning(f"缓存断层检测: {report.reason}, 位置: {report.break_position}")
    else:
        logger.debug(
            f"缓存前缀完整, 预估节省 {report.cache_savings_estimate:.0f} tokens, "
            f"动态消息数: {report.dynamic_suffix_count}"
        )

    return {
        "system": cached_system,
        "tools": cached_tools,
        "messages": ordered_messages,
        "_cache_report": report,
    }


def build_openai_cached_request(
    system_prompt: str,
    tools: list[dict],
    messages: list[dict],
) -> dict:
    cached_tools = []
    for i, tool in enumerate(tools):
        t = dict(tool)
        if i == len(tools) - 1:
            func = dict(t.get("function", {}))
            params = dict(func.get("parameters", {}))
            params.update(CACHE_CONTROL_EPHEMERAL)
            func["parameters"] = params
            t["function"] = func
        cached_tools.append(t)

    ordered_messages = build_openai_cached_messages(system_prompt, messages)
    ordered_messages = reorder_messages_for_cache(ordered_messages)

    static_hash = compute_content_hash(system_prompt) + compute_content_hash(tools)
    report = detect_cache_break(ordered_messages, static_hash)

    _update_stats(report, ordered_messages)

    return {
        "messages": ordered_messages,
        "tools": cached_tools,
        "_cache_report": report,
    }


def get_cache_stats() -> CacheStats:
    return _cache_stats


def reset_cache_stats():
    global _cache_stats
    _cache_stats = CacheStats()


def _compute_static_prefix_hash(messages: list[dict]) -> str:
    static_parts = []
    for msg in messages:
        if _is_static_message(msg):
            content = msg.get("content", "")
            static_parts.append(compute_content_hash(content))
        else:
            break
    return hashlib.sha256("|".join(static_parts).encode()).hexdigest()[:16]


def _find_break_position(messages: list[dict], old_hash: str) -> int:
    for i in range(len(messages)):
        prefix = messages[:i + 1]
        prefix_hash = _compute_static_prefix_hash(prefix)
        if prefix_hash != old_hash[:len(prefix_hash)]:
            return i
    return -1


def _is_static_message(msg: dict) -> bool:
    role = msg.get("role", "")
    content = msg.get("content", "")

    if role == "system":
        return True

    if role == "user" and isinstance(content, str):
        if content.startswith("[系统: 以下是对话历史的摘要"):
            return True

    if msg.get(STATIC_PREFIX_HASH_KEY):
        return True

    return False


def _count_dynamic_messages(messages: list[dict]) -> int:
    count = 0
    for msg in messages:
        if not _is_static_message(msg):
            count += 1
    return count


def _estimate_static_tokens(messages: list[dict]) -> int:
    total_chars = 0
    for msg in messages:
        if _is_static_message(msg):
            content = msg.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        total_chars += len(json.dumps(block, ensure_ascii=False))
    return total_chars // 3


def _has_cache_control(msg: dict) -> bool:
    if "cache_control" in msg:
        return True
    content = msg.get("content", "")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and "cache_control" in block:
                return True
    if isinstance(msg, dict):
        schema = msg.get("input_schema", {})
        if isinstance(schema, dict) and "cache_control" in schema:
            return True
    return False


def _inject_cache_control(msg: dict) -> dict:
    new_msg = dict(msg)
    content = new_msg.get("content", "")

    if isinstance(content, str):
        new_msg["content"] = [
            {
                "type": "text",
                "text": content,
                **CACHE_CONTROL_EPHEMERAL,
            }
        ]
    elif isinstance(content, list):
        new_content = list(content)
        if new_content and isinstance(new_content[-1], dict):
            last_block = dict(new_content[-1])
            last_block.update(CACHE_CONTROL_EPHEMERAL)
            new_content[-1] = last_block
        new_msg["content"] = new_content

    return new_msg


def _update_stats(report: CacheBreakReport, messages: list[dict]):
    global _cache_stats
    _cache_stats.total_requests += 1

    if report.has_break:
        _cache_stats.cache_misses += 1
    else:
        _cache_stats.cache_hits += 1
        _cache_stats.tokens_saved += int(report.cache_savings_estimate)
        _cache_stats.money_saved += report.cache_savings_estimate * 3.0 / 1_000_000 * 0.9
        _cache_stats.last_cache_hit_time = time.time()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    system_prompt = "你是一个专业的编程助手，名为 Eruitah。"
    tools = [
        {"name": "bash", "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}}},
        {"name": "file_edit", "input_schema": {"type": "object", "properties": {"file_path": {"type": "string"}}}},
    ]
    messages = [
        {"role": "user", "content": "帮我写一个快速排序"},
        {"role": "assistant", "content": "好的，我来创建文件..."},
        {"role": "user", "content": "编译报错了"},
    ]

    print("=" * 60)
    print("Anthropic 缓存请求构建测试")
    print("=" * 60)

    result = build_anthropic_cached_request(system_prompt, tools, messages)
    print(f"\nSystem (带缓存标记):")
    print(json.dumps(result["system"], indent=2, ensure_ascii=False))
    print(f"\nTools (最后一个带缓存标记):")
    for t in result["tools"]:
        has_cache = "input_schema" in t and "cache_control" in t.get("input_schema", {})
        print(f"  {t['name']}: cache_control={has_cache}")
    print(f"\n缓存报告: has_break={result['_cache_report'].has_break}")
    print(f"预估节省: {result['_cache_report'].cache_savings_estimate:.0f} tokens")

    print(f"\n\n{'=' * 60}")
    print("OpenAI 缓存请求构建测试")
    print("=" * 60)

    result = build_openai_cached_request(system_prompt, tools, messages)
    print(f"\nMessages (system 带缓存标记):")
    for m in result["messages"]:
        role = m.get("role", "")
        has_cache = "cache_control" in m
        print(f"  [{role}] cache_control={has_cache}")

    stats = get_cache_stats()
    print(f"\n缓存统计: 命中率={stats.hit_rate:.1%}, 节省={stats.tokens_saved} tokens")
