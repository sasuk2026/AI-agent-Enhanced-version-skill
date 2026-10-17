"""渲染层：Playwright 真实浏览器内核渲染（带 Stealth 反检测）。

2.0 新增模块。用于：
- 抓取 SPA / JS 渲染页面
- 触发懒加载图片（自动滚动到底部，等待图片真正加载后再取 HTML）
- 静态请求被反爬拦截时自动升级到此层（见 fetcher.py）

依赖 playwright + 浏览器二进制；缺失时返回友好错误，不影响静态抓取主流程。
"""
from __future__ import annotations

import time
from typing import Callable, Optional

from antibot import STEALTH_JS, browser_headers, pick_ua

Progress = Optional[Callable[[str], None]]


def playwright_available() -> tuple[bool, str]:
    try:
        import playwright.sync_api  # noqa: F401
        return True, ""
    except Exception:
        return False, ("未安装 playwright。执行：pip install playwright && "
                       "playwright install chromium")


def render(
    url: str,
    *,
    timeout: int = 30,
    wait_until: str = "domcontentloaded",
    networkidle_timeout: float = 8.0,
    scroll: bool = True,
    scroll_pause: float = 0.7,
    max_scroll_steps: int = 25,
    viewport: tuple[int, int] = (1920, 1080),
    user_agent: Optional[str] = None,
    proxy: Optional[str] = None,
    extra_headers: Optional[dict] = None,
    screenshot_path: Optional[str] = None,
    stealth: bool = True,
    locale: str = "zh-CN",
    timezone: str = "Asia/Shanghai",
    progress: Progress = None,
) -> dict:
    """渲染页面并返回 {ok, html, final_url, status, error, used_browser, screenshot}。

    scroll=True 时自动滚动页面触发懒加载（对图片抓取至关重要）。
    """
    ok, reason = playwright_available()
    if not ok:
        return {"ok": False, "error": reason, "used_browser": False}

    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:  # pragma: no cover
        return {"ok": False, "error": f"playwright 导入失败：{e}", "used_browser": False}

    def log(msg: str):
        if progress:
            progress(msg)

    ua = pick_ua(user_agent, rotate=False)
    launch_args = [
        "--disable-blink-features=AutomationControlled",  # 去掉 "Chrome is being controlled..." 条
        "--no-sandbox",
        "--disable-dev-shm-usage",
    ]
    result = {"ok": False, "used_browser": True}
    with sync_playwright() as p:
        browser = None
        try:
            browser = p.chromium.launch(
                headless=True, args=launch_args,
                proxy={"server": proxy} if proxy else None,
            )
            context = browser.new_context(
                user_agent=ua,
                viewport={"width": viewport[0], "height": viewport[1]},
                locale=locale,
                timezone_id=timezone,
                extra_http_headers=browser_headers(ua, extra=extra_headers),
                ignore_https_errors=True,
            )
            if stealth:
                context.add_init_script(STEALTH_JS)
            page = context.new_page()
            log(f"[render] 浏览器渲染中：{url}")

            # goto 超时不等于失败：部分慢站/长连接站 domcontentloaded 迟迟不触发，
            # 但页面可能已可用。超时则降级继续，尽力取内容。
            try:
                resp = page.goto(url, timeout=timeout * 1000,
                                 wait_until=wait_until)
            except Exception as goto_err:
                if "Timeout" not in str(goto_err):
                    raise
                log(f"[render] goto 超时（{wait_until}），降级继续取已加载内容")
                resp = None
            result["status"] = resp.status if resp else 0
            result["final_url"] = page.url
            # 页面完全没加载出来才算真失败
            try:
                body_len = page.evaluate(
                    "document.body ? document.body.innerHTML.length : 0")
            except Exception:
                body_len = 0
            if body_len == 0 and resp is None:
                result["error"] = f"页面未能加载：{goto_err}"
                return result

            # 等待网络趋于安静（最多 networkidle_timeout 秒，超时也继续）
            if wait_until != "networkidle":
                try:
                    page.wait_for_load_state("networkidle",
                                             timeout=networkidle_timeout * 1000)
                except Exception:
                    pass

            if scroll:
                _auto_scroll(page, scroll_pause, max_scroll_steps, log)

            result["html"] = page.content()
            result["ok"] = True
            if screenshot_path:
                try:
                    page.screenshot(path=screenshot_path, full_page=True)
                    result["screenshot"] = screenshot_path
                except Exception as e:
                    result["screenshot_error"] = str(e)
        except Exception as e:
            result["error"] = f"{e.__class__.__name__}: {e}"
        finally:
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass
    return result


def _auto_scroll(page, pause: float, max_steps: int, log) -> None:
    """缓慢滚动到底部并回滚一段，触发懒加载/无限滚动图片。"""
    try:
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(pause)
    except Exception:
        return
    last_height = 0
    stable = 0
    for step in range(max_steps):
        try:
            height = page.evaluate("document.body.scrollHeight")
            page.evaluate("window.scrollBy(0, window.innerHeight)")
            time.sleep(pause)
            new_height = page.evaluate("document.body.scrollHeight")
        except Exception:
            return
        if new_height == last_height and new_height == height:
            stable += 1
            if stable >= 2:
                break
        else:
            stable = 0
        last_height = new_height
        if step % 5 == 4:
            log(f"[render] 滚动触发懒加载… 第 {step + 1} 步")
    log("[render] 滚动完成，懒加载内容已触发")
