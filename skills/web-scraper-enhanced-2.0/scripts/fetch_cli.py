#!/usr/bin/env python3
"""增强版网站资源抓取 2.0 —— 主编排器。

子命令：
  fetch    抓取单个页面，按模式/选择器抽取指定或全部内容
  crawl    广度优先爬取站点，收集所有页面与资源（可顺带批量下图）
  images   页面图片专项：全源发现 → AI 限量 → 下载落盘 → 报告

2.0 增强：真实浏览器指纹反爬 · 被拦自动升级 Playwright 隐身渲染 ·
          懒加载自动滚动 · 12 类图片来源 · 图片数量 AI 可控（--max-images，0=全部）

示例：
  # 抓取单页正文+链接，输出 Markdown
  python3 fetch_cli.py fetch --url https://example.com --type all --format md

  # 精准抽取：文章内所有外链 href
  python3 fetch_cli.py fetch --url https://news.site --type custom \
      --select "article a::href" --format json

  # 爬取整站前 30 页、深度 3，存为 JSON
  python3 fetch_cli.py crawl --url https://example.com --max-pages 30 \
      --max-depth 3 --format json --out site.json

  # 被反爬拦截的站点：强制浏览器渲染
  python3 fetch_cli.py fetch --url https://spa.app --browser --type text

  # ★ 图片专项：AI 自行决定抓 10 张，下载到 ./imgs
  python3 fetch_cli.py images --url https://example.com/gallery \
      --out-dir ./imgs --max-images 10

  # 页面全部图片（--max-images 0 或不传）
  python3 fetch_cli.py images --url https://example.com/gallery --out-dir ./imgs
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
EXTRACT_MODES = ["all", "text", "links", "images", "tables", "metadata",
                 "assets", "custom"]


# ---------------------------------------------------------------- 配置
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


def merge_cfg(cfg: dict, args) -> dict:
    """把命令行参数合并进 fetcher 配置（命令行优先）。"""
    fcfg = dict(cfg.get("fetcher", cfg))
    if getattr(args, "timeout", None):
        fcfg["timeout"] = args.timeout
    if getattr(args, "delay", None) is not None:
        fcfg["delay"] = args.delay
    if getattr(args, "user_agent", None):
        fcfg["user_agent"] = args.user_agent
        fcfg["rotate_ua"] = False
    if getattr(args, "proxy", None):
        fcfg["proxy"] = args.proxy
    if getattr(args, "no_robots", False):
        fcfg["obey_robots"] = False
    if getattr(args, "browser", False):
        fcfg["browser_fallback"] = "always"
    if getattr(args, "cookies", None):
        fcfg["cookies"] = dict(
            kv.split("=", 1) for kv in args.cookies if "=" in kv)
    if getattr(args, "headers", None):
        fcfg["extra_headers"] = dict(
            kv.split(":", 1) for kv in args.headers if ":" in kv)
    return fcfg


def render_options_of(args) -> dict:
    return {
        "scroll": not getattr(args, "no_scroll", False),
        "timeout": getattr(args, "timeout", None) or 30,
        "screenshot_path": getattr(args, "screenshot", None),
    }


def stderr(msg: str):
    print(msg, file=sys.stderr, flush=True)


def _write_or_print(content: str, out: str | None, fmt: str):
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            f.write(content)
        stderr(f"[ok] 已写入 {fmt.upper()} 结果 -> {out}")
    else:
        print(content)


# ---------------------------------------------------------------- fetch
def cmd_fetch(args):
    fcfg = merge_cfg(load_config(args.config), args)
    fetcher = Fetcher(fcfg)
    res = fetcher.fetch_smart(args.url, render_options=render_options_of(args),
                              progress=stderr)
    if res.ok:
        data = extract(res.html, res.final_url, mode=args.type,
                       selector=args.select,
                       options={"scan_inline_css": args.scan_css})
        data["url"] = res.final_url
        data["status"] = res.status
        data["ok"] = True
        data["used_browser"] = res.used_browser
    else:
        data = {"url": args.url, "ok": False, "error": res.error,
                "status": res.status, "blocked": res.blocked}
    _write_or_print(FORMATS[args.format](data), args.out, args.format)


# ---------------------------------------------------------------- crawl
def cmd_crawl(args):
    cfg = load_config(args.config)
    fcfg = merge_cfg(cfg, args)
    result = crawl(
        args.url, config=fcfg, max_pages=args.max_pages,
        max_depth=args.max_depth, same_domain=not args.cross_domain,
        mode=args.type, selector=args.select,
        save_images=args.save_images, out_dir=args.out_dir,
        max_images=args.max_images,
        img_options={"scan_inline_css": args.scan_css},
        render_options=render_options_of(args), progress=stderr,
    )
    payload = result.__dict__
    _write_or_print(FORMATS[args.format](payload), args.out, args.format)
    if result.image_report:
        stderr(f"[ok] 整站图片：成功 {result.image_report['downloaded']} 张 "
               f"-> {result.image_report['out_dir']}")


# ---------------------------------------------------------------- images
def cmd_images(args):
    """图片专项：全源发现 → 过滤 → AI 限量 → 下载 → 报告。"""
    from images import ImageDownloader, filter_images

    fcfg = merge_cfg(load_config(args.config), args)
    fetcher = Fetcher(fcfg)

    # 1) 抓页面：静态优先；被拦、或静态 0 图（JS 渲染/懒加载）时自动升级浏览器渲染
    stderr(f"[images] 抓取页面：{args.url}")
    res = fetcher.fetch_smart(args.url, render_options=render_options_of(args),
                              progress=stderr)
    if res.ok and fetcher.browser_fallback != "never":
        probe = extract(res.html, res.final_url, mode="images",
                        options={"scan_inline_css": args.scan_css})
        if not probe.get("images"):
            stderr("[images] 静态抓取未发现图片（JS 渲染/懒加载页面），"
                   "自动升级浏览器渲染…")
            res = fetcher._fetch_via_browser(
                args.url, render_options_of(args), stderr)
    if not res.ok:
        report = {"page_url": args.url, "out_dir": args.out_dir, "found": 0,
                  "downloaded": 0, "skipped": 0, "failed": 0,
                  "error": res.error, "blocked": res.blocked, "images": []}
        _write_or_print(FORMATS[args.format](report), args.out, args.format)
        sys.exit(2)

    # 2) 全源图片发现
    data = extract(res.html, res.final_url, mode="images",
                   options={"scan_inline_css": args.scan_css,
                            "keep_all_candidates": args.keep_all_candidates,
                            "include_icons": args.include_icons})
    found = data.get("images", [])
    stderr(f"[images] 发现 {len(found)} 个图片来源"
           f"{'（渲染层）' if res.used_browser else ''}")

    # 3) 过滤 + 限量（AI 通过 --max-images 控制；0 = 全部）
    items = filter_images(
        found, max_images=args.max_images,
        min_width=args.min_width, min_height=args.min_height,
        formats=args.formats.split(",") if args.formats else None,
        skip_icons=not args.include_icons)
    limit_desc = "全部" if not args.max_images else f"前 {args.max_images} 张"
    stderr(f"[images] 过滤后待下载：{len(items)} 张（限量：{limit_desc}）")

    # 4) 下载
    out_dir = args.out_dir or os.path.join(
        "images", (args.url.split("//")[-1].split("/")[0] or "site")
        .replace(":", "_"))
    dl = ImageDownloader(
        out_dir, referer=res.final_url,
        user_agent=fetcher._current_ua, timeout=int(fetcher.timeout),
        workers=args.workers, verify_ssl=fetcher.verify_ssl,
        extra_headers=fetcher.extra_headers, progress=stderr)
    report = dl.download_all(items)
    report.page_url = args.url

    # 5) 报告落盘 + 输出
    report_path = args.report or os.path.join(out_dir, "report.json")
    os.makedirs(out_dir, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
    stderr(f"[ok] 图片报告 -> {report_path}")
    stderr(f"[ok] 完成：成功 {report.downloaded} ｜ 跳过 {report.skipped} ｜ "
           f"失败 {report.failed}")
    _write_or_print(FORMATS[args.format](report.to_dict()), args.out,
                    args.format)
    if report.downloaded == 0:
        sys.exit(3)


# ---------------------------------------------------------------- 参数
def _add_common(p, with_image_opts=False):
    p.add_argument("--url", required=True)
    p.add_argument("--format", default="json", choices=list(FORMATS))
    p.add_argument("--out", help="结果输出文件路径（默认打印 stdout）")
    p.add_argument("--config", help="YAML 配置文件路径")
    p.add_argument("--timeout", type=int, help="请求超时（秒）")
    p.add_argument("--delay", type=float, help="请求间隔（秒）")
    p.add_argument("--user-agent", help="指定 UA（指定后关闭 UA 轮换）")
    p.add_argument("--proxy", help="代理，如 http://127.0.0.1:7890")
    p.add_argument("--cookie", action="append", dest="cookies",
                   help='Cookie "k=v"，可多次')
    p.add_argument("--header", action="append", dest="headers",
                   help='自定义请求头 "K: V"，可多次')
    p.add_argument("--no-robots", action="store_true",
                   help="不遵守 robots.txt（默认遵守）")
    p.add_argument("--browser", action="store_true",
                   help="强制使用 Playwright 隐身渲染")
    p.add_argument("--no-scroll", action="store_true",
                   help="渲染时不自动滚动（默认滚动触发懒加载）")
    p.add_argument("--screenshot", help="渲染时保存整页截图路径")
    p.add_argument("--scan-css", action="store_true",
                   help="扫描 <style> 块内背景图")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="增强版网站资源抓取 2.0（反爬对抗 · 图片专项 · AI 可控数量）")
    sub = p.add_subparsers(dest="cmd", required=True)

    pf = sub.add_parser("fetch", help="抓取单个页面")
    _add_common(pf)
    pf.add_argument("--type", default="all", choices=EXTRACT_MODES)
    pf.add_argument("--select", help="custom 模式的选择器，如 'article a::href'")
    pf.set_defaults(func=cmd_fetch)

    pc = sub.add_parser("crawl", help="爬取整站")
    _add_common(pc)
    pc.add_argument("--max-pages", type=int, default=20)
    pc.add_argument("--max-depth", type=int, default=2)
    pc.add_argument("--cross-domain", action="store_true", help="允许跨域链接")
    pc.add_argument("--type", default="all", choices=EXTRACT_MODES)
    pc.add_argument("--select", help="custom 模式的选择器")
    pc.add_argument("--save-images", action="store_true",
                    help="爬取同时把全站图片下载到 --out-dir")
    pc.add_argument("--out-dir", help="图片输出目录")
    pc.add_argument("--max-images", type=int, default=0,
                    help="整站最多下载多少张图片（0=全部）")
    pc.set_defaults(func=cmd_crawl)

    pi = sub.add_parser("images", help="页面图片专项：发现→限量→下载→报告")
    _add_common(pi)
    pi.add_argument("--out-dir", default=None,
                    help="图片输出目录（默认 images/<域名>）")
    pi.add_argument("--max-images", type=int, default=0,
                    help="最多抓取多少张图片：0=全部，N=前 N 张（AI 可自行决定）")
    pi.add_argument("--min-width", type=int, default=0, help="最小宽度 px")
    pi.add_argument("--min-height", type=int, default=0, help="最小高度 px")
    pi.add_argument("--formats",
                    help="限定格式，逗号分隔，如 jpg,png,webp")
    pi.add_argument("--include-icons", action="store_true",
                    help="收录图标/favicon（默认过滤）")
    pi.add_argument("--keep-all-candidates", action="store_true",
                    help="srcset 全部候选都抓（默认只取最大图）")
    pi.add_argument("--workers", type=int, default=4, help="并发下载数")
    pi.add_argument("--report", help="图片报告 JSON 路径")
    pi.set_defaults(func=cmd_images)
    return p


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
