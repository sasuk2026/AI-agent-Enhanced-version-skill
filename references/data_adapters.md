# 增强版自动数据分类 · 多数据类型适配指南

四类数据由 `features.py` 中不同的提取器统一处理，目标是都产出数值特征矩阵 X。

## 1. text（文本/文档）

- 输入：CSV/JSONL，含 `text` 列与标签列。
- 特征：`TfidfVectorizer`（1~2 gram，sublinear_tf）→ `TruncatedSVD` 降维到稠密 `svd_dims` 维。
- 为何降维：稠密低维矩阵可兼容 RandomForest 等不支持稀疏的模型；同时去噪、提速。
- 候选模型：MultinomialNB、ComplementNB、LogisticRegression、LinearSVC、RandomForest。

## 2. tabular（结构化表格）

- 输入：CSV/Excel，含标签列；其余列为特征。
- 特征：数值列 Min-Max 归一；类别列按 fit 时取值做 one-hot。fit 锁定列与取值，保证 retrain 对齐。
- 候选模型：LogisticRegression、RandomForest、GradientBoosting、KNeighbors（+ 视情况 SVC）。

## 3. files（混合文件归类）

- 输入：CSV，含 `path`（文件路径）与 `label` 列。
- 特征：每个文件 → `ext_<后缀>`、`name_<文件名>` 令牌 + 可读内容文本（前 `max_chars` 字符），
  整体走文本管线（TF-IDF + SVD）。
- 说明：二进制（pdf/docx/图片）仅取元数据令牌，语义弱；如要更强，可先抽取文本再喂入。

## 4. image（图片分类）

- 输入：CSV，含 `path`（图片路径）与 `label` 列。
- 特征（无需预训练模型）：文件大小、宽、高、宽高比，RGB 通道均值与标准差（PIL 可用时）。
- 候选模型：RandomForest、GradientBoosting、LogisticRegression、KNeighbors。
- 进阶：若已有图像 embedding（如 CLIP），把 embedding 作为 tabular 输入即可复用本 skill。

## 标签编码与置信度

- 所有标签经 `LabelEncoder` 编码；预测时 `predict_proba` 取最大类概率作为 **置信度**。
- 置信度 < `threshold` → 进入人工复核队列（见 workflows.md 阶段二/三）。
