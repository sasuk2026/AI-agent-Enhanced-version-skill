---
name: web-scraper-enhanced-2.0
description: 增强版网站资源抓取 Agent 工具（2.0）。当用户需要抓取指定网站的全部或指定内容（正文/链接/图片/表格/元数据/静态资源），爬取整站，下载页面图片（数量可控），或按 CSS 选择器精准抽取内容时使用。2.0 新增：真实浏览器指纹反爬（UA 轮换 + 完整请求头）、被拦截自动升级 Playwright 隐身渲染、懒加载自动滚动、12 类图片来源全量发现、图片批量下载（AI 通过 --max-images 自行决定抓取数量，0=全部）。触发词：抓取、爬取、爬站、采集、抓网页、提取网页内容、整站抓取、抓图片、下载图片、图片批量下载、页面所有图片、scrape、crawl、download images。
---

# 增强版网站资源抓取 2.0（web-scraper-enhanced-2.0）

把 Agent 变成「网站资源抓取专家」：抓取用户指定网站的全部或指定内容，
安全、礼貌、可复现地交付结构化结果；图片可全量发现并批量下载，**数量由 AI 自行决定**。

## 何时使用

- 用户要「抓这个网站 / 这个页面的内容」→ 用 `fetch`
- 用户要「整站 / 全站链接 / 站点归档」→ 用 `crawl`
- 用户要「这个页面的图片都要 / 下载前 N 张图」→ 用 `images`（**数量 AI 可控**）
- 用户要「只要某区块 / 某类资源」→ `fetch --type custom --select`
- 目标站是 SPA / 内容靠 JS 渲染 / 懒加载 → `--render` 或默认自动升级
- 目标站有反爬（403/5 秒盾/JS 挑战）→ 默认 auto 策略自动切隐身浏览器，无需额外操作

## 2.0 增强能力（相对 1.0）

| 能力 | 说明 | 默认 |
| --- | --- | --- |
| **反爬对抗** | 真实 UA 池轮换 + 浏览器级请求头（sec-ch-ua/Sec-Fetch-*/Accept-Language）+ 会话级 Cookie | 开启 |
| **封锁自动升级** | 静态请求被拦（403/429/503/挑战页特征）→ 自动切 Playwright 隐身渲染 | auto |
| **隐身渲染** | 真实 Chromium 内核 + Stealth 补丁（webdriver/chrome/plugins/WebGL 指纹抹除） | 关闭（按需） |
| **懒加载支持** | 渲染时自动滚动页面触发懒加载图片/无限滚动 | 开启 |
| **图片全源发现** | 12 类来源：img src/srcset、picture、懒加载属性、video poster、内联/块级 CSS 背景图、og:image、a 直链、link icon、svg image、input/object/embed | 开启 |
| **图片批量下载** | 并发下载 + 重试 + 断点跳过 + URL/SHA1 双去重 + 尺寸/格式/体积过滤 | 开启 |
| **数量 AI 可控** | `--max-images N`：0=全部图片；N=前 N 张（保持页面顺序）。AI 按用户意图自行决定 | 0（全部） |
| SSRF 防护 | 请求前 + 重定向链后双重校验，拦截私有/环回/云元数据地址 | 开启 |
| robots 遵守 | 自动读 robots.txt 的 Disallow 与 Crawl-delay，违规则跳过 | 开启 |
| 礼貌抓取 | 可配延迟、超时、重试（指数退避）、自定义 UA、代理池 | 开启 |
| 智能正文 | trafilatura（若装）否则 bs4 启发式抽取正文/表格 | 自适应 |
| 指定内容 | CSS 选择器 + 属性抽取（`selector::attr`） | 按需 |
| 多格式导出 | `json` / `markdown` / `csv`；图片附带 report.json 报告 | 支持 |

## 工作流

编辑/调用 `scripts/fetch_cli.py`（脚本目录已加入 sys.path，可任意目录运行）：

```bash
# 1) 单页全量抽取 → Markdown
python3 scripts/fetch_cli.py fetch --url <URL> --type all --format md

# 2) 精准抽取：文章内所有外链 href
python3 scripts/fetch_cli.py fetch --url <URL> --type custom \
    --select "article a::href" --format json

# 3) 整站爬取（前 30 页、深度 3）→ JSON 文件
python3 scripts/fetch_cli.py crawl --url <URL> --max-pages 30 \
    --max-depth 3 --format json --out site.json

# 4) 被反爬拦截的站点：静态失败会自动升级；也可强制浏览器渲染
python3 scripts/fetch_cli.py fetch --url <URL> --browser --type text

# ★ 5) 图片专项：用户说「这页图片都要」→ 不传 --max-images（全部）
python3 scripts/fetch_cli.py images --url <URL> --out-dir ./imgs

# ★ 6) 图片专项：用户说「下载前 10 张就够」→ AI 自己决定 N
python3 scripts/fetch_cli.py images --url <URL> --out-dir ./imgs --max-images 10

# ★ 7) 图片专项：只要大尺寸 JPG/WebP，过滤图标
python3 scripts/fetch_cli.py images --url <URL> --out-dir ./imgs \
    --max-images 20 --min-width 400 --formats jpg,webp

# 8) 整站爬取顺带把全站图片下载下来（同样可限量）
python3 scripts/fetch_cli.py crawl --url <URL> --save-images \
    --out-dir ./site_imgs --max-images 50

# 9) 用配置控制礼貌/反爬策略
python3 scripts/fetch_cli.py crawl --url <URL> --config assets/config_template.yaml
```

## 抽取模式（--type）

`all`(默认) · `text`(正文) · `links`(链接) · `images`(图片) · `tables`(表格) ·
`metadata`(元信息) · `assets`(CSS/JS/文档) · `custom`(选择器)

## 图片抓取数量决策指南（AI 必读）

用户要图片时，**由 AI 根据用户意图决定 `--max-images`**：

| 用户说法 | 调用方式 |
| --- | --- |
| 「这个页面的图片都要 / 全部抓下来」 | `images --url <URL>`（`--max-images 0` 即全部） |
| 「抓 10 张 / 前 5 张 / 来 20 张图看看」 | `images --url <URL> --max-images 10` |
| 「随便抓几张 / 抓点图」 | AI 自行选个合理数量，如 `--max-images 5` |
| 「图片太多，挑大的下」 | 加 `--min-width 600 --min-height 400` |
| 「只要 JPG」 | 加 `--formats jpg` |
| 不确定时 | 默认全部（0），下载后报告里给出数量，用户不满意再限量重跑 |

其他图片参数：`--min-width/--min-height`（尺寸过滤）· `--formats`（格式过滤）·
`--include-icons`（连 favicon 都要）· `--keep-all-candidates`（srcset 全部候选）·
`--workers`（并发数）· `--scan-css`（连 `<style>` 块内背景图也扫）。

下载产物：`<out-dir>/001_xxx.jpg …`（按页面顺序编号）+ `<out-dir>/report.json`
（每张图的 URL/本地路径/字节数/宽高/格式/SHA1/来源/状态）。

## 反爬能力边界（如实说明）

| 反爬手段 | 2.0 能否直接跳过 |
| --- | --- |
| UA 黑名单 / 请求头指纹校验 | ✅ 真实 UA 池 + 完整浏览器头 |
| 基础 JS 挑战 / Cloudflare 5 秒盾 | ✅ Playwright 真实内核 + Stealth，多数可过 |
| 懒加载 / 无限滚动 | ✅ 渲染时自动滚动 |
| TLS/JA3 指纹 | ⚠️ 标准 requests 特征；如需可换 curl_cffi（见 references） |
| 频率限制 | ✅ 指数退避 + 代理池轮换（需配置 `proxies`） |
| 验证码 / 登录墙 / 企业级 WAF | ❌ 自动检测并如实报告，不盲目硬刚；需用户提供登录态 Cookie |

## 使用到的权限

本 skill 在运行时会访问并使用以下权限/资源：

- **出站网络访问**：向目标站点发起 HTTP 请求（requests / 浏览器内核），
  读取页面、robots.txt、图片资源，跟进重定向。**只对用户明确指定的 URL 发起请求**。
- **动态渲染（可选）**：默认 auto——静态被拦或页面无图时自动启用；也可 `--browser` 强制。
  用 Playwright 启动真实浏览器内核执行页面 JS。
- **本地文件读写**：`--out` 导出抓取结果；`--out-dir` 保存图片与 report.json。
- **Python 运行时与依赖包**：需 `requests`、`beautifulsoup4`、`lxml`；
  增强（缺失则降级）`trafilatura`、`playwright`、`pyyaml`、`pillow`。
- **不涉及**：不访问本机文件系统上非指定的文件，不主动收集个人信息，
  不读取用户浏览器登录态（用户主动 `--cookie` 传入的除外）。

## 安全要点（务必遵守）

- **SSRF 是第一道闸门**：任何解析到内网/云元数据（如 `169.254.169.254`）的 URL 都会被拦，含重定向跳转后的目标。
- **遵守 robots.txt**：被禁止时 skill 会跳过并说明，不要强行绕过（`--no-robots` 仅限用户明确要求已授权场景）。
- **`allow_private: true` 仅在本地 mock/内网自检时开启**，日常勿开。
- **`--render/--browser` 会真实执行页面 JS**，仅对可信站点使用。
- **合规使用**：仅供个人学习、研究或已获授权的抓取；不得用于绕过付费墙、大规模侵权转载、或对目标站造成压力（保持默认 `delay`）。

## 依赖与降级

- 必需：`requests`、`beautifulsoup4`、`lxml`
- 增强（缺失则降级，不影响主流程）：`playwright`（反爬升级/懒加载，缺失时静态抓了但遇挑战会报告）、
  `trafilatura`（正文质量↑）、`pyyaml`（读 --config）、`pillow`（图片宽高识别）
- 降级行为：缺 trafilatura → bs4 启发式正文；缺 playwright → 提示安装，挑战页如实报告；
  缺 pillow → 宽高记 0，下载照常

## 参考文档

- `references/workflows.md`：工作流与命令速查、能力对照
- `references/extraction_guide.md`：选择器语法、图片 12 类来源、模式字段、安全说明
- `references/antibot_guide.md`：反爬策略详解、封锁判定、代理/Cookie/TLS 进阶配置
- `assets/config_template.yaml`：可调参数模板
