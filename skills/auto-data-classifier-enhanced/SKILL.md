---
name: auto-data-classifier-enhanced
description: 增强版自动数据分类 Agent 工具。当用户需要对文本/文档、结构化表格、混合文件或图片做自动分类/打标签，并希望具备「自动特征工程+模型优选、多模型集成投票、低置信度人工回路、人工反馈主动学习自迭代」等增强能力时使用。覆盖 train（训练）→ predict（预测+复核队列）→ retrain（反馈回流）完整闭环，支持无标签的预测与带标签的监督训练。
---

# 增强版自动数据分类（Auto Data Classifier · Enhanced）

## Overview

把 Agent 变成「自动数据分类专家」：给定一份带标签的数据，自动完成特征工程、模型选择与集成，
产出可复用的分类管线；对未标注数据预测时给出「标签 + 置信度」，低置信样本自动进入人工复核队列；
人工校正结果可回流重训，使模型持续变准。

四大增强能力：
1. **自动特征工程 + 模型优选**：按数据类型自动选特征方案，多候选模型交叉验证排名挑最优。
2. **多模型集成投票**：前 K 个模型组成 soft Voting 集成，降低单模型误判。
3. **置信度 + 人工回路**：低置信预测不裸奔，导出复核队列交人工把关。
4. **自动反馈自迭代（active learning）**：人工校正回流训练集，重新优选+集成，越用越准。

支持四类数据：`text`（文本/文档）、`tabular`（结构化表格）、`files`（混合文件归类）、`image`（图片）。

## When to use

- “把这批邮件/工单/日志按主题分类”
- “用这份 CSV 训练一个分类器，新数据自动打标签”
- “把这些文件按项目/类型整理归类”
- “图片按内容分类”
- 任何需要「自动分类 + 可信度评估 + 可人工校正 + 持续迭代」的场景。

## Workflow（核心闭环）

### 1. 训练 train
```bash
python3 scripts/classify_cli.py train \
  --data <数据文件.csv|.jsonl|.xlsx> --type <text|tabular|files|image> \
  --label-col <标签列名> [--text-col text] [--file-col path] \
  [--config assets/config_template.yaml] --out artifacts
```
产物：`artifacts/pipeline.joblib`（管线）、`artifacts/report.json`、`artifacts/REPORT.md`（模型排名等）。

### 2. 预测 predict（自动导出复核队列）
```bash
python3 scripts/classify_cli.py predict \
  --model artifacts/pipeline.joblib --data <新数据> --type <同训练类型> \
  --threshold 0.6 --out predictions.csv
```
产物：`predictions.csv`（`id, predicted, confidence, [true], needs_review`）；
若有关键置信样本，额外导出 `review_queue.csv`（含空 `corrected_label` 列）。

### 3. 人工回路（human-in-the-loop）
打开 `review_queue.csv`，在 `corrected_label` 列填写正确标签，留空=不采纳。

### 4. 回流重训 retrain（active learning）
```bash
python3 scripts/classify_cli.py retrain \
  --model artifacts/pipeline.joblib --queue artifacts/review_queue.csv --out artifacts
```
校正样本并入训练集后重新优选+集成，覆盖更新管线。

> 细节见 `references/workflows.md`；各数据类型特征方案见 `references/data_adapters.md`；
> 可调参数见 `assets/config_template.yaml`。

## 使用到的权限

本 skill 在运行时会访问并使用以下权限/资源：

- **本地文件读写**：读取训练/预测数据（CSV / JSONL / Excel / 文本 / 图片 / 目录下的文件），
  并在 `--out` 指定目录写入产物（`pipeline.joblib`、`report.json`、`REPORT.md`、`predictions.csv`、`review_queue.csv`）。
- **命令行执行**：调用 `python3 scripts/classify_cli.py` 及其子命令（train / predict / retrain）。
- **Python 运行时与依赖包**：需 `scikit-learn`、`pandas`、`joblib`；按数据类型可能额外需要 `Pillow`（图片）、`openpyxl`（Excel）、`pyyaml`（配置）。
- **不涉及**：不访问网络，不收集或外传数据，不触碰用户数据文件以外的内容。

## 执行要点（Agent 应遵守）

- **先确认数据类型与标签列**：训练必须指定 `--type` 与 `--label_col`；`files`/`image` 的数据文件
  需含 `path` 列指向实际文件。
- **预测与训练 type 必须一致**，否则特征空间不匹配。
- **低置信必须走复核**：`predict` 后若 `review_queue.csv` 非空，提示用户人工校正再 `retrain`，
  不要直接把低置信结果当作最终结论。
- **依赖自检**：运行前确认 `scikit-learn`、`pandas`、`joblib` 已安装；`image` 建议装 `Pillow`、
  `.xlsx` 需 `openpyxl`、用 `--config` 需 `pyyaml`。缺包时给出安装提示而非静默失败。

## 模块说明（scripts/）

| 文件 | 职责 |
| --- | --- |
| `classify_cli.py` | 主编排器：train / predict / retrain 三个子命令 |
| `features.py` | 四类数据的自动特征工程（`TextExtractor`/`TabularExtractor`/`FileExtractor`/`ImageExtractor`） |
| `models.py` | 候选模型池、交叉验证优选、Voting 集成、带置信度预测 |
| `review.py` | 低置信路由、复核队列导出/读取、主动学习回流 |
| `dataio.py` | CSV/JSONL/Excel 统一加载 |

## 输出报告格式

`REPORT.md` 固定包含：数据类型、训练样本数、类别数、最优单模型、集成模型、各模型交叉验证
均值±标准差排名。用于快速判断当前分类器质量与是否需补充数据/调整阈值。
