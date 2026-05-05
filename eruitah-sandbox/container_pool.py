"""
Eruitah 智能编程沙盒 - Docker 容器池化技术 (Container Pooling)

借鉴操作系统的线程池思想（完美契合 408 考点）:
┌─────────────────────────────────────────────────────────────────────┐
│  痛点: 每次执行代码都临时 run 一个全新容器 → 几秒冷启动延迟          │
│                                                                     │
│  优化: 预热容器池，消除冷启动                                        │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  容器池 (ContainerPool)                                      │   │
│  │                                                              │   │
│  │  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐          │   │
│  │  │ C-01 │  │ C-02 │  │ C-03 │  │ C-04 │  │ C-05 │ ← 热容器 │   │
│  │  │ idle │  │ idle │  │ busy │  │ idle │  │ idle │          │   │
│  │  └──────┘  └──────┘  └──────┘  └──────┘  └──────┘          │   │
│  │     ↑                    ↑                                   │   │
│  │     └── 可分配            └── 执行中                          │   │
│  │                                                              │   │
│  │  系统启动时: 提前拉起 3-5 个干净容器 (pause/闲置)              │   │
│  │  用户请求时: 直接从池中抓取"热容器"分配                        │   │
│  │  执行完毕后: commit/rm 重置容器，异步补充新容器                │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  对应 408 知识点:                                                    │
│    - 线程池: 预创建线程，避免频繁创建/销毁开销                       │
│    - 页面置换: 容器 ↔ 内存页，分配/回收 ↔ 换入/换出                 │
│    - 资源调度: 先来先服务 (FCFS) + 优先级调度                       │
└─────────────────────────────────────────────────────────────────────┘
"""

import os
import time
import json
import uuid
import logging
import threading
import subprocess
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)

DEFAULT_POOL_SIZE = int(os.environ.get("ERUITAH_POOL_SIZE", "3"))
DEFAULT_CONTAINER_IMAGE = os.environ.get("ERUITAH_CONTAINER_IMAGE", "eruitah-sandbox:latest")
DEFAULT_WORK_DIR = os.environ.get("ERUITAH_SANDBOX_DIR", "/tmp/eruitah-sandbox")


class ContainerState(Enum):
    CREATING = "creating"
    IDLE = "idle"
    BUSY = "busy"
    RESETTING = "resetting"
    FAILED = "failed"


@dataclass
class PooledContainer:
    container_id: str = ""
    name: str = ""
    state: ContainerState = ContainerState.CREATING
    assigned_session: str = ""
    created_at: float = 0.0
    last_used_at: float = 0.0
    use_count: int = 0
    work_dir: str = DEFAULT_WORK_DIR


@dataclass
class PoolStats:
    total_created: int = 0
    total_destroyed: int = 0
    total_acquires: int = 0
    total_releases: int = 0
    cold_start_count: int = 0
    warm_hit_count: int = 0
    avg_acquire_time_ms: float = 0.0
    current_idle: int = 0
    current_busy: int = 0

    @property
    def warm_hit_rate(self) -> float:
        if self.total_acquires == 0:
            return 0.0
        return self.warm_hit_count / self.total_acquires


class ContainerPool:
    """
    Docker 容器池 - 预热容器消除冷启动

    生命周期:
        CREATING → IDLE → BUSY → RESETTING → IDLE → ...
                                   ↓
                               FAILED → 销毁 → 补充新容器
    """

    def __init__(
        self,
        pool_size: int = DEFAULT_POOL_SIZE,
        image: str = DEFAULT_CONTAINER_IMAGE,
        work_dir: str = DEFAULT_WORK_DIR,
    ):
        self.pool_size = pool_size
        self.image = image
        self.work_dir = work_dir
        self._pool: dict[str, PooledContainer] = {}
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._stats = PoolStats()
        self._running = False
        self._replenish_thread: Optional[threading.Thread] = None
        self._docker_available = self._check_docker()

    def _check_docker(self) -> bool:
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            logger.warning("Docker 不可用，容器池将使用本地模式")
            return False

    def start(self):
        if not self._docker_available:
            logger.info("Docker 不可用，容器池以本地模式启动")
            self._running = True
            return

        logger.info(f"容器池启动: 预热 {self.pool_size} 个容器 (image={self.image})")
        self._running = True

        for i in range(self.pool_size):
            self._create_container(f"eruitah-pool-{i+1}")

        self._replenish_thread = threading.Thread(
            target=self._replenish_worker,
            daemon=True,
            name="container-pool-replenish",
        )
        self._replenish_thread.start()

        logger.info(f"容器池就绪: {self._count_state(ContainerState.IDLE)} 个热容器可用")

    def stop(self):
        self._running = False

        with self._condition:
            self._condition.notify_all()

        for cid, container in list(self._pool.items()):
            self._destroy_container(cid)

        self._pool.clear()
        logger.info("容器池已停止，所有容器已销毁")

    def acquire(self, session_id: str = "", timeout: float = 30.0) -> Optional[PooledContainer]:
        """
        从池中获取一个热容器

        对应线程池的 getThread():
        1. 有空闲容器 → 直接返回（热启动，0 延迟）
        2. 无空闲容器 → 等待其他容器释放
        3. 超时 → 冷启动创建新容器
        """
        if not self._docker_available:
            return self._create_local_container(session_id)

        start_time = time.time()

        with self._condition:
            while True:
                idle_container = self._find_idle_container()
                if idle_container:
                    idle_container.state = ContainerState.BUSY
                    idle_container.assigned_session = session_id or str(uuid.uuid4())[:8]
                    idle_container.last_used_at = time.time()
                    idle_container.use_count += 1
                    self._stats.total_acquires += 1
                    self._stats.warm_hit_count += 1
                    self._stats.current_idle -= 1
                    self._stats.current_busy += 1

                    elapsed_ms = (time.time() - start_time) * 1000
                    self._update_avg_acquire_time(elapsed_ms)

                    logger.info(
                        f"🔥 热容器分配: {idle_container.name} -> session={idle_container.assigned_session} "
                        f"({elapsed_ms:.0f}ms)"
                    )
                    return idle_container

                if time.time() - start_time > timeout:
                    break

                self._condition.wait(timeout=1.0)

        logger.warning(f"容器池耗尽，冷启动创建新容器 (session={session_id})")
        self._stats.cold_start_count += 1
        self._stats.total_acquires += 1

        container = self._create_container(f"eruitah-cold-{uuid.uuid4().hex[:8]}")
        if container:
            container.state = ContainerState.BUSY
            container.assigned_session = session_id or str(uuid.uuid4())[:8]
            container.last_used_at = time.time()
            container.use_count += 1
            self._stats.current_busy += 1
            return container

        return None

    def release(self, container_id: str, reset: bool = True):
        """
        释放容器回池中

        对应线程池的 returnThread():
        1. 重置容器状态（清理工作目录）
        2. 如果容器使用次数过多，销毁并补充新容器
        3. 否则标记为 IDLE，等待下次分配
        """
        with self._condition:
            container = self._pool.get(container_id)
            if not container:
                return

            container.assigned_session = ""
            self._stats.total_releases += 1
            self._stats.current_busy -= 1

            if not self._docker_available:
                container.state = ContainerState.IDLE
                self._stats.current_idle += 1
                self._condition.notify()
                return

            if reset and container.use_count >= 10:
                logger.info(f"容器 {container.name} 已使用 {container.use_count} 次，销毁并补充")
                self._destroy_container(container_id)
                self._create_container(f"eruitah-pool-{uuid.uuid4().hex[:8]}")
            elif reset:
                self._reset_container(container)
            else:
                container.state = ContainerState.IDLE
                self._stats.current_idle += 1

            self._condition.notify()

    def execute_in_container(
        self,
        container_id: str,
        command: str,
        timeout: int = 120,
    ) -> tuple[str, int, float]:
        """
        在容器中执行命令

        Returns:
            (stdout, exit_code, elapsed_seconds)
        """
        container = self._pool.get(container_id)
        if not container:
            return "容器不存在", -1, 0.0

        if not self._docker_available:
            return self._execute_local(command, timeout)

        start_time = time.time()

        try:
            result = subprocess.run(
                [
                    "docker", "exec",
                    container.container_id,
                    "/bin/bash", "-c", command,
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            elapsed = time.time() - start_time
            output = result.stdout
            if result.stderr:
                output += f"\n{result.stderr}"
            if result.returncode != 0:
                output += f"\nExit code {result.returncode}"

            return output[:5000], result.returncode, elapsed

        except subprocess.TimeoutExpired:
            return f"命令超时 ({timeout}s)", -1, time.time() - start_time
        except Exception as e:
            return f"执行失败: {e}", -1, time.time() - start_time

    def get_stats(self) -> PoolStats:
        with self._lock:
            self._stats.current_idle = self._count_state(ContainerState.IDLE)
            self._stats.current_busy = self._count_state(ContainerState.BUSY)
            return self._stats

    def _create_container(self, name: str) -> Optional[PooledContainer]:
        if not self._docker_available:
            return None

        container = PooledContainer(
            name=name,
            state=ContainerState.CREATING,
            created_at=time.time(),
        )

        try:
            result = subprocess.run(
                [
                    "docker", "run",
                    "-d",
                    "--name", name,
                    "--network", "host",
                    "-v", f"{self.work_dir}:/workspace",
                    "--memory", "512m",
                    "--cpus", "0.5",
                    self.image,
                    "sleep", "infinity",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                container.container_id = result.stdout.strip()[:12]
                container.state = ContainerState.IDLE
                self._stats.total_created += 1
                self._stats.current_idle += 1
                logger.info(f"容器创建成功: {name} (id={container.container_id})")
            else:
                container.state = ContainerState.FAILED
                logger.error(f"容器创建失败: {name} - {result.stderr}")

        except Exception as e:
            container.state = ContainerState.FAILED
            logger.error(f"容器创建异常: {name} - {e}")

        with self._lock:
            self._pool[name] = container

        return container

    def _destroy_container(self, container_id_or_name: str):
        container = self._pool.pop(container_id_or_name, None)
        if not container:
            return

        try:
            subprocess.run(
                ["docker", "rm", "-f", container.name],
                capture_output=True,
                timeout=10,
            )
            self._stats.total_destroyed += 1
            logger.info(f"容器已销毁: {container.name}")
        except Exception as e:
            logger.error(f"容器销毁失败: {container.name} - {e}")

    def _reset_container(self, container: PooledContainer):
        container.state = ContainerState.RESETTING

        try:
            subprocess.run(
                [
                    "docker", "exec", container.container_id,
                    "/bin/bash", "-c",
                    f"find /workspace -mindepth 1 -delete 2>/dev/null; "
                    f"cd /workspace",
                ],
                capture_output=True,
                timeout=10,
            )
            container.state = ContainerState.IDLE
            self._stats.current_idle += 1
        except Exception:
            container.state = ContainerState.FAILED
            logger.error(f"容器重置失败: {container.name}")

    def _find_idle_container(self) -> Optional[PooledContainer]:
        for c in self._pool.values():
            if c.state == ContainerState.IDLE:
                return c
        return None

    def _count_state(self, state: ContainerState) -> int:
        return sum(1 for c in self._pool.values() if c.state == state)

    def _replenish_worker(self):
        while self._running:
            try:
                time.sleep(10)

                with self._lock:
                    idle_count = self._count_state(ContainerState.IDLE)
                    failed_count = self._count_state(ContainerState.FAILED)

                if idle_count < self.pool_size:
                    needed = self.pool_size - idle_count - failed_count
                    for _ in range(min(needed, 2)):
                        self._create_container(f"eruitah-pool-{uuid.uuid4().hex[:8]}")

                for name, container in list(self._pool.items()):
                    if container.state == ContainerState.FAILED:
                        self._destroy_container(name)
                        self._create_container(f"eruitah-pool-{uuid.uuid4().hex[:8]}")

            except Exception as e:
                logger.error(f"容器补充线程异常: {e}")

    def _create_local_container(self, session_id: str) -> PooledContainer:
        name = f"local-{uuid.uuid4().hex[:8]}"
        container = PooledContainer(
            name=name,
            state=ContainerState.BUSY,
            assigned_session=session_id or name,
            created_at=time.time(),
            last_used_at=time.time(),
            use_count=1,
        )
        with self._lock:
            self._pool[name] = container
            self._stats.total_acquires += 1
            self._stats.current_busy += 1
        return container

    def _execute_local(self, command: str, timeout: int = 120) -> tuple[str, int, float]:
        start_time = time.time()
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.work_dir,
            )
            elapsed = time.time() - start_time
            output = result.stdout
            if result.stderr:
                output += f"\n{result.stderr}"
            if result.returncode != 0:
                output += f"\nExit code {result.returncode}"
            return output[:5000], result.returncode, elapsed
        except subprocess.TimeoutExpired:
            return f"命令超时 ({timeout}s)", -1, time.time() - start_time
        except Exception as e:
            return f"执行失败: {e}", -1, time.time() - start_time

    def _update_avg_acquire_time(self, elapsed_ms: float):
        if self._stats.total_acquires == 1:
            self._stats.avg_acquire_time_ms = elapsed_ms
        else:
            alpha = 0.3
            self._stats.avg_acquire_time_ms = (
                alpha * elapsed_ms + (1 - alpha) * self._stats.avg_acquire_time_ms
            )


_local_pool: Optional[ContainerPool] = None


def get_container_pool() -> ContainerPool:
    global _local_pool
    if _local_pool is None:
        _local_pool = ContainerPool()
    return _local_pool


def start_container_pool():
    pool = get_container_pool()
    if not pool._running:
        pool.start()
    return pool


def stop_container_pool():
    global _local_pool
    if _local_pool:
        _local_pool.stop()
        _local_pool = None


import atexit
atexit.register(stop_container_pool)
