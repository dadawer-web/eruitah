"""
任务增量日志管道（Task Incremental Log Pipeline）

生产端：push_log(task_id, state, message, percent)
  → Redis RPUSH task_logs:{task_id} + EXPIRE 1800s
  → Redis SET task_alive:{task_id} timestamp + EXPIRE 1800s（保活心跳）

消费端：drain_logs(task_id)
  → Redis LRANGE + DELETE（读后即焚，实现真正的增量流）

防僵尸：is_task_alive(task_id)
  → 检查 task_alive:{task_id} 是否存在，不存在则任务已死亡

Redis DB 2 专用于任务日志，避免与 Celery broker(0)/backend(1) 冲突。
"""

import json
import logging
import os
import time
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ── 硬性过期时间：1800 秒（30 分钟） ──
# Worker 被 SIGKILL 后，最多 30 分钟尸体自动清理
TASK_TTL = 1800

# ── 全局 Redis 客户端（懒初始化，进程级复用） ──
_redis_client = None


def _get_redis():
    """懒初始化 Redis 客户端，进程级复用"""
    global _redis_client
    if _redis_client is not None:
        try:
            _redis_client.ping()
            return _redis_client
        except Exception:
            _redis_client = None

    try:
        import redis as _redis
        _redis_client = _redis.Redis(
            host=os.getenv("REDIS_HOST", "127.0.0.1"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            password=os.getenv("REDIS_PASSWORD", "123456"),
            db=2,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
            retry_on_timeout=True,
        )
        _redis_client.ping()
        logger.info("[TaskLogs] Redis 客户端连接成功 (DB 2)")
        return _redis_client
    except Exception as e:
        logger.warning(f"[TaskLogs] Redis 连接失败，增量日志将不可用: {e}")
        _redis_client = None
        return None


def push_log(task_id: str, state: str, message: str, percent: int = 0, **meta):
    """
    向 Redis 增量日志队列追加一条日志（生产端）

    同时维护保活心跳 Key task_alive:{task_id}，TTL = 1800s。
    如果 Worker 被 SIGKILL，心跳 Key 会在 30 分钟后自动过期，
    消费端即可判定任务已死亡。

    Args:
        task_id: Celery 任务 ID
        state: 状态标识（如 EXTRACTING, VISION_PROCESSING, GRAPH_BUILDING）
        message: 中文描述文本
        percent: 进度百分比 0-100
        **meta: 额外元数据
    """
    r = _get_redis()
    if r is None:
        return

    try:
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = json.dumps({
            "ts": timestamp,
            "state": state,
            "message": message,
            "percent": percent,
            **meta,
        }, ensure_ascii=False)

        log_key = f"task_logs:{task_id}"
        alive_key = f"task_alive:{task_id}"

        # 原子 pipeline：写日志 + 刷新心跳 + 设置过期
        pipe = r.pipeline()
        pipe.rpush(log_key, log_entry)
        pipe.expire(log_key, TASK_TTL)
        pipe.set(alive_key, str(int(time.time())), ex=TASK_TTL)
        pipe.execute()
    except Exception as e:
        logger.warning(f"[TaskLogs] push_log FAILED for task={task_id}: {e}")
        # 管道验证：如果 Redis 写入失败，至少在进程日志中留下痕迹
        try:
            import sys
            print(f"[TaskLogs-STDERR] push_log FAILED task={task_id} state={state}: {e}", file=sys.stderr, flush=True)
        except Exception:
            pass


def drain_logs(task_id: str) -> List[Dict]:
    """
    读后即焚：读取并删除 Redis 日志队列中的所有日志（消费端）

    返回日志列表，每条日志为 dict: {"ts", "state", "message", "percent", ...}
    """
    r = _get_redis()
    if r is None:
        return []

    key = f"task_logs:{task_id}"
    try:
        # 原子操作：读取全部 + 删除
        pipe = r.pipeline()
        pipe.lrange(key, 0, -1)
        pipe.delete(key)
        results = pipe.execute()

        raw_logs = results[0]
        logs = []
        for raw in raw_logs:
            try:
                entry = json.loads(raw)
                logs.append(entry)
            except Exception:
                logs.append({"ts": "?", "state": "RAW", "message": raw, "percent": 0})

        return logs
    except Exception as e:
        logger.warning(f"[TaskLogs] drain_logs FAILED for task={task_id}: {e}")
        return []


def is_task_alive(task_id: str) -> bool:
    """
    检查任务是否仍然存活（保活心跳 Key 是否存在）

    返回 True: 任务仍在运行（心跳 Key 存在）
    返回 False: 任务已死亡（心跳 Key 已过期，Worker 可能被 SIGKILL）
    """
    r = _get_redis()
    if r is None:
        # Redis 不可用时，无法判定，默认存活（避免误杀）
        return True

    try:
        alive_key = f"task_alive:{task_id}"
        return r.exists(alive_key) > 0
    except Exception:
        return True


def mark_task_dead(task_id: str):
    """
    标记任务为死亡状态（清理心跳 Key + 日志 Key）
    """
    r = _get_redis()
    if r is None:
        return

    try:
        r.delete(f"task_alive:{task_id}", f"task_logs:{task_id}")
    except Exception:
        pass
