# 工作流详解与命令速查

本 skill 把 Agent 变成「网站资源抓取专家」，闭环为 **fetch（单页）/ crawl（整站）** 两类操作，
所有请求都经过 SSRF 防护、robots 遵守与速率限制。

## 一、单页抓取 fetch

```
fetch --url <URL> [--type MODE] [--select SEL] [--render] [--format FMT] [--out PATH] [--config CFG]
```

| 参数 | 说明 |
| --- | --- |
| `--url` | 目标页面 URL（必填） |
| `--type` | `all`(默认) / `text` / `links` / `images` / `tables` / `metadata` / `assets` / `custom` |
| `--select` | 仅 `custom` 模式使用，CSS 选择器；`selector::attr` 抽取属性 |
| `--render` | 可选，启用 Playwright 执行 JS 后抓取（需安装浏览器二进制） |
| `--format` | `json`(默认) / `md` / `csv` |
| `--out` | 输出文件路径，省略则打印到 stdout |
| `--config` | YAML 配置（超时/延迟/UA/robots 等） |

## 二、整站爬取 crawl

```
crawl --url <URL> [--max-pages N] [--max-depth D] [--cross-domain] [--type MODE] [--format FMT] [--out PATH]
```

- `--max-pages`：最多抓取页数（默认 20）
- `--max-depth`：BFS 最大深度（默认 2）
- `--cross-domain`：默认仅同域；加此参数允许跨域链接

## 三、增强能力对照

| 能力 | 实现 | 默认 |
| --- | --- | --- |
| SSRF 防护 | 请求前 + 重定向链后双重校验私有/环回/链路本地/云元数据 | 开启 |
| robots 遵守 | 自动读取 robots.txt 的 Disallow 与 Crawl-delay | 开启 |
| 礼貌抓取 | 可配延迟、超时、重试（指数退避）、自定义 UA | 开启 |
| 智能正文 | trafilatura（若装）否则 bs4 启发式 | 自适应 |
| 指定内容 | CSS 选择器 + 属性抽取 | 按需 |
| 动态渲染 | Playwright 渲染后抓取 | 可选关闭 |
| 多格式导出 | json / markdown / csv | 支持 |

## 四、Agent 调用建议

1. 用户给单个 URL 且要"全部内容" → `fetch --type all --format md`
2. 用户要"某栏目/某区块" → `fetch --type custom --select "选择器::href"`
3. 用户要"整站归档/全站链接" → `crawl --max-pages N --format json`
4. 目标站是 SPA/需登录态渲染 → 加 `--render`（并确认已装浏览器）
5. 大规模抓取前务必用 config 调大 `delay`、确认 `obey_robots: true`
