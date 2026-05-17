"""
Eruitah 智能编程沙盒 - 浏览器视觉工具

基于 Playwright 的 Headless 浏览器截图工具，
让 Agent 拥有"看网页"的能力。
"""

import base64
import logging
import asyncio
from typing import Optional

logger = logging.getLogger(__name__)

_browser_instance = None
_browser_context = None


async def _ensure_browser():
    global _browser_instance, _browser_context
    if _browser_instance is None or not _browser_instance.is_connected():
        from playwright.async_api import async_playwright
        pw = await async_playwright().start()
        _browser_instance = await pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )
        _browser_context = await _browser_instance.new_context(
            viewport={"width": 1280, "height": 720},
            device_scale_factor=1,
        )
    return _browser_context


async def _screenshot_async(url: str, wait_until: str = "networkidle", timeout_ms: int = 30000) -> dict:
    context = await _ensure_browser()
    page = await context.new_page()
    try:
        await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
        await page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        screenshot_bytes = await page.screenshot(full_page=False, type="png")
        base64_str = base64.b64encode(screenshot_bytes).decode("utf-8")
        title = await page.title()
        return {
            "status": "success",
            "base64_image": base64_str,
            "title": title,
            "url": url,
        }
    except Exception as e:
        logger.error(f"浏览器截图失败: {e}")
        return {
            "status": "error",
            "error": str(e),
            "url": url,
        }
    finally:
        await page.close()


def execute_browser_vision(
    url: str,
    wait_until: str = "networkidle",
    timeout_ms: int = 30000,
) -> dict:
    """
    执行浏览器截图

    Args:
        url: 要访问的 URL（本地或远程）
        wait_until: 等待策略，可选 "load", "domcontentloaded", "networkidle"
        timeout_ms: 超时时间（毫秒）

    Returns:
        dict: 包含 status 和 base64_image（或 error）的字典
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run,
                    _screenshot_async(url, wait_until, timeout_ms),
                )
                return future.result(timeout=timeout_ms / 1000 + 10)
        else:
            return loop.run_until_complete(_screenshot_async(url, wait_until, timeout_ms))
    except Exception as e:
        logger.error(f"browser_vision 执行异常: {e}")
        return {
            "status": "error",
            "error": str(e),
            "url": url,
        }
