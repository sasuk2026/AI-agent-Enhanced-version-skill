#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
models.py —— 候选模型池、交叉验证自动优选、Voting 集成、带置信度预测

增强点：
  1. 自动特征+模型优选：对每种数据类型维护一组候选模型，用分层 K 折交叉验证
     按指定指标（默认 f1_macro）自动排名，挑选最优单模型。
  2. 多模型集成投票：取交叉验证排名前 top_k 且支持概率输出的模型，组成
     soft VotingClassifier 投票，降低单模型误判风险。

最终返回的对象一定具备 predict_proba，方便上层统一输出「标签 + 置信度」。
"""

from __future__ import annotations

import numpy as np
from sklearn.ensemble import (
    RandomForestClassifier, GradientBoostingClassifier, VotingClassifier)
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import MultinomialNB, ComplementNB
from sklearn.svm import LinearSVC
from sklearn.neighbors import KNeighborsClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import cross_val_score, StratifiedKFold


def candidate_models(data_type: str) -> dict:
    """按数据类型返回候选模型字典。"""
    common = {
        "logreg": LogisticRegression(max_iter=2000, C=1.0),
        "rf": RandomForestClassifier(n_estimators=200, n_jobs=-1, random_state=42),
        "gb": GradientBoostingClassifier(random_state=42),
    }
    if data_type in ("text", "files"):
        # 文本/文件场景：朴素贝叶斯系通常很强，线性模型次之
        return {
            "mnb": MultinomialNB(),
            "cnb": ComplementNB(),
            "logreg": LogisticRegression(max_iter=2000, C=1.0),
            "linear_svc": LinearSVC(C=1.0),
            "rf": RandomForestClassifier(n_estimators=200, n_jobs=-1, random_state=42),
        }
    if data_type == "image":
        return {**common, "knn": KNeighborsClassifier(n_neighbors=5)}
    # tabular
    return {**common, "knn": KNeighborsClassifier(n_neighbors=5)}


def build_classifier(X, y, data_type: str, cv: int = 5,
                     scoring: str = "f1_macro", top_k: int = 3) -> dict:
    """
    交叉验证评分 -> 排名 -> 集成。返回：
      final_model     : 集成或最优单模型（必有 predict_proba）
      label_encoder   : 标签编码器
      scores          : {模型名: (mean, std)}（失败为 (nan, err)）
      ranked          : [(模型名, mean, std), ...] 降序
      best_name       : 单模型最优名
      ensemble_names  : 参与集成的模型名列表
    """
    models = candidate_models(data_type)
    le = LabelEncoder()
    y_enc = le.fit_transform(list(map(str, y)))
    skf = StratifiedKFold(n_splits=cv, shuffle=True, random_state=42)

    scores = {}
    for name, m in models.items():
        try:
            s = cross_val_score(m, X, y_enc, cv=skf, scoring=scoring, n_jobs=-1)
            scores[name] = (float(s.mean()), float(s.std()))
        except Exception as e:  # 个别模型在该特征上不可用
            scores[name] = (float("nan"), str(e)[:120])

    ranked = sorted(((n, sc) for n, sc in scores.items() if not np.isnan(sc[0])),
                    key=lambda kv: kv[1][0], reverse=True)

    # 仅用支持概率输出的模型参与 soft 投票
    proba_models = [(n, models[n]) for n, _ in ranked
                    if hasattr(models[n], "predict_proba")]
    top = proba_models[: max(1, top_k)]

    if len(top) >= 2:
        ensemble = VotingClassifier(estimators=top, voting="soft", n_jobs=-1)
        ensemble.fit(X, y_enc)
        final_model = ensemble
    elif top:
        m = top[0][1]
        m.fit(X, y_enc)
        final_model = m
    else:  # 兜底：直接用单模型最优（即便无概率，也先训练）
        best = models[ranked[0][0]]
        best.fit(X, y_enc)
        final_model = best

    return {
        "final_model": final_model,
        "label_encoder": le,
        "scores": scores,
        "ranked": [(n, sc[0], sc[1]) for n, sc in ranked],
        "best_name": ranked[0][0] if ranked else None,
        "ensemble_names": [n for n, _ in top],
    }


def predict_with_confidence(final_model, label_encoder, X) -> tuple:
    """返回 (解码后的标签列表, 置信度数组)。"""
    proba = final_model.predict_proba(X)
    pred_idx = proba.argmax(axis=1)
    conf = proba.max(axis=1)
    labels = label_encoder.inverse_transform(pred_idx)
    return list(labels), conf
