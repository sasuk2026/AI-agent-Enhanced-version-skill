"""内容提取层 2.0：多模式抽取 + 全源图片发现。

相对 1.0 的图片增强（核心）：
- 覆盖 12 类图片来源，尽可能抓全「页面所有图片」：
    <img src/data-*/srcset> · <picture><source srcset> · <video poster> ·
    内联 style 背景图 · <style> 块背景图 · og:image / twitter:image ·
    <a href> 直链图片 · <link rel=image_src / apple-touch-icon> ·
    <svg><image href> · data: URI（标记不下载）
- srcset 完整解析，默认取最大候选（keep_all_candidates=True 时全部保留）
- 懒加载属性（data-src / data-original / data-lazy-src / data-echo…）自动识别
- URL 归一化 + 去重，保持页面出现顺序

其余模式（text/links/tables/metadata/assets/custom）与 1.0 兼容。
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

try:
    import trafilatura  # type: ignore
    _HAS_TRAFILATURA = True
except Exception:
    _HAS_TRAFILATURA = False

# 常见懒加载图片属性（按优先级）
_LAZY_ATTRS = ("data-src", "data-original", "data-lazy-src", "data-lazy",
               "data-echo", "data-image", "data-url", "data-actualsrc",
               "data-defer-src", "data-original-src")

# 视为图片的链接扩展名（用于 <a href> 直链、<link> 图标判定）
_IMG_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".bmp",
             ".svg", ".ico", ".tiff", ".tif", ".heic", ".jfif")

# 内联 CSS / <style> 中 url(...) 的背景图
_CSS_URL_RE = re.compile(
    r"""url\(\s*["']?\s*([^"')]+?)\s*["']?\s*\)""", re.IGNORECASE)


def extract(html: str, base_url: str, mode: str = "all",
            selector: Optional[str] = None,
            options: Optional[dict] = None) -> dict:
    """options 可含图片相关开关：
      keep_all_candidates(bool)  srcset 是否保留全部候选
      scan_inline_css(bool)      是否扫描 <style> 块内背景图
      include_icons(bool)        是否收录 favicon/apple-touch-icon
    """
    opt = options or {}
    soup = BeautifulSoup(html, "lxml")
    out: dict = {"url": base_url, "mode": mode}

    if mode == "metadata" or mode == "all":
        out["metadata"] = _metadata(soup, base_url)
    if mode in ("text", "all"):
        out["text"] = _main_text(soup, html)
    if mode in ("links", "all"):
        out["links"] = _collect(soup, base_url, "a", "href")
    if mode in ("images", "all"):
        out["images"] = _images(soup, base_url, opt)
    if mode in ("tables", "all"):
        out["tables"] = _tables(soup)
    if mode in ("assets", "all"):
        out["stylesheets"] = _collect(soup, base_url, "link", "href",
                                      rel="stylesheet")
        out["scripts"] = _collect(soup, base_url, "script", "src")
        out["documents"] = _documents(soup, base_url)
    if mode == "custom" and selector:
        out["custom"] = _custom(soup, base_url, selector)
    if mode == "custom" and not selector:
        out["error"] = "custom 模式需提供 --select 选择器"
    return out


# ---------- 元数据 ----------
def _metadata(soup: BeautifulSoup, base_url: str) -> dict:
    m = {}
    t = soup.find("title")
    if t and t.string:
        m["title"] = t.string.strip()
    meta = {(tag.get("name") or tag.get("property") or "").lower(): tag.get("content")
            for tag in soup.find_all("meta") if tag.get("content")}
    for k in ("description", "keywords", "author", "og:title", "og:description",
              "og:image", "twitter:title", "article:published_time"):
        if k in meta:
            m[k.replace(":", "_")] = meta[k]
    canonical = soup.find("link", rel="canonical")
    if canonical and canonical.get("href"):
        m["canonical"] = urljoin(base_url, canonical["href"])
    html_tag = soup.find("html")
    if html_tag and html_tag.get("lang"):
        m["lang"] = html_tag["lang"]
    return m


# ---------- 正文 ----------
def _main_text(soup: BeautifulSoup, html: str) -> str:
    if _HAS_TRAFILATURA:
        try:
            txt = trafilatura.extract(html, include_comments=False,
                                      include_tables=True)
            if txt:
                return txt
        except Exception:
            pass
    for tag in soup(["script", "style", "noscript", "header", "footer",
                     "nav", "aside", "form", "iframe"]):
        tag.decompose()
    candidates = soup.find_all(["article", "main", "section", "div", "p"])
    best, score = "", 0
    for c in candidates:
        text = c.get_text(" ", strip=True)
        s = len(text) - text.count(" ") * 0.1
        if s > score:
            best, score = text, s
    return best or soup.get_text(" ", strip=True)


# ---------- 链接/资源 ----------
def _collect(soup, base_url, tag, attr, rel=None):
    items = []
    for el in soup.find_all(tag):
        if rel and el.get("rel") != rel:
            continue
        val = el.get(attr)
        if val and not val.startswith(("javascript:", "#", "mailto:")):
            items.append(urljoin(base_url, val))
    return sorted(set(items))


def _documents(soup, base_url):
    docs = []
    exts = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
            ".csv", ".txt", ".zip")
    for a in soup.find_all("a"):
        href = a.get("href")
        if href and href.lower().endswith(exts):
            docs.append(urljoin(base_url, href))
    return sorted(set(docs))


# ---------- 图片（2.0 核心增强） ----------
def _img_ext_of(url: str) -> str:
    path = urlparse(url).path.lower()
    for ext in _IMG_EXTS:
        if path.endswith(ext):
            return ext.lstrip(".")
    return ""


def _make_item(url: str, base_url: str, source: str, alt: str = "",
               width="", height="", extra_srcset=None) -> Optional[dict]:
    if not url:
        return None
    url = url.strip()
    if not url or url.startswith(("javascript:", "about:")):
        return None
    if url.startswith("data:"):
        # data URI 图片：保留标记，下载层默认跳过（体积大且通常可现场生成）
        return {"url": url, "alt": alt, "width": width, "height": height,
                "source": source, "format": "data-uri",
                "srcset": extra_srcset or []}
    abs_url = urljoin(base_url, url)
    if not abs_url.startswith(("http://", "https://")):
        return None
    return {"url": abs_url, "alt": (alt or "").strip(), "width": width,
            "height": height, "source": source, "format": _img_ext_of(abs_url),
            "srcset": extra_srcset or []}


def parse_srcset(value: str) -> list[dict]:
    """解析 srcset 为 [{url, descriptor, weight}]，weight 用于选最大候选。"""
    candidates = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        bits = part.split()
        url = bits[0]
        desc = bits[1] if len(bits) > 1 else ""
        weight = 0
        m = re.match(r"([\d.]+)w$", desc)
        if m:
            weight = int(float(m.group(1)))
        else:
            m = re.match(r"([\d.]+)x$", desc)
            if m:
                weight = int(float(m.group(1)) * 1000)
        candidates.append({"url": url, "descriptor": desc, "weight": weight})
    return candidates


def _images(soup, base_url, opt: dict) -> list[dict]:
    """从全部已知来源收集图片，保持页面顺序、按 URL 去重。"""
    keep_all = bool(opt.get("keep_all_candidates"))
    include_icons = bool(opt.get("include_icons"))
    items: list[dict] = []
    seen: set[str] = set()

    def add(item):
        if item and item["url"] not in seen:
            seen.add(item["url"])
            items.append(item)

    def lazy_src(img) -> str:
        for attr in _LAZY_ATTRS:
            v = img.get(attr)
            if v and not v.startswith("data:,"):
                return v
        return ""

    # 1) <img>：src + srcset + 懒加载属性
    for img in soup.find_all("img"):
        alt = img.get("alt", "")
        w, h = img.get("width", ""), img.get("height", "")
        srcset = img.get("srcset") or img.get("data-srcset") or ""
        added_src = False
        if srcset:
            cands = parse_srcset(srcset)
            if cands:
                best = max(cands, key=lambda c: c["weight"])
                add(_make_item(best["url"], base_url, "img-srcset", alt, w, h,
                               extra_srcset=[c["url"] for c in cands] if keep_all else None))
                if keep_all:
                    for c in cands:
                        add(_make_item(c["url"], base_url, "img-srcset-candidate", alt, w, h))
                added_src = True
        src = img.get("src") or lazy_src(img)
        if src:
            add(_make_item(src, base_url, "img-src", alt, w, h))
            added_src = True
        if not added_src:
            # 仅有懒加载占位但无真实地址时也记录占位来源（下载层会失败并如实报告）
            pass

    # 2) <picture><source srcset/src>
    for pic in soup.find_all("picture"):
        for source in pic.find_all("source"):
            ss = source.get("srcset") or ""
            if ss:
                cands = parse_srcset(ss)
                if cands:
                    best = max(cands, key=lambda c: c["weight"])
                    add(_make_item(best["url"], base_url, "picture-source"))
                    if keep_all:
                        for c in cands:
                            add(_make_item(c["url"], base_url, "picture-source-candidate"))
            s = source.get("src")
            if s:
                add(_make_item(s, base_url, "picture-source-src"))

    # 3) <video poster>
    for video in soup.find_all("video"):
        poster = video.get("poster")
        if poster:
            add(_make_item(poster, base_url, "video-poster"))

    # 4) 内联 style 背景图
    for el in soup.find_all(style=True):
        m = _CSS_URL_RE.search(el["style"])
        if m:
            add(_make_item(m.group(1), base_url, "inline-style-bg"))

    # 5) <style> 块内背景图（可选）
    if opt.get("scan_inline_css"):
        for style_tag in soup.find_all("style"):
            css = style_tag.string or style_tag.get_text() or ""
            for m in _CSS_URL_RE.finditer(css):
                u = m.group(1).strip()
                if not u.startswith("data:"):
                    add(_make_item(u, base_url, "style-block-bg"))

    # 6) og:image / twitter:image
    for meta in soup.find_all("meta"):
        prop = (meta.get("property") or meta.get("name") or "").lower()
        if prop in ("og:image", "og:image:url", "og:image:secure_url",
                    "twitter:image", "twitter:image:src"):
            content = meta.get("content")
            if content:
                add(_make_item(content, base_url, f"meta-{prop}"))

    # 7) <a href> 直链图片
    for a in soup.find_all("a"):
        href = a.get("href", "")
        if href and _img_ext_of(href):
            add(_make_item(href, base_url, "a-href-image"))

    # 8) <link rel=image_src / apple-touch-icon / icon>（图标默认收集中由 include_icons 控制）
    for link in soup.find_all("link"):
        rel = [r.lower() for r in (link.get("rel") or [])]
        href = link.get("href")
        if not href:
            continue
        if "image_src" in rel:
            add(_make_item(href, base_url, "link-image_src"))
        elif include_icons and ("apple-touch-icon" in rel or "icon" in rel):
            if _img_ext_of(href) or "apple-touch-icon" in rel:
                add(_make_item(href, base_url, "link-icon"))

    # 9) <svg><image href/xlink:href>
    for svg_img in soup.find_all("image"):
        href = svg_img.get("href") or svg_img.get("{http://www.w3.org/1999/xlink}href")
        if href:
            add(_make_item(href, base_url, "svg-image"))

    # 10) <input type=image src>
    for inp in soup.find_all("input"):
        if (inp.get("type") or "").lower() == "image" and inp.get("src"):
            add(_make_item(inp["src"], base_url, "input-image"))

    # 11) <object data> / <embed src> 图片
    for tag_name in ("object", "embed"):
        for el in soup.find_all(tag_name):
            u = el.get("data") or el.get("src")
            if u and _img_ext_of(u):
                add(_make_item(u, base_url, f"{tag_name}-image"))

    return items


# ---------- 表格 ----------
def _tables(soup):
    tables = []
    for ti, table in enumerate(soup.find_all("table")):
        rows = []
        for tr in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True)
                     for c in tr.find_all(["td", "th"])]
            if cells:
                rows.append(cells)
        if rows:
            tables.append({"index": ti, "rows": rows})
    return tables


# ---------- 自定义选择器 ----------
def _custom(soup, base_url, selector: str):
    """支持 `tag.class` 选择器，以及 `selector::attr` 抽取属性。"""
    attr = None
    if "::" in selector:
        selector, attr = selector.rsplit("::", 1)
    results = []
    for el in soup.select(selector):
        if attr:
            val = el.get(attr)
            if val:
                results.append(urljoin(base_url, val)
                               if attr in ("href", "src") else val)
        else:
            results.append(el.get_text(" ", strip=True))
    return [r for r in results if r]
