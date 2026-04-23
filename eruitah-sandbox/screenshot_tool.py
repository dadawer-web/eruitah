"""
Eruitah 智能编程沙盒 - 截图工具 (Screenshot Tool)

核心思想（来自 Claude Code 的 computerUse 模块）:
┌─────────────────────────────────────────────────────────────────────┐
│  Agent 不再是"瞎子" —— 它能看到屏幕！                               │
│                                                                     │
│  工作流程:                                                          │
│    1. 大模型发出 computer_use 工具调用                               │
│    2. Python 后端截取虚拟屏幕截图                                    │
│    3. 截图编码为 base64 发送给大模型                                 │
│    4. 大模型分析截图，决定下一步操作（点击/输入/滚动）                 │
│    5. Python 后端执行鼠标/键盘操作                                   │
│    6. 再次截图 → 循环                                                │
│                                                                     │
│  沙盒环境:                                                          │
│    Docker 容器内运行 Xvfb (虚拟 X11 桌面)                            │
│    x11vnc 提供远程查看能力                                          │
│    xdotool 模拟鼠标/键盘输入                                        │
│                                                                     │
│  坐标映射:                                                          │
│    大模型输出坐标 (x, y) → Python 调用 xdotool mousemove + click    │
│    截图分辨率与虚拟桌面分辨率一致 (默认 1280x720)                    │
└─────────────────────────────────────────────────────────────────────┘

参考源码:
    claude-code-rev/src/utils/computerUse/executor.ts
    claude-code-rev/src/utils/screenshotClipboard.ts
"""

import os
import base64
import logging
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

DISPLAY = os.environ.get("DISPLAY", ":99")
SCREEN_WIDTH = int(os.environ.get("ERUITAH_SCREEN_WIDTH", "1280"))
SCREEN_HEIGHT = int(os.environ.get("ERUITAH_SCREEN_HEIGHT", "720"))


@dataclass
class ScreenshotResult:
    success: bool
    base64_image: str = ""
    width: int = 0
    height: int = 0
    error: str = ""


@dataclass
class ClickResult:
    success: bool
    x: int = 0
    y: int = 0
    button: str = "left"
    error: str = ""


@dataclass
class TypeResult:
    success: bool
    text: str = ""
    error: str = ""


@dataclass
class ScrollResult:
    success: bool
    direction: str = "down"
    amount: int = 3
    error: str = ""


@dataclass
class KeyResult:
    success: bool
    key: str = ""
    error: str = ""


def ensure_display() -> bool:
    if os.environ.get("DISPLAY"):
        return True

    os.environ["DISPLAY"] = DISPLAY
    return True


def start_xvfb(width: int = SCREEN_WIDTH, height: int = SCREEN_HEIGHT, depth: int = 24) -> bool:
    try:
        display_num = DISPLAY.lstrip(":")
        lock_file = f"/tmp/.X{display_num}-lock"
        if os.path.exists(lock_file):
            logger.info(f"Xvfb 已在 {DISPLAY} 上运行")
            return True

        cmd = [
            "Xvfb", DISPLAY,
            "-screen", "0", f"{width}x{height}x{depth}",
            "-ac",
            "-nolisten", "tcp",
        ]

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        import time
        time.sleep(1)

        if proc.poll() is not None:
            logger.error(f"Xvfb 启动失败，退出码: {proc.returncode}")
            return False

        os.environ["DISPLAY"] = DISPLAY
        logger.info(f"Xvfb 已启动: {DISPLAY} ({width}x{height}x{depth})")
        return True

    except FileNotFoundError:
        logger.error("Xvfb 未安装，请运行: apt-get install xvfb")
        return False
    except Exception as e:
        logger.error(f"Xvfb 启动异常: {e}")
        return False


def start_x11vnc(port: int = 5900) -> bool:
    try:
        result = subprocess.run(
            ["pgrep", "-x", "x11vnc"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            logger.info(f"x11vnc 已在运行 (端口 {port})")
            return True

        cmd = [
            "x11vnc",
            "-display", DISPLAY,
            "-rfbport", str(port),
            "-nopw",
            "-shared",
            "-forever",
            "-bg",
        ]

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        import time
        time.sleep(1)

        logger.info(f"x11vnc 已启动: 端口 {port}")
        return True

    except FileNotFoundError:
        logger.warning("x11vnc 未安装，VNC 远程查看不可用")
        return False
    except Exception as e:
        logger.error(f"x11vnc 启动异常: {e}")
        return False


def take_screenshot() -> ScreenshotResult:
    ensure_display()

    try:
        tmp_path = os.path.join(tempfile.gettempdir(), f"eruitah_screenshot_{os.getpid()}.png")

        if _try_xdotool_screenshot(tmp_path):
            pass
        elif _try_scrot_screenshot(tmp_path):
            pass
        elif _try_import_screenshot(tmp_path):
            pass
        elif _try_python_screenshot(tmp_path):
            pass
        else:
            return ScreenshotResult(
                success=False,
                error="所有截图方法均失败，请安装 xdotool/scrot/ImageMagick/mss",
            )

        if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
            return ScreenshotResult(success=False, error="截图文件为空或不存在")

        with open(tmp_path, "rb") as f:
            img_data = f.read()

        base64_img = base64.b64encode(img_data).decode("utf-8")

        try:
            os.unlink(tmp_path)
        except Exception:
            pass

        return ScreenshotResult(
            success=True,
            base64_image=base64_img,
            width=SCREEN_WIDTH,
            height=SCREEN_HEIGHT,
        )

    except Exception as e:
        return ScreenshotResult(success=False, error=str(e))


def _try_xdotool_screenshot(path: str) -> bool:
    try:
        result = subprocess.run(
            ["xdotool", "key", "--delay", "0", "Print"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return False
        import time
        time.sleep(0.5)
        return _try_import_screenshot(path)
    except Exception:
        return False


def _try_scrot_screenshot(path: str) -> bool:
    try:
        result = subprocess.run(
            ["scrot", "-overwrite", path],
            capture_output=True, text=True, timeout=10,
            env={**os.environ, "DISPLAY": DISPLAY},
        )
        return result.returncode == 0 and os.path.exists(path)
    except Exception:
        return False


def _try_import_screenshot(path: str) -> bool:
    try:
        result = subprocess.run(
            ["import", "-window", "root", "-display", DISPLAY, path],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0 and os.path.exists(path)
    except Exception:
        return False


def _try_python_screenshot(path: str) -> bool:
    try:
        import mss
        with mss.mss() as sct:
            monitor = sct.monitors[0] if sct.monitors else {"left": 0, "top": 0, "width": SCREEN_WIDTH, "height": SCREEN_HEIGHT}
            screenshot = sct.grab(monitor)
            from PIL import Image
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            img.save(path, "PNG")
        return os.path.exists(path)
    except ImportError:
        return False
    except Exception:
        return False


def mouse_click(x: int, y: int, button: str = "left", click_count: int = 1) -> ClickResult:
    ensure_display()

    try:
        x = max(0, min(x, SCREEN_WIDTH - 1))
        y = max(0, min(y, SCREEN_HEIGHT - 1))

        button_map = {"left": "1", "middle": "2", "right": "3"}
        btn = button_map.get(button, "1")

        subprocess.run(
            ["xdotool", "mousemove", str(x), str(y)],
            capture_output=True, text=True, timeout=5,
            env={**os.environ, "DISPLAY": DISPLAY},
        )

        import time
        time.sleep(0.05)

        click_args = ["xdotool", "click"]
        if click_count > 1:
            click_args.extend(["--repeat", str(click_count), "--delay", "100"])
        click_args.append(btn)

        result = subprocess.run(
            click_args,
            capture_output=True, text=True, timeout=5,
            env={**os.environ, "DISPLAY": DISPLAY},
        )

        if result.returncode != 0:
            return ClickResult(success=False, x=x, y=y, button=button, error=result.stderr)

        return ClickResult(success=True, x=x, y=y, button=button)

    except FileNotFoundError:
        return ClickResult(success=False, error="xdotool 未安装，请运行: apt-get install xdotool")
    except Exception as e:
        return ClickResult(success=False, error=str(e))


def mouse_drag(start_x: int, start_y: int, end_x: int, end_y: int) -> ClickResult:
    ensure_display()

    try:
        env = {**os.environ, "DISPLAY": DISPLAY}

        subprocess.run(
            ["xdotool", "mousemove", str(start_x), str(start_y)],
            capture_output=True, text=True, timeout=5, env=env,
        )

        import time
        time.sleep(0.05)

        subprocess.run(
            ["xdotool", "mousedown", "1"],
            capture_output=True, text=True, timeout=5, env=env,
        )

        time.sleep(0.05)

        steps = 10
        for i in range(1, steps + 1):
            t = i / steps
            cx = int(start_x + (end_x - start_x) * t)
            cy = int(start_y + (end_y - start_y) * t)
            subprocess.run(
                ["xdotool", "mousemove", str(cx), str(cy)],
                capture_output=True, text=True, timeout=5, env=env,
            )
            time.sleep(0.02)

        subprocess.run(
            ["xdotool", "mouseup", "1"],
            capture_output=True, text=True, timeout=5, env=env,
        )

        return ClickResult(success=True, x=end_x, y=end_y)

    except Exception as e:
        return ClickResult(success=False, error=str(e))


def type_text(text: str) -> TypeResult:
    ensure_display()

    try:
        result = subprocess.run(
            ["xdotool", "type", "--delay", "12", text],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "DISPLAY": DISPLAY},
        )

        if result.returncode != 0:
            return TypeResult(success=False, text=text, error=result.stderr)

        return TypeResult(success=True, text=text)

    except FileNotFoundError:
        return TypeResult(success=False, error="xdotool 未安装")
    except Exception as e:
        return TypeResult(success=False, error=str(e))


def press_key(key: str) -> KeyResult:
    ensure_display()

    key_map = {
        "enter": "Return", "return": "Return",
        "tab": "Tab", "escape": "Escape", "esc": "Escape",
        "backspace": "BackSpace", "delete": "Delete",
        "up": "Up", "down": "Down", "left": "Left", "right": "Right",
        "home": "Home", "end": "End",
        "page_up": "Page_Up", "page_down": "Page_Down",
        "space": "space",
        "ctrl": "ctrl", "alt": "alt", "shift": "shift", "super": "super",
    }

    mapped_key = key_map.get(key.lower(), key)

    try:
        result = subprocess.run(
            ["xdotool", "key", mapped_key],
            capture_output=True, text=True, timeout=5,
            env={**os.environ, "DISPLAY": DISPLAY},
        )

        if result.returncode != 0:
            return KeyResult(success=False, key=key, error=result.stderr)

        return KeyResult(success=True, key=key)

    except Exception as e:
        return KeyResult(success=False, key=key, error=str(e))


def scroll(direction: str = "down", amount: int = 3) -> ScrollResult:
    ensure_display()

    try:
        button = "5" if direction == "down" else "4"

        for _ in range(amount):
            subprocess.run(
                ["xdotool", "click", button],
                capture_output=True, text=True, timeout=5,
                env={**os.environ, "DISPLAY": DISPLAY},
            )

        return ScrollResult(success=True, direction=direction, amount=amount)

    except Exception as e:
        return ScrollResult(success=False, direction=direction, amount=amount, error=str(e))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("Eruitah Computer Use 截图工具测试")
    print("=" * 60)

    print(f"\nDISPLAY: {DISPLAY}")
    print(f"屏幕分辨率: {SCREEN_WIDTH}x{SCREEN_HEIGHT}")

    print("\n--- 启动 Xvfb ---")
    if start_xvfb():
        print("✅ Xvfb 启动成功")
    else:
        print("❌ Xvfb 启动失败")

    print("\n--- 截图测试 ---")
    result = take_screenshot()
    if result.success:
        print(f"✅ 截图成功: {result.width}x{result.height}, base64 长度: {len(result.base64_image)}")
    else:
        print(f"❌ 截图失败: {result.error}")

    print("\n--- 点击测试 ---")
    click_result = mouse_click(100, 100)
    if click_result.success:
        print(f"✅ 点击成功: ({click_result.x}, {click_result.y})")
    else:
        print(f"❌ 点击失败: {click_result.error}")

    print("\n--- 输入测试 ---")
    type_result = type_text("Hello World")
    if type_result.success:
        print(f"✅ 输入成功: {type_result.text}")
    else:
        print(f"❌ 输入失败: {type_result.error}")
