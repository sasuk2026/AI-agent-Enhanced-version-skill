#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dataio.py —— 数据集加载（CSV / JSONL / Excel）

统一接口返回 (raw_inputs, labels, df)：
  - text    : raw = 文本列表；labels = 标签列表
  - tabular : raw = 去标签列后的 DataFrame；labels = 标签列表
  - files   : raw = 文件路径列表（CSV 中由 file_col 指定）；labels = 标签列表
  - image   : raw = 图片路径列表；labels = 标签列表

当 label_col=None 时（纯预测场景），labels=None，仅返回原始输入与 df。
"""

from __future__ import annotations

from pathlib import Path
import pandas as pd


def _read_any(path: str) -> pd.DataFrame:
    p = Path(path)
    ext = p.suffix.lower()
    if ext in (".jsonl",):
        return pd.read_json(path, lines=True)
    if ext in (".json",):
        return pd.read_json(path)
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(path)
    return pd.read_csv(path)


def load_dataset(path: str, data_type: str, label_col: str | None = None,
                 text_col: str = "text", file_col: str = "path") -> tuple:
    df = _read_any(path)
    if data_type == "text":
        raw = df[text_col].astype(str).tolist()
    elif data_type == "tabular":
        raw = df.drop(columns=[label_col]) if label_col else df.copy()
    else:  # files / image
        raw = df[file_col].astype(str).tolist()
    labels = df[label_col].astype(str).tolist() if label_col else None
    return raw, labels, df
