"""
AIOS 全局事件总线 — RabbitMQ 发布者单例

线程安全的 AMQP 发布者，将微服务内部事件推送到 aios_exchange 交换机，
供 C++ 桌面端通过 MQTT 插件订阅，驱动桌宠状态机。

Routing Key 规范: aios.events.user_{user_id}.{source}
示例: aios.events.user_42.knowledge_base

设计原则:
  - 懒连接：首次 publish 时才建立 TCP 连接
  - 自愈：连接断开后自动重置，下次调用时重连
  - 非阻断：发布失败只打日志，不抛异常，绝不影响主业务
"""
import json
import logging
import os
import threading
from typing import Any, Optional

import pika

logger = logging.getLogger(__name__)

# ── 交换机常量 ──
EXCHANGE_NAME = "amq.topic"  # RabbitMQ MQTT 插件默认交换机
EXCHANGE_TYPE = "topic"

# ── 连接配置（环境变量优先）──
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.getenv("RABBITMQ_DEFAULT_USER", "admin")
RABBITMQ_PASS = os.getenv("RABBITMQ_DEFAULT_PASS", "eruitah2026")


class AiosEventBus:
    """
    线程安全的 RabbitMQ 发布者单例。

    用法:
        from app.core.event_bus import aios_event_bus

        aios_event_bus.publish(
            user_id="42",
            source="knowledge_base",
            action="working",
            message="图谱构建中..."
        )
    """

    _instance: Optional["AiosEventBus"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "AiosEventBus":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._connection: Optional[pika.BlockingConnection] = None
        self._channel: Optional[pika.adapters.blocking_connection.BlockingChannel] = None
        self._channel_lock = threading.Lock()
        self._initialized = True

    # ── 连接管理 ──

    def _get_channel(self):
        """获取或创建 AMQP 通道（懒加载，线程安全）"""
        with self._channel_lock:
            if self._channel and self._channel.is_open:
                # 检查底层连接是否还活着
                if self._connection and self._connection.is_open:
                    return self._channel
                else:
                    logger.warning("[AiosEventBus] 连接已断开，正在重连...")
                    self._reset_connection()

            try:
                credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
                params = pika.ConnectionParameters(
                    host=RABBITMQ_HOST,
                    port=RABBITMQ_PORT,
                    credentials=credentials,
                    heartbeat=0,  # 关闭心跳：Celery Worker 长时间处理文档时不发心跳会被服务端断开
                    blocked_connection_timeout=None,
                    connection_attempts=3,
                    retry_delay=1,
                )
                self._connection = pika.BlockingConnection(params)
                self._channel = self._connection.channel()
                self._channel.exchange_declare(
                    exchange=EXCHANGE_NAME,
                    exchange_type=EXCHANGE_TYPE,
                    durable=True,
                )
                logger.info(
                    f"[AiosEventBus] 已连接 RabbitMQ {RABBITMQ_HOST}:{RABBITMQ_PORT}, "
                    f"交换机={EXCHANGE_NAME}"
                )
                return self._channel
            except Exception as e:
                logger.error(f"[AiosEventBus] 连接 RabbitMQ 失败: {e}")
                self._reset_connection()
                return None

    def _reset_connection(self):
        """重置连接状态"""
        try:
            if self._connection and self._connection.is_open:
                self._connection.close()
        except Exception:
            pass
        self._connection = None
        self._channel = None

    # ── 公共 API ──

    def publish(self, user_id: str, source: str, action: str, message: str) -> bool:
        """
        向 aios_exchange 发布事件（失败自动重试一次）。

        Args:
            user_id: 用户 ID（拼入 routing key，保证多租户路由）
            source:  事件来源模块（如 "knowledge_base", "sandbox", "ai_service"）
            action:  动作类型（working / error / success / notify / idle）
            message: 人类可读的消息

        Returns:
            True 发布成功，False 发布失败（不抛异常，不阻断业务）
        """
        for attempt in range(2):
            try:
                channel = self._get_channel()
                if channel is None:
                    return False

                routing_key = f"aios.events.user_{user_id}.{source}"
                payload = {"action": action, "source": source, "msg": message}
                body = json.dumps(payload, ensure_ascii=False, default=str)

                channel.basic_publish(
                    exchange=EXCHANGE_NAME,
                    routing_key=routing_key,
                    body=body.encode("utf-8"),
                    properties=pika.BasicProperties(
                        content_type="application/json",
                        delivery_mode=2,  # 持久化
                    ),
                )
                logger.debug(f"[AiosEventBus] → {routing_key}: action={action}")
                return True

            except Exception as e:
                logger.error(
                    f"[AiosEventBus] 发布失败 (user={user_id}, source={source}, "
                    f"action={action}, attempt={attempt+1}): {e}"
                )
                with self._channel_lock:
                    self._reset_connection()
                if attempt == 0:
                    logger.info("[AiosEventBus] 重连后重试发布...")

        return False

    def close(self):
        """关闭连接（应用退出时调用）"""
        with self._channel_lock:
            self._reset_connection()


# ── 模块级便捷单例 ──
aios_event_bus = AiosEventBus()
