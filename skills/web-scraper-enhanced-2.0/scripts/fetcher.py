"""抓取层 2.0：带真实浏览器指纹的 HTTP 客户端 + 反爬自动升级。

相对 1.0 的增强：
- 真实 UA 池轮换 + 完整浏览器级请求头（sec-ch-ua / Sec-Fetch-* / Accept-Language…）
- 会话级 Cookie 持久化（同站多次请求保持登录/风控状态）
- 封锁自动识别（状态码 + 挑战页特征），auto 模式下被拦自动升级 Playwright 渲染
- 支持代理轮换 / 自定义 Cookie / 自定义请求头
- 保留全部 1.0 安全特性：SSRF 双重校验、robots.txt 遵守、礼貌限速、指数退避
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse, urljoin

import requests

from antibot import browser_headers, is_blocked_response, pick_ua
from security import check_chain

DEFAULT_UA = (
    "Mozilla/5.0 (compatible; WebScraperEnhanced/2.0; +https://example.com/bot)"
)
_ROBOTS_CACHE: dict[str, "RobotsPolicy"] = {}
_CACHE_LOCK = threading.Lock()


@dataclass
class FetchResult:
    ok: bool
    url: str
    final_url: str = ""
    status: int = 0
    html: str = ""
    error: str = ""
    elapsed: float = 0.0
    used_browser: bool = False      # 是否走了渲染层
    blocked: bool = False           # 是否被反爬拦截
    block_reason: str = ""


@dataclass
class RobotsPolicy:
    disallowed: list[str] = field(default_factory=list)
    crawl_delay: float = 0.0

    def allows(self, path: str) -> bool:
        return not any(path.startswith(d) for d in self.disallowed)


class Fetcher:
    """config 支持的键（均可用 YAML 配置或命令行覆盖）：

    基础：timeout / delay / max_retries / verify_ssl / obey_robots /
          user_agent / allow_private
    反爬：rotate_ua / browser_fallback(auto|always|never) / proxy / proxies /
          extra_headers / cookies
    """

    def __init__(self, config: Optional[dict] = None):
        cfg = config or {}
        self.timeout = float(cfg.get("timeout", 20))
        self.delay = float(cfg.get("delay", 1.0))
        self.max_retries = int(cfg.get("max_retries", 3))
        self.verify_ssl = bool(cfg.get("verify_ssl", True))
        self.obey_robots = bool(cfg.get("obey_robots", True))
        self.user_agent = cfg.get("user_agent") or DEFAULT_UA
        self.allow_private = bool(cfg.get("allow_private", False))
        # --- 2.0 反爬配置 ---
        self.rotate_ua = bool(cfg.get("rotate_ua", True))
        self.browser_fallback = str(cfg.get("browser_fallback", "auto"))
        self.proxy = cfg.get("proxy")
        self.proxies = cfg.get("proxies") or ([self.proxy] if self.proxy else [])
        self.extra_headers = dict(cfg.get("extra_headers") or {})
        self.cookies = dict(cfg.get("cookies") or {})
        self._proxy_idx = 0
        self._last_req = 0.0
        self._lock = threading.Lock()
        self._session = requests.Session()
        self._apply_identity()

    # ---------------------------------------------------------- 身份/请求头
    def _apply_identity(self):
        """按当前 UA 重建会话请求头 + Cookie（UA 轮换时调用）。"""
        self._current_ua = pick_ua(self.user_agent if not self.rotate_ua else None,
                                   rotate=self.rotate_ua)
        self._session.headers.clear()
        self._session.headers.update(
            browser_headers(self._current_ua, extra=self.extra_headers))
        if self.cookies:
            self._session.cookies.update(self.cookies)

    def _next_proxy(self) -> Optional[dict]:
        if not self.proxies:
            return None
        with self._lock:
            p = self.proxies[self._proxy_idx % len(self.proxies)]
            self._proxy_idx += 1
        return {"http": p, "https": p}

    # ---------------------------------------------------------- 礼貌限速
    def _throttle(self):
        with self._lock:
            now = time.time()
            wait = self.delay - (now - self._last_req)
            if wait > 0:
                time.sleep(wait)
            self._last_req = time.time()

    # ---------------------------------------------------------- robots.txt
    def _robots_for(self, url: str) -> RobotsPolicy:
        base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        if base in _ROBOTS_CACHE:
            return _ROBOTS_CACHE[base]
        policy = RobotsPolicy()
        if self.obey_robots:
            try:
                r = self._session.get(
                    urljoin(base, "/robots.txt"), timeout=self.timeout,
                    verify=self.verify_ssl)
                if r.status_code == 200:
                    agent_block = False
                    for line in r.text.splitlines():
                        line = line.split("#", 1)[0].strip()
                        if not line:
                            continue
                        k, _, v = line.partition(":")
                        k, v = k.strip().lower(), v.strip()
                        if k == "user-agent":
                            agent_block = (v == "*" or
                                           "webscraperenhanced" in v.lower())
                        elif k == "disallow" and agent_block and v:
                            policy.disallowed.append(v)
                        elif k == "crawl-delay" and agent_block:
                            try:
                                policy.crawl_delay = float(v)
                            except ValueError:
                                pass
            except requests.RequestException:
                pass
        if policy.crawl_delay and policy.crawl_delay > self.delay:
            self.delay = policy.crawl_delay
        with _CACHE_LOCK:
            _ROBOTS_CACHE[base] = policy
        return policy

    def _robots_ok(self, url: str) -> tuple[bool, str]:
        policy = self._robots_for(url)
        path = urlparse(url).path or "/"
        if not policy.allows(path):
            return False, f"robots.txt 禁止抓取路径 {path}"
        return True, "OK"

    # ---------------------------------------------------------- 静态抓取
    def fetch(self, url: str) -> FetchResult:
        """纯静态抓取（requests）。不触发渲染层。"""
        t0 = time.time()
        ok, reason = check_chain([url], allow_private=self.allow_private)
        if not ok:
            return FetchResult(False, url, error=reason, elapsed=time.time() - t0)
        ok, reason = self._robots_ok(url)
        if not ok:
            return FetchResult(False, url, error=reason, elapsed=time.time() - t0)

        last_err = ""
        for attempt in range(1, self.max_retries + 1):
            self._throttle()
            try:
                r = self._session.get(
                    url, timeout=self.timeout, verify=self.verify_ssl,
                    allow_redirects=True, proxies=self._next_proxy())
                # 重定向链后再次 SSRF 校验
                chain = [h.url for h in r.history] + [r.url]
                ok, reason = check_chain(chain, allow_private=self.allow_private)
                if not ok:
                    return FetchResult(False, url, error=reason,
                                       elapsed=time.time() - t0)
                if r.status_code >= 400:
                    last_err = f"HTTP {r.status_code}"
                    blocked, br = is_blocked_response(r.status_code, r.text,
                                                      dict(r.headers))
                    if blocked:
                        return FetchResult(False, url, final_url=r.url,
                                           status=r.status_code, error=last_err,
                                           blocked=True, block_reason=br,
                                           elapsed=time.time() - t0)
                    if r.status_code in (429, 503) and attempt < self.max_retries:
                        time.sleep(min(2 ** attempt, 8))
                        continue
                    return FetchResult(False, url, final_url=r.url,
                                       status=r.status_code, error=last_err,
                                       elapsed=time.time() - t0)
                # 挑战页可能是 200 状态码，特征判定补刀
                blocked, br = is_blocked_response(r.status_code, r.text)
                if blocked:
                    return FetchResult(False, url, final_url=r.url,
                                       status=r.status_code, error=last_err or br,
                                       blocked=True, block_reason=br,
                                       elapsed=time.time() - t0)
                if not r.encoding or r.encoding.lower() == "iso-8859-1":
                    guessed = r.apparent_encoding
                    if guessed:
                        r.encoding = guessed
                return FetchResult(True, url, final_url=r.url, status=r.status_code,
                                   html=r.text, elapsed=time.time() - t0)
            except requests.RequestException as e:
                last_err = f"{e.__class__.__name__}: {e}"
                if attempt < self.max_retries:
                    time.sleep(min(2 ** attempt, 8))
        return FetchResult(False, url, error=f"重试耗尽：{last_err}",
                           elapsed=time.time() - t0)

    # ---------------------------------------------------------- 智能抓取
    def fetch_smart(self, url: str, *, render_options: Optional[dict] = None,
                    progress=None) -> FetchResult:
        """静态优先；被反爬拦截且 browser_fallback=auto 时自动升级渲染层。

        browser_fallback=always 时直接用渲染层。
        """
        if self.browser_fallback == "always":
            return self._fetch_via_browser(url, render_options, progress)

        res = self.fetch(url)
        if res.blocked and self.browser_fallback == "auto":
            if progress:
                progress(f"[fetch] 静态抓取被拦截（{res.block_reason}），"
                         "自动升级浏览器渲染…")
            return self._fetch_via_browser(url, render_options, progress)
        return res

    def _fetch_via_browser(self, url: str, render_options: Optional[dict],
                           progress=None) -> FetchResult:
        t0 = time.time()
        # 渲染层同样先过 SSRF 校验
        ok, reason = check_chain([url], allow_private=self.allow_private)
        if not ok:
            return FetchResult(False, url, error=reason, elapsed=time.time() - t0)
        try:
            from renderer import render
        except Exception as e:
            return FetchResult(False, url, error=f"渲染层不可用：{e}",
                               elapsed=time.time() - t0)
        opts = dict(render_options or {})
        r = render(url, progress=progress, **opts)
        if not r.get("ok"):
            return FetchResult(False, url, error=r.get("error", "渲染失败"),
                               used_browser=True, elapsed=time.time() - t0)
        return FetchResult(True, url, final_url=r.get("final_url", url),
                           status=r.get("status", 0), html=r.get("html", ""),
                           used_browser=True, elapsed=time.time() - t0)
