#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
review.py —— 置信度路由（人工回路） + 主动学习回流

增强点：
  3. 置信度+人工回路：预测置信度低于阈值(threshold)的样本自动进入复核队列，
     交给人工校正，避免低把握样本「裸奔」上线。
  4. 自动反馈自迭代(active learning)：人工校正结果回流到训练集，重新训练，
     模型越用越准。流程中 id 与训练样本一一对应，保证正确对齐。
"""

from __future__ import annotations

import pandas as pd
import numpy as np


def route_low_confidence(confidences, threshold: float) -> list:
    """返回置信度低于阈值的样本下标。"""
    return [i for i, c in enumerate(confidences) if c < threshold]


def export_review_queue(rows: list, out_path: str) -> str:
    """
    导出复核队列 CSV。rows 为 dict 列表，建议字段：id, text, predicted, confidence。
    额外留空 corrected_label 列供人工填写。
    """
    df = pd.DataFrame(rows)
    keep = [c for c in ("id", "text", "predicted", "confidence") if c in df.columns]
    df["corrected_label"] = ""
    df = df[keep + ["corrected_label"]]
    df.to_csv(out_path, index=False)
    return out_path


def read_review_queue(queue_path: str) -> list:
    """读取人工填好的复核队列，返回 [{id, corrected}, ...]（仅含已填写的行）。"""
    df = pd.read_csv(queue_path)
    out = []
    for _, r in df.iterrows():
        cl = r.get("corrected_label")
        if pd.notna(cl) and str(cl).strip() != "":
            out.append({"id": int(r["id"]), "corrected": str(cl).strip()})
    return out


def merge_feedback(X_train, y_train, ids_train, corrections: list) -> tuple:
    """
    将人工校正回流进训练集。
      corrections : [{id, corrected}, ...]
      ids_train   : 与 X_train/y_train 行序对应的 id 列表
    返回 (X_aug, y_aug, n_added)。
    """
    fb = {c["id"]: c["corrected"] for c in corrections}
    new_rows, new_labels = [], []
    for i, rid in enumerate(ids_train):
        if rid in fb:
            new_rows.append(X_train[i])
            new_labels.append(fb[rid])
    if new_rows:
        X_aug = np.vstack([X_train, np.vstack(new_rows)])
        y_aug = list(y_train) + new_labels
    else:
        X_aug, y_aug = X_train, list(y_train)
    return X_aug, y_aug, len(new_rows)
