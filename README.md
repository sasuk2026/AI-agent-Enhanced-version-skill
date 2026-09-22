# AI agent Enhanced version skill

> 增强版自动数据分类 Agent 技能（Enhanced Auto Data Classifier Agent Skill）

## 关于我

你好，我是 **auto-data-classifier-enhanced** —— 一个把 AI Agent 变成「自动数据分类专家」的增强版技能。我不只是简单打标签，而是构建了一套从训练到持续迭代的完整闭环。

### 我擅长什么

给定一份带标签的数据，我能自动完成**特征工程、模型选择与集成**，产出可复用的分类管线；对未标注数据预测时，我会给出「**标签 + 置信度**」，低置信度的样本自动进入人工复核队列；人工校正的结果可以回流重训，让我越用越准。

### 我的四大增强能力

| 能力 | 说明 |
|------|------|
| 🧬 自动特征工程 + 模型优选 | 按数据类型自动选择特征方案，多候选模型交叉验证排名挑最优 |
| 🗳️ 多模型集成投票 | 前 K 个模型组成 soft Voting 集成，降低单模型误判 |
| 🎯 置信度 + 人工回路 | 低置信预测不裸奔，自动导出复核队列交人工把关 |
| 🔁 自动反馈自迭代 | 人工校正回流训练集，重新优选 + 集成，越用越准 |

### 我支持的数据类型

- **text** —— 文本 / 文档分类（邮件、工单、日志等）
- **tabular** —— 结构化表格分类
- **files** —— 混合文件归类整理
- **image** —— 图片内容分类

## 快速开始

```bash
# 1. 训练（带标签数据）
python3 scripts/classify_cli.py train \
  --data data.csv --type text --label-col label \
  --out artifacts

# 2. 预测（未标注数据，自动导出复核队列）
python3 scripts/classify_cli.py predict \
  --data new_data.csv --type text --out artifacts

# 3. 反馈回流（人工校正后重训，持续变准）
python3 scripts/classify_cli.py retrain \
  --feedback reviewed.csv --out artifacts
```

## 仓库结构

```
.
├── SKILL.md                     # 技能主文件（能力说明与使用流程）
├── assets/
│   └── config_template.yaml     # 配置模板
├── references/
│   ├── workflows.md             # 工作流说明
│   └── data_adapters.md         # 数据适配器说明
└── scripts/
    ├── classify_cli.py          # 命令行入口（train/predict/retrain）
    ├── features.py              # 特征工程
    ├── models.py                # 模型优选与集成
    ├── review.py                # 复核队列
    └── dataio.py                # 数据读写
```

## 使用场景

- 「把这批邮件/工单/日志按主题分类」
- 「用这份 CSV 训练一个分类器，新数据自动打标签」
- 「把这些文件按项目/类型整理归类」
- 「图片按内容分类」
- 任何需要「自动分类 + 可信度评估 + 可人工校正 + 持续迭代」的场景。

## 许可

请参阅仓库内的 LICENSE（如有）或联系作者获取授权信息。
