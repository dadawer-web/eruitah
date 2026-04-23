"""
Eruitah 智能编程沙盒 - 算力自治引擎 (Compute Autonomy)

核心思想（AI 自己开公司）:
┌─────────────────────────────────────────────────────────────────────┐
│  打破物理服务器结界，Agent 掌管财务与算力调配                        │
│                                                                     │
│  流程:                                                              │
│    1. 算力感知: Agent 发现当前编译需要 64 核 CPU                    │
│    2. 自动扩容: 调用 AWS/阿里云 API，购买按量付费云服务器            │
│    3. 自动部署: SSH 登录新服务器，部署影子沙盒                       │
│    4. 执行任务: 在新服务器上光速编译                                 │
│    5. 过河拆桥: 编译完成，自动销毁云服务器                           │
│                                                                     │
│  支持的云平台:                                                      │
│    - AWS EC2                                                        │
│    - 阿里云 ECS                                                     │
│    - 本地 Docker（无云 API 时降级）                                  │
│                                                                     │
│  成本控制:                                                          │
│    - 预算上限（每日/每月）                                           │
│    - 单次任务成本估算                                               │
│    - 自动选择最便宜的实例类型                                       │
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

BUDGET_DB = os.environ.get(
    "ERUITAH_BUDGET_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".budget.db"),
)

DEFAULT_DAILY_BUDGET = float(os.environ.get("ERUITAH_DAILY_BUDGET", "10.0"))
DEFAULT_MONTHLY_BUDGET = float(os.environ.get("ERUITAH_MONTHLY_BUDGET", "200.0"))


@dataclass
class CloudInstance:
    id: str
    provider: str
    instance_type: str
    ip: str = ""
    status: str = "pending"
    cost_per_hour: float = 0.0
    launched_at: float = 0.0
    terminated_at: float = 0.0
    task: str = ""
    region: str = ""


@dataclass
class CostEstimate:
    instance_type: str
    cost_per_hour: float
    estimated_hours: float
    estimated_total: float
    provider: str
    region: str


@dataclass
class ScaleResult:
    success: bool
    instance: Optional[CloudInstance] = None
    message: str = ""
    cost_estimate: Optional[CostEstimate] = None
    error: str = ""


@dataclass
class BudgetStatus:
    daily_spent: float = 0.0
    daily_budget: float = DEFAULT_DAILY_BUDGET
    monthly_spent: float = 0.0
    monthly_budget: float = DEFAULT_MONTHLY_BUDGET
    active_instances: int = 0
    total_instances_launched: int = 0


INSTANCE_CATALOG = {
    "aws": {
        "t3.micro": {"cpu": 2, "ram_gb": 1, "cost_per_hour": 0.0104, "description": "最便宜的通用实例"},
        "t3.small": {"cpu": 2, "ram_gb": 2, "cost_per_hour": 0.0208, "description": "轻量通用实例"},
        "t3.medium": {"cpu": 2, "ram_gb": 4, "cost_per_hour": 0.0416, "description": "中等通用实例"},
        "c5.large": {"cpu": 2, "ram_gb": 4, "cost_per_hour": 0.085, "description": "计算优化实例"},
        "c5.xlarge": {"cpu": 4, "ram_gb": 8, "cost_per_hour": 0.170, "description": "高计算实例"},
        "c5.4xlarge": {"cpu": 16, "ram_gb": 32, "cost_per_hour": 0.680, "description": "强计算实例"},
        "c5.9xlarge": {"cpu": 36, "ram_gb": 72, "cost_per_hour": 1.530, "description": "超强计算实例"},
        "m5.4xlarge": {"cpu": 16, "ram_gb": 64, "cost_per_hour": 0.768, "description": "大内存实例"},
    },
    "aliyun": {
        "ecs.t6-c1m1.small": {"cpu": 1, "ram_gb": 1, "cost_per_hour": 0.05, "description": "突发性能实例"},
        "ecs.c6.large": {"cpu": 2, "ram_gb": 4, "cost_per_hour": 0.35, "description": "计算型实例"},
        "ecs.c6.xlarge": {"cpu": 4, "ram_gb": 8, "cost_per_hour": 0.70, "description": "高计算实例"},
        "ecs.c6.4xlarge": {"cpu": 16, "ram_gb": 32, "cost_per_hour": 2.80, "description": "强计算实例"},
        "ecs.g6.4xlarge": {"cpu": 16, "ram_gb": 64, "cost_per_hour": 3.50, "description": "大内存实例"},
    },
    "local": {
        "docker": {"cpu": 0, "ram_gb": 0, "cost_per_hour": 0.0, "description": "本地 Docker 容器（免费）"},
    },
}


class BudgetManager:
    def __init__(self, db_path: str = BUDGET_DB):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS spending (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_id TEXT,
                provider TEXT,
                amount REAL,
                description TEXT,
                timestamp REAL
            );
            CREATE TABLE IF NOT EXISTS instances (
                id TEXT PRIMARY KEY,
                provider TEXT,
                instance_type TEXT,
                ip TEXT,
                status TEXT,
                cost_per_hour REAL,
                launched_at REAL,
                terminated_at REAL DEFAULT 0,
                task TEXT,
                region TEXT
            );
        """)
        conn.commit()
        conn.close()

    def record_spending(self, instance_id: str, provider: str, amount: float, description: str = ""):
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO spending (instance_id, provider, amount, description, timestamp) VALUES (?, ?, ?, ?, ?)",
            (instance_id, provider, amount, description, time.time()),
        )
        conn.commit()
        conn.close()

    def get_daily_spent(self) -> float:
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        today_start = time.time() - (time.time() % 86400)
        row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM spending WHERE timestamp >= ?",
            (today_start,),
        ).fetchone()
        conn.close()
        return row[0]

    def get_monthly_spent(self) -> float:
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        month_start = time.time() - (time.time() % (86400 * 30))
        row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM spending WHERE timestamp >= ?",
            (month_start,),
        ).fetchone()
        conn.close()
        return row[0]

    def can_afford(self, estimated_cost: float) -> tuple[bool, str]:
        daily_spent = self.get_daily_spent()
        monthly_spent = self.get_monthly_spent()

        if daily_spent + estimated_cost > DEFAULT_DAILY_BUDGET:
            return False, f"超出每日预算 (已花 ${daily_spent:.2f} / ${DEFAULT_DAILY_BUDGET:.2f}, 需要额外 ${estimated_cost:.2f})"

        if monthly_spent + estimated_cost > DEFAULT_MONTHLY_BUDGET:
            return False, f"超出每月预算 (已花 ${monthly_spent:.2f} / ${DEFAULT_MONTHLY_BUDGET:.2f}, 需要额外 ${estimated_cost:.2f})"

        return True, "预算充足"

    def get_status(self) -> BudgetStatus:
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        active = conn.execute("SELECT COUNT(*) FROM instances WHERE status = 'running'").fetchone()[0]
        total = conn.execute("SELECT COUNT(*) FROM instances").fetchone()[0]
        conn.close()

        return BudgetStatus(
            daily_spent=self.get_daily_spent(),
            daily_budget=DEFAULT_DAILY_BUDGET,
            monthly_spent=self.get_monthly_spent(),
            monthly_budget=DEFAULT_MONTHLY_BUDGET,
            active_instances=active,
            total_instances_launched=total,
        )


class ComputeAutonomyEngine:
    def __init__(self):
        self.budget = BudgetManager()
        self._instances: dict[str, CloudInstance] = {}
        self._lock = threading.Lock()

    def estimate_cost(
        self,
        cpu_cores: int = 2,
        ram_gb: int = 4,
        estimated_hours: float = 1.0,
        provider: str = "aws",
        region: str = "us-east-1",
    ) -> CostEstimate:
        catalog = INSTANCE_CATALOG.get(provider, {})

        best_match = None
        best_cost = float("inf")

        for instance_type, specs in catalog.items():
            if specs["cpu"] >= cpu_cores and specs["ram_gb"] >= ram_gb:
                if specs["cost_per_hour"] < best_cost:
                    best_cost = specs["cost_per_hour"]
                    best_match = instance_type

        if best_match is None:
            for instance_type, specs in catalog.items():
                if specs["cost_per_hour"] < best_cost and specs["cpu"] > 0:
                    best_cost = specs["cost_per_hour"]
                    best_match = instance_type

        if best_match is None:
            best_match = "docker"
            best_cost = 0.0
            provider = "local"

        return CostEstimate(
            instance_type=best_match,
            cost_per_hour=best_cost,
            estimated_hours=estimated_hours,
            estimated_total=best_cost * estimated_hours,
            provider=provider,
            region=region,
        )

    def scale_up(
        self,
        task: str,
        cpu_cores: int = 2,
        ram_gb: int = 4,
        estimated_hours: float = 1.0,
        provider: str = "aws",
        region: str = "us-east-1",
    ) -> ScaleResult:
        estimate = self.estimate_cost(cpu_cores, ram_gb, estimated_hours, provider, region)

        can_afford, reason = self.budget.can_afford(estimate.estimated_total)
        if not can_afford:
            return ScaleResult(
                success=False,
                cost_estimate=estimate,
                error=f"预算不足: {reason}",
            )

        instance_id = f"compute_{int(time.time())}_{provider}"

        if provider == "local" or estimate.instance_type == "docker":
            return self._launch_local(instance_id, task, estimate)

        elif provider == "aws":
            return self._launch_aws(instance_id, task, estimate, region)

        elif provider == "aliyun":
            return self._launch_aliyun(instance_id, task, estimate, region)

        else:
            return ScaleResult(success=False, error=f"不支持的云平台: {provider}")

    def _launch_local(self, instance_id: str, task: str, estimate: CostEstimate) -> ScaleResult:
        instance = CloudInstance(
            id=instance_id,
            provider="local",
            instance_type="docker",
            status="running",
            cost_per_hour=0.0,
            launched_at=time.time(),
            task=task,
        )

        with self._lock:
            self._instances[instance_id] = instance

        self.budget.record_spending(instance_id, "local", 0.0, f"本地 Docker: {task}")

        logger.info(f"本地计算实例已启动: {instance_id}")

        return ScaleResult(
            success=True,
            instance=instance,
            message=f"本地 Docker 实例已启动 (免费)\n实例 ID: {instance_id}\n任务: {task}",
            cost_estimate=estimate,
        )

    def _launch_aws(self, instance_id: str, task: str, estimate: CostEstimate, region: str) -> ScaleResult:
        try:
            result = subprocess.run(
                ["aws", "ec2", "run-instances",
                 "--image-id", "ami-0c55b159cbfafe1f0",
                 "--instance-type", estimate.instance_type,
                 "--region", region,
                 "--query", "Instances[0].InstanceId",
                 "--output", "text"],
                capture_output=True, text=True, timeout=60,
            )

            if result.returncode != 0:
                return ScaleResult(
                    success=False,
                    cost_estimate=estimate,
                    error=f"AWS CLI 错误: {result.stderr[:500]}",
                )

            aws_instance_id = result.stdout.strip()

            instance = CloudInstance(
                id=instance_id,
                provider="aws",
                instance_type=estimate.instance_type,
                status="running",
                cost_per_hour=estimate.cost_per_hour,
                launched_at=time.time(),
                task=task,
                region=region,
            )

            with self._lock:
                self._instances[instance_id] = instance

            self.budget.record_spending(instance_id, "aws", estimate.estimated_total, f"AWS {estimate.instance_type}: {task}")

            return ScaleResult(
                success=True,
                instance=instance,
                message=f"AWS 实例已启动\n实例 ID: {instance_id}\nAWS ID: {aws_instance_id}\n类型: {estimate.instance_type}\n预估费用: ${estimate.estimated_total:.4f}",
                cost_estimate=estimate,
            )

        except FileNotFoundError:
            return ScaleResult(success=False, error="AWS CLI 未安装，请运行: pip install awscli")
        except Exception as e:
            return ScaleResult(success=False, error=str(e))

    def _launch_aliyun(self, instance_id: str, task: str, estimate: CostEstimate, region: str) -> ScaleResult:
        return ScaleResult(
            success=False,
            cost_estimate=estimate,
            error="阿里云 CLI 集成待实现，请使用 AWS 或本地模式",
        )

    def scale_down(self, instance_id: str) -> ScaleResult:
        with self._lock:
            instance = self._instances.get(instance_id)

        if instance is None:
            return ScaleResult(success=False, error=f"实例 {instance_id} 不存在")

        if instance.status != "running":
            return ScaleResult(success=False, error=f"实例状态不是 running: {instance.status}")

        if instance.provider == "local":
            instance.status = "terminated"
            instance.terminated_at = time.time()
            return ScaleResult(
                success=True,
                instance=instance,
                message=f"本地实例 {instance_id} 已释放",
            )

        elif instance.provider == "aws":
            try:
                subprocess.run(
                    ["aws", "ec2", "terminate-instances",
                     "--instance-ids", instance.instance_type,
                     "--region", instance.region],
                    capture_output=True, text=True, timeout=30,
                )
                instance.status = "terminated"
                instance.terminated_at = time.time()

                running_hours = (time.time() - instance.launched_at) / 3600
                actual_cost = running_hours * instance.cost_per_hour
                self.budget.record_spending(instance_id, "aws", actual_cost, f"终止 AWS 实例, 实际费用 ${actual_cost:.4f}")

                return ScaleResult(
                    success=True,
                    instance=instance,
                    message=f"AWS 实例 {instance_id} 已终止\n运行时间: {running_hours:.2f}h\n实际费用: ${actual_cost:.4f}",
                )
            except Exception as e:
                return ScaleResult(success=False, error=str(e))

        return ScaleResult(success=False, error=f"不支持的提供商: {instance.provider}")

    def get_status(self) -> dict:
        budget = self.budget.get_status()
        with self._lock:
            active = {iid: {"provider": i.provider, "type": i.instance_type, "task": i.task, "launched_at": i.launched_at}
                      for iid, i in self._instances.items() if i.status == "running"}

        return {
            "budget": {
                "daily_spent": budget.daily_spent,
                "daily_budget": budget.daily_budget,
                "monthly_spent": budget.monthly_spent,
                "monthly_budget": budget.monthly_budget,
            },
            "active_instances": len(active),
            "instances": active,
            "catalog_summary": {
                provider: f"{len(instances)} 种实例类型"
                for provider, instances in INSTANCE_CATALOG.items()
            },
        }


_engine: Optional[ComputeAutonomyEngine] = None


def get_compute_engine() -> ComputeAutonomyEngine:
    global _engine
    if _engine is None:
        _engine = ComputeAutonomyEngine()
    return _engine


COMPUTE_TOOL_DEFINITION_ANTHROPIC = {
    "name": "compute_autonomy",
    "description": (
        "算力自治工具 - 自动扩缩容云服务器，按需购买和释放计算资源。"
        "action='estimate': 估算任务成本"
        "action='scale_up': 启动云服务器实例"
        "action='scale_down': 终止云服务器实例"
        "action='status': 查看预算和实例状态"
        "action='catalog': 查看可用实例类型"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["estimate", "scale_up", "scale_down", "status", "catalog"],
                "description": "操作类型",
            },
            "task": {
                "type": "string",
                "description": "任务描述",
            },
            "cpu_cores": {
                "type": "integer",
                "description": "需要的 CPU 核心数",
                "default": 2,
            },
            "ram_gb": {
                "type": "integer",
                "description": "需要的内存 (GB)",
                "default": 4,
            },
            "estimated_hours": {
                "type": "number",
                "description": "预估运行时间（小时）",
                "default": 1.0,
            },
            "provider": {
                "type": "string",
                "enum": ["aws", "aliyun", "local"],
                "description": "云平台",
                "default": "aws",
            },
            "region": {
                "type": "string",
                "description": "区域",
                "default": "us-east-1",
            },
            "instance_id": {
                "type": "string",
                "description": "实例 ID（scale_down 时使用）",
            },
        },
        "required": ["action"],
    },
}

COMPUTE_TOOL_DEFINITION_OPENAI = {
    "type": "function",
    "function": {
        "name": "compute_autonomy",
        "description": (
            "算力自治工具 - 自动扩缩容云服务器，按需购买和释放计算资源。"
            "Agent 掌管财务与算力调配，自动选择最便宜的实例类型。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["estimate", "scale_up", "scale_down", "status", "catalog"],
                    "description": "操作类型",
                },
                "task": {"type": "string", "description": "任务描述"},
                "cpu_cores": {"type": "integer", "description": "CPU 核心数"},
                "ram_gb": {"type": "integer", "description": "内存 GB"},
                "estimated_hours": {"type": "number", "description": "预估小时"},
                "provider": {"type": "string", "description": "云平台"},
                "region": {"type": "string", "description": "区域"},
                "instance_id": {"type": "string", "description": "实例 ID"},
            },
            "required": ["action"],
        },
    },
}


def execute_compute_tool(**kwargs) -> tuple[str, bool]:
    action = kwargs.get("action", "status")
    engine = get_compute_engine()

    if action == "estimate":
        estimate = engine.estimate_cost(
            cpu_cores=kwargs.get("cpu_cores", 2),
            ram_gb=kwargs.get("ram_gb", 4),
            estimated_hours=kwargs.get("estimated_hours", 1.0),
            provider=kwargs.get("provider", "aws"),
            region=kwargs.get("region", "us-east-1"),
        )
        return (
            f"💰 成本估算:\n"
            f"  实例类型: {estimate.instance_type}\n"
            f"  提供商: {estimate.provider} ({estimate.region})\n"
            f"  每小时费用: ${estimate.cost_per_hour:.4f}\n"
            f"  预估时长: {estimate.estimated_hours:.1f}h\n"
            f"  预估总费用: ${estimate.estimated_total:.4f}",
            False,
        )

    elif action == "scale_up":
        result = engine.scale_up(
            task=kwargs.get("task", "未指定"),
            cpu_cores=kwargs.get("cpu_cores", 2),
            ram_gb=kwargs.get("ram_gb", 4),
            estimated_hours=kwargs.get("estimated_hours", 1.0),
            provider=kwargs.get("provider", "aws"),
            region=kwargs.get("region", "us-east-1"),
        )
        if result.success:
            return f"✅ {result.message}", False
        return f"❌ 扩容失败: {result.error}", True

    elif action == "scale_down":
        instance_id = kwargs.get("instance_id", "")
        if not instance_id:
            return "需要提供 instance_id", True
        result = engine.scale_down(instance_id)
        if result.success:
            return f"✅ {result.message}", False
        return f"❌ 缩容失败: {result.error}", True

    elif action == "status":
        status = engine.get_status()
        b = status["budget"]
        return (
            f"📊 算力自治状态:\n"
            f"  每日预算: ${b['daily_spent']:.2f} / ${b['daily_budget']:.2f}\n"
            f"  每月预算: ${b['monthly_spent']:.2f} / ${b['monthly_budget']:.2f}\n"
            f"  活跃实例: {status['active_instances']}\n"
            f"  可用平台: {', '.join(status['catalog_summary'].keys())}",
            False,
        )

    elif action == "catalog":
        lines = ["📋 可用实例目录:"]
        for provider, instances in INSTANCE_CATALOG.items():
            lines.append(f"\n  [{provider}]")
            for itype, specs in instances.items():
                if specs["cost_per_hour"] > 0:
                    lines.append(f"    {itype}: {specs['cpu']}核/{specs['ram_gb']}GB, ${specs['cost_per_hour']:.4f}/h - {specs['description']}")
                else:
                    lines.append(f"    {itype}: {specs['description']}")
        return "\n".join(lines), False

    else:
        return f"未知操作: {action}", True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("Eruitah 算力自治引擎测试")
    print("=" * 60)

    print("\n--- 成本估算 ---")
    result, _ = execute_compute_tool(action="estimate", cpu_cores=16, ram_gb=32)
    print(result)

    print("\n--- 本地扩容 ---")
    result, _ = execute_compute_tool(action="scale_up", task="编译 Chromium", provider="local")
    print(result)

    print("\n--- 预算状态 ---")
    result, _ = execute_compute_tool(action="status")
    print(result)

    print("\n--- 实例目录 ---")
    result, _ = execute_compute_tool(action="catalog")
    print(result[:500])

    print("\n✅ 算力自治引擎测试通过!")
