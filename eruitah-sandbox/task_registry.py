"""
Eruitah 智能编程沙盒 - 任务注册表 + 物理快照系统（多租户隔离版）

核心设计:
  每个用户提问 = 一个任务 (Task)
  任务开始前 = 物理备份整个工作目录 (shutil.copytree)
  任务回退 = 物理还原整个工作目录 (shutil.rmtree + shutil.copytree) + 消息截断

物理备份路径: .user_data/user_{user_id}/snapshots/{task_id}_pre/
注册表文件: .user_data/user_{user_id}/snapshots/registry.json

重要：所有路径严格绑定 user_id，绝不允许跨用户访问
"""

import os
import json
import time
import shutil
import logging
import threading
from dataclasses import dataclass
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)

USER_DATA_ROOT = os.environ.get(
    "ERUITAH_USER_DATA_ROOT",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".user_data"),
)

IGNORE_PATTERNS = {
    "node_modules", "__pycache__", ".git", "venv", ".venv",
    "dist", "build", ".next", ".nuxt", "target", ".gradle",
    ".eruitah_snapshots", ".checkpoints", ".eruitah_cache",
    ".tasks", ".user_data",
}


@dataclass
class TaskRecord:
    task_id: str
    summary: str
    work_dir: str
    snapshot_path: str
    messages_before: List[Dict[str, Any]]
    created_at: float
    status: str = "active"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "summary": self.summary,
            "work_dir": self.work_dir,
            "snapshot_path": self.snapshot_path,
            "messages_before": self.messages_before,
            "created_at": self.created_at,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskRecord":
        return cls(
            task_id=data["task_id"],
            summary=data["summary"],
            work_dir=data["work_dir"],
            snapshot_path=data["snapshot_path"],
            messages_before=data.get("messages_before", []),
            created_at=data.get("created_at", time.time()),
            status=data.get("status", "active"),
        )


def _get_user_snapshot_dir(user_id: int) -> str:
    d = os.path.join(USER_DATA_ROOT, f"user_{user_id}", "snapshots")
    os.makedirs(d, exist_ok=True)
    return d


class TaskRegistry:
    def __init__(self, user_id: int):
        if not user_id:
            user_id = 1
            logger.warning("TaskRegistry created with user_id=0, falling back to 1")
        self._user_id = user_id
        self._tasks: Dict[str, TaskRecord] = {}
        self._lock = threading.Lock()
        os.makedirs(self._snapshot_base_dir(), exist_ok=True)
        self._load_registry()

    def _snapshot_base_dir(self) -> str:
        return _get_user_snapshot_dir(self._user_id)

    def _registry_path(self) -> str:
        return os.path.join(self._snapshot_base_dir(), "registry.json")

    def _load_registry(self):
        path = self._registry_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for item in data:
                    record = TaskRecord.from_dict(item)
                    self._tasks[record.task_id] = record
                logger.info(f"TaskRegistry(user={self._user_id}) 已加载 {len(self._tasks)} 条任务记录")
            except Exception as e:
                logger.error(f"加载任务注册表失败: {e}")

    def _save_registry(self):
        path = self._registry_path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(
                    [t.to_dict() for t in self._tasks.values()],
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as e:
            logger.error(f"保存任务注册表失败: {e}")

    def _ignore_filter(self, directory: str, contents: list) -> list:
        ignored = []
        for name in contents:
            if name in IGNORE_PATTERNS:
                ignored.append(name)
        return ignored

    def register_task(
        self,
        task_id: str,
        summary: str,
        work_dir: str,
        messages_before: List[Dict[str, Any]],
    ) -> TaskRecord:
        snapshot_path = os.path.join(self._snapshot_base_dir(), f"{task_id}_pre")

        with self._lock:
            if task_id in self._tasks:
                logger.warning(f"任务 {task_id} 已存在，跳过注册")
                return self._tasks[task_id]

            logger.info(f"📦 注册任务 {task_id}: {summary[:50]}")

            if os.path.exists(work_dir):
                if os.path.exists(snapshot_path):
                    shutil.rmtree(snapshot_path, ignore_errors=True)
                shutil.copytree(
                    work_dir,
                    snapshot_path,
                    ignore=self._ignore_filter,
                    dirs_exist_ok=True,
                )
                logger.info(f"📦 物理快照已创建: {work_dir} → {snapshot_path}")
            else:
                logger.warning(f"工作目录不存在，跳过快照: {work_dir}")

            record = TaskRecord(
                task_id=task_id,
                summary=summary,
                work_dir=work_dir,
                snapshot_path=snapshot_path,
                messages_before=messages_before.copy() if messages_before else [],
                created_at=time.time(),
                status="active",
            )
            self._tasks[task_id] = record
            self._save_registry()

        return record

    def rollback_task(self, task_id: str) -> Dict[str, Any]:
        with self._lock:
            if task_id not in self._tasks:
                return {"success": False, "error": f"任务 {task_id} 不存在"}

            record = self._tasks[task_id]

            if record.status == "rolled_back":
                return {"success": False, "error": f"任务 {task_id} 已被回退过"}

            if not os.path.exists(record.snapshot_path):
                return {
                    "success": False,
                    "error": f"快照目录不存在: {record.snapshot_path}",
                }

            work_dir = record.work_dir

            logger.info(f"⏪ 物理回退任务 {task_id}: {record.summary[:50]}")
            logger.info(f"⏪ 删除当前工作目录: {work_dir}")
            logger.info(f"⏪ 从快照还原: {record.snapshot_path}")

            try:
                for item in os.listdir(work_dir):
                    if item in IGNORE_PATTERNS:
                        continue
                    item_path = os.path.join(work_dir, item)
                    try:
                        if os.path.isdir(item_path):
                            shutil.rmtree(item_path)
                        else:
                            os.unlink(item_path)
                    except Exception as e:
                        logger.warning(f"删除 {item_path} 失败: {e}")

                for item in os.listdir(record.snapshot_path):
                    if item in IGNORE_PATTERNS:
                        continue
                    src = os.path.join(record.snapshot_path, item)
                    dst = os.path.join(work_dir, item)
                    try:
                        if os.path.isdir(src):
                            shutil.copytree(src, dst, dirs_exist_ok=True)
                        else:
                            shutil.copy2(src, dst)
                    except Exception as e:
                        logger.warning(f"还原 {item} 失败: {e}")

                record.status = "rolled_back"
                self._save_registry()

                logger.info(f"⏪ 物理回退完成: {task_id}")

                return {
                    "success": True,
                    "task_id": task_id,
                    "summary": record.summary,
                    "messages_before": record.messages_before,
                    "work_dir": work_dir,
                }

            except Exception as e:
                logger.error(f"⏪ 物理回退失败: {e}")
                return {"success": False, "error": str(e)}

    def list_tasks(self, work_dir: str = "") -> List[Dict[str, Any]]:
        with self._lock:
            tasks = []
            for record in self._tasks.values():
                if work_dir and record.work_dir != work_dir:
                    continue
                tasks.append(record.to_dict())
            tasks.sort(key=lambda t: t.get("created_at", 0), reverse=True)
            return tasks

    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        with self._lock:
            return self._tasks.get(task_id)

    def set_task_status(self, task_id: str, status: str):
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].status = status
                self._save_registry()

    def delete_task_snapshot(self, task_id: str):
        with self._lock:
            if task_id in self._tasks:
                record = self._tasks[task_id]
                if os.path.exists(record.snapshot_path):
                    shutil.rmtree(record.snapshot_path, ignore_errors=True)
                    logger.info(f"已删除快照: {record.snapshot_path}")

    def delete_task(self, task_id: str):
        with self._lock:
            if task_id in self._tasks:
                record = self._tasks[task_id]
                if os.path.exists(record.snapshot_path):
                    shutil.rmtree(record.snapshot_path, ignore_errors=True)
                del self._tasks[task_id]
                self._save_registry()
                logger.info(f"已彻底删除任务记录: {task_id}")


_registries: Dict[int, TaskRegistry] = {}
_registries_lock = threading.Lock()


def get_task_registry(user_id: int = 0) -> TaskRegistry:
    if not user_id:
        user_id = 1
        logger.warning("get_task_registry() called without user_id, falling back to 1")
    with _registries_lock:
        if user_id not in _registries:
            _registries[user_id] = TaskRegistry(user_id=user_id)
        return _registries[user_id]
