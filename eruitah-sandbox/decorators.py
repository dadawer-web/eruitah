"""
AIOS 无侵入式事件通知装饰器 (sandbox 版)

与 butcanthic/app/core/decorators.py 功能完全一致，
仅适配 sandbox 的扁平目录结构（导入路径不同）。

用法:
    from decorators import aios_notify

    @aios_notify(source="sandbox", start_msg_template="编译中...")
    async def run_agent(user_id: int, task: str):
        ...
"""
import asyncio
import functools
import inspect
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_DEFAULT_USER_ID = "anonymous"


def _extract_user_id(args: tuple, kwargs: dict, func: Callable) -> str:
    """智能提取 user_id（与 butcanthic 版完全一致）"""
    for key in ("user_id", "userId", "uid"):
        if key in kwargs:
            return str(kwargs[key])

    try:
        sig = inspect.signature(func)
        param_names = list(sig.parameters.keys())
        for name in ("user_id", "userId", "uid"):
            if name in param_names:
                idx = param_names.index(name)
                if idx < len(args):
                    return str(args[idx])
    except (ValueError, TypeError):
        pass

    if args:
        first_arg = args[0]
        if hasattr(first_arg, "__class__") and not isinstance(first_arg, type):
            if len(args) > 1 and isinstance(args[1], (int, str)):
                return str(args[1])
        if isinstance(first_arg, (int, str)):
            return str(first_arg)

    return _DEFAULT_USER_ID


def _do_publish(user_id: str, source: str, action: str, message: str):
    try:
        from event_bus import aios_event_bus
        aios_event_bus.publish(user_id=user_id, source=source, action=action, message=message)
    except Exception as e:
        logger.error(f"[aios_notify] 事件发布失败（不阻断）: {e}")


def aios_notify(
    source: str,
    action_start: str = "working",
    action_error: str = "error",
    action_success: str = "success",
    start_msg_template: str = "{func_name} 开始执行",
    success_msg_template: str = "{func_name} 执行成功",
):
    """无侵入式 AIOS 事件通知装饰器（异步/同步兼容）。"""

    def decorator(func: Callable) -> Callable:
        is_async = asyncio.iscoroutinefunction(func)
        func_name = func.__qualname__

        if is_async:
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                uid = _extract_user_id(args, kwargs, func)

                msg = start_msg_template.format(func_name=func_name)
                _do_publish(uid, source, action_start, msg)

                try:
                    result = await func(*args, **kwargs)
                    msg = success_msg_template.format(func_name=func_name)
                    _do_publish(uid, source, action_success, msg)
                    return result
                except Exception as e:
                    _do_publish(uid, source, action_error, f"{func_name} 异常: {e}")
                    raise

            return async_wrapper

        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                uid = _extract_user_id(args, kwargs, func)

                msg = start_msg_template.format(func_name=func_name)
                _do_publish(uid, source, action_start, msg)

                try:
                    result = func(*args, **kwargs)
                    msg = success_msg_template.format(func_name=func_name)
                    _do_publish(uid, source, action_success, msg)
                    return result
                except Exception as e:
                    _do_publish(uid, source, action_error, f"{func_name} 异常: {e}")
                    raise

            return sync_wrapper

    return decorator
