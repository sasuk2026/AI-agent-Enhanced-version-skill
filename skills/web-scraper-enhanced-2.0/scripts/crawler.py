"""站点遍历层 2.0：BFS 爬取 + 资源收集 + 可选图片批量落盘。

相对 1.0：新增整站图片收集（全局限量 max_images，AI 可控）、
复用 2.0 的 fetch_smart（反爬自动升级）、进度回调。
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Optional
from urllib.parse import urljoin, urlparse

from fetcher import Fetcher, FetchResult
from extractor import extract

Progress = Optional[Callable[[str], None]]


@dataclass
class CrawlResult:
    pages: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    image_report: Optional[dict] = None


def crawl(start_url: str, config: Optional[dict] = None,
          max_pages: int = 20, max_depth: int = 2,
          same_domain: bool = True, mode: str = "all",
          selector: Optional[str] = None,
          save_images: bool = False, out_dir: Optional[str] = None,
          max_images: int = 0, img_options: Optional[dict] = None,
          render_options: Optional[dict] = None,
          progress: Progress = None) -> CrawlResult:
    cfg = dict(config or {})
    fetcher = Fetcher(cfg)
    base_host = urlparse(start_url).netloc
    seen: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(start_url, 0)])
    seen.add(start_url)
    result = CrawlResult()
    fetched = 0
    all_images: list[dict] = []
    t0 = time.time()

    def log(msg: str):
        if progress:
            progress(msg)

    while queue and fetched < max_pages:
        url, depth = queue.popleft()
        log(f"[crawl] ({fetched + 1}/{max_pages}) {url}")
        res: FetchResult = fetcher.fetch_smart(
            url, render_options=render_options, progress=progress)
        if not res.ok:
            result.pages.append({"url": url, "ok": False, "error": res.error,
                                 "blocked": res.blocked})
            continue
        fetched += 1
        data = extract(res.html, res.final_url, mode=mode, selector=selector,
                       options=img_options)
        data["ok"] = True
        data["status"] = res.status
        data["used_browser"] = res.used_browser
        result.pages.append(data)

        # 收集整站图片（全局去重，无论是否落盘都统计）
        for im in data.get("images", []):
            if im["url"] not in {x["url"] for x in all_images}:
                all_images.append(im)

        if depth >= max_depth:
            continue
        for link in data.get("links", []):
            host = urlparse(link).netloc
            if same_domain and host and host != base_host:
                continue
            if link not in seen:
                seen.add(link)
                queue.append((link, depth + 1))

    # 整站图片统一限量 + 下载
    if save_images and all_images:
        from images import ImageDownloader, filter_images
        items = filter_images(all_images, max_images=max_images)
        dl = ImageDownloader(
            out_dir or "images", referer=start_url,
            user_agent=fetcher._current_ua,
            timeout=int(fetcher.timeout), verify_ssl=fetcher.verify_ssl,
            extra_headers=fetcher.extra_headers, progress=progress)
        rep = dl.download_all(items)
        rep.page_url = start_url
        result.image_report = rep.to_dict()

    result.stats = {
        "start_url": start_url,
        "pages_fetched": fetched,
        "unique_discovered": len(seen),
        "max_depth": max_depth,
        "images_found": len(all_images),
        "elapsed_sec": round(time.time() - t0, 2),
    }
    return result
