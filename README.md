# AI agent Enhanced version skill

> 🧩 通用 AI Agent 技能集合仓库 —— 收纳、增强并持续沉淀各类 Agent Skills

## 关于本仓库

欢迎！这里是一个**面向 AI Agent 的技能集合仓库**，用来收纳、整理、增强各种可复用的 Agent Skills。每个 Skill 都是一个独立的能力包，放在 `skills/` 目录下，可直接部署到支持 AgentSkills 规范的平台使用。

我**不只专注自动数据分类**——凡是能让 Agent 变强的能力，都在收集之列：数据、文本、图像、Web、办公、代码、研究……持续扩充中。

## 收录的技能（skills/）

| Skill | 目录 | 能力简介 | 状态 |
|-------|------|----------|------|
| 🧬 增强版自动数据分类 | `skills/auto-data-classifier-enhanced/` | 自动特征工程 + 模型优选 + 多模型集成投票 + 置信度/人工复核 + 反馈自迭代，覆盖 text/tabular/files/image 四类数据 | ✅ 已收录 |
| 🕷️ 增强版网站抓取 | `skills/web-scraper-enhanced/` | 抓取网页/整站内容，CSS 选择器精准抽取，SSRF 防护 + robots.txt 遵守 + 礼貌限速 + 智能正文提取 + 动态渲染 + 多格式导出 | ✅ 已收录 |

> 持续收录中：欢迎贡献或提出你需要的技能方向。

## Skill 规范

每个 Skill 遵循标准的 AgentSkills 结构：

```
skills/<skill-name>/
├── SKILL.md                    # 技能主文件（name + description + 使用流程）
├── assets/                     # 配置文件、静态资源
├── references/                 # 参考文档、数据适配说明
└── scripts/                    # 可执行脚本（命令入口、核心逻辑）
```

## 如何新增一个 Skill

1. 在 `skills/` 下新建目录，按上述规范组织文件；
2. 编写 `SKILL.md`（frontmatter 含 `name` 与 `description`，正文说明触发条件与工作流）；
3. 提交 Pull Request，或在 Issue 中提出你想要的能力方向。

## 目标

打造一个**不断生长的 Agent 能力工具箱**——沉淀一个，增强一个，复用一处，处处可用。

## 使用场景

- 数据分类、打标签、批量归类
- 文本 / 文档处理与洞察
- 文件整理、图片分类
- 更多能力持续加入……

## 许可

本项目基于 **GNU GPL v3.0** 开源（见 [LICENSE](LICENSE)）。各 Skill 目录内如另有 LICENSE，以该目录为准。
