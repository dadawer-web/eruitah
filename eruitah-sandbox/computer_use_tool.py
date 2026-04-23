"""
Eruitah 智能编程沙盒 - Computer Use 工具

核心思想（来自 Claude Code 的 computerUse executor）:
┌─────────────────────────────────────────────────────────────────────┐
│  大模型 → 输出动作指令 → Python 执行 → 截图反馈 → 循环              │
│                                                                     │
│  支持的动作:                                                        │
│    - screenshot: 截取当前屏幕                                       │
│    - mouse_click: 点击指定坐标                                      │
│    - mouse_drag: 从 A 点拖拽到 B 点                                 │
│    - type_text: 输入文字                                            │
│    - press_key: 按下键盘按键                                        │
│    - scroll: 滚动鼠标滚轮                                          │
│                                                                     │
│  Anthropic Computer Use 协议:                                       │
│    大模型输出 tool_use:                                             │
│      {"action": "screenshot"}                                       │
│      {"action": "mouse_click", "coordinate": [450, 300]}            │
│      {"action": "type_text", "text": "Hello"}                       │
│      {"action": "key", "key": "Return"}                             │
│                                                                     │
│  截图以 base64 编码的 image block 返回给大模型                      │
└─────────────────────────────────────────────────────────────────────┘

参考源码:
    claude-code-rev/src/utils/computerUse/executor.ts
    shims/ant-computer-use-mcp/
"""

import json
import logging
from dataclasses import dataclass
from typing import Optional

from screenshot_tool import (
    take_screenshot,
    mouse_click,
    mouse_drag,
    type_text,
    press_key,
    scroll,
    start_xvfb,
    start_x11vnc,
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
)

logger = logging.getLogger(__name__)


@dataclass
class ComputerUseResult:
    success: bool
    action: str = ""
    content: str = ""
    image_base64: str = ""
    error: str = ""


COMPUTER_USE_TOOL_DEFINITION_ANTHROPIC = {
    "name": "computer_use",
    "description": (
        "控制计算机的鼠标和键盘，并截取屏幕截图。"
        "可以点击屏幕坐标、输入文字、按键、滚动等。"
        "坐标原点在左上角，x 向右增大，y 向下增大。"
        f"屏幕分辨率: {SCREEN_WIDTH}x{SCREEN_HEIGHT}"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["screenshot", "mouse_click", "mouse_drag", "type_text", "key", "scroll"],
                "description": "要执行的动作",
            },
            "coordinate": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "点击/拖拽的坐标 [x, y]，原点在左上角",
            },
            "start_coordinate": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "拖拽起始坐标 [x, y]",
            },
            "text": {
                "type": "string",
                "description": "要输入的文字 (type_text 动作)",
            },
            "key": {
                "type": "string",
                "description": "要按下的按键 (key 动作)，如 Return, Tab, Escape, Up, Down",
            },
            "direction": {
                "type": "string",
                "enum": ["up", "down"],
                "description": "滚动方向 (scroll 动作)",
            },
            "amount": {
                "type": "integer",
                "description": "滚动量 (scroll 动作)，默认 3",
            },
            "button": {
                "type": "string",
                "enum": ["left", "middle", "right"],
                "description": "鼠标按钮 (mouse_click 动作)，默认 left",
            },
        },
        "required": ["action"],
    },
}

COMPUTER_USE_TOOL_DEFINITION_OPENAI = {
    "type": "function",
    "function": {
        "name": "computer_use",
        "description": (
            "控制计算机的鼠标和键盘，并截取屏幕截图。"
            "可以点击屏幕坐标、输入文字、按键、滚动等。"
            "坐标原点在左上角，x 向右增大，y 向下增大。"
            f"屏幕分辨率: {SCREEN_WIDTH}x{SCREEN_HEIGHT}"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["screenshot", "mouse_click", "mouse_drag", "type_text", "key", "scroll"],
                    "description": "要执行的动作",
                },
                "coordinate": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "点击/拖拽的坐标 [x, y]",
                },
                "start_coordinate": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "拖拽起始坐标 [x, y]",
                },
                "text": {
                    "type": "string",
                    "description": "要输入的文字",
                },
                "key": {
                    "type": "string",
                    "description": "要按下的按键",
                },
                "direction": {
                    "type": "string",
                    "enum": ["up", "down"],
                    "description": "滚动方向",
                },
                "amount": {
                    "type": "integer",
                    "description": "滚动量",
                },
                "button": {
                    "type": "string",
                    "enum": ["left", "middle", "right"],
                    "description": "鼠标按钮",
                },
            },
            "required": ["action"],
        },
    },
}


_xvfb_initialized = False


def ensure_computer_use_env() -> bool:
    global _xvfb_initialized
    if _xvfb_initialized:
        return True

    if start_xvfb():
        _xvfb_initialized = True
        start_x11vnc()
        return True
    return False


def execute_computer_use(action: str, **kwargs) -> ComputerUseResult:
    if not ensure_computer_use_env():
        return ComputerUseResult(
            success=False,
            action=action,
            error="虚拟桌面环境未就绪，请确保 Xvfb 已安装",
        )

    try:
        if action == "screenshot":
            return _handle_screenshot()

        elif action == "mouse_click":
            coordinate = kwargs.get("coordinate", [0, 0])
            if not coordinate or len(coordinate) < 2:
                return ComputerUseResult(
                    success=False, action=action, error="缺少 coordinate 参数"
                )
            x, y = coordinate[0], coordinate[1]
            button = kwargs.get("button", "left")
            result = mouse_click(x, y, button=button)
            if result.success:
                return _handle_screenshot(action=f"mouse_click({x},{y})")
            return ComputerUseResult(
                success=False, action=action, error=result.error
            )

        elif action == "mouse_drag":
            start = kwargs.get("start_coordinate", [0, 0])
            end = kwargs.get("coordinate", [0, 0])
            if not start or not end:
                return ComputerUseResult(
                    success=False, action=action, error="缺少 start_coordinate 或 coordinate"
                )
            result = mouse_drag(start[0], start[1], end[0], end[1])
            if result.success:
                return _handle_screenshot(action=f"mouse_drag({start}→{end})")
            return ComputerUseResult(
                success=False, action=action, error=result.error
            )

        elif action == "type_text":
            text = kwargs.get("text", "")
            if not text:
                return ComputerUseResult(
                    success=False, action=action, error="缺少 text 参数"
                )
            result = type_text(text)
            if result.success:
                return _handle_screenshot(action=f"type_text({text[:50]})")
            return ComputerUseResult(
                success=False, action=action, error=result.error
            )

        elif action == "key":
            key = kwargs.get("key", "")
            if not key:
                return ComputerUseResult(
                    success=False, action=action, error="缺少 key 参数"
                )
            result = press_key(key)
            if result.success:
                return _handle_screenshot(action=f"key({key})")
            return ComputerUseResult(
                success=False, action=action, error=result.error
            )

        elif action == "scroll":
            direction = kwargs.get("direction", "down")
            amount = kwargs.get("amount", 3)
            result = scroll(direction=direction, amount=amount)
            if result.success:
                return _handle_screenshot(action=f"scroll({direction},{amount})")
            return ComputerUseResult(
                success=False, action=action, error=result.error
            )

        else:
            return ComputerUseResult(
                success=False, action=action, error=f"未知动作: {action}"
            )

    except Exception as e:
        logger.error(f"Computer Use 执行异常: {e}")
        return ComputerUseResult(success=False, action=action, error=str(e))


def _handle_screenshot(action: str = "screenshot") -> ComputerUseResult:
    result = take_screenshot()
    if result.success:
        return ComputerUseResult(
            success=True,
            action=action,
            content=f"截图成功 ({result.width}x{result.height})",
            image_base64=result.base64_image,
        )
    return ComputerUseResult(
        success=False, action=action, error=f"截图失败: {result.error}"
    )


def format_computer_use_result_for_anthropic(result: ComputerUseResult) -> list[dict]:
    content_blocks = []

    if result.image_base64:
        content_blocks.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": result.image_base64,
            },
        })

    text = result.content if result.success else f"错误: {result.error}"
    content_blocks.append({
        "type": "text",
        "text": text,
    })

    return content_blocks


def format_computer_use_result_for_openai(result: ComputerUseResult) -> list[dict]:
    content_parts = []

    if result.image_base64:
        content_parts.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{result.image_base64}",
                "detail": "low",
            },
        })

    text = result.content if result.success else f"错误: {result.error}"
    content_parts.append({
        "type": "text",
        "text": text,
    })

    return content_parts


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("Eruitah Computer Use 工具测试")
    print("=" * 60)

    print("\n--- 初始化环境 ---")
    if ensure_computer_use_env():
        print("✅ 虚拟桌面环境就绪")
    else:
        print("❌ 虚拟桌面环境初始化失败")
        exit(1)

    print("\n--- 截图测试 ---")
    result = execute_computer_use("screenshot")
    if result.success:
        print(f"✅ 截图成功: base64 长度 {len(result.image_base64)}")
    else:
        print(f"❌ 截图失败: {result.error}")

    print("\n--- 点击测试 ---")
    result = execute_computer_use("mouse_click", coordinate=[100, 100])
    print(f"结果: success={result.success}, content={result.content}")

    print("\n--- 输入测试 ---")
    result = execute_computer_use("type_text", text="echo hello")
    print(f"结果: success={result.success}, content={result.content}")

    print("\n--- 按键测试 ---")
    result = execute_computer_use("key", key="Return")
    print(f"结果: success={result.success}, content={result.content}")
