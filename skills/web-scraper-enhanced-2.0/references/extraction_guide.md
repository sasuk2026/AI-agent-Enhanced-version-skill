# 抽取指南：选择器语法 · 图片来源 · 输出字段（2.0）

## 一、CSS 选择器语法（--type custom）

```
--select "<css-selector>"            # 抽元素文本
--select "<css-selector>::attr"      # 抽元素属性（href/src/data-*/content…）
--select "img::src"                  # 例：所有 img 的 src
--select "a::href"                   # 例：所有链接
--select "span.price::text"          # ::text 等价于取文本（无 attr 时默认行为）
--select "div.card h2::text"         # 组合选择器
```

属性为 `href/src` 时自动补全为绝对 URL；其他属性原样返回。
空结果会被过滤；结果最多保留前 100 条（Markdown 导出时）。

## 二、图片 12 类来源（2.0 全量发现）

| # | 来源 | HTML 形态 | source 标记 |
| --- | --- | --- | --- |
| 1 | img 常规 | `<img src="a.jpg">` | img-src |
| 2 | img srcset | `<img srcset="a.jpg 1x, b.jpg 2x">` | img-srcset |
| 3 | img 懒加载 | `<img data-src="a.jpg">` 等 10 种属性 | img-src |
| 4 | picture | `<picture><source srcset="a.webp">` | picture-source |
| 5 | video 封面 | `<video poster="a.jpg">` | video-poster |
| 6 | 内联背景图 | `<div style="background:url(a.jpg)">` | inline-style-bg |
| 7 | style 块背景图 | `<style>…url(a.jpg)…</style>`（需 --scan-css） | style-block-bg |
| 8 | 社交meta | `<meta property="og:image">` | meta-og:image |
| 9 | a 直链图片 | `<a href="a.jpg">` | a-href-image |
| 10 | link 图标 | `<link rel="image_src">` | link-image_src |
| 11 | svg 内嵌图 | `<svg><image href="a.png">` | svg-image |
| 12 | 表单/插件图 | `<input type=image>` `<object data>` `<embed src>` | input-image 等 |

默认行为：
- srcset **只取最大候选**；`--keep-all-candidates` 时全部候选入列
- favicon/apple-touch-icon 默认过滤；`--include-icons` 收录
- 33×33 以下的声明尺寸视为图标/追踪像素，默认过滤
- data: URI 保留在列表但默认不下载（`--include-icons` 不影响它，见 filter_images）
- 全部结果按 URL 去重，保持页面出现顺序

## 三、输出字段

### fetch --type images
```json
{
  "url": "https://site/page",
  "images": [
    {"url": "https://site/a.jpg", "alt": "描述", "width": "800",
     "height": "600", "source": "img-srcset", "format": "jpg",
     "srcset": ["https://site/a.jpg", "https://site/b.jpg"]}
  ]
}
```

### images 子命令 → report.json
```json
{
  "page_url": "https://site/gallery",
  "out_dir": "./imgs",
  "found": 42, "downloaded": 10, "skipped": 0, "failed": 0,
  "images": [
    {"url": "https://site/a.jpg", "file": "./imgs/001_a.jpg",
     "bytes": 123456, "format": "jpg", "width": 1920, "height": 1080,
     "sha1": "...", "source": "img-srcset", "alt": "", "status": "ok"}
  ]
}
```

`status` 取值：`ok`（已下载）/ `skipped`（内容重复/已存在/超限/data URI）/ `failed`（HTTP 错误、非图片内容、网络失败，附 error）。

### fetch --type all
`metadata`（title/description/keywords/author/og:*/canonical/lang）·
`text`（正文）· `links`（去重绝对 URL）· `images`（见上）·
`tables`（[{index, rows:[[…]]}]）· `stylesheets`/`scripts`/`documents`。

### crawl
`{pages: [...], stats: {start_url, pages_fetched, unique_discovered, max_depth, images_found, elapsed_sec}, image_report?: {...}}`

## 四、安全说明

- 所有 URL 请求前过 SSRF 校验；重定向链逐跳复核
- robots.txt 默认遵守（Disallow + Crawl-delay；crawl-delay 大于设定 delay 时自动采用更大值）
- `data:`/`javascript:`/`mailto:` 等非资源 URL 不会发起请求
- 图片下载校验 Content-Type 与魔数，防 HTML 错误页伪装成图片落盘
