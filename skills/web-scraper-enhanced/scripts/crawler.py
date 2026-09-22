"""站点遍历层：BFS 爬取同域/限定范围页面并抽取资源。

增强能力：
- 广度优先遍历，支持最大页数 / 最大深度 / 仅同域 限制
- 全局 URL 去重，避免环路死循环
- 复用 Fetcher 的防护（SSRF / robots / 速率）与 Extractor 的多模式抽取
- 每页结果累积为列表，便于统一导出
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin, urlparse

from fetcher import Fetcher
from extractor import extract


@dataclass
class CrawlResult:
    pages: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)


def crawl(start_url: str, config: Optional[dict] = None,
          max_pages: int = 20, max_depth: int = 2,
          same_domain: bool = True, mode: str = "all",
          selector: Optional[str] = None) -> CrawlResult:
    cfg = config or {}
    fetcher = Fetcher(cfg)
    base_host = urlparse(start_url).netloc
    seen: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(start_url, 0)])
    seen.add(start_url)
    result = CrawlResult()
    fetched = 0
    t0 = time.time()

    while queue and fetched < max_pages:
        url, depth = queue.popleft()
        res = fetcher.fetch(url)
        if not res.ok:
            result.pages.append({"url": url, "ok": False, "error": res.error})
            continue
        fetched += 1
        data = extract(res.html, res.final_url, mode=mode, selector=selector)
        data["ok"] = True
        data["status"] = res.status
        result.pages.append(data)

        if depth >= max_depth:
            continue
        # 从已抓页面的链接里发现新页面
        for link in data.get("links", []):
            host = urlparse(link).netloc
            if same_domain and host and host != base_host:
                continue
            if link not in seen:
                seen.add(link)
                queue.append((link, depth + 1))

    result.stats = {
        "start_url": start_url,
        "pages_fetched": fetched,
        "unique_discovered": len(seen),
        "max_depth": max_depth,
        "elapsed_sec": round(time.time() - t0, 2),
    }
    return result
