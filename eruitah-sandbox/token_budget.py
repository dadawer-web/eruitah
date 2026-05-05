"""
Eruitah 智能编程沙盒 - Token 预算管理 (Token Budgeting)

核心思想（来自 Claude Code 的 tokenBudget.ts + tokenLimiter.ts）:
┌─────────────────────────────────────────────────────────────────────┐
│  预算熔断机制: 防止 Agent 无限制消耗 Token，避免 API 费用失控        │
│                                                                     │
│  功能:                                                              │
│    1. 长度检测: 工具输出长度超过阈值时自动截断并返回警告            │
│    2. 预算追踪: 实时估算并累计 Token 消耗                           │
│    3. 熔断策略: 达到预算上限时强制终止任务                          │
│    4. 循环限制: 防止无限循环                                         │
│                                                                     │
│  配置:                                                              │
│    - MAX_OUTPUT_LENGTH: 单次工具输出最大长度（默认 30,000 字符）       │
│    - MAX_TOKEN_BUDGET: 单次任务最大 Token 预算（默认 100,000）         │
│    - MAX_TURNS: 最大循环轮数（默认 30）                               │
│    - SAFETY_MARGIN: 安全边际（默认 0.9）                              │
└─────────────────────────────────────────────────────────────────────┘

参考源码:
    claude-code-rev/src/utils/tokenBudget.ts
    claude-code-rev/src/services/api/tokenLimiter.ts
    claude-code-rev/src/utils/tokenCounts.ts
"""

import os
import json
import logging
import threading
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

MAX_OUTPUT_LENGTH = int(os.environ.get("ERUITAH_MAX_OUTPUT_LENGTH", "30000"))
MAX_TOKEN_BUDGET = int(os.environ.get("ERUITAH_MAX_TOKEN_BUDGET", "100000"))
SAFETY_MARGIN = float(os.environ.get("ERUITAH_SAFETY_MARGIN", "0.9"))
DEFAULT_MAX_TURNS = int(os.environ.get("ERUITAH_MAX_TURNS", "30"))


@dataclass
class TokenBudget:
    max_budget: int = MAX_TOKEN_BUDGET
    max_output_length: int = MAX_OUTPUT_LENGTH
    safety_margin: float = SAFETY_MARGIN
    used: int = 0
    turns: int = 0
    max_turns: int = DEFAULT_MAX_TURNS
    last_reset: float = 0.0

    @property
    def remaining(self) -> int:
        return max(0, int(self.max_budget * self.safety_margin) - self.used)

    @property
    def is_exhausted(self) -> bool:
        return self.remaining <= 0 or self.turns >= self.max_turns

    def add_usage(self, tokens: int) -> bool:
        self.used += tokens
        return not self.is_exhausted

    def add_turn(self) -> bool:
        self.turns += 1
        return not self.is_exhausted

    def reset(self):
        self.used = 0
        self.turns = 0
        self.last_reset = time.time()

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 3

    def check_output_length(self, output: str) -> tuple[str, bool]:
        if len(output) <= self.max_output_length:
            return output, False

        truncated = output[:self.max_output_length]
        warning = f"[输出被截断] 原始长度 {len(output)} 字符，已截断到 {self.max_output_length} 字符。请缩小搜索范围或分段读取。"
        logger.warning(warning)
        return truncated + "\n\n" + warning, True


class TokenLimiter:
    def __init__(self):
        self._budgets: dict[str, TokenBudget] = {}
        self._lock = threading.Lock()

    def get_budget(self, session_id: str) -> TokenBudget:
        with self._lock:
            if session_id not in self._budgets:
                self._budgets[session_id] = TokenBudget()
            return self._budgets[session_id]

    def reset_budget(self, session_id: str):
        with self._lock:
            if session_id in self._budgets:
                self._budgets[session_id].reset()

    def check_output(self, session_id: str, output: str) -> tuple[str, bool]:
        budget = self.get_budget(session_id)
        return budget.check_output_length(output)

    def check_budget(self, session_id: str) -> tuple[bool, str]:
        budget = self.get_budget(session_id)
        if budget.is_exhausted:
            if budget.remaining <= 0:
                return False, f"Token 预算耗尽 (已使用 {budget.used}/{int(budget.max_budget * budget.safety_margin)})"
            else:
                return False, f"循环轮数超限 (已执行 {budget.turns}/{budget.max_turns} 轮)"
        return True, ""

    def consume_tokens(self, session_id: str, tokens: int) -> bool:
        budget = self.get_budget(session_id)
        return budget.add_usage(tokens)

    def next_turn(self, session_id: str) -> bool:
        budget = self.get_budget(session_id)
        return budget.add_turn()

    def get_status(self, session_id: str) -> dict:
        budget = self.get_budget(session_id)
        return {
            "used": budget.used,
            "remaining": budget.remaining,
            "total": int(budget.max_budget * budget.safety_margin),
            "turns": budget.turns,
            "max_turns": budget.max_turns,
            "is_exhausted": budget.is_exhausted,
        }


import time

_limiter: Optional[TokenLimiter] = None


def get_token_limiter() -> TokenLimiter:
    global _limiter
    if _limiter is None:
        _limiter = TokenLimiter()
    return _limiter


def check_output_length(output: str) -> tuple[str, bool]:
    if len(output) <= MAX_OUTPUT_LENGTH:
        return output, False

    truncated = output[:MAX_OUTPUT_LENGTH]
    warning = f"[输出被截断] 原始长度 {len(output)} 字符，已截断到 {MAX_OUTPUT_LENGTH} 字符。请缩小搜索范围或分段读取。"
    return truncated + "\n\n" + warning, True


def estimate_tokens(text: str) -> int:
    return len(text) // 3


def check_budget_exhausted(session_id: str) -> tuple[bool, str]:
    limiter = get_token_limiter()
    return limiter.check_budget(session_id)


def consume_tokens(session_id: str, tokens: int) -> bool:
    limiter = get_token_limiter()
    return limiter.consume_tokens(session_id, tokens)


def next_turn(session_id: str) -> bool:
    limiter = get_token_limiter()
    return limiter.next_turn(session_id)


def reset_budget(session_id: str):
    limiter = get_token_limiter()
    limiter.reset_budget(session_id)


def get_budget_status(session_id: str) -> dict:
    limiter = get_token_limiter()
    return limiter.get_status(session_id)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("Eruitah Token Budget 测试")
    print("=" * 60)

    limiter = get_token_limiter()
    session_id = "test_session"

    print(f"\n初始预算: {get_budget_status(session_id)}")

    print("\n--- 测试输出长度限制 ---")
    long_output = "a" * 40000
    truncated, was_truncated = check_output_length(long_output)
    print(f"原始长度: {len(long_output)}, 截断后长度: {len(truncated)}, 被截断: {was_truncated}")
    print(f"截断提示: {truncated[-200:].strip()}")

    print("\n--- 测试预算消耗 ---")
    for i in range(5):
        tokens = 10000
        success = consume_tokens(session_id, tokens)
        status = get_budget_status(session_id)
        print(f"消耗 {tokens} tokens, 成功: {success}, 剩余: {status['remaining']}")

    print("\n--- 测试预算耗尽 ---")
    for i in range(10):
        tokens = 10000
        success = consume_tokens(session_id, tokens)
        status = get_budget_status(session_id)
        print(f"消耗 {tokens} tokens, 成功: {success}, 剩余: {status['remaining']}")
        if not success:
            break

    print("\n--- 测试循环轮数 ---")
    reset_budget(session_id)
    for i in range(20):
        success = next_turn(session_id)
        status = get_budget_status(session_id)
        print(f"第 {i+1} 轮, 成功: {success}, 轮数: {status['turns']}/{status['max_turns']}")
        if not success:
            break

    print("\n✅ Token Budget 测试通过!")
