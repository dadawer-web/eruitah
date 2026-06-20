"""
AIOS 全局事件总线 — RabbitMQ 发布者单例 (sandbox 版)

与 butcanthic/app/core/event_bus.py 功能完全一致，
仅适配 sandbox 的扁平目录结构（导入路径不同）。

Routing Key 规范: aios.events.user_{user_id}.{source}
"""
import json
import logging
import os
import threading
from typing import Optional

import pika

logger = logging.getLogger(__name__)

EXCHANGE_NAME = "amq.topic"  # RabbitMQ MQTT 插件默认交换机
EXCHANGE_TYPE = "topic"

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.getenv("RABBITMQ_DEFAULT_USER", "admin")
RABBITMQ_PASS = os.getenv("RABBITMQ_DEFAULT_PASS", "eruitah2026")


class AiosEventBus:
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

    def _get_channel(self):
        with self._channel_lock:
            if self._channel and self._channel.is_open:
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
                    heartbeat=0,  # 关闭心跳：长时间处理任务时不发心跳会被服务端断开
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
                logger.info(f"[AiosEventBus] 已连接 RabbitMQ {RABBITMQ_HOST}:{RABBITMQ_PORT}")
                return self._channel
            except Exception as e:
                logger.error(f"[AiosEventBus] 连接 RabbitMQ 失败: {e}")
                self._reset_connection()
                return None

    def _reset_connection(self):
        try:
            if self._connection and self._connection.is_open:
                self._connection.close()
        except Exception:
            pass
        self._connection = None
        self._channel = None

    def publish(self, user_id: str, source: str, action: str, message: str) -> bool:
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
                        delivery_mode=2,
                    ),
                )
                logger.debug(f"[AiosEventBus] → {routing_key}: action={action}")
                return True
            except Exception as e:
                logger.error(
                    f"[AiosEventBus] 发布失败 (attempt={attempt+1}): {e}"
                )
                with self._channel_lock:
                    self._reset_connection()
                if attempt == 0:
                    logger.info("[AiosEventBus] 重连后重试发布...")
        return False

    def close(self):
        with self._channel_lock:
            self._reset_connection()


aios_event_bus = AiosEventBus()
