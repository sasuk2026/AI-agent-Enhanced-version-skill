"""抓取层：带防护的 HTTP 客户端。

增强能力：
- 请求前/重定向后均过 SSRF 校验（security.check_chain）
- 自动遵守 robots.txt（Disallow 路径 + Crawl-delay）
- 礼貌抓取：可配置 User-Agent、超时、请求间隔、并发上限、指数退避重试
- 失败友好：返回结构化结果而非抛异常中断整条流水线
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse, urljoin

import requests

from security import check_chain

DEFAULT_UA = (
    "Mozilla/5.0 (compatible; WebScraperEnhanced/1.0; +https://example.com/bot)"
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


@dataclass
class RobotsPolicy:
    disallowed: list[str] = field(default_factory=list)
    crawl_delay: float = 0.0

    def allows(self, path: str) -> bool:
        return not any(path.startswith(d) for d in self.disallowed)


class Fetcher:
    def __init__(self, config: Optional[dict] = None):
        cfg = config or {}
        self.timeout = float(cfg.get("timeout", 15))
        self.delay = float(cfg.get("delay", 1.0))          # 请求间隔（秒）
        self.max_retries = int(cfg.get("max_retries", 3))
        self.verify_ssl = bool(cfg.get("verify_ssl", True))
        self.obey_robots = bool(cfg.get("obey_robots", True))
        self.user_agent = cfg.get("user_agent", DEFAULT_UA)
        self.allow_private = bool(cfg.get("allow_private", False))
        self._last_req = 0.0
        self._lock = threading.Lock()
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": self.user_agent})

    # ---- 速率限制：全局串行节流 ----
    def _throttle(self):
        with self._lock:
            now = time.time()
            wait = self.delay - (now - self._last_req)
            if wait > 0:
                time.sleep(wait)
            self._last_req = time.time()

    # ---- robots.txt ----
    def _robots_for(self, url: str) -> RobotsPolicy:
        base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        if base in _ROBOTS_CACHE:
            return _ROBOTS_CACHE[base]
        policy = RobotsPolicy()
        if self.obey_robots:
            try:
                r = self._session.get(
                    urljoin(base, "/robots.txt"), timeout=self.timeout,
                    verify=self.verify_ssl, headers={"User-Agent": self.user_agent},
                )
                if r.status_code == 200:
                    lines = r.text.splitlines()
                    agent_block = False
                    for line in lines:
                        line = line.split("#", 1)[0].strip()
                        if not line:
                            continue
                        k, _, v = line.partition(":")
                        k, v = k.strip().lower(), v.strip()
                        if k == "user-agent":
                            agent_block = v == "*" or "webscraperenhanced" in v.lower()
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

    # ---- 主抓取 ----
    def fetch(self, url: str) -> FetchResult:
        t0 = time.time()
        # 1) 请求前 SSRF 校验
        ok, reason = check_chain([url], allow_private=self.allow_private)
        if not ok:
            return FetchResult(False, url, error=reason, elapsed=time.time() - t0)
        # 2) robots 校验
        ok, reason = self._robots_ok(url)
        if not ok:
            return FetchResult(False, url, error=reason, elapsed=time.time() - t0)

        # 3) 带重试的抓取
        last_err = ""
        for attempt in range(1, self.max_retries + 1):
            self._throttle()
            try:
                r = self._session.get(
                    url, timeout=self.timeout, verify=self.verify_ssl,
                    allow_redirects=True,
                )
                # 4) 重定向链后再次 SSRF 校验（防 30x 跳内网）
                chain = [h.url for h in r.history] + [r.url]
                ok, reason = check_chain(chain, allow_private=self.allow_private)
                if not ok:
                    return FetchResult(False, url, error=reason, elapsed=time.time() - t0)
                if r.status_code >= 400:
                    last_err = f"HTTP {r.status_code}"
                    if r.status_code in (429, 503) and attempt < self.max_retries:
                        time.sleep(min(2 ** attempt, 8))
                        continue
                    return FetchResult(False, url, final_url=r.url, status=r.status_code,
                                       error=last_err, elapsed=time.time() - t0)
                # 编码校正：目标站未声明 charset 时（默认 ISO-8859-1）
                # 用 apparent_encoding 探测，避免中文等非 ASCII 乱码
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
