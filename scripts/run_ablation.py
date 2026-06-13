#!/usr/bin/env python3
"""Ablation study for FluxEV two-step smoothing.

Reproduces the experiment from FluxEV Table 4:
    - No smoothing
    - First-step smoothing only (Delta_sigma)
    - Two-step smoothing (full pipeline)

Usage:
    python scripts/run_ablation.py --input data/sample_prometheus_metrics.csv
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import f1_score, precision_score, recall_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fluxev import FluxEVDetector


def evaluate(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """Compute precision, recall, F1."""
    return {
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "true_anomalies": int(y_true.sum()),
        "predicted_anomalies": int(y_pred.sum()),
    }


def run_variant(
    df: pd.DataFrame,
    period: int,
    variant: str,
    disable_first: bool = False,
    disable_second: bool = False,
) -> dict:
    """Run FluxEV with specific smoothing disabled."""
    # Use high-risk for aggressive detection in ablation
    detector = FluxEVDetector(l=period, risk=0.05, base_quantile=0.95)

    if disable_first and disable_second:
        # No smoothing: use raw fluctuation |E| as score
        result = detector.detect(df["value"])
        # Replace score with raw fluctuation (pre-smoothing)
        raw_score = np.abs(result.fluctuation)
        threshold = float(np.nanquantile(raw_score[detector.warmup:], 0.98))
        labels = (raw_score > threshold).astype(int)
        labels[:detector.warmup] = 0
        result.score[:] = raw_score
        result.threshold = threshold
        y_pred = labels
    elif disable_second:
        # Only first-step smoothing: use F as score
        result = detector.detect(df["value"])
        raw_score = np.array(result.F)
        threshold = float(np.nanquantile(raw_score[detector.warmup:], 0.98))
        labels = (raw_score > threshold).astype(int)
        labels[:detector.warmup] = 0
        result.score[:] = raw_score
        result.threshold = threshold
        y_pred = labels
    else:
        # Full two-step smoothing (default)
        result = detector.detect(df["value"])
        y_pred = result.labels

    y_true = df["is_anomaly"].astype(int).to_numpy()
    metrics = evaluate(y_true, y_pred)
    metrics["variant"] = variant
    metrics["threshold"] = float(result.threshold)
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="FluxEV ablation study")
    parser.add_argument("--input", default=str(ROOT / "data" / "sample_prometheus_metrics.csv"))
    parser.add_argument("--period", type=int, default=60)
    args = parser.parse_args()

    out_dir = ROOT / "outputs" / "ablation"
    fig_dir = out_dir / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(Path(args.input), parse_dates=["timestamp"])

    results = []
    variants = [
        ("No smoothing", True, True),
        ("First-step only (Delta_sigma)", False, True),
        ("Two-step (full FluxEV)", False, False),
    ]

    print("=== FluxEV Ablation Study ===")
    print(f"Data: {len(df)} points, period={args.period}")
    print()

    for name, disable_first, disable_second in variants:
        metrics = run_variant(df, args.period, name, disable_first, disable_second)
        results.append(metrics)
        print(f"  {name}:")
        print(f"    Precision={metrics['precision']:.4f}  Recall={metrics['recall']:.4f}  "
              f"F1={metrics['f1']:.4f}  Threshold={metrics['threshold']:.4f}")
        print(f"    True={metrics['true_anomalies']}  Predicted={metrics['predicted_anomalies']}")

    # Save results
    (out_dir / "ablation_summary.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Plot comparison bar chart
    names = [r["variant"] for r in results]
    f1_scores = [r["f1"] for r in results]
    precisions = [r["precision"] for r in results]
    recalls = [r["recall"] for r in results]

    x = np.arange(len(names))
    width = 0.25

    fig, ax = plt.subplots(figsize=(10, 5))
    bars1 = ax.bar(x - width, precisions, width, label="Precision", color="#1f77b4")
    bars2 = ax.bar(x, recalls, width, label="Recall", color="#ff7f0e")
    bars3 = ax.bar(x + width, f1_scores, width, label="F1", color="#2ca02c")

    ax.set_ylabel("Score")
    ax.set_title("FluxEV Ablation Study — Smoothing Contributions (cf. Paper Table 4)")
    ax.set_xticks(x)
    ax.set_xticklabels(names, fontsize=9)
    ax.legend(loc="lower right")
    ax.set_ylim(0, 1.1)
    ax.grid(axis="y", alpha=0.25)

    # Add value labels on bars
    for bar in bars1 + bars2 + bars3:
        h = bar.get_height()
        if h > 0.05:
            ax.text(bar.get_x() + bar.get_width() / 2, h + 0.02, f"{h:.3f}",
                    ha="center", va="bottom", fontsize=7)

    plt.tight_layout()
    plt.savefig(fig_dir / "ablation_comparison.png", dpi=180)
    plt.close()

    print(f"\nAblation results saved to {out_dir / 'ablation_summary.json'}")
    print(f"Ablation chart saved to {fig_dir / 'ablation_comparison.png'}")


if __name__ == "__main__":
    main()
