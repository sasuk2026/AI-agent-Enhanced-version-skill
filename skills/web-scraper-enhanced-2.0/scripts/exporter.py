"""导出层 2.0：JSON / Markdown / CSV，新增图片报告导出。"""
from __future__ import annotations

import csv
import io
import json
from typing import Any


def to_json(data: Any, indent: int = 2) -> str:
    return json.dumps(data, ensure_ascii=False, indent=indent)


def to_markdown(data: Any) -> str:
    """支持单页 dict、crawl 的 {pages,stats}、或图片报告 dict。"""
    if isinstance(data, dict) and "images" in data and "found" in data:
        return _image_report_md(data)
    if isinstance(data, dict) and "pages" in data:
        lines = ["# 站点抓取结果", ""]
        stats = data.get("stats", {})
        lines.append(f"> 起点：{stats.get('start_url','')} ｜ "
                     f"抓取 {stats.get('pages_fetched',0)} 页 ｜ "
                     f"发现图片 {stats.get('images_found',0)} 张 ｜ "
                     f"耗时 {stats.get('elapsed_sec',0)}s")
        lines.append("")
        for p in data["pages"]:
            lines += _page_md(p)
        if data.get("image_report"):
            lines += ["", "---", ""] + _image_report_md(data["image_report"]).split("\n")
        return "\n".join(lines)
    if isinstance(data, dict):
        return "\n".join(_page_md(data))
    return str(data)


def _image_report_md(rep: dict) -> list[str]:
    lines = ["# 图片抓取报告", "",
             f"- 页面：{rep.get('page_url','')}",
             f"- 输出目录：{rep.get('out_dir','')}",
             f"- 发现 {rep.get('found',0)} 张 ｜ 成功 {rep.get('downloaded',0)} ｜ "
             f"跳过 {rep.get('skipped',0)} ｜ 失败 {rep.get('failed',0)}",
             "", "| # | 文件 | 尺寸 | 大小 | 来源 | URL |",
             "| --- | --- | --- | --- | --- | --- |"]
    import os
    for i, im in enumerate(rep.get("images", []), 1):
        fn = os.path.basename(im.get("file", "")) or "-"
        size = f"{im.get('bytes',0) // 1024}KB" if im.get("bytes") else "-"
        dim = f"{im.get('width',0)}x{im.get('height',0)}" if im.get("width") else "-"
        lines.append(f"| {i} | {fn} | {dim} | {size} | "
                     f"{im.get('source','')} | {im.get('url','')} |")
    return lines + [""]


def _page_md(p: dict) -> list[str]:
    lines = [f"## {p.get('url','')}", ""]
    if not p.get("ok", True):
        note = f"抓取失败：{p.get('error','')}"
        if p.get("blocked"):
            note += "（被反爬拦截）"
        lines.append(f"- ⚠️ {note}")
        return lines + [""]
    md = p.get("metadata", {})
    if md.get("title"):
        lines.append(f"- 标题：{md['title']}")
    if md.get("description"):
        lines.append(f"- 描述：{md['description']}")
    if p.get("text"):
        lines += ["", "### 正文", p["text"][:4000]]
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
    if isinstance(data, dict) and "images" in data and "found" in data:
        rows = [{"url": im.get("url", ""), "file": im.get("file", ""),
                 "bytes": im.get("bytes", 0), "width": im.get("width", 0),
                 "height": im.get("height", 0), "format": im.get("format", ""),
                 "sha1": im.get("sha1", ""), "source": im.get("source", ""),
                 "status": im.get("status", "")}
                for im in data.get("images", [])]
        if not rows:
            return ""
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
        return buf.getvalue()

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
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()
