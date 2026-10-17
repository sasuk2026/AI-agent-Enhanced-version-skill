# 反爬对抗指南（2.0）

## 一、三层防御体系

```
请求 → ① 静态层（requests + 真实浏览器指纹）
         └─ 被拦？→ ② 渲染层（Playwright + Chromium + Stealth）
                       └─ 仍被拦？→ ③ 如实报告（验证码/登录墙/WAF），不盲目硬刚
```

### ① 静态层（fetcher.py + antibot.py）

| 对抗点 | 实现 |
| --- | --- |
| UA 黑名单 | 10 个真实 UA 池轮换（Chrome/Edge/Firefox/Safari 桌面+移动，覆盖 Win/macOS/Linux/Android/iOS） |
| 请求头指纹 | 完整浏览器头：`Accept`（含 avif/webp q 值）、`Accept-Language`、`Accept-Encoding(br/zstd)`、`sec-ch-ua`（与 UA 版本号联动）、`sec-ch-ua-mobile/platform`、`Sec-Fetch-Dest/Mode/Site/User`、`Upgrade-Insecure-Requests` |
| Referer 缺失 | 下载图片时自动带页面级 Referer + Sec-Fetch 头 |
| Cookie 断裂 | 会话级 Cookie 持久化（同站多次请求保持状态）；支持 `--cookie k=v` 或配置 `cookies:` |
| TLS 指纹 | requests 标准指纹（多数站不校验）；高leck站点见下文「进阶」 |
| 频率封锁 | 指数退避（1s/2s/4s，上限 8s）+ 429 专属重试 + 全局/单主机限速 |

### ② 渲染层（renderer.py + antibot.STEALTH_JS）

| 对抗点 | 实现 |
| --- | --- |
| JS 挑战/5 秒盾 | 真实 Chromium 内核执行页面 JS，挑战自动通过后取 HTML |
| 自动化检测 | Stealth 补丁：`navigator.webdriver=undefined`、伪造 `window.chrome`、`plugins` 长度、`permissions.query` 通知分支、`hardwareConcurrency/deviceMemory`、WebGL 厂商（Intel Iris，抹除 SwiftShader 特征）、iframe contentWindow 同步抹除 |
| 无头特征 | `--disable-blink-features=AutomationControlled` + headless=new |
| 环境一致性 | context 固定 locale=zh-CN、timezone=Asia/Shanghai、viewport 1920×1080 |
| 懒加载图片 | 渲染后自动滚动（步进 innerHeight、停顿 0.7s、检测 scrollHeight 稳定即停） |
| 网络安静等待 | domcontentloaded 后最多再等 8s networkidle，超时不阻塞 |

### ③ 封锁判定（antibot.is_blocked_response）

- **状态码**：401/403/429/503 → blocked（404 等业务错误不算）
- **挑战页特征**（HTML 前 200KB 小写匹配）：
  `just a moment`、`cf-browser-verification`、`challenge-platform`、`_cf_chl_opt`、
  `attention required`、`verify you are human`、`captcha`、`access denied`、
  `rate limit exceeded`、`bot detection`、`ddos protection by`、`enable javascript and cookies` 等
- **200 伪装**：部分挑战页返回 200，靠特征匹配补刀
- 被拦后 auto 策略自动升级渲染层，升级成功 `used_browser=true`，失败如实返回 `blocked` + `block_reason`

## 二、典型场景处置

| 场景 | 命令 |
| --- | --- |
| 普通站 403 | `fetch --url X`（auto 自动升级） |
| Cloudflare 5 秒盾 | `fetch --url X` 或 `--browser` |
| SPA 空壳 | `--browser --type text` |
| 懒加载图床 | `images --url X --browser`（自动滚动触发加载） |
| 需要登录 | `--cookie "sessionid=xxx" --browser`（用户主动提供登录态） |
| IP 被限 | `--proxy http://127.0.0.1:7890` 或配置 `proxies:` 池 |
| 验证码墙 | 工具会报告 `blocked`；需人工过验证码后复用 Cookie，不要脚本硬刚 |

## 三、进阶配置

### 代理池（YAML）
```yaml
fetcher:
  proxies:
    - http://127.0.0.1:7890
    - socks5://127.0.0.1:7891
```
静态请求按序轮换；渲染层用 `proxy:` 单代理（浏览器会话固定一个出口更稳）。

### TLS/JA3 指纹（高leck站点）
标准 requests 的 TLS 指纹可被极少数站点识别。如需模拟浏览器 TLS 指纹：

```bash
pip install curl_cffi
```
然后把 fetcher.py 中 `requests.get` 换成：
```python
from curl_cffi import requests as creq
r = creq.get(url, impersonate="chrome131", headers=..., timeout=...)
```
（`impersonate="chrome131"` 提供与真实 Chrome 一致的 JA3/JA4 指纹。）

### 自定义请求头
```bash
--header "Accept-Language: en-US,en;q=0.9" --header "X-Requested-With: XMLHttpRequest"
```
或配置 `extra_headers:`。

## 四、合规红线

1. **robots.txt 默认遵守**——Disallow 的路径直接跳过；`--no-robots` 仅限用户明确声明已获授权。
2. **不得用于**：绕过付费墙、撞库、爬取个人隐私信息、对目标站造成压力（保持默认 1s 延迟）。
3. **验证码/登录墙不硬刚**：检测到即报告，由用户决定是否提供登录态。
4. **代理仅用于**：自建代理或已获授权的出口，不得用于匿名化违法抓取。
