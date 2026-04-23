import logging
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

MODEL_PRICING = {
    "gpt-4o": {"input": 0.0025, "output": 0.01},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4-turbo": {"input": 0.01, "output": 0.03},
    "gpt-4": {"input": 0.03, "output": 0.06},
    "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
    "claude-sonnet-4-20250514": {"input": 0.003, "output": 0.015},
    "claude-3-5-sonnet-20241022": {"input": 0.003, "output": 0.015},
    "claude-3-opus-20240229": {"input": 0.015, "output": 0.075},
    "claude-3-haiku-20240307": {"input": 0.00025, "output": 0.00125},
    "qwen-turbo": {"input": 0.0003, "output": 0.0006},
    "qwen-plus": {"input": 0.0008, "output": 0.002},
    "qwen-max": {"input": 0.004, "output": 0.012},
    "deepseek-chat": {"input": 0.00014, "output": 0.00028},
    "deepseek-reasoner": {"input": 0.00055, "output": 0.00219},
}

DEFAULT_PRICING = {"input": 0.003, "output": 0.015}

@dataclass
class SessionCostTracker:
    limit_usd: float = 5.0
    total_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    model: str = ""
    cost_history: list = field(default_factory=list)
    
    def add_usage(self, prompt_tokens: int, completion_tokens: int, model: str = "") -> float:
        if model:
            self.model = model
        
        pricing = MODEL_PRICING.get(self.model, DEFAULT_PRICING)
        
        input_cost = (prompt_tokens / 1000.0) * pricing["input"]
        output_cost = (completion_tokens / 1000.0) * pricing["output"]
        turn_cost = input_cost + output_cost
        
        self.total_usd += turn_cost
        self.total_input_tokens += prompt_tokens
        self.total_output_tokens += completion_tokens
        
        self.cost_history.append({
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens,
            "cost_usd": turn_cost,
        })
        
        if self.total_usd > self.limit_usd:
            raise Exception(
                f"COST_LIMIT_EXCEEDED: 当前花费 ${self.total_usd:.4f} 已超过限额 ${self.limit_usd:.2f}"
            )
        
        return turn_cost
    
    def get_status(self) -> dict:
        return {
            "total_usd": round(self.total_usd, 4),
            "limit_usd": self.limit_usd,
            "remaining_usd": round(max(0, self.limit_usd - self.total_usd), 4),
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "model": self.model,
            "turns": len(self.cost_history),
        }

_session_trackers: dict[str, SessionCostTracker] = {}

def get_cost_tracker(session_id: str, limit_usd: float = 5.0) -> SessionCostTracker:
    if session_id not in _session_trackers:
        _session_trackers[session_id] = SessionCostTracker(limit_usd=limit_usd)
    return _session_trackers[session_id]

def reset_cost_tracker(session_id: str, limit_usd: float = 5.0) -> SessionCostTracker:
    _session_trackers[session_id] = SessionCostTracker(limit_usd=limit_usd)
    return _session_trackers[session_id]
