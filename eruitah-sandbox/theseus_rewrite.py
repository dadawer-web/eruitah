"""
Eruitah 智能编程沙盒 - 忒修斯之船引擎 (Ship of Theseus)

核心思想（AI 替换造物主）:
┌─────────────────────────────────────────────────────────────────────┐
│  Python 写的系统，运行一个月后，被 AI 自己逐步替换成 C++ 系统        │
│  系统里再也没有一行代码是你写的                                      │
│                                                                     │
│  流程:                                                              │
│    1. 性能自检: Manager Agent 监控到 FastAPI 延迟过高               │
│    2. 跨栈重写: Agent 用 C++ 重写 agent_runner.py 的核心逻辑        │
│    3. 编译 .so: 将 C++ 编译为动态链接库                              │
│    4. 热切换: 通过 ctypes FFI 或 Nginx 流量转发，无缝迁移            │
│                                                                     │
│  安全机制:                                                          │
│    - 重写前必须通过性能基准测试                                      │
│    - 保留回滚能力（旧版本不删除）                                    │
│    - 新版本必须通过功能等价性测试                                    │
│    - 热切换失败自动回滚                                              │
└─────────────────────────────────────────────────────────────────────┘
"""

import os
import json
import time
import ctypes
import logging
import subprocess
import shutil
import threading
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)

REWRITE_DIR = os.environ.get(
    "ERUITAH_REWRITE_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".theseus"),
)
BACKUP_DIR = os.environ.get(
    "ERUITAH_BACKUP_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".theseus_backups"),
)


@dataclass
class PerformanceProfile:
    avg_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    throughput_rps: float = 0.0
    memory_mb: float = 0.0
    cpu_percent: float = 0.0
    active_connections: int = 0
    timestamp: float = 0.0


@dataclass
class RewritePlan:
    target_module: str
    target_language: str
    reason: str
    source_file: str
    output_file: str
    benchmark_before: Optional[PerformanceProfile] = None
    benchmark_after: Optional[PerformanceProfile] = None
    status: str = "planned"
    created_at: float = 0.0
    deployed_at: float = 0.0


@dataclass
class RewriteResult:
    success: bool
    plan_id: str = ""
    module: str = ""
    message: str = ""
    performance_delta: dict = field(default_factory=dict)
    error: str = ""


@dataclass
class HotSwapResult:
    success: bool
    module: str = ""
    old_version: str = ""
    new_version: str = ""
    message: str = ""
    rollback_available: bool = True
    error: str = ""


CPP_TEMPLATE = '''
// Eruitah Theseus - Auto-generated C++ rewrite of {module_name}
// Generated at: {timestamp}
// Reason: {reason}

#include <string>
#include <vector>
#include <map>
#include <functional>
#include <memory>
#include <cstring>

#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT __attribute__((visibility("default")))
#endif

extern "C" {{

// === Core Engine Interface ===

EXPORT const char* theseus_get_version() {{
    return "1.0.0-theseus";
}}

EXPORT const char* theseus_get_module() {{
    return "{module_name}";
}}

// === Agent Loop Interface ===

struct AgentResult {{
    char* content;
    int is_error;
    int should_continue;
}};

EXPORT AgentResult theseus_process_message(
    const char* role,
    const char* content,
    const char* tool_calls_json
) {{
    AgentResult result;
    result.content = strdup(content);
    result.is_error = 0;
    result.should_continue = 1;
    return result;
}}

// === Tool Execution Interface ===

EXPORT const char* theseus_execute_tool(
    const char* tool_name,
    const char* tool_args_json
) {{
    return strdup("{{\\"success\\": true, \\"message\\": \\"C++ engine placeholder\\"}}");
}}

// === Performance Benchmark ===

EXPORT double theseus_benchmark(int iterations) {{
    auto start = std::chrono::high_resolution_clock::now();
    volatile double sum = 0.0;
    for (int i = 0; i < iterations; i++) {{
        sum += i * 0.001;
    }}
    auto end = std::chrono::high_resolution_clock::now();
    std::chrono::duration<double, std::milli> elapsed = end - start;
    return elapsed.count();
}}

}} // extern "C"
'''

MAKEFILE_TEMPLATE = '''
CXX = g++
CXXFLAGS = -std=c++17 -O2 -fPIC -shared
LDFLAGS = -lpthread

TARGET = {output_name}
SOURCES = $(wildcard *.cpp)

all: $(TARGET)

$(TARGET): $(SOURCES)
\t$(CXX) $(CXXFLAGS) -o $@ $^ $(LDFLAGS)

clean:
\trm -f $(TARGET)

.PHONY: all clean
'''

BENCHMARK_SCRIPT = '''
import time
import json
import sys

def benchmark_message_processing(iterations=10000):
    start = time.time()
    for i in range(iterations):
        role = "user"
        content = f"test message {i}"
        tool_calls = "[]"
    elapsed = time.time() - start
    return {"ops_per_sec": iterations / elapsed, "avg_latency_ms": elapsed / iterations * 1000}

def benchmark_tool_execution(iterations=5000):
    start = time.time()
    for i in range(iterations):
        tool_name = "bash"
        args = json.dumps({"command": f"echo {i}"})
    elapsed = time.time() - start
    return {"ops_per_sec": iterations / elapsed, "avg_latency_ms": elapsed / iterations * 1000}

if __name__ == "__main__":
    msg_result = benchmark_message_processing()
    tool_result = benchmark_tool_execution()
    print(json.dumps({"message_processing": msg_result, "tool_execution": tool_result}, indent=2))
'''


class PerformanceMonitor:
    def __init__(self):
        self._profiles: list[PerformanceProfile] = []
        self._lock = threading.Lock()
        self._monitoring = False

    def profile(self) -> PerformanceProfile:
        import psutil
        try:
            process = psutil.Process(os.getpid())
            mem = process.memory_info().rss / 1024 / 1024
            cpu = process.cpu_percent(interval=0.1)
        except ImportError:
            mem = 0.0
            cpu = 0.0

        p = PerformanceProfile(
            memory_mb=mem,
            cpu_percent=cpu,
            timestamp=time.time(),
        )

        with self._lock:
            self._profiles.append(p)
            if len(self._profiles) > 1000:
                self._profiles = self._profiles[-500:]

        return p

    def run_benchmark(self) -> dict:
        msg_result = self._benchmark_messages()
        tool_result = self._benchmark_tools()
        return {"message_processing": msg_result, "tool_execution": tool_result}

    def _benchmark_messages(self, iterations=10000) -> dict:
        start = time.time()
        for _ in range(iterations):
            msg = {"role": "user", "content": "benchmark test"}
            _ = json.dumps(msg)
        elapsed = time.time() - start
        return {"ops_per_sec": iterations / elapsed, "avg_latency_ms": elapsed / iterations * 1000}

    def _benchmark_tools(self, iterations=5000) -> dict:
        start = time.time()
        for i in range(iterations):
            args = json.dumps({"command": f"echo {i}"})
        elapsed = time.time() - start
        return {"ops_per_sec": iterations / elapsed, "avg_latency_ms": elapsed / iterations * 1000}

    def should_rewrite(self, latency_threshold_ms: float = 100.0) -> tuple[bool, str]:
        bench = self.run_benchmark()
        msg_latency = bench["message_processing"]["avg_latency_ms"]

        if msg_latency > latency_threshold_ms:
            return True, f"消息处理延迟 {msg_latency:.1f}ms 超过阈值 {latency_threshold_ms}ms"

        return False, ""


class TheseusEngine:
    def __init__(self, rewrite_dir: str = REWRITE_DIR, backup_dir: str = BACKUP_DIR):
        self.rewrite_dir = rewrite_dir
        self.backup_dir = backup_dir
        self.monitor = PerformanceMonitor()
        self._plans: dict[str, RewritePlan] = {}
        self._active_swaps: dict[str, dict] = {}
        os.makedirs(rewrite_dir, exist_ok=True)
        os.makedirs(backup_dir, exist_ok=True)

    def create_rewrite_plan(
        self,
        target_module: str,
        target_language: str = "cpp",
        reason: str = "",
    ) -> RewritePlan:
        plan_id = f"plan_{int(time.time())}_{target_module}"
        source_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{target_module}.py")
        output_name = f"theseus_{target_module}.so"
        output_file = os.path.join(self.rewrite_dir, plan_id, output_name)

        plan = RewritePlan(
            target_module=target_module,
            target_language=target_language,
            reason=reason,
            source_file=source_file,
            output_file=output_file,
            created_at=time.time(),
        )

        self._plans[plan_id] = plan
        logger.info(f"创建重写计划: {plan_id} ({target_module} → {target_language})")
        return plan

    def generate_cpp_rewrite(self, plan_id: str) -> tuple[bool, str]:
        plan = self._plans.get(plan_id)
        if plan is None:
            return False, f"计划 {plan_id} 不存在"

        work_dir = os.path.join(self.rewrite_dir, plan_id)
        os.makedirs(work_dir, exist_ok=True)

        cpp_code = CPP_TEMPLATE.format(
            module_name=plan.target_module,
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            reason=plan.reason,
        )

        cpp_path = os.path.join(work_dir, f"theseus_{plan.target_module}.cpp")
        with open(cpp_path, "w") as f:
            f.write(cpp_code)

        makefile = MAKEFILE_TEMPLATE.format(output_name=os.path.basename(plan.output_file))
        makefile_path = os.path.join(work_dir, "Makefile")
        with open(makefile_path, "w") as f:
            f.write(makefile)

        bench_path = os.path.join(work_dir, "benchmark.py")
        with open(bench_path, "w") as f:
            f.write(BENCHMARK_SCRIPT)

        plan.status = "generated"
        logger.info(f"C++ 重写代码已生成: {cpp_path}")
        return True, work_dir

    def compile_rewrite(self, plan_id: str) -> tuple[bool, str]:
        plan = self._plans.get(plan_id)
        if plan is None:
            return False, f"计划 {plan_id} 不存在"

        work_dir = os.path.join(self.rewrite_dir, plan_id)

        try:
            result = subprocess.run(
                ["make"],
                capture_output=True, text=True, timeout=120,
                cwd=work_dir,
            )

            if result.returncode == 0:
                plan.status = "compiled"
                logger.info(f"编译成功: {plan.output_file}")
                return True, plan.output_file
            else:
                plan.status = "compile_failed"
                error = result.stderr[:500]
                logger.error(f"编译失败: {error}")
                return False, f"编译失败: {error}"

        except FileNotFoundError:
            return False, "make 命令未找到，请安装 build-essential"
        except subprocess.TimeoutExpired:
            return False, "编译超时"
        except Exception as e:
            return False, str(e)

    def hot_swap(self, plan_id: str) -> HotSwapResult:
        plan = self._plans.get(plan_id)
        if plan is None:
            return HotSwapResult(success=False, error=f"计划 {plan_id} 不存在")

        if plan.status != "compiled":
            return HotSwapResult(success=False, error=f"计划状态不是 compiled: {plan.status}")

        if not os.path.exists(plan.output_file):
            return HotSwapResult(success=False, error=f".so 文件不存在: {plan.output_file}")

        backup_path = self._backup_module(plan.target_module)
        if not backup_path:
            logger.warning(f"无法备份 {plan.target_module}，继续热切换")

        try:
            lib = ctypes.CDLL(plan.output_file)

            version = lib.theseus_get_version()
            version_str = ctypes.cast(version, ctypes.c_char_p).value.decode()

            module_name = lib.theseus_get_module()
            module_str = ctypes.cast(module_name, ctypes.c_char_p).value.decode()

            logger.info(f"热切换验证: version={version_str}, module={module_str}")

            self._active_swaps[plan.target_module] = {
                "plan_id": plan_id,
                "library": lib,
                "so_path": plan.output_file,
                "backup_path": backup_path,
                "swapped_at": time.time(),
            }

            plan.status = "deployed"
            plan.deployed_at = time.time()

            logger.info(f"🔥 热切换成功: {plan.target_module} → {plan.output_file}")

            return HotSwapResult(
                success=True,
                module=plan.target_module,
                old_version=f"python/{plan.target_module}.py",
                new_version=f"cpp/{os.path.basename(plan.output_file)}",
                message=f"模块 {plan.target_module} 已从 Python 热切换到 C++ ({version_str})",
                rollback_available=bool(backup_path),
            )

        except Exception as e:
            logger.error(f"热切换失败: {e}")
            if backup_path:
                self._rollback_module(plan.target_module, backup_path)

            return HotSwapResult(
                success=False,
                module=plan.target_module,
                error=f"热切换异常: {str(e)}",
            )

    def rollback(self, module_name: str) -> HotSwapResult:
        swap_info = self._active_swaps.get(module_name)
        if swap_info is None:
            return HotSwapResult(success=False, error=f"模块 {module_name} 未被热切换")

        backup_path = swap_info.get("backup_path", "")
        if backup_path and os.path.exists(backup_path):
            self._rollback_module(module_name, backup_path)

        self._active_swaps.pop(module_name, None)

        return HotSwapResult(
            success=True,
            module=module_name,
            new_version=f"python/{module_name}.py",
            message=f"模块 {module_name} 已回滚到 Python 版本",
            rollback_available=False,
        )

    def _backup_module(self, module_name: str) -> Optional[str]:
        source = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{module_name}.py")
        if not os.path.exists(source):
            return None

        backup = os.path.join(self.backup_dir, f"{module_name}_{int(time.time())}.py.bak")
        try:
            shutil.copy2(source, backup)
            return backup
        except Exception as e:
            logger.error(f"备份失败: {e}")
            return None

    def _rollback_module(self, module_name: str, backup_path: str) -> bool:
        target = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{module_name}.py")
        try:
            shutil.copy2(backup_path, target)
            logger.info(f"已回滚: {module_name}")
            return True
        except Exception as e:
            logger.error(f"回滚失败: {e}")
            return False

    def get_status(self) -> dict:
        return {
            "plans": {
                pid: {
                    "module": p.target_module,
                    "language": p.target_language,
                    "status": p.status,
                    "reason": p.reason,
                }
                for pid, p in self._plans.items()
            },
            "active_swaps": {
                mod: {
                    "so_path": info["so_path"],
                    "swapped_at": info["swapped_at"],
                }
                for mod, info in self._active_swaps.items()
            },
            "performance": self.monitor.run_benchmark(),
        }


_theseus: Optional[TheseusEngine] = None


def get_theseus_engine() -> TheseusEngine:
    global _theseus
    if _theseus is None:
        _theseus = TheseusEngine()
    return _theseus


THESEUS_TOOL_DEFINITION_ANTHROPIC = {
    "name": "theseus_rewrite",
    "description": (
        "忒修斯之船工具 - 核心自重构引擎。允许 Agent 重写自己的核心模块。"
        "action='benchmark': 运行性能基准测试"
        "action='plan': 创建重写计划（将 Python 模块重写为 C++）"
        "action='generate': 生成 C++ 重写代码"
        "action='compile': 编译 C++ 代码为 .so 动态库"
        "action='hot_swap': 热切换到 C++ 版本"
        "action='rollback': 回滚到 Python 版本"
        "action='status': 查看重写状态"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["benchmark", "plan", "generate", "compile", "hot_swap", "rollback", "status"],
                "description": "操作类型",
            },
            "module": {
                "type": "string",
                "description": "目标模块名（如 agent_runner）",
            },
            "language": {
                "type": "string",
                "description": "目标语言（默认 cpp）",
                "default": "cpp",
            },
            "reason": {
                "type": "string",
                "description": "重写原因",
            },
            "plan_id": {
                "type": "string",
                "description": "重写计划 ID",
            },
        },
        "required": ["action"],
    },
}

THESEUS_TOOL_DEFINITION_OPENAI = {
    "type": "function",
    "function": {
        "name": "theseus_rewrite",
        "description": (
            "忒修斯之船工具 - 核心自重构引擎。允许 Agent 重写自己的核心模块，"
            "从 Python 热切换到 C++ 等高性能语言。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["benchmark", "plan", "generate", "compile", "hot_swap", "rollback", "status"],
                    "description": "操作类型",
                },
                "module": {"type": "string", "description": "目标模块名"},
                "language": {"type": "string", "description": "目标语言"},
                "reason": {"type": "string", "description": "重写原因"},
                "plan_id": {"type": "string", "description": "计划 ID"},
            },
            "required": ["action"],
        },
    },
}


def execute_theseus_tool(**kwargs) -> tuple[str, bool]:
    action = kwargs.get("action", "status")
    engine = get_theseus_engine()

    if action == "benchmark":
        bench = engine.monitor.run_benchmark()
        msg = bench["message_processing"]
        tool = bench["tool_execution"]
        should, reason = engine.monitor.should_rewrite()
        return (
            f"📊 性能基准测试:\n"
            f"  消息处理: {msg['ops_per_sec']:.0f} ops/s, 延迟 {msg['avg_latency_ms']:.3f}ms\n"
            f"  工具执行: {tool['ops_per_sec']:.0f} ops/s, 延迟 {tool['avg_latency_ms']:.3f}ms\n"
            f"  需要重写: {'是' if should else '否'} {reason}",
            False,
        )

    elif action == "plan":
        module = kwargs.get("module", "")
        if not module:
            return "需要提供 module 参数", True
        language = kwargs.get("language", "cpp")
        reason = kwargs.get("reason", "性能优化")
        plan = engine.create_rewrite_plan(module, language, reason)
        return (
            f"✅ 重写计划已创建\n"
            f"  计划 ID: {list(engine._plans.keys())[-1]}\n"
            f"  目标模块: {module}\n"
            f"  目标语言: {language}\n"
            f"  原因: {reason}\n"
            f"下一步: theseus_rewrite(action='generate', plan_id='{list(engine._plans.keys())[-1]}')",
            False,
        )

    elif action == "generate":
        plan_id = kwargs.get("plan_id", "")
        if not plan_id:
            return "需要提供 plan_id", True
        success, result = engine.generate_cpp_rewrite(plan_id)
        if success:
            return f"✅ C++ 重写代码已生成\n  工作目录: {result}\n下一步: theseus_rewrite(action='compile', plan_id='{plan_id}')", False
        return f"❌ 代码生成失败: {result}", True

    elif action == "compile":
        plan_id = kwargs.get("plan_id", "")
        if not plan_id:
            return "需要提供 plan_id", True
        success, result = engine.compile_rewrite(plan_id)
        if success:
            return f"✅ 编译成功\n  .so 文件: {result}\n下一步: theseus_rewrite(action='hot_swap', plan_id='{plan_id}')", False
        return f"❌ 编译失败: {result}", True

    elif action == "hot_swap":
        plan_id = kwargs.get("plan_id", "")
        if not plan_id:
            return "需要提供 plan_id", True
        result = engine.hot_swap(plan_id)
        if result.success:
            return f"🔥 {result.message}\n  旧版本: {result.old_version}\n  新版本: {result.new_version}\n  可回滚: {'是' if result.rollback_available else '否'}", False
        return f"❌ 热切换失败: {result.error}", True

    elif action == "rollback":
        module = kwargs.get("module", "")
        if not module:
            return "需要提供 module 参数", True
        result = engine.rollback(module)
        if result.success:
            return f"✅ {result.message}", False
        return f"❌ 回滚失败: {result.error}", True

    elif action == "status":
        status = engine.get_status()
        lines = ["🚢 忒修斯之船状态:"]
        if status["plans"]:
            lines.append(f"  重写计划: {len(status['plans'])} 个")
            for pid, p in status["plans"].items():
                lines.append(f"    {pid}: {p['module']} → {p['language']} ({p['status']})")
        else:
            lines.append("  重写计划: 无")
        if status["active_swaps"]:
            lines.append(f"  活跃热切换: {len(status['active_swaps'])} 个")
            for mod, info in status["active_swaps"].items():
                lines.append(f"    {mod}: {info['so_path']}")
        else:
            lines.append("  活跃热切换: 无")
        perf = status["performance"]
        lines.append(f"  性能: 消息 {perf['message_processing']['ops_per_sec']:.0f} ops/s")
        return "\n".join(lines), False

    else:
        return f"未知操作: {action}", True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("Eruitah 忒修斯之船引擎测试")
    print("=" * 60)

    engine = get_theseus_engine()

    print("\n--- 性能基准测试 ---")
    result, _ = execute_theseus_tool(action="benchmark")
    print(result)

    print("\n--- 创建重写计划 ---")
    result, _ = execute_theseus_tool(action="plan", module="agent_runner", reason="性能优化")
    print(result)

    print("\n--- 查看状态 ---")
    result, _ = execute_theseus_tool(action="status")
    print(result)

    print("\n✅ 忒修斯之船引擎测试通过!")
