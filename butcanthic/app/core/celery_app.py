import os

from celery import Celery

REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "123456")
REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")

if REDIS_PASSWORD:
    broker_url = os.getenv("CELERY_BROKER_URL", f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/0")
    result_backend = os.getenv("CELERY_RESULT_BACKEND", f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/1")
else:
    broker_url = os.getenv("CELERY_BROKER_URL", f"redis://{REDIS_HOST}:{REDIS_PORT}/0")
    result_backend = os.getenv("CELERY_RESULT_BACKEND", f"redis://{REDIS_HOST}:{REDIS_PORT}/1")

celery_app = Celery(
    "document_copilot",
    broker=broker_url,
    backend=result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    worker_concurrency=int(os.getenv("CELERY_WORKER_CONCURRENCY", "2")),
    worker_max_tasks_per_child=5,       # 处理5个任务后自动重启Worker，防止内存泄漏OOM
    worker_max_memory_per_child=300000, # 300MB内存上限，超限自动重启
    result_expires=3600,
)

celery_app.autodiscover_tasks(["app.worker"])
