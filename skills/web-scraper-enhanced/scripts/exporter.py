"""导出层：把抓取/抽取结果转为 Markdown / JSON / CSV。"""
from __future__ import annotations

import csv
import json
from typing import Any


def to_json(data: Any, indent: int = 2) -> str:
    return json.dumps(data, ensure_ascii=False, indent=indent)


def to_markdown(data: Any) -> str:
    """支持单页 dict 或 crawl 返回的 {pages:[...], stats:{}}。"""
    if isinstance(data, dict) and "pages" in data:
        lines = ["# 站点抓取结果", ""]
        stats = data.get("stats", {})
        lines.append(f"> 起点：{stats.get('start_url','')} ｜ "
                     f"抓取 {stats.get('pages_fetched',0)} 页 ｜ "
                     f"耗时 {stats.get('elapsed_sec',0)}s")
        lines.append("")
        for p in data["pages"]:
            lines += _page_md(p)
        return "\n".join(lines)
    if isinstance(data, dict):
        return "\n".join(_page_md(data))
    return str(data)


def _page_md(p: dict) -> list[str]:
    lines = [f"## {p.get('url','')}", ""]
    if not p.get("ok", True):
        lines.append(f"- ⚠️ 抓取失败：{p.get('error','')}")
        return lines + [""]
    md = p.get("metadata", {})
    if md.get("title"):
        lines.append(f"- 标题：{md['title']}")
    if md.get("description"):
        lines.append(f"- 描述：{md['description']}")
    if p.get("text"):
        lines.append("")
        lines.append("### 正文")
        lines.append(p["text"][:4000])
    if p.get("links"):
        lines += ["", f"### 链接（{len(p['links'])}）"]
        for l in p["links"][:50]:
            lines.append(f"- {l}")
    if p.get("images"):
        lines += ["", f"### 图片（{len(p['images'])}）"]
        for im in p["images"][:50]:
            lines.append(f"- {im.get('url','')}  _alt: {im.get('alt','')}_")
    if p.get("tables"):
        lines += ["", f"### 表格（{len(p['tables'])}）"]
        for t in p["tables"][:10]:
            for row in t["rows"][:10]:
                lines.append("| " + " | ".join(row) + " |")
            lines.append("")
    if p.get("documents"):
        lines += ["", f"### 文档（{len(p['documents'])}）"]
        for d in p["documents"]:
            lines.append(f"- {d}")
    if p.get("custom"):
        lines += ["", "### 自定义选择器结果"]
        for c in p["custom"][:100]:
            lines.append(f"- {c}")
    return lines + [""]


def to_csv(data: Any) -> str:
    """把多页结果拍平为 URL + 模式字段的 CSV（便于表格软件/分析）。"""
    rows = []
    pages = data.get("pages", [data]) if isinstance(data, dict) else [data]
    for p in pages:
        if not isinstance(p, dict):
            continue
        base = {"url": p.get("url", ""), "ok": p.get("ok", True)}
        for key in ("links", "images", "tables", "documents", "custom"):
            vals = p.get(key)
            if isinstance(vals, list):
                if vals and isinstance(vals[0], dict):
                    base[key] = " | ".join(str(v.get("url", v)) for v in vals)
                else:
                    base[key] = " | ".join(str(v) for v in vals)
        rows.append(base)
    if not rows:
        return ""
    fieldnames = sorted({k for r in rows for k in r})
    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()
