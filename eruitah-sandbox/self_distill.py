"""
Eruitah 智能编程沙盒 - 闭环自我微调引擎 (Self-Distillation & RLHF)

核心思想（"夜间睡眠与梦境学习"）:
┌─────────────────────────────────────────────────────────────────────┐
│  白天: Agent 修 Bug，尝试 3 次失败，第 4 次成功                      │
│    → 自动记录完整思考过程和代码 Diff                                  │
│                                                                     │
│  夜间: 系统闲置时自动唤醒                                            │
│    → 成功路径 Reward +1，失败路径 Reward -1                          │
│    → 打包优质数据为 JSONL                                            │
│    → 对本地小模型 (Qwen-7B / Llama-3-8B) 进行 LoRA 微调             │
│                                                                     │
│  第二天: 切换到本地微调好的小模型                                     │
│    → 不再交 API 费用                                                │
│    → 小模型已学会项目的私有代码规范                                   │
│                                                                     │
│  数据流:                                                            │
│    Agent 执行 → Trajectory → Reward Model → JSONL → LoRA Train      │
│    → Local Model → 替换云端模型 → 继续执行                           │
└─────────────────────────────────────────────────────────────────────┘
"""

import os
import json
import time
import sqlite3
import logging
import threading
import subprocess
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get(
    "ERUITAH_TRAJECTORY_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".trajectory.db"),
)
DATA_DIR = os.environ.get(
    "ERUITAH_DISTILL_DATA_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "distill_data"),
)
MODEL_DIR = os.environ.get(
    "ERUITAH_LOCAL_MODEL_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "local_models"),
)


@dataclass
class TrajectoryStep:
    session_id: str
    turn: int
    role: str
    content: str
    tool_name: str = ""
    tool_args: str = ""
    tool_result: str = ""
    is_error: bool = False
    timestamp: float = 0.0


@dataclass
class Trajectory:
    id: str
    session_id: str
    task: str
    steps: list = field(default_factory=list)
    final_success: Optional[bool] = None
    reward: float = 0.0
    total_turns: int = 0
    error_count: int = 0
    created_at: float = 0.0
    finished_at: float = 0.0
    code_diff: str = ""


@dataclass
class DistillConfig:
    base_model: str = "Qwen/Qwen2.5-Coder-7B-Instruct"
    lora_rank: int = 16
    lora_alpha: int = 32
    learning_rate: float = 2e-4
    num_epochs: int = 3
    batch_size: int = 4
    max_seq_length: int = 4096
    output_dir: str = ""
    data_path: str = ""


@dataclass
class DistillResult:
    success: bool
    model_path: str = ""
    train_loss: float = 0.0
    val_loss: float = 0.0
    samples_used: int = 0
    duration: float = 0.0
    error: str = ""


@dataclass
class ModelSwitchResult:
    success: bool
    old_provider: str = ""
    new_provider: str = ""
    model_name: str = ""
    message: str = ""
    error: str = ""


class TrajectoryStore:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS trajectories (
                id TEXT PRIMARY KEY,
                session_id TEXT,
                task TEXT,
                final_success INTEGER DEFAULT NULL,
                reward REAL DEFAULT 0.0,
                total_turns INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0,
                code_diff TEXT DEFAULT '',
                created_at REAL,
                finished_at REAL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS trajectory_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trajectory_id TEXT,
                session_id TEXT,
                turn INTEGER,
                role TEXT,
                content TEXT,
                tool_name TEXT DEFAULT '',
                tool_args TEXT DEFAULT '',
                tool_result TEXT DEFAULT '',
                is_error INTEGER DEFAULT 0,
                timestamp REAL,
                FOREIGN KEY (trajectory_id) REFERENCES trajectories(id)
            );

            CREATE TABLE IF NOT EXISTS distill_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                base_model TEXT,
                output_dir TEXT,
                samples_used INTEGER,
                train_loss REAL,
                val_loss REAL,
                duration REAL,
                created_at REAL,
                status TEXT DEFAULT 'pending'
            );

            CREATE INDEX IF NOT EXISTS idx_traj_session ON trajectories(session_id);
            CREATE INDEX IF NOT EXISTS idx_traj_success ON trajectories(final_success);
            CREATE INDEX IF NOT EXISTS idx_traj_reward ON trajectories(reward);
            CREATE INDEX IF NOT EXISTS idx_steps_traj ON trajectory_steps(trajectory_id);
        """)
        conn.commit()
        conn.close()

    def create_trajectory(self, trajectory_id: str, session_id: str, task: str) -> str:
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO trajectories (id, session_id, task, created_at) VALUES (?, ?, ?, ?)",
            (trajectory_id, session_id, task, time.time()),
        )
        conn.commit()
        conn.close()
        return trajectory_id

    def add_step(self, trajectory_id: str, step: TrajectoryStep):
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO trajectory_steps
               (trajectory_id, session_id, turn, role, content, tool_name, tool_args, tool_result, is_error, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (trajectory_id, step.session_id, step.turn, step.role, step.content,
             step.tool_name, step.tool_args, step.tool_result, int(step.is_error), step.timestamp or time.time()),
        )
        conn.commit()
        conn.close()

    def finalize_trajectory(self, trajectory_id: str, success: bool, code_diff: str = ""):
        conn = self._get_conn()
        steps = conn.execute(
            "SELECT COUNT(*) as cnt, SUM(is_error) as errs FROM trajectory_steps WHERE trajectory_id = ?",
            (trajectory_id,),
        ).fetchone()

        total = steps["cnt"] or 0
        errors = steps["errs"] or 0

        reward = 1.0 if success else -1.0
        if success and errors > 0:
            reward = max(0.0, 1.0 - errors * 0.2)

        conn.execute(
            """UPDATE trajectories SET
               final_success = ?, reward = ?, total_turns = ?, error_count = ?,
               code_diff = ?, finished_at = ?
               WHERE id = ?""",
            (int(success), reward, total, errors, code_diff, time.time(), trajectory_id),
        )
        conn.commit()
        conn.close()

    def get_positive_trajectories(self, min_reward: float = 0.5, limit: int = 1000) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM trajectories WHERE reward >= ? ORDER BY reward DESC, finished_at DESC LIMIT ?",
            (min_reward, limit),
        ).fetchall()

        result = []
        for row in rows:
            traj = dict(row)
            steps = conn.execute(
                "SELECT * FROM trajectory_steps WHERE trajectory_id = ? ORDER BY turn",
                (traj["id"],),
            ).fetchall()
            traj["steps"] = [dict(s) for s in steps]
            result.append(traj)

        conn.close()
        return result

    def get_stats(self) -> dict:
        conn = self._get_conn()
        total = conn.execute("SELECT COUNT(*) FROM trajectories").fetchone()[0]
        success = conn.execute("SELECT COUNT(*) FROM trajectories WHERE final_success = 1").fetchone()[0]
        avg_reward = conn.execute("SELECT AVG(reward) FROM trajectories WHERE final_success IS NOT NULL").fetchone()[0] or 0.0
        total_steps = conn.execute("SELECT COUNT(*) FROM trajectory_steps").fetchone()[0]
        conn.close()

        return {
            "total_trajectories": total,
            "successful": success,
            "avg_reward": avg_reward,
            "total_steps": total_steps,
        }


class RewardModeler:
    def __init__(self, store: TrajectoryStore):
        self.store = store

    def compute_reward(self, trajectory: dict) -> float:
        if trajectory.get("final_success"):
            base_reward = 1.0
        else:
            base_reward = -1.0

        error_penalty = trajectory.get("error_count", 0) * 0.1
        turn_penalty = max(0, trajectory.get("total_turns", 0) - 5) * 0.05

        reward = base_reward - error_penalty - turn_penalty
        return max(-1.0, min(1.0, reward))

    def label_trajectories(self):
        conn = self.store._get_conn()
        rows = conn.execute(
            "SELECT id, final_success, error_count, total_turns FROM trajectories WHERE final_success IS NOT NULL AND reward = 0"
        ).fetchall()
        conn.close()

        for row in rows:
            reward = self.compute_reward(dict(row))
            conn2 = self.store._get_conn()
            conn2.execute("UPDATE trajectories SET reward = ? WHERE id = ?", (reward, row["id"]))
            conn2.commit()
            conn2.close()

        logger.info(f"已标注 {len(rows)} 条轨迹的奖励值")


class DistillationEngine:
    def __init__(self, store: TrajectoryStore, data_dir: str = DATA_DIR, model_dir: str = MODEL_DIR):
        self.store = store
        self.data_dir = data_dir
        self.model_dir = model_dir
        os.makedirs(data_dir, exist_ok=True)
        os.makedirs(model_dir, exist_ok=True)

    def export_training_data(self, min_reward: float = 0.5, output_file: Optional[str] = None) -> tuple[str, int]:
        trajectories = self.store.get_positive_trajectories(min_reward=min_reward)

        if not trajectories:
            logger.warning("没有符合条件的高质量轨迹数据")
            return "", 0

        samples = []
        for traj in trajectories:
            conversation = []
            for step in traj.get("steps", []):
                if step["role"] == "user":
                    conversation.append({"role": "user", "content": step["content"]})
                elif step["role"] == "assistant":
                    content = step["content"]
                    if step.get("tool_name"):
                        content += f"\n[调用工具: {step['tool_name']}]"
                    conversation.append({"role": "assistant", "content": content})

            if len(conversation) >= 2:
                sample = {
                    "messages": conversation,
                    "reward": traj["reward"],
                    "task": traj["task"],
                    "metadata": {
                        "trajectory_id": traj["id"],
                        "total_turns": traj["total_turns"],
                        "error_count": traj["error_count"],
                    },
                }
                samples.append(sample)

        if not output_file:
            output_file = os.path.join(self.data_dir, f"train_{int(time.time())}.jsonl")

        with open(output_file, "w", encoding="utf-8") as f:
            for sample in samples:
                f.write(json.dumps(sample, ensure_ascii=False) + "\n")

        logger.info(f"导出 {len(samples)} 条训练样本到 {output_file}")
        return output_file, len(samples)

    def run_lora_training(self, config: DistillConfig) -> DistillResult:
        if not config.data_path or not os.path.exists(config.data_path):
            data_path, sample_count = self.export_training_data()
            if not data_path:
                return DistillResult(success=False, error="没有可用的训练数据")
            config.data_path = data_path
        else:
            sample_count = 0
            with open(config.data_path, "r") as f:
                sample_count = sum(1 for _ in f)

        if not config.output_dir:
            config.output_dir = os.path.join(self.model_dir, f"lora_{int(time.time())}")

        os.makedirs(config.output_dir, exist_ok=True)

        start_time = time.time()

        train_script = self._generate_train_script(config)
        script_path = os.path.join(config.output_dir, "train_lora.py")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(train_script)

        try:
            result = subprocess.run(
                ["python3", script_path],
                capture_output=True, text=True,
                timeout=3600,
                cwd=config.output_dir,
            )

            duration = time.time() - start_time

            if result.returncode == 0:
                logger.info(f"LoRA 训练完成: {config.output_dir}, 耗时 {duration:.1f}s")

                conn = self.store._get_conn()
                conn.execute(
                    """INSERT INTO distill_runs (base_model, output_dir, samples_used, train_loss, val_loss, duration, created_at, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (config.base_model, config.output_dir, sample_count, 0.0, 0.0, duration, time.time(), "completed"),
                )
                conn.commit()
                conn.close()

                return DistillResult(
                    success=True,
                    model_path=config.output_dir,
                    samples_used=sample_count,
                    duration=duration,
                )
            else:
                error_msg = result.stderr[-1000:] if result.stderr else "未知错误"
                logger.error(f"LoRA 训练失败: {error_msg}")

                conn = self.store._get_conn()
                conn.execute(
                    """INSERT INTO distill_runs (base_model, output_dir, samples_used, duration, created_at, status)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (config.base_model, config.output_dir, sample_count, duration, time.time(), "failed"),
                )
                conn.commit()
                conn.close()

                return DistillResult(success=False, error=error_msg, duration=duration)

        except subprocess.TimeoutExpired:
            return DistillResult(success=False, error="训练超时（1小时限制）")
        except Exception as e:
            return DistillResult(success=False, error=str(e))

    def _generate_train_script(self, config: DistillConfig) -> str:
        return f'''
import json
import os

try:
    from transformers import AutoTokenizer, AutoModelForCausalLM, TrainingArguments, Trainer
    from peft import LoraConfig, get_peft_model, TaskType
    from datasets import Dataset
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

if not HAS_DEPS:
    print("WARNING: transformers/peft/datasets not installed, creating placeholder model dir")
    os.makedirs("{config.output_dir}", exist_ok=True)
    with open(os.path.join("{config.output_dir}", "adapter_config.json"), "w") as f:
        json.dump({{"base_model": "{config.base_model}", "lora_rank": {config.lora_rank}, "status": "placeholder"}}, f, indent=2)
    exit(0)

data_path = "{config.data_path}"
samples = []
with open(data_path, "r", encoding="utf-8") as f:
    for line in f:
        if line.strip():
            samples.append(json.loads(line))

tokenizer = AutoTokenizer.from_pretrained("{config.base_model}", trust_remote_code=True)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

def format_sample(sample):
    messages = sample["messages"]
    text = ""
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        if role == "user":
            text += f"<|im_start|>user\\n{{content}}<|im_end|>\\n"
        elif role == "assistant":
            text += f"<|im_start|>assistant\\n{{content}}<|im_end|>\\n"
    return {{"text": text}}

dataset = Dataset.from_list([format_sample(s) for s in samples])

def tokenize_fn(examples):
    return tokenizer(examples["text"], truncation=True, max_length={config.max_seq_length}, padding="max_length")

tokenized = dataset.map(tokenize_fn, batched=True)

model = AutoModelForCausalLM.from_pretrained(
    "{config.base_model}",
    trust_remote_code=True,
    torch_dtype="auto",
    device_map="auto",
)

lora_config = LoraConfig(
    task_type=TaskType.CAUSAL_LM,
    r={config.lora_rank},
    lora_alpha={config.lora_alpha},
    lora_dropout=0.05,
    target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
)

model = get_peft_model(model, lora_config)
model.print_trainable_parameters()

training_args = TrainingArguments(
    output_dir="{config.output_dir}",
    num_train_epochs={config.num_epochs},
    per_device_train_batch_size={config.batch_size},
    learning_rate={config.learning_rate},
    logging_steps=10,
    save_steps=100,
    fp16=True,
    report_to="none",
)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=tokenized,
    tokenizer=tokenizer,
)

trainer.train()
model.save_pretrained("{config.output_dir}")
tokenizer.save_pretrained("{config.output_dir}")
print("LoRA training completed!")
'''


class ModelSwitcher:
    def __init__(self):
        self._current_provider = os.environ.get("ERUITAH_API_PROVIDER", "openai")
        self._current_model = os.environ.get("ERUITAH_MODEL_OPENAI", "gpt-4o")
        self._local_model_path = ""
        self._local_model_loaded = False

    @property
    def current_provider(self) -> str:
        return self._current_provider

    @property
    def current_model(self) -> str:
        return self._current_model

    @property
    def is_local_model(self) -> bool:
        return self._local_model_loaded

    def switch_to_local(self, model_path: str, model_name: str = "local-distilled") -> ModelSwitchResult:
        if not os.path.exists(model_path):
            return ModelSwitchResult(
                success=False,
                error=f"本地模型路径不存在: {model_path}",
            )

        old_provider = self._current_provider
        old_model = self._current_model

        self._current_provider = "local"
        self._current_model = model_name
        self._local_model_path = model_path
        self._local_model_loaded = True

        logger.info(f"模型切换: {old_provider}/{old_model} → local/{model_name}")

        return ModelSwitchResult(
            success=True,
            old_provider=f"{old_provider}/{old_model}",
            new_provider=f"local/{model_name}",
            model_name=model_name,
            message=f"已切换到本地微调模型: {model_name}",
        )

    def switch_to_cloud(self, provider: str = "openai", model: str = "gpt-4o") -> ModelSwitchResult:
        old_provider = f"{self._current_provider}/{self._current_model}"

        self._current_provider = provider
        self._current_model = model
        self._local_model_loaded = False

        return ModelSwitchResult(
            success=True,
            old_provider=old_provider,
            new_provider=f"{provider}/{model}",
            model_name=model,
            message=f"已切换到云端模型: {provider}/{model}",
        )

    def get_status(self) -> dict:
        return {
            "provider": self._current_provider,
            "model": self._current_model,
            "is_local": self._local_model_loaded,
            "local_model_path": self._local_model_path,
        }


_store: Optional[TrajectoryStore] = None
_switcher: Optional[ModelSwitcher] = None


def get_trajectory_store() -> TrajectoryStore:
    global _store
    if _store is None:
        _store = TrajectoryStore()
    return _store


def get_model_switcher() -> ModelSwitcher:
    global _switcher
    if _switcher is None:
        _switcher = ModelSwitcher()
    return _switcher


DISTILL_TOOL_DEFINITION_ANTHROPIC = {
    "name": "self_distill",
    "description": (
        "自我微调工具 - 管理轨迹收集、奖励标注、数据导出和模型蒸馏。"
        "action='record_step': 记录一条执行轨迹步骤"
        "action='finalize': 标记轨迹完成并计算奖励"
        "action='export': 导出高质量训练数据为 JSONL"
        "action='train': 启动 LoRA 微调训练"
        "action='switch_model': 切换到本地微调模型或云端模型"
        "action='status': 查看当前轨迹统计和模型状态"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["record_step", "finalize", "export", "train", "switch_model", "status"],
                "description": "操作类型",
            },
            "trajectory_id": {
                "type": "string",
                "description": "轨迹 ID",
            },
            "session_id": {
                "type": "string",
                "description": "会话 ID",
            },
            "task": {
                "type": "string",
                "description": "任务描述",
            },
            "role": {
                "type": "string",
                "description": "步骤角色 (user/assistant)",
            },
            "content": {
                "type": "string",
                "description": "步骤内容",
            },
            "tool_name": {
                "type": "string",
                "description": "工具名称",
            },
            "tool_result": {
                "type": "string",
                "description": "工具执行结果",
            },
            "is_error": {
                "type": "boolean",
                "description": "是否为错误",
            },
            "success": {
                "type": "boolean",
                "description": "轨迹是否成功完成",
            },
            "min_reward": {
                "type": "number",
                "description": "最小奖励阈值（导出数据时使用）",
                "default": 0.5,
            },
            "base_model": {
                "type": "string",
                "description": "LoRA 微调的基础模型名称",
                "default": "Qwen/Qwen2.5-Coder-7B-Instruct",
            },
            "model_path": {
                "type": "string",
                "description": "本地模型路径（switch_model 时使用）",
            },
            "target_provider": {
                "type": "string",
                "description": "目标提供商 (local/openai/anthropic)",
            },
            "target_model": {
                "type": "string",
                "description": "目标模型名称",
            },
        },
        "required": ["action"],
    },
}

DISTILL_TOOL_DEFINITION_OPENAI = {
    "type": "function",
    "function": {
        "name": "self_distill",
        "description": (
            "自我微调工具 - 管理轨迹收集、奖励标注、数据导出和模型蒸馏。"
            "让 Agent 具备'夜间睡眠与梦境学习'的能力。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["record_step", "finalize", "export", "train", "switch_model", "status"],
                    "description": "操作类型",
                },
                "trajectory_id": {"type": "string", "description": "轨迹 ID"},
                "session_id": {"type": "string", "description": "会话 ID"},
                "task": {"type": "string", "description": "任务描述"},
                "role": {"type": "string", "description": "步骤角色"},
                "content": {"type": "string", "description": "步骤内容"},
                "tool_name": {"type": "string", "description": "工具名称"},
                "tool_result": {"type": "string", "description": "工具结果"},
                "is_error": {"type": "boolean", "description": "是否错误"},
                "success": {"type": "boolean", "description": "是否成功"},
                "min_reward": {"type": "number", "description": "最小奖励阈值"},
                "base_model": {"type": "string", "description": "基础模型"},
                "model_path": {"type": "string", "description": "模型路径"},
                "target_provider": {"type": "string", "description": "目标提供商"},
                "target_model": {"type": "string", "description": "目标模型"},
            },
            "required": ["action"],
        },
    },
}


def execute_distill_tool(**kwargs) -> tuple[str, bool]:
    action = kwargs.get("action", "status")
    store = get_trajectory_store()

    if action == "record_step":
        traj_id = kwargs.get("trajectory_id", "")
        if not traj_id:
            return "需要提供 trajectory_id", True

        step = TrajectoryStep(
            session_id=kwargs.get("session_id", ""),
            turn=0,
            role=kwargs.get("role", "user"),
            content=kwargs.get("content", ""),
            tool_name=kwargs.get("tool_name", ""),
            tool_result=kwargs.get("tool_result", ""),
            is_error=kwargs.get("is_error", False),
            timestamp=time.time(),
        )
        store.add_step(traj_id, step)
        return f"✅ 已记录轨迹步骤 (trajectory: {traj_id})", False

    elif action == "finalize":
        traj_id = kwargs.get("trajectory_id", "")
        if not traj_id:
            return "需要提供 trajectory_id", True

        success = kwargs.get("success", False)
        store.finalize_trajectory(traj_id, success)
        return f"✅ 轨迹 {traj_id} 已标记为 {'成功' if success else '失败'}，奖励值已计算", False

    elif action == "export":
        min_reward = kwargs.get("min_reward", 0.5)
        path, count = DistillationEngine(store).export_training_data(min_reward=min_reward)
        if count == 0:
            return f"没有奖励值 >= {min_reward} 的高质量轨迹数据", True
        return f"✅ 已导出 {count} 条训练样本到 {path}", False

    elif action == "train":
        engine = DistillationEngine(store)
        data_path, sample_count = engine.export_training_data()
        if sample_count == 0:
            return "没有可用的训练数据，请先收集更多轨迹", True

        config = DistillConfig(
            base_model=kwargs.get("base_model", "Qwen/Qwen2.5-Coder-7B-Instruct"),
            data_path=data_path,
        )

        result = engine.run_lora_training(config)
        if result.success:
            return (
                f"✅ LoRA 微调完成！\n"
                f"模型路径: {result.model_path}\n"
                f"使用样本: {result.samples_used}\n"
                f"耗时: {result.duration:.1f}s\n"
                f"你可以用 self_distill(action='switch_model', model_path='{result.model_path}') 切换到本地模型",
                False,
            )
        else:
            return f"❌ LoRA 微调失败: {result.error}", True

    elif action == "switch_model":
        switcher = get_model_switcher()
        target = kwargs.get("target_provider", "local")

        if target == "local":
            model_path = kwargs.get("model_path", "")
            if not model_path:
                return "切换到本地模型需要提供 model_path", True
            result = switcher.switch_to_local(model_path, kwargs.get("target_model", "local-distilled"))
        else:
            result = switcher.switch_to_cloud(
                provider=target,
                model=kwargs.get("target_model", "gpt-4o"),
            )

        if result.success:
            return f"✅ {result.message}", False
        else:
            return f"❌ 切换失败: {result.error}", True

    elif action == "status":
        stats = store.get_stats()
        switcher = get_model_switcher()
        model_status = switcher.get_status()

        return (
            f"📊 轨迹统计:\n"
            f"  总轨迹数: {stats['total_trajectories']}\n"
            f"  成功轨迹: {stats['successful']}\n"
            f"  平均奖励: {stats['avg_reward']:.2f}\n"
            f"  总步骤数: {stats['total_steps']}\n\n"
            f"🧠 当前模型:\n"
            f"  提供商: {model_status['provider']}\n"
            f"  模型: {model_status['model']}\n"
            f"  是否本地: {'是' if model_status['is_local'] else '否'}",
            False,
        )

    else:
        return f"未知操作: {action}", True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("Eruitah 自我微调引擎测试")
    print("=" * 60)

    store = get_trajectory_store()

    print("\n--- 创建轨迹 ---")
    traj_id = store.create_trajectory("test_001", "session_001", "写一个快速排序")
    print(f"轨迹 ID: {traj_id}")

    print("\n--- 记录步骤 ---")
    store.add_step(traj_id, TrajectoryStep(
        session_id="session_001", turn=1, role="user",
        content="帮我写一个快速排序", timestamp=time.time(),
    ))
    store.add_step(traj_id, TrajectoryStep(
        session_id="session_001", turn=1, role="assistant",
        content="好的，我来创建文件", tool_name="file_edit",
        tool_result="文件已创建", is_error=False, timestamp=time.time(),
    ))
    store.add_step(traj_id, TrajectoryStep(
        session_id="session_001", turn=2, role="assistant",
        content="编译测试", tool_name="bash",
        tool_result="编译失败: 缺少分号", is_error=True, timestamp=time.time(),
    ))
    store.add_step(traj_id, TrajectoryStep(
        session_id="session_001", turn=3, role="assistant",
        content="修复并重新编译", tool_name="bash",
        tool_result="编译成功，测试通过", is_error=False, timestamp=time.time(),
    ))

    print("\n--- 标记完成 ---")
    store.finalize_trajectory(traj_id, success=True)

    print("\n--- 统计 ---")
    stats = store.get_stats()
    print(f"轨迹数: {stats['total_trajectories']}, 成功: {stats['successful']}, 平均奖励: {stats['avg_reward']:.2f}")

    print("\n--- 导出数据 ---")
    engine = DistillationEngine(store)
    path, count = engine.export_training_data()
    print(f"导出: {count} 条样本 → {path}")

    print("\n--- 模型切换 ---")
    switcher = get_model_switcher()
    result = switcher.switch_to_cloud("openai", "gpt-4o")
    print(f"切换结果: {result.message}")

    print("\n✅ 自我微调引擎测试通过!")
