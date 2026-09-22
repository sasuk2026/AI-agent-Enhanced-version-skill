#!/usr/bin/env python3
"""增强版网站资源抓取 —— 主编排器。

子命令：
  fetch   抓取单个页面，按模式/选择器抽取指定或全部内容
  crawl   广度优先爬取站点，收集所有页面与资源

增强能力：SSRF 防护 · robots 遵守 · 速率限制 · 智能正文提取 ·
         多模式/选择器抽取 · 动态渲染(可选) · 多格式导出(json/md/csv)

示例：
  # 抓取单页正文+链接，输出 Markdown
  python3 fetch_cli.py fetch --url https://example.com --type all --format md

  # 只抓某区块（CSS 选择器 + 抽 href 属性）
  python3 fetch_cli.py fetch --url https://news.site --type custom \
      --select "article a::href" --format json

  # 爬取整站前 30 页、深度 3，存为 JSON
  python3 fetch_cli.py crawl --url https://example.com --max-pages 30 \
      --max-depth 3 --format json --out site.json

  # 需要 JS 渲染的页面（可选，需 pip install playwright + 浏览器）
  python3 fetch_cli.py fetch --url https://spa.app --render --type text
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# 保证脚本目录可 import 兄弟模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from security import check_url  # noqa: E402
from fetcher import Fetcher  # noqa: E402
from extractor import extract  # noqa: E402
from crawler import crawl  # noqa: E402
from exporter import to_json, to_markdown, to_csv  # noqa: E402

FORMATS = {"json": to_json, "md": to_markdown, "csv": to_csv}


def load_config(path: str | None) -> dict:
    if not path:
        return {}
    try:
        import yaml  # noqa
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(f"[warn] 配置加载失败，使用默认值：{e}", file=sys.stderr)
        return {}


def _render_html(url: str, timeout: int = 20) -> str:
    """可选动态渲染：用 Playwright 执行 JS 后取页面 HTML。"""
    ok, reason = check_url(url)
    if not ok:
        raise RuntimeError(f"SSRF 防护拦截：{reason}")
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        raise RuntimeError("未安装 playwright，请先 `pip install playwright` "
                           "并执行 `playwright install chromium`")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(url, timeout=timeout, wait_until="networkidle")
        html = page.content()
        browser.close()
    return html


def _write_or_print(content: str, out: str | None, fmt: str):
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[ok] 已写入 {fmt.upper()} 结果 -> {out}", file=sys.stderr)
    else:
        print(content)


def cmd_fetch(args):
    cfg = load_config(args.config)
    if args.render:
        try:
            html = _render_html(args.url)
            data = extract(html, args.url, mode=args.type, selector=args.select)
            data["url"] = args.url
            data["ok"] = True
            data["render"] = True
        except RuntimeError as e:
            data = {"url": args.url, "ok": False, "error": str(e)}
    else:
        fetcher = Fetcher(cfg.get("fetcher", cfg))
        res = fetcher.fetch(args.url)
        if res.ok:
            data = extract(res.html, res.final_url, mode=args.type,
                           selector=args.select)
            data["url"] = res.final_url
            data["status"] = res.status
            data["ok"] = True
        else:
            data = {"url": args.url, "ok": False, "error": res.error,
                    "status": res.status}

    content = FORMATS[args.format](data)
    _write_or_print(content, args.out, args.format)


def cmd_crawl(args):
    cfg = load_config(args.config)
    result = crawl(
        args.url, config=cfg.get("fetcher", cfg), max_pages=args.max_pages,
        max_depth=args.max_depth, same_domain=not args.cross_domain,
        mode=args.type, selector=args.select,
    )
    content = FORMATS[args.format](result.__dict__)
    _write_or_print(content, args.out, args.format)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="增强版网站资源抓取 Agent 工具")
    sub = p.add_subparsers(dest="cmd", required=True)

    pf = sub.add_parser("fetch", help="抓取单个页面")
    pf.add_argument("--url", required=True)
    pf.add_argument("--type", default="all",
                    choices=["all", "text", "links", "images", "tables",
                             "metadata", "assets", "custom"])
    pf.add_argument("--select", help="custom 模式的选择器，如 'article a::href'")
    pf.add_argument("--render", action="store_true", help="启用 Playwright 动态渲染")
    pf.add_argument("--format", default="json", choices=list(FORMATS))
    pf.add_argument("--out", help="输出文件路径（默认打印到 stdout）")
    pf.add_argument("--config", help="YAML 配置文件路径")
    pf.set_defaults(func=cmd_fetch)

    pc = sub.add_parser("crawl", help="爬取整站")
    pc.add_argument("--url", required=True)
    pc.add_argument("--max-pages", type=int, default=20)
    pc.add_argument("--max-depth", type=int, default=2)
    pc.add_argument("--cross-domain", action="store_true", help="允许跨域链接")
    pc.add_argument("--type", default="all",
                    choices=["all", "text", "links", "images", "tables",
                             "metadata", "assets", "custom"])
    pc.add_argument("--select", help="custom 模式的选择器")
    pc.add_argument("--format", default="json", choices=list(FORMATS))
    pc.add_argument("--out", help="输出文件路径（默认打印到 stdout）")
    pc.add_argument("--config", help="YAML 配置文件路径")
    pc.set_defaults(func=cmd_crawl)
    return p


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
