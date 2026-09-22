"""内容提取层：从 HTML 中按模式/选择器抽取目标资源。

增强能力：
- 多模式：all / text / links / images / tables / metadata / custom
- 指定内容：custom 模式支持 CSS 选择器（含属性提取，如 `a::href`）
- 正文提取：优先 trafilatura（若安装），否则 bs4 启发式兜底
- 资源收集：链接、图片、表格、CSS/JS、文档链接，并补全为绝对 URL
- 元数据：title / description / og / canonical / lang / 发布时间
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


def extract(html: str, base_url: str, mode: str = "all",
            selector: Optional[str] = None) -> dict:
    soup = BeautifulSoup(html, "lxml")
    out: dict = {"url": base_url, "mode": mode}

    if mode == "metadata" or mode == "all":
        out["metadata"] = _metadata(soup, base_url)
    if mode in ("text", "all"):
        out["text"] = _main_text(soup, html)
    if mode in ("links", "all"):
        out["links"] = _collect(soup, base_url, "a", "href")
    if mode in ("images", "all"):
        out["images"] = _images(soup, base_url)
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
    meta = { (tag.get("name") or tag.get("property") or "").lower(): tag.get("content")
             for tag in soup.find_all("meta") if tag.get("content") }
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
    # bs4 启发式：去噪声标签后取正文块
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


def _images(soup, base_url):
    imgs = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if src:
            imgs.append({
                "url": urljoin(base_url, src),
                "alt": img.get("alt", ""),
                "width": img.get("width", ""),
                "height": img.get("height", ""),
            })
    return imgs


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


def _documents(soup, base_url):
    docs = []
    exts = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
            ".csv", ".txt", ".zip")
    for a in soup.find_all("a"):
        href = a.get("href")
        if href and href.lower().endswith(exts):
            docs.append(urljoin(base_url, href))
    return sorted(set(docs))


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
                results.append(urljoin(base_url, val) if attr in ("href", "src") else val)
        else:
            results.append(el.get_text(" ", strip=True))
    return [r for r in results if r]
