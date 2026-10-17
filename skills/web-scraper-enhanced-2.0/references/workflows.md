# 工作流与命令速查（2.0）

## 一、单页抓取

```bash
# 全量抽取（元信息+正文+链接+图片+表格+静态资源）
python3 scripts/fetch_cli.py fetch --url https://example.com --type all --format md

# 只要正文
python3 scripts/fetch_cli.py fetch --url https://example.com --type text

# 只要所有外链
python3 scripts/fetch_cli.py fetch --url https://example.com --type links --format json

# 只要图片列表（不下载）
python3 scripts/fetch_cli.py fetch --url https://example.com --type images --format json

# CSS 选择器精准抽取：所有价格
python3 scripts/fetch_cli.py fetch --url https://shop.site --type custom \
    --select "span.price::text" --format json

# 选择器抽属性：文章内所有站内文章链接
python3 scripts/fetch_cli.py fetch --url https://news.site --type custom \
    --select "article a::href" --format json
```

## 二、整站爬取

```bash
# 基础：前 20 页、深度 2、仅同域
python3 scripts/fetch_cli.py crawl --url https://example.com

# 深挖：100 页、深度 5、存 JSON
python3 scripts/fetch_cli.py crawl --url https://docs.site --max-pages 100 \
    --max-depth 5 --format json --out site.json

# 只要链接拓扑（发现整站 URL）
python3 scripts/fetch_cli.py crawl --url https://example.com --type links \
    --format csv --out urls.csv

# 爬取同时批量下图（全站图片，限量 50 张）
python3 scripts/fetch_cli.py crawl --url https://example.com --save-images \
    --out-dir ./site_imgs --max-images 50
```

## 三、图片专项（数量 AI 可控）

```bash
# 页面全部图片
python3 scripts/fetch_cli.py images --url https://example.com/gallery --out-dir ./imgs

# 前 10 张（AI 根据用户「抓 10 张」的意图决定 N）
python3 scripts/fetch_cli.py images --url https://example.com/gallery \
    --out-dir ./imgs --max-images 10

# 过滤：至少 600px 宽，只要 jpg/png/webp
python3 scripts/fetch_cli.py images --url https://example.com/gallery \
    --out-dir ./imgs --min-width 600 --formats jpg,png,webp

# 懒加载严重的站点：强制浏览器 + 滚动
python3 scripts/fetch_cli.py images --url https://example.com/feed \
    --out-dir ./imgs --browser

# 输出目录不传时默认 images/<域名>；报告固定写 <out-dir>/report.json
```

## 四、反爬场景

```bash
# auto（默认）：静态被 403/挑战页拦 → 自动升级隐身浏览器
python3 scripts/fetch_cli.py fetch --url https://protected.site

# 已知是 SPA：直接浏览器渲染
python3 scripts/fetch_cli.py fetch --url https://spa.app --browser --type text

# 带登录态 Cookie 抓取（用户主动提供）
python3 scripts/fetch_cli.py fetch --url https://private.site \
    --cookie "sessionid=xxxx" --browser

# 走代理
python3 scripts/fetch_cli.py fetch --url https://protected.site --proxy http://127.0.0.1:7890

# 自定义 UA（关闭轮换）
python3 scripts/fetch_cli.py fetch --url https://example.com \
    --user-agent "Mozilla/5.0 ..."
```

## 五、能力对照表

| 用户意图 | 子命令 | 关键参数 |
| --- | --- | --- |
| 抓页面全部内容 | fetch | `--type all` |
| 抓正文 | fetch | `--type text` |
| 抓所有链接 | fetch / crawl | `--type links` |
| 抓所有图片（仅列表） | fetch | `--type images` |
| **下载图片** | **images** | `--out-dir` |
| **下载前 N 张图** | **images** | `--max-images N` |
| 下载全部图片 | images | 不传 `--max-images` |
| 只要大图/指定格式 | images | `--min-width/--min-height/--formats` |
| 爬整站 | crawl | `--max-pages/--max-depth` |
| 整站链接归档 | crawl | `--type links --format csv` |
| 整站+全站图片 | crawl | `--save-images --out-dir` |
| SPA/懒加载页面 | fetch/images | `--browser`（默认 auto 也会自动升级） |
| 反爬拦截站 | fetch/images | auto 自动升级；或 `--proxy` |
| 精准抽区块 | fetch | `--type custom --select "css::attr"` |

## 六、退出码

| 码 | 含义 |
| --- | --- |
| 0 | 成功 |
| 2 | 页面抓取失败（网络/被拦/SSRF 拦截） |
| 3 | 页面抓到了但一张图都没下载成功 |

## 七、配置驱动

```bash
cp assets/config_template.yaml config.yaml   # 按需修改
python3 scripts/fetch_cli.py images --url <URL> --config config.yaml
```

配置优先级：命令行参数 > YAML 配置 > 内置默认值。
