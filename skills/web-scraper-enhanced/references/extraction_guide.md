# 内容抽取与选择器指南

## 抽取模式（--type）

| 模式 | 返回字段 | 典型用途 |
| --- | --- | --- |
| `all` | 全字段 | 默认，整页快照 |
| `text` | `text` 正文 | 正文归档、摘要、喂给 LLM |
| `links` | `links[]` 绝对 URL | 发现子页面、外链分析 |
| `images` | `images[]` {url, alt, w, h} | 图片资源收集 |
| `tables` | `tables[]` {index, rows} | 表格数据提取 → CSV |
| `metadata` | `metadata{}` | SEO/元信息普查 |
| `assets` | `stylesheets/scripts/documents` | 静态资源/文档盘点 |
| `custom` | `custom[]` | 用选择器精准抽取 |

## 自定义选择器（custom 模式）

语法：`选择器` 或 `选择器::属性`

```bash
# 抽取所有文章标题文本
--select "article h2"

# 抽取文章内所有链接的 href（自动补全为绝对 URL）
--select "article a::href"

# 抽取图片 src + alt（分别跑两次，或 text 模式取 alt）
--select ".gallery img::src"

# 抽取表格单元格
--select "table#price td"
```

常见 CSS 速记：
- `#id`、`.class`、`tag`、`tag.class`、`a[href^="https"]`
- 组合：`main article div.post`

## 正文提取优先级

1. 若环境安装 `trafilatura` → 用它做高质量正文/表格抽取
2. 否则用 BeautifulSoup + lxml 启发式：剔除 script/style/nav/footer 等噪声，
   在 article/main/section/div/p 中选正文密度最高的块

## 安全说明（务必阅读）

- **SSRF 防护**：任何 URL（含 30x 重定向后的目标）只要解析到私有网段
  （10/172.16/192.168、127.0.0.1、169.254.169.254 云元数据、fc00::/7 等）
  都会被拦截。这是防内网探测/云凭据泄露的硬性闸门。
- **robots.txt**：默认遵守；如目标站明确禁止，skill 会跳过并说明原因，不要强行绕过。
- **`allow_private: true`** 仅用于你明确要抓本地 mock/内网自检的场景，日常勿开。
- **动态渲染**：`--render` 会真实执行页面 JS，请仅对可信站点使用。
