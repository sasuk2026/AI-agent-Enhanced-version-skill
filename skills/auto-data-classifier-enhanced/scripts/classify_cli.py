#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
classify_cli.py —— 增强版自动数据分类 skill 的主流程编排器

子命令：
  train    训练：特征工程 → 交叉验证模型优选 → 集成 → 保存管线 + 报告
  predict  预测：加载管线 → 输出 标签/置信度 → 低置信样本导出复核队列
  retrain  回流：读取人工校正队列 → 并入训练集 → 重新训练 → 保存更新管线

示例：
  python3 classify_cli.py train   --data data.csv --type text --label-col label --out artifacts
  python3 classify_cli.py predict --model artifacts/pipeline.joblib --data test.csv --type text --threshold 0.6 --out preds.csv
  python3 classify_cli.py retrain --model artifacts/pipeline.joblib --queue artifacts/review_queue.csv --out artifacts
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import joblib

from features import make_extractor
from models import build_classifier, predict_with_confidence
from review import (route_low_confidence, export_review_queue,
                    read_review_queue, merge_feedback)
from dataio import load_dataset


class ClassifierPipeline:
    """把 提取器 + 分类器 + 元数据 打包成一个可序列化对象。"""

    def __init__(self, data_type: str, config: dict | None = None):
        self.data_type = data_type
        self.config = config or {}
        self.extractor = make_extractor(data_type, config)
        self.final_model = None
        self.label_encoder = None
        self.scores = {}
        self.ranked = []
        self.best_name = None
        self.ensemble_names = []
        self.classes_ = []
        self.X_train_ = None
        self.y_train_ = None
        self.ids_train_ = None

    def fit(self, X_raw, y):
        X = self.extractor.fit_transform(X_raw, y)
        self.X_train_ = X
        self.y_train_ = list(map(str, y))
        self.ids_train_ = list(range(len(y)))
        mcfg = self.config.get("model", {})
        res = build_classifier(
            X, y, self.data_type,
            cv=mcfg.get("cv", 5),
            scoring=mcfg.get("scoring", "f1_macro"),
            top_k=mcfg.get("top_k", 3))
        self.final_model = res["final_model"]
        self.label_encoder = res["label_encoder"]
        self.scores = res["scores"]
        self.ranked = res["ranked"]
        self.best_name = res["best_name"]
        self.ensemble_names = res["ensemble_names"]
        self.classes_ = list(self.label_encoder.classes_)
        return self

    def predict(self, X_raw):
        X = self.extractor.transform(X_raw)
        labels, conf = predict_with_confidence(self.final_model, self.label_encoder, X)
        return labels, conf

    def save(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    @staticmethod
    def load(path: str):
        return joblib.load(path)


# ---------------------------------------------------------------------------
# 报告生成
# ---------------------------------------------------------------------------
def build_report(pipe: ClassifierPipeline, n_train: int, extra: dict | None = None) -> dict:
    ranked = [{"model": n, "score_mean": round(m, 4), "score_std": round(s, 4)}
              for n, m, s in pipe.ranked]
    return {
        "data_type": pipe.data_type,
        "n_train": n_train,
        "n_classes": len(pipe.classes_),
        "classes": pipe.classes_,
        "best_single_model": pipe.best_name,
        "ensemble_models": pipe.ensemble_names,
        "model_ranking": ranked,
        **(extra or {}),
    }


def write_markdown_report(report: dict, path: str):
    lines = []
    lines.append(f"# 自动数据分类 · 增强版报告\n")
    lines.append(f"- 数据类型: **{report['data_type']}**")
    lines.append(f"- 训练样本: **{report['n_train']}**  类别数: **{report['n_classes']}**")
    lines.append(f"- 最优单模型: **{report['best_single_model']}**")
    lines.append(f"- 集成模型: **{', '.join(report['ensemble_models']) or '无（单模型兜底）'}**")
    if report.get("n_added"):
        lines.append(f"- 本次回流校正样本: **{report['n_added']}**")
    lines.append("\n## 模型交叉验证排名（{0}）\n".format(
        report.get("scoring", "f1_macro")))
    lines.append("| 模型 | 均值 | 标准差 |")
    lines.append("| --- | --- | --- |")
    for r in report["model_ranking"]:
        lines.append(f"| {r['model']} | {r['score_mean']} | {r['score_std']} |")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# train
# ---------------------------------------------------------------------------
def cmd_train(args):
    cfg = {}
    if args.config:
        import yaml
        cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) or {}
    raw, labels, df = load_dataset(args.data, args.type,
                                   label_col=args.label_col,
                                   text_col=args.text_col,
                                   file_col=args.file_col)
    pipe = ClassifierPipeline(args.type, cfg)
    pipe.fit(raw, labels)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    model_path = out / "pipeline.joblib"
    pipe.save(str(model_path))

    report = build_report(pipe, n_train=len(labels),
                          extra={"scoring": cfg.get("model", {}).get("scoring", "f1_macro")})
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown_report(report, str(out / "REPORT.md"))

    print(f"✅ 训练完成 → {model_path}")
    print(f"   数据类型: {pipe.data_type} | 样本: {len(labels)} | 类别: {len(pipe.classes_)}")
    print(f"   最优单模型: {pipe.best_name} | 集成: {', '.join(pipe.ensemble_names) or '单模型兜底'}")
    print("   模型排名:")
    for r in report["model_ranking"]:
        print(f"     - {r['model']:12s} {r['score_mean']:.4f} ± {r['score_std']:.4f}")
    print(f"   报告: {out / 'REPORT.md'}")


# ---------------------------------------------------------------------------
# predict
# ---------------------------------------------------------------------------
def cmd_predict(args):
    pipe = ClassifierPipeline.load(args.model)
    raw, labels, df = load_dataset(args.data, pipe.data_type,
                                   label_col=args.label_col,
                                   text_col=args.text_col,
                                   file_col=args.file_col)
    preds, confs = pipe.predict(raw)
    ids = list(range(len(raw)))

    out_df = pd.DataFrame({"id": ids, "predicted": preds, "confidence": np.round(confs, 4)})
    if labels is not None:
        out_df["true"] = labels
    low = route_low_confidence(confs, args.threshold)
    out_df["needs_review"] = [i in low for i in ids]

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(args.out, index=False)

    # 复核队列
    if low:
        review_rows = []
        for i in low:
            text = raw[i] if isinstance(raw, list) else str(raw.iloc[i].to_dict())
            review_rows.append({
                "id": ids[i],
                "text": (text[:500] if isinstance(text, str) else text),
                "predicted": preds[i],
                "confidence": round(float(confs[i]), 4),
            })
        queue_path = str(Path(args.out).parent / "review_queue.csv")
        export_review_queue(review_rows, queue_path)
    else:
        queue_path = None

    print(f"✅ 预测完成 → {args.out}")
    print(f"   样本: {len(raw)} | 平均置信度: {float(np.mean(confs)):.4f}")
    print(f"   低置信(<{args.threshold})需复核: {len(low)}")
    if queue_path:
        print(f"   复核队列已导出: {queue_path}（人工填 corrected_label 后用 retrain）")


# ---------------------------------------------------------------------------
# retrain（主动学习回流）
# ---------------------------------------------------------------------------
def cmd_retrain(args):
    pipe = ClassifierPipeline.load(args.model)
    corrections = read_review_queue(args.queue)
    if not corrections:
        print("⚠️ 复核队列中没有已填写的 corrected_label，未做任何更新。")
        return
    X_aug, y_aug, n_added = merge_feedback(
        pipe.X_train_, pipe.y_train_, pipe.ids_train_, corrections)
    mcfg = pipe.config.get("model", {})
    res = build_classifier(X_aug, y_aug, pipe.data_type,
                            cv=mcfg.get("cv", 5),
                            scoring=mcfg.get("scoring", "f1_macro"),
                            top_k=mcfg.get("top_k", 3))
    pipe.final_model = res["final_model"]
    pipe.label_encoder = res["label_encoder"]
    pipe.scores = res["scores"]
    pipe.ranked = res["ranked"]
    pipe.best_name = res["best_name"]
    pipe.ensemble_names = res["ensemble_names"]
    pipe.classes_ = list(res["label_encoder"].classes_)
    pipe.X_train_ = X_aug
    pipe.y_train_ = list(map(str, y_aug))
    # ids 扩充（新样本 id 用负数避免冲突）
    pipe.ids_train_ = list(pipe.ids_train_) + list(range(-1, -n_added - 1, -1))

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    model_path = out / "pipeline.joblib"
    pipe.save(str(model_path))

    report = build_report(pipe, n_train=len(y_aug), extra={"n_added": n_added,
                        "scoring": mcfg.get("scoring", "f1_macro")})
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown_report(report, str(out / "REPORT.md"))

    print(f"✅ 回流重训完成 → {model_path}")
    print(f"   新增校正样本: {n_added} | 训练集规模: {len(y_aug)}")
    print(f"   最优单模型: {pipe.best_name} | 集成: {', '.join(pipe.ensemble_names) or '单模型兜底'}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(description="增强版自动数据分类编排器")
    sub = p.add_subparsers(dest="cmd", required=True)

    pt = sub.add_parser("train", help="训练分类管线")
    pt.add_argument("--data", required=True, help="带标签的数据文件 CSV/JSONL/XLSX")
    pt.add_argument("--type", required=True, choices=["text", "tabular", "files", "image"])
    pt.add_argument("--label-col", required=True, help="标签列名")
    pt.add_argument("--text-col", default="text")
    pt.add_argument("--file-col", default="path")
    pt.add_argument("--config", default=None, help="可选 YAML 配置")
    pt.add_argument("--out", default="artifacts")
    pt.set_defaults(func=cmd_train)

    pp = sub.add_parser("predict", help="预测并导出复核队列")
    pp.add_argument("--model", required=True)
    pp.add_argument("--data", required=True)
    pp.add_argument("--label-col", default=None, help="若有则输出真实标签列用于评估")
    pp.add_argument("--text-col", default="text")
    pp.add_argument("--file-col", default="path")
    pp.add_argument("--threshold", type=float, default=0.6, help="置信度阈值")
    pp.add_argument("--out", default="predictions.csv")
    pp.set_defaults(func=cmd_predict)

    pr = sub.add_parser("retrain", help="读取复核队列回流重训")
    pr.add_argument("--model", required=True)
    pr.add_argument("--queue", required=True, help="人工填好的 review_queue.csv")
    pr.add_argument("--out", default=None, help="默认覆盖原 model 目录")
    pr.set_defaults(func=cmd_retrain)
    return p


def main():
    args = build_parser().parse_args()
    if args.cmd == "retrain" and not args.out:
        args.out = str(Path(args.model).parent)
    args.func(args)


if __name__ == "__main__":
    main()
