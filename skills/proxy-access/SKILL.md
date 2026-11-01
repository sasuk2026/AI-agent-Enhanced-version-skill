---
name: proxy-access
description: 通过用户提供的代理地址连接海外平台（Google、GitHub、OpenAI、HuggingFace、YouTube、X/Twitter 等）。当用户说"用代理"、"配置代理"、"挂代理访问XX"、"代理是 http://x.x.x.x:port，帮我访问海外网站"，或直接请求访问已知被墙的海外服务时使用。用户提供代理后，本技能负责验证代理可用性并设置 http_proxy/https_proxy 环境变量，使 curl、git、pip、npm、Python 等工具都能通过代理联网。
---

# 代理访问海外平台

## 快速开始

用户提供代理地址后，先运行验证脚本：

```bash
chmod +x scripts/proxy.sh && bash scripts/proxy.sh <代理地址>
```

- 返回 `"ok":true` → 按返回的 env 字段在本轮会话中导出环境变量，然后正常执行用户任务。
- 返回 `"ok":false` → 按返回的 error 向用户说明问题（端口不通 / 代理不可用），不要反复重试，请用户检查代理。

## 工作流

1. **获取代理地址**。用户未提供时，请用户提供，格式支持：
   - `http://host:port`
   - `socks5://host:port`（带认证：`socks5://user:pass@host:port`）
   - 仅 `host:port`（默认按 http 处理）
2. **验证**：运行 `scripts/proxy.sh`，确认端口可达且能访问测试 URL。
3. **启用**：验证通过后，在当前 bash 调用中设置（同一 bash 调用内设置和使用要放在同一条命令里，因为每次调用是新进程）：

   ```bash
   export http_proxy=<代理> https_proxy=<代理> all_proxy=<代理>
   export no_proxy="localhost,127.0.0.1"
   <实际要执行的命令>
   ```

4. **执行任务**：正常使用 curl、web 请求、git、pip、npm 等访问海外平台。
5. **完成后不残留配置**：不写入 shell 配置文件（~/.bashrc 等），不执行 `git config --global`，除非用户明确要求持久化。

## 常用工具的代理方式（未导出全局变量时）

| 工具 | 用法 |
|---|---|
| curl | `curl -x <代理> <url>` |
| git clone | `git -c http.proxy=<代理> -c https.proxy=<代理> clone <url>` |
| pip | `pip install --proxy <代理> <pkg>` |
| npm | `npm --proxy <代理> --https-proxy <代理> install <pkg>` |
| Python requests | `requests.get(url, proxies={"http": p, "https": p})`，p 为代理字符串 |

## 常见平台测试地址

验证特定平台连通性可用（返回 200/204 即通）：

- Google: `https://www.google.com/generate_204`
- GitHub: `https://api.github.com/zen`
- OpenAI: `https://api.openai.com/v1/models`（401 也说明网络可达）
- HuggingFace: `https://huggingface.co/api/whoami-v2`

## 注意事项

- 代理凭据属敏感信息：不要把代理地址写进交付文档或最终回复的正文里复述完整凭据。
- socks5 代理对某些工具需用 `socks5h://`（让 DNS 也走代理），curl 支持 `-x socks5h://`。
- 代理仅对 shell 级网络请求生效；web/browser 工具的网络通道不受这些环境变量影响，需要浏览器访问海外站点时告知用户此限制。
