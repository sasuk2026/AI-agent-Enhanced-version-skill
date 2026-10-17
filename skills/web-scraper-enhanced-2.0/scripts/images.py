"""图片管线 2.0：过滤 · 限量 · 下载 · 报告。

设计目标（对应用户需求）：
- 「页面的所有图片都能抓到」：配合 extractor 全源发现，下载端并发 + 重试 + 断点跳过
- 「抓多少张可以自己调整、AI 直接调用」：max_images=0 表示全部；
  AI 在调用时通过 --max-images N 决定数量；另支持按尺寸/体积/格式过滤
- 「功能完整」：去重（URL + 内容 SHA1）、尺寸识别、报告导出、失败如实记录

典型用法（由 AI 在 SKILL.md 工作流中调用）：
    python3 fetch_cli.py images --url <URL> --out-dir ./imgs --max-images 10
"""
from __future__ import annotations

import hashlib
import io
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional
from urllib.parse import urlparse, unquote

import requests

# content-type → 扩展名
_CT_EXT = {
    "image/jpeg": "jpg", "image/jpg": "jpg", "image/pjpeg": "jpg",
    "image/png": "png", "image/apng": "png", "image/x-png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/avif": "avif",
    "image/bmp": "bmp", "image/x-ms-bmp": "bmp",
    "image/svg+xml": "svg",
    "image/x-icon": "ico", "image/vnd.microsoft.icon": "ico",
    "image/tiff": "tiff",
    "image/heic": "heic", "image/heif": "heif",
}

# URL 路径后缀 → 扩展名
_URL_EXT = ("jpg", "jpeg", "png", "gif", "webp", "avif", "bmp", "svg",
            "ico", "tiff", "tif", "heic", "heif", "jfif")

Progress = Optional[Callable[[str], None]]


# ---------------------------------------------------------------- 工具
def guess_ext(url: str, content_type: str = "") -> str:
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct in _CT_EXT:
        return _CT_EXT[ct]
    path = urlparse(url).path.lower()
    for ext in _URL_EXT:
        if path.endswith("." + ext):
            return "jpg" if ext == "jpeg" else ext
    return "jpg" if "jpeg" in ct else "png"  # 最后兜底


def sanitize_name(name: str, max_len: int = 60) -> str:
    """把任意字符串变成安全文件名片段。"""
    name = unquote(name or "")
    name = re.sub(r"[^\w\-. ]", "_", name, flags=re.UNICODE)
    name = name.strip(" ._")
    return (name[:max_len] or "image")


def image_size(data: bytes) -> tuple[int, int]:
    """从字节流读宽高（支持 jpg/png/gif/webp/bmp/svg/ico），失败返回 (0,0)。"""
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as im:
            return im.size
    except Exception:
        pass
    # SVG：读 width/height 属性
    try:
        head = data[:2048].decode("utf-8", "ignore")
        m = re.search(r'<svg[^>]*\swidth=["\']?(\d+)', head)
        n = re.search(r'<svg[^>]*\sheight=["\']?(\d+)', head)
        if m and n:
            return int(m.group(1)), int(n.group(1))
    except Exception:
        pass
    return 0, 0


# ---------------------------------------------------------------- 过滤
def filter_images(items: list[dict], *, max_images: int = 0,
                  min_width: int = 0, min_height: int = 0,
                  min_size_kb: float = 0, formats: Optional[list[str]] = None,
                  skip_icons: bool = True,
                  include_data_uri: bool = False) -> list[dict]:
    """按 AI/用户指定的条件过滤图片。

    max_images=0 → 不限量（全部）；N>0 → 取前 N 张（保持页面顺序）。
    skip_icons=True → 过滤已知小图标（favicon 类、尺寸声明 <=32px 的追踪像素）。
    """
    fmt_set = {f.lower().lstrip(".") for f in formats} if formats else None
    out: list[dict] = []
    for it in items:
        url = it.get("url", "")
        if url.startswith("data:") and not include_data_uri:
            continue
        if url.startswith("data:"):
            out.append(it)
            continue
        ext = (it.get("format") or guess_ext(url)).lower()
        if fmt_set and ext not in fmt_set and ext != "jpeg":
            continue
        # 尺寸过滤（HTML 属性里声明的才可用；未声明的留给下载后判定）
        try:
            w = int(it.get("width") or 0)
            h = int(it.get("height") or 0)
        except (TypeError, ValueError):
            w = h = 0
        if skip_icons and it.get("source") == "link-icon":
            continue
        if w and h and (w < 33 or h < 33):  # 33x33 以下基本是图标/追踪像素
            continue
        if w and min_width and w < min_width:
            continue
        if h and min_height and h < min_height:
            continue
        out.append(it)
    if max_images and max_images > 0:
        out = out[:max_images]
    return out


# ---------------------------------------------------------------- 下载器
@dataclass
class DownloadReport:
    page_url: str = ""
    out_dir: str = ""
    found: int = 0
    downloaded: int = 0
    skipped: int = 0
    failed: int = 0
    images: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "page_url": self.page_url, "out_dir": self.out_dir,
            "found": self.found, "downloaded": self.downloaded,
            "skipped": self.skipped, "failed": self.failed,
            "images": self.images,
        }


class ImageDownloader:
    """并发下载图片，礼貌限速 + 指数退避重试 + 断点跳过 + 内容去重。"""

    def __init__(self, out_dir: str, *, referer: str = "",
                 user_agent: str = "", timeout: int = 20,
                 workers: int = 4, max_bytes: int = 20 * 1024 * 1024,
                 verify_ssl: bool = True, delay: float = 0.3,
                 extra_headers: Optional[dict] = None,
                 progress: Progress = None):
        self.out_dir = out_dir
        self.referer = referer
        self.user_agent = user_agent
        self.timeout = timeout
        self.workers = max(1, int(workers))
        self.max_bytes = max_bytes
        self.verify_ssl = verify_ssl
        self.delay = delay
        self.extra_headers = dict(extra_headers or {})
        self.progress = progress
        self._seen_sha: set[str] = set()
        self._host_last: dict[str, float] = {}
        self._host_lock = threading.Lock()

    # ---- 单主机礼貌间隔 ----
    def _host_throttle(self, url: str):
        host = urlparse(url).netloc
        with self._host_lock:
            now = time.time()
            last = self._host_last.get(host, 0.0)
            wait = self.delay - (now - last)
            if wait > 0:
                time.sleep(wait)
            self._host_last[host] = time.time()

    def _headers_for(self, url: str) -> dict:
        h = {"User-Agent": self.user_agent or "Mozilla/5.0"}
        if self.referer:
            h["Referer"] = self.referer
            h["Sec-Fetch-Dest"] = "image"
            h["Sec-Fetch-Mode"] = "no-cors"
            h["Sec-Fetch-Site"] = ("same-origin"
                                   if urlparse(url).netloc ==
                                   urlparse(self.referer).netloc
                                   else "cross-site")
            h["Accept"] = "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"
        h.update(self.extra_headers)
        return h

    def _target_path(self, idx: int, url: str, content_type: str) -> str:
        ext = guess_ext(url, content_type)
        base = sanitize_name(os.path.basename(urlparse(url).path) or "")
        if not base.lower().endswith("." + ext):
            base = f"{base}.{ext}" if base and base != "image" else f"image.{ext}"
        return os.path.join(self.out_dir, f"{idx:03d}_{base}")

    def _download_one(self, idx: int, item: dict) -> dict:
        url = item["url"]
        rec = {"url": url, "source": item.get("source", ""),
               "alt": item.get("alt", ""), "status": "ok",
               "file": "", "bytes": 0, "format": "", "width": 0,
               "height": 0, "sha1": "", "error": ""}
        if url.startswith("data:"):
            rec.update(status="skipped", error="data URI（未下载）")
            return rec
        for attempt in (1, 2, 3):
            try:
                self._host_throttle(url)
                r = requests.get(url, headers=self._headers_for(url),
                                 timeout=self.timeout, stream=True,
                                 verify=self.verify_ssl, allow_redirects=True)
                if r.status_code >= 400:
                    rec.update(status="failed",
                               error=f"HTTP {r.status_code}")
                    if r.status_code in (429, 503) and attempt < 3:
                        time.sleep(min(2 ** attempt, 6))
                        continue
                    return rec
                # 读取并限制体积
                chunks, total = [], 0
                for chunk in r.iter_content(65536):
                    total += len(chunk)
                    if total > self.max_bytes:
                        rec.update(status="skipped",
                                   error=f"超过体积上限 {self.max_bytes // 1024}KB")
                        return rec
                    chunks.append(chunk)
                data = b"".join(chunks)
                if not data:
                    rec.update(status="failed", error="空响应")
                    return rec
                # 校验真的是图片（防 HTML 错误页伪装）
                ct = r.headers.get("Content-Type", "")
                if "image" not in ct and "octet-stream" not in ct \
                        and not data[:4].startswith(b"\x89PNG") \
                        and not data[:3].startswith(b"\xff\xd8\xff") \
                        and not data[:6].startswith(b"GIF89a") \
                        and not data[:4].startswith(b"RIFF") \
                        and b"<svg" not in data[:512].lower():
                    rec.update(status="failed",
                               error=f"非图片内容（Content-Type: {ct or '未知'}）")
                    return rec
                # 内容去重
                sha1 = hashlib.sha1(data).hexdigest()
                with self._host_lock:  # 复用锁保护 seen 集合即可
                    if sha1 in self._seen_sha:
                        rec.update(status="skipped",
                                   error="内容重复（SHA1 已存在）")
                        return rec
                    self._seen_sha.add(sha1)
                w, h = image_size(data)
                path = self._target_path(idx, url, ct)
                if os.path.exists(path) and os.path.getsize(path) == len(data):
                    rec.update(status="skipped", error="文件已存在（断点跳过）",
                               file=path, bytes=len(data), format=guess_ext(url, ct),
                               width=w, height=h, sha1=sha1)
                    return rec
                with open(path, "wb") as f:
                    f.write(data)
                rec.update(file=path, bytes=len(data),
                           format=guess_ext(url, ct), width=w, height=h,
                           sha1=sha1)
                return rec
            except requests.RequestException as e:
                rec["error"] = f"{e.__class__.__name__}: {e}"
                if attempt < 3:
                    time.sleep(min(2 ** attempt, 6))
        rec["status"] = "failed"
        return rec

    def download_all(self, items: list[dict]) -> DownloadReport:
        """下载全部（已过滤/限量后的）图片，返回报告。"""
        os.makedirs(self.out_dir, exist_ok=True)
        report = DownloadReport(out_dir=self.out_dir)
        report.found = len(items)
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = {pool.submit(self._download_one, i + 1, it): it
                       for i, it in enumerate(items)}
            for fut in as_completed(futures):
                rec = fut.result()
                report.images.append(rec)
                st = rec["status"]
                if st == "ok":
                    report.downloaded += 1
                    if self.progress:
                        self.progress(f"[img] ✓ {rec['bytes'] // 1024}KB "
                                      f"{rec['width']}x{rec['height']} → "
                                      f"{os.path.basename(rec['file'])}")
                elif st == "skipped":
                    report.skipped += 1
                else:
                    report.failed += 1
                    if self.progress:
                        self.progress(f"[img] ✗ {rec['url'][:80]} "
                                      f"（{rec['error']}）")
        # 按页面顺序排序输出
        report.images.sort(key=lambda r: items.index(
            next(i for i in items if i["url"] == r["url"])) if r["url"] in
            {i["url"] for i in items} else 0)
        return report
