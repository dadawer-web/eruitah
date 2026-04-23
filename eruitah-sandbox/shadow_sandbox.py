"""
Eruitah 智能编程沙盒 - 影子沙盒引擎 (Shadow Sandbox Engine)

核心思想（借鉴 CPU 分支预测机制）:
┌─────────────────────────────────────────────────────────────────────┐
│  线性执行: 用户 → Agent → 改代码 → 报错 → 修复 → ... 1 分钟       │
│                                                                     │
│  推测执行: 用户 → 同时开 3 个影子沙盒 → 并行尝试 → 最快者胜出！     │
│                                                                     │
│  场景: 用户说 "用 C++ 写一个线程池"                                 │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────┐       │
│  │  主控节点 (Python 中台)                                   │       │
│  │    │                                                      │       │
│  │    ├──→ 影子沙盒1: Agent 尝试 std::thread 方案            │       │
│  │    ├──→ 影子沙盒2: Agent 尝试 pthread 方案                │       │
│  │    └──→ 影子沙盒3: Agent 尝试开源线程池方案               │       │
│  │                                                           │       │
│  │  沙盒1: ❌ 编译失败                                       │       │
│  │  沙盒2: ✅ 编译通过 + 测试通过 → 坍缩！                    │       │
│  │  沙盒3: ⏳ 还在跑... → 被杀死                             │       │
│  │                                                           │       │
│  │  结果: 沙盒2 的代码瞬间推送到用户前端                      │       │
│  └──────────────────────────────────────────────────────────┘       │
│                                                                     │
│  实现:                                                              │
│    - Docker SDK 管理 Container 生命周期                              │
│    - 每个影子沙盒运行独立的 Agent 实例                               │
│    - 通过共享 Volume 传递任务描述                                    │
│    - 通过文件系统信号检测完成状态                                    │
│    - 第一个成功者触发坍缩，杀死其余容器                              │
└─────────────────────────────────────────────────────────────────────┘
"""

import os
import json
import time
import logging
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_IMAGE = os.environ.get("ERUITAH_SHADOW_IMAGE", "eruitah-sandbox")
SANDBOX_BASE_DIR = os.environ.get("ERUITAH_SHADOW_BASE_DIR", "/tmp/eruitah-shadows")
MAX_SHADOWS = int(os.environ.get("ERUITAH_MAX_SHADOWS", "5"))
SHADOW_TIMEOUT = int(os.environ.get("ERUITAH_SHADOW_TIMEOUT", "300"))


@dataclass
class ShadowSandbox:
    id: str
    container_id: str = ""
    strategy: str = ""
    status: str = "pending"
    result: str = ""
    output_files: list = field(default_factory=list)
    created_at: float = 0.0
    finished_at: float = 0.0
    exit_code: Optional[int] = None
    error: str = ""


@dataclass
class SpeculativeResult:
    success: bool
    winner_id: str = ""
    winner_strategy: str = ""
    result_data: str = ""
    all_results: list = field(default_factory=list)
    total_time: float = 0.0
    shadows_used: int = 0


@dataclass
class Strategy:
    name: str
    prompt_suffix: str
    description: str = ""


DEFAULT_STRATEGIES = [
    Strategy(
        name="standard",
        prompt_suffix="请使用标准库和常规方法实现。",
        description="标准方案",
    ),
    Strategy(
        name="alternative",
        prompt_suffix="请使用不同于常规的替代方案实现，尝试不同的技术路线。",
        description="替代方案",
    ),
    Strategy(
        name="minimal",
        prompt_suffix="请用最简洁、最少的代码实现核心功能，不要过度设计。",
        description="极简方案",
    ),
]


class ShadowSandboxManager:
    def __init__(self):
        self._shadows: dict[str, ShadowSandbox] = {}
        self._docker_available: Optional[bool] = None
        self._lock = threading.Lock()

    def _check_docker(self) -> bool:
        if self._docker_available is not None:
            return self._docker_available

        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True, text=True, timeout=10,
            )
            self._docker_available = result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            self._docker_available = False

        if not self._docker_available:
            logger.warning("Docker 不可用，影子沙盒将使用进程模式")

        return self._docker_available

    def create_shadow(
        self,
        shadow_id: str,
        strategy: Strategy,
        task: str,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        work_dir: str = SANDBOX_BASE_DIR,
    ) -> ShadowSandbox:
        shadow = ShadowSandbox(
            id=shadow_id,
            strategy=strategy.name,
            created_at=time.time(),
        )

        shadow_dir = os.path.join(work_dir, shadow_id)
        os.makedirs(shadow_dir, exist_ok=True)

        task_file = os.path.join(shadow_dir, "task.json")
        with open(task_file, "w", encoding="utf-8") as f:
            json.dump({
                "task": task + "\n\n" + strategy.prompt_suffix,
                "strategy": strategy.name,
                "shadow_id": shadow_id,
            }, f, ensure_ascii=False, indent=2)

        signal_dir = os.path.join(shadow_dir, "signals")
        os.makedirs(signal_dir, exist_ok=True)

        if self._check_docker():
            shadow = self._create_docker_shadow(shadow, shadow_dir, strategy)
        else:
            shadow = self._create_process_shadow(shadow, shadow_dir, strategy, task, api_key, model, base_url)

        with self._lock:
            self._shadows[shadow_id] = shadow

        return shadow

    def _create_docker_shadow(
        self,
        shadow: ShadowSandbox,
        shadow_dir: str,
        strategy: Strategy,
    ) -> ShadowSandbox:
        try:
            container_name = f"eruitah-shadow-{shadow.id}"

            cmd = [
                "docker", "run",
                "-d",
                "--name", container_name,
                "-v", f"{shadow_dir}:/workspace",
                "-e", f"ERUITAH_SHADOW_ID={shadow.id}",
                "-e", f"ERUITAH_STRATEGY={strategy.name}",
                DEFAULT_IMAGE,
                "python3", "-c",
                self._shadow_agent_script(),
            ]

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
            )

            if result.returncode == 0:
                shadow.container_id = result.stdout.strip()[:12]
                shadow.status = "running"
                logger.info(f"影子沙盒 {shadow.id} 已启动 (容器: {shadow.container_id})")
            else:
                shadow.status = "failed"
                shadow.error = result.stderr[:500]
                logger.error(f"影子沙盒启动失败: {shadow.error}")

        except Exception as e:
            shadow.status = "failed"
            shadow.error = str(e)
            logger.error(f"影子沙盒异常: {e}")

        return shadow

    def _create_process_shadow(
        self,
        shadow: ShadowSandbox,
        shadow_dir: str,
        strategy: Strategy,
        task: str,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> ShadowSandbox:
        full_task = task + "\n\n" + strategy.prompt_suffix

        def _run_in_thread():
            try:
                from agent_runner import run_agent

                events = []
                for event in run_agent(
                    user_input=full_task,
                    work_dir=shadow_dir,
                    max_turns=10,
                    api_key=api_key,
                    model=model,
                    base_url=base_url,
                ):
                    events.append(event)

                    if event.get("type") == "finish":
                        shadow.result = event.get("data", "")
                        shadow.status = "completed"
                        shadow.finished_at = time.time()
                    elif event.get("type") == "error":
                        shadow.result = event.get("data", "")
                        shadow.status = "failed"
                        shadow.finished_at = time.time()

                signal_file = os.path.join(shadow_dir, "signals", "done")
                with open(signal_file, "w") as f:
                    json.dump({
                        "status": shadow.status,
                        "result": shadow.result[:2000],
                        "strategy": strategy.name,
                    }, f, ensure_ascii=False)

            except Exception as e:
                shadow.status = "failed"
                shadow.error = str(e)
                shadow.finished_at = time.time()

        thread = threading.Thread(target=_run_in_thread, daemon=True)
        thread.start()

        shadow.status = "running"
        shadow.container_id = f"process-{shadow.id}"
        logger.info(f"影子沙盒 {shadow.id} 已启动 (进程模式, 策略: {strategy.name})")

        return shadow

    def _shadow_agent_script(self) -> str:
        return '''
import json
import os
import sys

task_file = "/workspace/task.json"
signal_dir = "/workspace/signals"

with open(task_file) as f:
    task_data = json.load(f)

task = task_data["task"]
strategy = task_data["strategy"]
shadow_id = task_data["shadow_id"]

try:
    from agent_runner import run_agent

    for event in run_agent(task, work_dir="/workspace", max_turns=10):
        if event.get("type") == "finish":
            with open(os.path.join(signal_dir, "done"), "w") as sf:
                json.dump({"status": "completed", "result": event.get("data", ""), "strategy": strategy}, sf)
            sys.exit(0)
        elif event.get("type") == "error":
            with open(os.path.join(signal_dir, "done"), "w") as sf:
                json.dump({"status": "failed", "result": event.get("data", ""), "strategy": strategy}, sf)
            sys.exit(1)

except Exception as e:
    with open(os.path.join(signal_dir, "done"), "w") as sf:
        json.dump({"status": "failed", "result": str(e), "strategy": strategy}, sf)
    sys.exit(1)
'''

    def check_shadow(self, shadow_id: str) -> ShadowSandbox:
        with self._lock:
            shadow = self._shadows.get(shadow_id)

        if shadow is None:
            return ShadowSandbox(id=shadow_id, status="unknown")

        if shadow.status in ("completed", "failed", "killed"):
            return shadow

        if shadow.container_id.startswith("process-"):
            return shadow

        try:
            result = subprocess.run(
                ["docker", "inspect", "--format", "{{.State.Status}}", shadow.container_id],
                capture_output=True, text=True, timeout=10,
            )

            if result.returncode == 0:
                container_status = result.stdout.strip()
                if container_status == "exited":
                    exit_result = subprocess.run(
                        ["docker", "inspect", "--format", "{{.State.ExitCode}}", shadow.container_id],
                        capture_output=True, text=True, timeout=10,
                    )
                    shadow.exit_code = int(exit_result.stdout.strip()) if exit_result.returncode == 0 else -1
                    shadow.status = "completed" if shadow.exit_code == 0 else "failed"
                    shadow.finished_at = time.time()

        except Exception as e:
            logger.error(f"检查影子沙盒状态失败: {e}")

        return shadow

    def kill_shadow(self, shadow_id: str) -> bool:
        with self._lock:
            shadow = self._shadows.get(shadow_id)

        if shadow is None:
            return False

        if shadow.container_id and not shadow.container_id.startswith("process-"):
            try:
                subprocess.run(
                    ["docker", "rm", "-f", shadow.container_id],
                    capture_output=True, text=True, timeout=10,
                )
            except Exception:
                pass

        shadow.status = "killed"
        shadow.finished_at = time.time()
        logger.info(f"影子沙盒 {shadow_id} 已杀死")
        return True

    def speculative_execute(
        self,
        task: str,
        strategies: Optional[list[Strategy]] = None,
        max_shadows: int = MAX_SHADOWS,
        timeout: int = SHADOW_TIMEOUT,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> SpeculativeResult:
        if strategies is None:
            strategies = DEFAULT_STRATEGIES[:max_shadows]

        start_time = time.time()
        shadows = []

        for i, strategy in enumerate(strategies):
            shadow_id = f"shadow_{int(time.time())}_{i}"
            shadow = self.create_shadow(shadow_id, strategy, task, api_key, model, base_url)
            shadows.append(shadow)

        logger.info(f"已启动 {len(shadows)} 个影子沙盒，等待结果...")

        winner = None
        deadline = start_time + timeout

        while time.time() < deadline:
            for shadow in shadows:
                if shadow.status in ("completed", "failed"):
                    continue

                self.check_shadow(shadow.id)

                if shadow.status == "completed" and winner is None:
                    winner = shadow
                    break

            if winner:
                break

            time.sleep(2)

        if winner is None:
            for shadow in shadows:
                if shadow.status == "running":
                    self.check_shadow(shadow.id)
                    if shadow.status == "completed":
                        winner = shadow
                        break

        if winner:
            logger.info(f"🏆 影子沙盒 {winner.id} ({winner.strategy}) 率先完成！")

            for shadow in shadows:
                if shadow.id != winner.id and shadow.status == "running":
                    self.kill_shadow(shadow.id)

            all_results = []
            for shadow in shadows:
                all_results.append({
                    "id": shadow.id,
                    "strategy": shadow.strategy,
                    "status": shadow.status,
                    "result": shadow.result[:500] if shadow.result else "",
                    "error": shadow.error[:200] if shadow.error else "",
                })

            return SpeculativeResult(
                success=True,
                winner_id=winner.id,
                winner_strategy=winner.strategy,
                result_data=winner.result,
                all_results=all_results,
                total_time=time.time() - start_time,
                shadows_used=len(shadows),
            )
        else:
            logger.warning("所有影子沙盒均未成功完成")

            for shadow in shadows:
                if shadow.status == "running":
                    self.kill_shadow(shadow.id)

            all_results = []
            for shadow in shadows:
                all_results.append({
                    "id": shadow.id,
                    "strategy": shadow.strategy,
                    "status": shadow.status,
                    "result": shadow.result[:500] if shadow.result else "",
                    "error": shadow.error[:200] if shadow.error else "",
                })

            return SpeculativeResult(
                success=False,
                all_results=all_results,
                total_time=time.time() - start_time,
                shadows_used=len(shadows),
            )

    def cleanup(self):
        with self._lock:
            for shadow_id, shadow in self._shadows.items():
                if shadow.status == "running":
                    self.kill_shadow(shadow_id)
            self._shadows.clear()


_manager: Optional[ShadowSandboxManager] = None


def get_shadow_manager() -> ShadowSandboxManager:
    global _manager
    if _manager is None:
        _manager = ShadowSandboxManager()
    return _manager


SPECULATIVE_TOOL_DEFINITION_ANTHROPIC = {
    "name": "speculative_execute",
    "description": (
        "推测执行工具 - 同时启动多个影子沙盒并行尝试不同方案，返回最先成功的结果。"
        "适用于复杂编程任务，可以同时尝试多种技术路线，用算力换时间。"
        "最多同时启动 5 个影子沙盒，第一个编译通过+测试通过的方案胜出。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "要执行的任务描述",
            },
            "strategies": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "策略名称"},
                        "prompt_suffix": {"type": "string", "description": "策略提示词后缀"},
                    },
                },
                "description": "策略列表（最多5个），每个策略会在独立的影子沙盒中执行",
            },
            "max_shadows": {
                "type": "integer",
                "description": "最大影子沙盒数量（默认3）",
                "default": 3,
            },
            "timeout": {
                "type": "integer",
                "description": "超时时间（秒，默认300）",
                "default": 300,
            },
        },
        "required": ["task"],
    },
}

SPECULATIVE_TOOL_DEFINITION_OPENAI = {
    "type": "function",
    "function": {
        "name": "speculative_execute",
        "description": (
            "推测执行工具 - 同时启动多个影子沙盒并行尝试不同方案，返回最先成功的结果。"
            "适用于复杂编程任务，可以同时尝试多种技术路线，用算力换时间。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "要执行的任务描述",
                },
                "strategies": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "策略名称"},
                            "prompt_suffix": {"type": "string", "description": "策略提示词后缀"},
                        },
                    },
                    "description": "策略列表",
                },
                "max_shadows": {
                    "type": "integer",
                    "description": "最大影子沙盒数量",
                    "default": 3,
                },
                "timeout": {
                    "type": "integer",
                    "description": "超时时间（秒）",
                    "default": 300,
                },
            },
            "required": ["task"],
        },
    },
}


def execute_speculative(
    task: str,
    strategies: Optional[list[dict]] = None,
    max_shadows: int = 3,
    timeout: int = 300,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
) -> tuple[str, bool]:
    manager = get_shadow_manager()

    strat_list = []
    if strategies:
        for s in strategies:
            strat_list.append(Strategy(
                name=s.get("name", "unnamed"),
                prompt_suffix=s.get("prompt_suffix", ""),
            ))
    else:
        strat_list = DEFAULT_STRATEGIES[:max_shadows]

    result = manager.speculative_execute(
        task=task,
        strategies=strat_list,
        max_shadows=max_shadows,
        timeout=timeout,
        api_key=api_key,
        model=model,
        base_url=base_url,
    )

    if result.success:
        lines = [
            f"🏆 推测执行成功！",
            f"获胜策略: {result.winner_strategy} (沙盒 {result.winner_id})",
            f"总耗时: {result.total_time:.1f}s",
            f"使用沙盒数: {result.shadows_used}",
            f"",
            f"--- 结果 ---",
            result.result_data[:3000],
            f"",
            f"--- 所有沙盒状态 ---",
        ]
        for r in result.all_results:
            status_icon = "✅" if r["status"] == "completed" else "❌" if r["status"] == "failed" else "💀"
            lines.append(f"  {status_icon} [{r['strategy']}] {r['status']}: {r.get('result', r.get('error', ''))[:100]}")

        return "\n".join(lines), False
    else:
        lines = [
            f"❌ 推测执行失败 - 所有影子沙盒均未成功",
            f"总耗时: {result.total_time:.1f}s",
            f"",
            f"--- 沙盒状态 ---",
        ]
        for r in result.all_results:
            lines.append(f"  ❌ [{r['strategy']}] {r['status']}: {r.get('error', r.get('result', ''))[:200]}")

        return "\n".join(lines), True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("Eruitah 影子沙盒引擎测试")
    print("=" * 60)

    manager = get_shadow_manager()

    print(f"\nDocker 可用: {manager._check_docker()}")
    print(f"最大影子数: {MAX_SHADOWS}")
    print(f"超时时间: {SHADOW_TIMEOUT}s")

    print("\n--- 默认策略 ---")
    for s in DEFAULT_STRATEGIES:
        print(f"  {s.name}: {s.description}")
        print(f"    提示词后缀: {s.prompt_suffix[:60]}...")

    print("\n--- 单沙盒创建测试 ---")
    shadow = manager.create_shadow(
        shadow_id="test_001",
        strategy=DEFAULT_STRATEGIES[0],
        task="创建一个 hello.py 文件，输出 Hello World",
    )
    print(f"沙盒状态: {shadow.status}")
    print(f"容器ID: {shadow.container_id}")

    import time
    time.sleep(5)

    shadow = manager.check_shadow("test_001")
    print(f"5秒后状态: {shadow.status}")

    manager.cleanup()
    print("\n✅ 影子沙盒引擎测试通过!")
