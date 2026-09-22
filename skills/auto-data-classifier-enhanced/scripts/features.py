#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
features.py —— 增强版自动数据分类 skill 的特征工程与多数据类型适配层

为四种数据形态提供统一、可复用的特征提取器：
  - text    : TF-IDF + TruncatedSVD 降维（稠密，避免稀疏矩阵坑）
  - tabular : 数值列 Min-Max 归一 + 类别列 one-hot（fit 时记忆取值）
  - files   : 把每个文件转成「元数据令牌 + 内容文本」后用文本管线向量化
  - image   : PIL 基础视觉统计（尺寸/宽高比/均值色/标准差），无预训练模型也能跑

所有提取器均继承自 sklearn BaseEstimator/TransformerMixin，fit 时记忆状态、
transform 时复用，保证 retrain（主动学习）时特征空间一致、可对齐。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD


# ----------------------------------------------------------------------------
# 文本
# ----------------------------------------------------------------------------
class TextExtractor(BaseEstimator, TransformerMixin):
    """TF-IDF 向量 + SVD 降维到稠密低维空间，兼容所有候选模型（含 RandomForest）。"""

    def __init__(self, max_features: int = 20000, ngram_range=(1, 2),
                 min_df: int = 2, svd_dims: int = 300):
        self.max_features = max_features
        self.ngram_range = ngram_range
        self.min_df = min_df
        self.svd_dims = svd_dims
        self.vec = TfidfVectorizer(
            max_features=max_features, ngram_range=ngram_range,
            min_df=min_df, sublinear_tf=True, strip_accents="unicode")
        self.svd = TruncatedSVD(n_components=svd_dims, random_state=42)

    def fit(self, texts, y=None):
        texts = [str(t) for t in texts]
        x = self.vec.fit_transform(texts)
        n = min(self.svd_dims, max(2, x.shape[1] - 1))
        self.svd.set_params(n_components=n)
        self.svd.fit(x)
        return self

    def transform(self, texts):
        texts = [str(t) for t in texts]
        x = self.vec.transform(texts)
        return self.svd.transform(x).astype(np.float32)


# ----------------------------------------------------------------------------
# 结构化表格
# ----------------------------------------------------------------------------
class TabularExtractor(BaseEstimator, TransformerMixin):
    """数值列 Min-Max 归一 + 类别列 one-hot。fit 时锁定列集合与取值，保证可复现。"""

    def __init__(self):
        self.num_cols_ = None
        self.cat_cols_ = None
        self.cat_values_ = {}
        self.num_min_ = {}
        self.num_max_ = {}

    def fit(self, df: pd.DataFrame, y=None):
        df = df.reset_index(drop=True)
        self.num_cols_ = [c for c in df.columns
                          if pd.api.types.is_numeric_dtype(df[c])]
        self.cat_cols_ = [c for c in df.columns
                          if not pd.api.types.is_numeric_dtype(df[c])]
        self.cat_values_ = {c: sorted(df[c].astype(str).unique().tolist())
                            for c in self.cat_cols_}
        self.num_min_ = {c: float(df[c].min()) for c in self.num_cols_}
        self.num_max_ = {c: float(df[c].max()) for c in self.num_cols_}
        return self

    def _num_block(self, df: pd.DataFrame):
        if not self.num_cols_:
            return None
        out = np.zeros((len(df), len(self.num_cols_)), dtype=np.float32)
        for j, c in enumerate(self.num_cols_):
            col = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(float).values
            lo, hi = self.num_min_[c], self.num_max_[c]
            out[:, j] = (col - lo) / (hi - lo) if hi > lo else 0.0
        return out

    def _cat_block(self, df: pd.DataFrame):
        if not self.cat_cols_:
            return None
        blocks = []
        for c in self.cat_cols_:
            vals = self.cat_values_[c]
            idx = {v: i for i, v in enumerate(vals)}
            mat = np.zeros((len(df), len(vals)), dtype=np.float32)
            for i, v in enumerate(df[c].astype(str).tolist()):
                if v in idx:
                    mat[i, idx[v]] = 1.0
            blocks.append(mat)
        return np.hstack(blocks)

    def transform(self, df: pd.DataFrame):
        df = df.reset_index(drop=True)
        parts = [p for p in (self._num_block(df), self._cat_block(df)) if p is not None]
        return np.hstack(parts) if parts else np.zeros((len(df), 0), dtype=np.float32)


# ----------------------------------------------------------------------------
# 混合文件（按内容/类型归类）
# ----------------------------------------------------------------------------
class FileExtractor(BaseEstimator, TransformerMixin):
    """把文件目录转成「扩展名令牌 + 文件名令牌 + 内容文本」再走文本管线。"""

    def __init__(self, text_ext=None, max_chars: int = 20000):
        self.text_ext = text_ext or {
            ".txt", ".md", ".csv", ".json", ".jsonl", ".log", ".py", ".java",
            ".js", ".ts", ".go", ".c", ".cpp", ".h", ".html", ".htm", ".xml",
            ".yaml", ".yml", ".toml", ".rst", ".tex"}
        self.max_chars = max_chars
        self.inner = TextExtractor()

    def _read_file(self, path):
        p = Path(path)
        ext = p.suffix.lower() or "unknown"
        meta = [f"ext_{ext[1:]}", f"name_{p.stem[:20]}"]
        content = ""
        if ext in self.text_ext:
            try:
                content = p.read_text(errors="ignore")[:self.max_chars]
            except Exception:
                content = ""
        return " ".join(meta) + " " + content

    def fit(self, file_paths, y=None):
        docs = [self._read_file(p) for p in file_paths]
        self.inner.fit(docs)
        return self

    def transform(self, file_paths):
        docs = [self._read_file(p) for p in file_paths]
        return self.inner.transform(docs)


# ----------------------------------------------------------------------------
# 图片（基础视觉统计）
# ----------------------------------------------------------------------------
class ImageExtractor(BaseEstimator, TransformerMixin):
    """基于 PIL 抽取尺寸/宽高比/均值色/标准差等统计特征，无需预训练模型。"""

    def __init__(self):
        self.use_pil = False
        try:
            from PIL import Image  # noqa: F401
            self.use_pil = True
        except Exception:
            self.use_pil = False

    def _features(self, path):
        p = Path(path)
        feats = [float(p.stat().st_size) if p.exists() else 0.0]
        if self.use_pil:
            try:
                from PIL import Image
                with Image.open(path) as im:
                    w, h = im.size
                    feats += [float(w), float(h), float(w / h) if h else 1.0]
                    arr = np.asarray(im.convert("RGB"), dtype=np.float32)
                    if arr.ndim == 3:
                        px = arr.reshape(-1, 3)
                        feats += list(px.mean(0)) + list(px.std(0))
                    else:
                        feats += [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
            except Exception:
                feats += [0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        else:
            feats += [0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        return np.array(feats, dtype=np.float32)

    def fit(self, file_paths, y=None):
        for p in file_paths:
            self._features(p)
        return self

    def transform(self, file_paths):
        return np.vstack([self._features(p) for p in file_paths]).astype(np.float32)


# ----------------------------------------------------------------------------
# 工厂
# ----------------------------------------------------------------------------
def make_extractor(data_type: str, config: dict | None = None):
    config = config or {}
    if data_type == "text":
        return TextExtractor(**config.get("text", {}))
    if data_type == "tabular":
        return TabularExtractor()
    if data_type == "files":
        return FileExtractor(**config.get("files", {}))
    if data_type == "image":
        return ImageExtractor()
    raise ValueError(f"未知 data_type: {data_type}（支持 text/tabular/files/image）")
