"""
AIOS 无侵入式事件通知装饰器

核心设计: @aios_notify 装饰器
  - 在被装饰函数执行前，自动发布 action_start 事件
  - 执行成功后，自动发布 action_success 事件
  - 执行异常时，自动发布 action_error 事件并带上异常信息，然后原样抛出异常
  - 智能从 kwargs 中提取 user_id，保证多租户路由正确

业务逻辑零侵入: 被装饰的函数无需任何修改，只需在定义处加一行装饰器。

用法示例:
    @aios_notify(source="knowledge_base", start_msg_template="图谱构建中...")
    async def process_documents(user_id: int, files: list):
        ...  # 业务逻辑完全不变

    @aios_notify(source="sandbox", start_msg_template="编译中...", success_msg_template="编译通过!")
    def compile_code(user_id, project_path):
        ...
"""
import asyncio
import functools
import inspect
import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# 默认 user_id（无法提取时的兜底值）
_DEFAULT_USER_ID = "anonymous"


def _extract_user_id(args: tuple, kwargs: dict, func: Callable) -> str:
    """
    智能提取 user_id，按优先级尝试以下策略:

    1. kwargs 中直接查找 "user_id" / "userId" / "uid" 键
    2. 函数签名中按参数名位置匹配
    3. 第一个 int/str 类型的位置参数（跳过 self/cls）
    4. 兜底返回 "anonymous"

    Returns:
        user_id 字符串
    """
    # 策略 1: 从 kwargs 直接查找
    for key in ("user_id", "userId", "uid"):
        if key in kwargs:
            return str(kwargs[key])

    # 策略 2: 按函数签名参数名匹配
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

    # 策略 3: 第一个 int/str 类型的位置参数（跳过 self/cls）
    if args:
        first_arg = args[0]
        # 如果第一个参数是实例方法中的 self，尝试第二个
        if hasattr(first_arg, "__class__") and not isinstance(first_arg, type):
            if len(args) > 1 and isinstance(args[1], (int, str)):
                return str(args[1])
        if isinstance(first_arg, (int, str)):
            return str(first_arg)

    return _DEFAULT_USER_ID


def _do_publish(user_id: str, source: str, action: str, message: str):
    """安全发布事件（导入在函数内部，避免循环依赖）"""
    try:
        from app.core.event_bus import aios_event_bus
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
    """
    无侵入式 AIOS 事件通知装饰器（异步/同步兼容）。

    Args:
        source:              模块名（如 "knowledge_base", "sandbox"）
        action_start:        函数开始执行时发布的动作（默认 "working"）
        action_error:        函数执行异常时发布的动作（默认 "error"）
        action_success:      函数执行成功时发布的动作（默认 "success"）
        start_msg_template:  开始时的消息模板，支持 {func_name} 占位符
        success_msg_template:成功时的消息模板，支持 {func_name} 占位符

    用法:
        @aios_notify(source="knowledge_base")
        async def process_docs(user_id: int, files: list):
            ...

        @aios_notify(source="sandbox", start_msg_template="编译中...", success_msg_template="编译通过!")
        def compile(user_id, path):
            ...
    """

    def decorator(func: Callable) -> Callable:
        is_async = asyncio.iscoroutinefunction(func)
        func_name = func.__qualname__

        if is_async:
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                uid = _extract_user_id(args, kwargs, func)

                # 发布 start 事件
                msg = start_msg_template.format(func_name=func_name)
                _do_publish(uid, source, action_start, msg)

                try:
                    result = await func(*args, **kwargs)
                    # 发布 success 事件
                    msg = success_msg_template.format(func_name=func_name)
                    _do_publish(uid, source, action_success, msg)
                    return result
                except Exception as e:
                    # 发布 error 事件，然后原样抛出
                    _do_publish(uid, source, action_error, f"{func_name} 异常: {e}")
                    raise

            return async_wrapper

        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                uid = _extract_user_id(args, kwargs, func)

                # 发布 start 事件
                msg = start_msg_template.format(func_name=func_name)
                _do_publish(uid, source, action_start, msg)

                try:
                    result = func(*args, **kwargs)
                    # 发布 success 事件
                    msg = success_msg_template.format(func_name=func_name)
                    _do_publish(uid, source, action_success, msg)
                    return result
                except Exception as e:
                    # 发布 error 事件，然后原样抛出
                    _do_publish(uid, source, action_error, f"{func_name} 异常: {e}")
                    raise

            return sync_wrapper

    return decorator
