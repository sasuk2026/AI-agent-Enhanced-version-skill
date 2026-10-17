# web-scraper-enhanced-2.0

增强版网站资源抓取 Agent Skill 的 2.0 版本。在 1.0（SSRF 防护 / robots 遵守 /
礼貌限速 / 智能正文 / 多模式抽取 / 多格式导出）基础上，新增：

- **反爬对抗**：真实 UA 池轮换 + 浏览器级请求头；静态被拦自动升级 Playwright
  隐身渲染（Stealth 抹除 webdriver 等自动化指纹）
- **懒加载支持**：渲染时自动滚动触发懒加载图片/无限滚动
- **图片全源发现**：12 类图片来源（img/srcset/懒加载属性/picture/video poster/
  CSS 背景图/og:image/a 直链/link 图标/svg/input/object/embed）
- **图片批量下载**：并发 + 重试 + 断点跳过 + URL/SHA1 双去重 + 尺寸/格式过滤
- **数量 AI 可控**：`--max-images N`（0=全部），AI 按用户意图自行决定抓多少张
- **整站带图爬取**：`crawl --save-images` 全站图片统一限量下载

## 快速开始

```bash
# 抓单页 → Markdown
python3 scripts/fetch_cli.py fetch --url https://example.com --type all --format md

# 下载页面全部图片
python3 scripts/fetch_cli.py images --url https://example.com/gallery --out-dir ./imgs

# AI 决定只抓 10 张
python3 scripts/fetch_cli.py images --url https://example.com/gallery --out-dir ./imgs --max-images 10
```

## 安装依赖

```bash
pip install requests beautifulsoup4 lxml
# 可选增强：
pip install playwright pyyaml pillow trafilatura
playwright install chromium
```

## 结构

```
web-scraper-enhanced-2.0/
├── SKILL.md                        # Skill 定义（触发词/工作流/安全要点）
├── scripts/
│   ├── fetch_cli.py                # 主编排器：fetch / crawl / images
│   ├── security.py                 # SSRF 防护（请求前 + 重定向链后双重校验）
│   ├── antibot.py                  # UA 池/浏览器头/封锁判定/Stealth 脚本
│   ├── renderer.py                 # Playwright 隐身渲染 + 懒加载滚动
│   ├── fetcher.py                  # 2.0 抓取层：指纹/封锁升级/robots/限速
│   ├── extractor.py                # 2.0 抽取层：12 类图片来源 + srcset 解析
│   ├── images.py                   # 图片过滤/限量/并发下载/报告
│   ├── crawler.py                  # BFS 整站爬取 + 整站图片限量下载
│   └── exporter.py                 # JSON / Markdown / CSV 导出
├── references/
│   ├── workflows.md                # 命令速查与能力对照
│   ├── extraction_guide.md         # 选择器语法/图片来源/输出字段
│   └── antibot_guide.md            # 反爬策略详解与合规红线
└── assets/
    └── config_template.yaml        # 可调参数模板
```

## 合规

仅供个人学习、研究或已获授权的抓取。robots.txt 默认遵守；不得用于绕过付费墙、
大规模侵权转载或对目标站造成压力。详见 `references/antibot_guide.md` 第四节。
