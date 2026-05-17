"""
Eruitah 智能编程沙盒 - Computer Use 工具 (OS 级别控制)

核心思想:
┌─────────────────────────────────────────────────────────────────────┐
│  大模型 → 输出动作指令 → pyautogui/mss 执行 → 截图反馈 → 循环       │
│                                                                     │
│  支持的动作:                                                        │
│    - take_screenshot: 使用 mss 极速截取全屏                         │
│    - mouse_move: 移动鼠标到 (x, y)                                  │
│    - left_click: 鼠标左键点击                                       │
│    - right_click: 鼠标右键点击                                      │
│    - mouse_click: 通用点击（支持坐标+按钮）                          │
│    - mouse_drag: 从 A 点拖拽到 B 点                                 │
│    - type_text: 模拟键盘输入文本                                    │
│    - press_key: 模拟单键敲击                                        │
│    - scroll: 滚动鼠标滚轮                                          │
│                                                                     │
│  手眼协调闭环:                                                      │
│    每次操作后强制截取屏幕截图，将操作结果文本 + base64 图片           │
│    一并返回给大模型，形成"看图→算坐标→操作→再看图确认"的闭环         │
│                                                                     │
│  沙盒环境:                                                          │
│    Docker 容器内运行 Xvfb (虚拟 X11 桌面)                            │
│    pyautogui 控制鼠标键盘                                           │
│    mss 极速截屏                                                     │
└─────────────────────────────────────────────────────────────────────┘
"""

import os
import base64
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

SCREEN_WIDTH = int(os.environ.get("ERUITAH_SCREEN_WIDTH", "1024"))
SCREEN_HEIGHT = int(os.environ.get("ERUITAH_SCREEN_HEIGHT", "768"))

_pyautogui_initialized = False


@dataclass
class ComputerUseResult:
    success: bool
    action: str = ""
    content: str = ""
    image_base64: str = ""
    error: str = ""


def _ensure_display():
    if not os.environ.get("DISPLAY"):
        os.environ["DISPLAY"] = os.environ.get("DISPLAY", ":99")


def _init_pyautogui():
    global _pyautogui_initialized
    if _pyautogui_initialized:
        return True

    _ensure_display()

    try:
        import pyautogui
        pyautogui.FAILSAFE = False
        pyautogui.PAUSE = 0.05
        _pyautogui_initialized = True
        logger.info(f"pyautogui 初始化成功, 屏幕尺寸: {pyautogui.size()}")
        return True
    except Exception as e:
        logger.error(f"pyautogui 初始化失败: {e}")
        return False


def _take_screenshot_mss() -> tuple[bool, str, str]:
    _ensure_display()
    try:
        import mss
        with mss.mss() as sct:
            monitor = sct.monitors[0] if sct.monitors else {
                "left": 0, "top": 0, "width": SCREEN_WIDTH, "height": SCREEN_HEIGHT
            }
            screenshot = sct.grab(monitor)
            img_bytes = mss.tools.to_png(screenshot.rgb, screenshot.size)
            base64_str = base64.b64encode(img_bytes).decode("utf-8")
            return True, base64_str, f"截图成功 ({screenshot.size[0]}x{screenshot.size[1]})"
    except Exception as e:
        logger.error(f"mss 截图失败: {e}")
        return False, "", str(e)


def _take_screenshot_fallback() -> tuple[bool, str, str]:
    _ensure_display()
    try:
        import subprocess
        import tempfile
        tmp_path = os.path.join(tempfile.gettempdir(), f"eruitah_cu_{os.getpid()}.png")
        display = os.environ.get("DISPLAY", ":99")

        result = subprocess.run(
            ["scrot", "-overwrite", tmp_path],
            capture_output=True, text=True, timeout=10,
            env={**os.environ, "DISPLAY": display},
        )
        if result.returncode == 0 and os.path.exists(tmp_path):
            with open(tmp_path, "rb") as f:
                img_data = f.read()
            base64_str = base64.b64encode(img_data).decode("utf-8")
            os.unlink(tmp_path)
            return True, base64_str, "截图成功 (scrot fallback)"
    except Exception:
        pass
    return False, "", "所有截图方法均失败"


def _screenshot_with_result(action_desc: str) -> ComputerUseResult:
    ok, b64, msg = _take_screenshot_mss()
    if not ok:
        ok, b64, msg = _take_screenshot_fallback()
    if ok:
        return ComputerUseResult(
            success=True,
            action=action_desc,
            content=msg,
            image_base64=b64,
        )
    return ComputerUseResult(success=False, action=action_desc, error=msg)


def _clamp_coords(x: int, y: int) -> tuple[int, int]:
    x = max(0, min(x, SCREEN_WIDTH - 1))
    y = max(0, min(y, SCREEN_HEIGHT - 1))
    return x, y


def execute_computer_use(action: str, **kwargs) -> ComputerUseResult:
    _ensure_display()

    if not _init_pyautogui():
        try:
            from screenshot_tool import start_xvfb
            if start_xvfb():
                _ensure_display()
                if not _init_pyautogui():
                    return ComputerUseResult(
                        success=False, action=action,
                        error="虚拟桌面环境未就绪，pyautogui 初始化失败",
                    )
        except Exception as e:
            return ComputerUseResult(
                success=False, action=action,
                error=f"虚拟桌面环境未就绪: {e}",
            )

    try:
        if action == "take_screenshot":
            return _screenshot_with_result("take_screenshot")

        elif action == "screenshot":
            return _screenshot_with_result("screenshot")

        elif action == "mouse_move":
            x = kwargs.get("x", kwargs.get("coordinate", [0, 0])[0] if "coordinate" in kwargs else 0)
            y = kwargs.get("y", kwargs.get("coordinate", [0, 0])[1] if "coordinate" in kwargs else 0)
            x, y = _clamp_coords(x, y)
            import pyautogui
            pyautogui.moveTo(x, y)
            return _screenshot_with_result(f"mouse_move({x},{y})")

        elif action == "left_click":
            import pyautogui
            coord = kwargs.get("coordinate", None)
            if coord and len(coord) >= 2:
                x, y = _clamp_coords(coord[0], coord[1])
                pyautogui.click(x=x, y=y, button="left")
            else:
                x = kwargs.get("x", 0)
                y = kwargs.get("y", 0)
                if x or y:
                    x, y = _clamp_coords(x, y)
                    pyautogui.click(x=x, y=y, button="left")
                else:
                    pyautogui.click(button="left")
            return _screenshot_with_result(f"left_click({x},{y})" if (x or y) else "left_click")

        elif action == "right_click":
            import pyautogui
            coord = kwargs.get("coordinate", None)
            if coord and len(coord) >= 2:
                x, y = _clamp_coords(coord[0], coord[1])
                pyautogui.click(x=x, y=y, button="right")
            else:
                x = kwargs.get("x", 0)
                y = kwargs.get("y", 0)
                if x or y:
                    x, y = _clamp_coords(x, y)
                    pyautogui.click(x=x, y=y, button="right")
                else:
                    pyautogui.click(button="right")
            return _screenshot_with_result(f"right_click({x},{y})" if (x or y) else "right_click")

        elif action == "mouse_click":
            import pyautogui
            coordinate = kwargs.get("coordinate", [0, 0])
            if not coordinate or len(coordinate) < 2:
                return ComputerUseResult(
                    success=False, action=action, error="缺少 coordinate 参数"
                )
            x, y = _clamp_coords(coordinate[0], coordinate[1])
            button = kwargs.get("button", "left")
            pyautogui.click(x=x, y=y, button=button)
            return _screenshot_with_result(f"mouse_click({x},{y},{button})")

        elif action == "mouse_drag":
            import pyautogui
            start = kwargs.get("start_coordinate", [0, 0])
            end = kwargs.get("coordinate", [0, 0])
            if not start or not end:
                return ComputerUseResult(
                    success=False, action=action, error="缺少 start_coordinate 或 coordinate"
                )
            sx, sy = _clamp_coords(start[0], start[1])
            ex, ey = _clamp_coords(end[0], end[1])
            pyautogui.moveTo(sx, sy)
            pyautogui.drag(ex - sx, ey - sy, duration=0.3, button="left")
            return _screenshot_with_result(f"mouse_drag({sx},{sy}→{ex},{ey})")

        elif action == "type_text":
            text = kwargs.get("text", "")
            if not text:
                return ComputerUseResult(
                    success=False, action=action, error="缺少 text 参数"
                )
            import pyautogui
            pyautogui.write(text, interval=0.02)
            return _screenshot_with_result(f"type_text({text[:50]})")

        elif action == "press_key":
            key = kwargs.get("key", "")
            if not key:
                return ComputerUseResult(
                    success=False, action=action, error="缺少 key 参数"
                )
            import pyautogui
            key_map = {
                "enter": "enter", "return": "enter",
                "tab": "tab", "escape": "escape", "esc": "escape",
                "backspace": "backspace", "delete": "delete",
                "up": "up", "down": "down", "left": "left", "right": "right",
                "home": "home", "end": "end",
                "pageup": "pageup", "pagedown": "pagedown",
                "space": "space",
            }
            mapped = key_map.get(key.lower(), key)
            pyautogui.press(mapped)
            return _screenshot_with_result(f"press_key({key})")

        elif action == "key":
            key = kwargs.get("key", "")
            if not key:
                return ComputerUseResult(
                    success=False, action=action, error="缺少 key 参数"
                )
            import pyautogui
            key_map = {
                "Return": "enter", "Enter": "enter",
                "Tab": "tab", "Escape": "escape",
                "BackSpace": "backspace", "Delete": "delete",
                "Up": "up", "Down": "down", "Left": "left", "Right": "right",
                "Home": "home", "End": "end",
                "Page_Up": "pageup", "Page_Down": "pagedown",
                "space": "space",
            }
            mapped = key_map.get(key, key)
            pyautogui.press(mapped)
            return _screenshot_with_result(f"key({key})")

        elif action == "scroll":
            import pyautogui
            direction = kwargs.get("direction", "down")
            amount = kwargs.get("amount", 3)
            scroll_clicks = -amount if direction == "up" else amount
            pyautogui.scroll(scroll_clicks)
            return _screenshot_with_result(f"scroll({direction},{amount})")

        elif action == "hotkey":
            keys = kwargs.get("keys", [])
            if not keys:
                return ComputerUseResult(
                    success=False, action=action, error="缺少 keys 参数"
                )
            import pyautogui
            pyautogui.hotkey(*keys)
            return _screenshot_with_result(f"hotkey({'+'.join(keys)})")

        else:
            return ComputerUseResult(
                success=False, action=action, error=f"未知动作: {action}"
            )

    except Exception as e:
        logger.error(f"Computer Use 执行异常: {e}")
        return ComputerUseResult(success=False, action=action, error=str(e))


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
                "detail": "auto",
            },
        })

    text = result.content if result.success else f"错误: {result.error}"
    content_parts.append({
        "type": "text",
        "text": text,
    })

    return content_parts


COMPUTER_USE_TOOL_DEFINITION_ANTHROPIC = {
    "name": "computer_use",
    "description": (
        "控制计算机的鼠标和键盘，并截取屏幕截图。"
        "可以移动鼠标、点击、输入文字、按键、滚动等。"
        "坐标原点在左上角，x 向右增大，y 向下增大。"
        f"屏幕分辨率: {SCREEN_WIDTH}x{SCREEN_HEIGHT}"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "take_screenshot", "screenshot",
                    "mouse_move", "left_click", "right_click", "mouse_click", "mouse_drag",
                    "type_text", "press_key", "key", "scroll", "hotkey",
                ],
                "description": "要执行的动作",
            },
            "x": {
                "type": "integer",
                "description": "鼠标目标 x 坐标",
            },
            "y": {
                "type": "integer",
                "description": "鼠标目标 y 坐标",
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
                "description": "要按下的按键 (press_key/key 动作)，如 enter, tab, escape, up, down",
            },
            "keys": {
                "type": "array",
                "items": {"type": "string"},
                "description": "组合键列表 (hotkey 动作)，如 ['ctrl', 'c']",
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
            "可以移动鼠标、点击、输入文字、按键、滚动等。"
            "坐标原点在左上角，x 向右增大，y 向下增大。"
            f"屏幕分辨率: {SCREEN_WIDTH}x{SCREEN_HEIGHT}"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "take_screenshot", "screenshot",
                        "mouse_move", "left_click", "right_click", "mouse_click", "mouse_drag",
                        "type_text", "press_key", "key", "scroll", "hotkey",
                    ],
                    "description": "要执行的动作",
                },
                "x": {
                    "type": "integer",
                    "description": "鼠标目标 x 坐标",
                },
                "y": {
                    "type": "integer",
                    "description": "鼠标目标 y 坐标",
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
                "keys": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "组合键列表 (hotkey 动作)",
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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("Eruitah Computer Use 工具测试 (OS 级别)")
    print("=" * 60)

    print(f"\nDISPLAY: {os.environ.get('DISPLAY', '未设置')}")
    print(f"屏幕分辨率: {SCREEN_WIDTH}x{SCREEN_HEIGHT}")

    print("\n--- 初始化环境 ---")
    if _init_pyautogui():
        import pyautogui
        print(f"✅ pyautogui 就绪, 屏幕尺寸: {pyautogui.size()}")
    else:
        print("❌ pyautogui 初始化失败")
        exit(1)

    print("\n--- 截图测试 (mss) ---")
    result = execute_computer_use("take_screenshot")
    if result.success:
        print(f"✅ 截图成功: base64 长度 {len(result.image_base64)}")
    else:
        print(f"❌ 截图失败: {result.error}")

    print("\n--- 鼠标移动测试 ---")
    result = execute_computer_use("mouse_move", x=100, y=100)
    print(f"结果: success={result.success}, content={result.content}")

    print("\n--- 左键点击测试 ---")
    result = execute_computer_use("left_click", coordinate=[200, 200])
    print(f"结果: success={result.success}, content={result.content}")

    print("\n--- 右键点击测试 ---")
    result = execute_computer_use("right_click", coordinate=[300, 300])
    print(f"结果: success={result.success}, content={result.content}")

    print("\n--- 输入测试 ---")
    result = execute_computer_use("type_text", text="echo hello")
    print(f"结果: success={result.success}, content={result.content}")

    print("\n--- 按键测试 ---")
    result = execute_computer_use("press_key", key="enter")
    print(f"结果: success={result.success}, content={result.content}")
