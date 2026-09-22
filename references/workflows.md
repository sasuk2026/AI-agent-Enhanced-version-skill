# 增强版自动数据分类 · 工作流详解

本 skill 把 Agent 变成一个「自动数据分类专家」，覆盖从训练到回流自迭代的完整闭环。
核心增强能力：① 自动特征工程 + 模型优选 ② 置信度 + 人工回路 ③ 多模型集成投票 ④ 自动反馈自迭代。

## 总览流程图

```
[训练数据] --train--> 特征工程 --> 候选模型 CV 评分 --> 选最优 + 集成 --> 保存管线
                                                                          |
[新数据]  --predict--> 加载管线 --> 预测(标签+置信度) --> 高置信直接产出 / 低置信入复核队列
                                                                          |
[人工校正] --retrain--> 读取复核队列 --> 回流训练集 --> 重新优选+集成 --> 覆盖/更新管线（越用越准）
```

## 阶段一：训练（train）

1. 用 `dataio.load_dataset` 按 `data_type` 加载（CSV/JSONL/Excel）。
2. `make_extractor(data_type)` 做自动特征工程（见 data_adapters.md）。
3. `build_classifier` 对每个候选模型跑分层 K 折交叉验证，按指标排名，挑最优单模型；
   取前 `top_k` 个支持概率输出的模型组成 soft Voting 集成。
4. `ClassifierPipeline.save` 落盘 `pipeline.joblib`，并输出 `report.json` + `REPORT.md`。

触发训练的典型指令：
> “用 data.csv 训练一个文本分类器，标签在 label 列”
> “把这批文件按项目归类，置信度阈值设 0.7”

## 阶段二：预测（predict）

1. 加载已保存管线，对输入做相同特征变换（特征空间与训练一致）。
2. 输出 `predicted` + `confidence`，可选对比 `true` 评估。
3. 置信度 < `threshold` 的样本标记 `needs_review=True`，并额外导出 `review_queue.csv`
   （含 `corrected_label` 空列供人工填写）。

输出 `predictions.csv` 列：`id, predicted, confidence, [true], needs_review`。

## 阶段三：人工回路（human-in-the-loop）

- 打开 `review_queue.csv`，在 `corrected_label` 列填写正确标签（留空=不采纳）。
- 这是“置信度+人工回路”增强点：低把握样本不自动放行，交由人工把关。

## 阶段四：回流自迭代（retrain / active learning）

1. 运行 `retrain`，读取人工填好的队列，把校正样本并入训练集。
2. 重新跑模型优选 + 集成，保存更新后的管线。
3. 模型随人工反馈持续变准——这是“自动反馈自迭代”增强点。

## 命令行速查

```bash
# 训练
python3 scripts/classify_cli.py train \
  --data data.csv --type text --label-col label --out artifacts

# 预测（导出复核队列）
python3 scripts/classify_cli.py predict \
  --model artifacts/pipeline.joblib --data test.csv --type text \
  --threshold 0.6 --out predictions.csv

# 回流重训
python3 scripts/classify_cli.py retrain \
  --model artifacts/pipeline.joblib --queue artifacts/review_queue.csv --out artifacts
```

## 依赖

- 必选：Python 3.9+，`numpy`、`pandas`、`scikit-learn`、`joblib`
- 可选：`pyyaml`（用 `--config` 时）、`Pillow`（image 类型更丰富的视觉特征）、
  `openpyxl`（读取 .xlsx）
- 若环境缺包：对 image 类型会退化为仅尺寸/文件大小特征；其余类型不受影响。
