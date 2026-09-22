---
name: web-scraper-enhanced
description: 增强版网站资源抓取 Agent 工具。当用户需要抓取指定网站的全部或指定内容（正文/链接/图片/表格/元数据/静态资源），爬取整站，或按 CSS 选择器精准抽取内容时使用。内置 SSRF 防护、robots.txt 遵守、礼貌速率限制、智能正文提取、可选动态渲染与多格式导出。触发词：抓取、爬取、爬站、采集、抓网页、提取网页内容、整站抓取、scrape、crawl、fetch page、网页资源。
---

# 增强版网站资源抓取（web-scraper-enhanced）

把 Agent 变成「网站资源抓取专家」：抓取用户指定网站的全部或指定内容，并安全、礼貌、可复现地交付结构化结果。

## 何时使用

- 用户要「抓这个网站 / 这个页面的内容」→ 用 `fetch`
- 用户要「整站 / 全站链接 / 站点归档」→ 用 `crawl`
- 用户要「只要某区块 / 某类资源（如所有图片链接、价格表）」→ `fetch --type custom --select`
- 目标站是 SPA / 内容靠 JS 渲染 → 加 `--render`

## 增强能力（区别于普通爬虫）

| 能力 | 说明 | 默认 |
| --- | --- | --- |
| **SSRF 防护** | 请求前 + 重定向链后双重校验，拦截私有/环回/链路本地/云元数据地址 | 开启 |
| **robots 遵守** | 自动读 robots.txt 的 Disallow 与 Crawl-delay，违规则跳过 | 开启 |
| **礼貌抓取** | 可配延迟、超时、重试（指数退避）、自定义 UA | 开启 |
| **智能正文** | trafilatura（若装）否则 bs4 启发式抽取正文/表格 | 自适应 |
| **指定内容** | CSS 选择器 + 属性抽取（`selector::attr`） | 按需 |
| **动态渲染** | Playwright 渲染后抓取（可选，需浏览器二进制） | 关闭 |
| **多格式导出** | `json` / `markdown` / `csv` | 支持 |

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

# 4) JS 渲染页面（可选）
python3 scripts/fetch_cli.py fetch --url <URL> --render --type text

# 5) 用配置控制礼貌策略
python3 scripts/fetch_cli.py crawl --url <URL> --config assets/config_template.yaml
```

## 抽取模式（--type）

`all`(默认) · `text`(正文) · `links`(链接) · `images`(图片) · `tables`(表格) ·
`metadata`(元信息) · `assets`(CSS/JS/文档) · `custom`(选择器)

## 使用到的权限

本 skill 在运行时会访问并使用以下权限/资源：

- **出站网络访问**：向目标站点发起 HTTP 请求（requests / GM_xmlhttpRequest / fetch），
  读取页面、robots.txt，跟进重定向。**只对用户明确指定的 URL 发起请求**。
- **动态渲染（可选）**：`--render` 时会用 Playwright 启动真实浏览器内核执行页面 JS，需浏览器二进制；默认关闭。
- **本地文件读写**：`--out` 导出 JSON / Markdown / CSV 抓取结果到指定路径。
- **Python 运行时与依赖包**：需 `requests`、`beautifulsoup4`、`lxml`；增强（缺失则降级）`trafilatura`、`playwright`、`pyyaml`、`markdownify`。
- **不涉及**：不访问本机文件系统上非指定的文件，不读取目标站登录态/凭证，不主动收集个人信息。

## 安全要点（务必遵守）

- **SSRF 是第一道闸门**：任何解析到内网/云元数据（如 `169.254.169.254`）的 URL 都会被拦，含重定向跳转后的目标。
- **遵守 robots.txt**：被禁止时 skill 会跳过并说明，不要强行绕过。
- **`allow_private: true` 仅在本地 mock/内网自检时开启**，日常勿开。
- **`--render` 会真实执行页面 JS**，仅对可信站点使用。

## 依赖与降级

- 必需：`requests`、`beautifulsoup4`、`lxml`（已预装）
- 增强（缺失则降级，不影响主流程）：`trafilatura`（正文质量↑）、`playwright`（动态渲染）、`pyyaml`（读 --config）、`markdownify`
- 降级行为：缺 trafilatura → bs4 启发式正文；缺 playwright → `--render` 给出安装提示；缺 pyyaml → 用默认配置

## 参考文档

- `references/workflows.md`：工作流与命令速查、能力对照
- `references/extraction_guide.md`：选择器语法、模式字段、安全说明
- `assets/config_template.yaml`：可调参数模板
