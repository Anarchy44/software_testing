#!/usr/bin/env python3
"""Run FluxEV anomaly detection on chaos/fault injection data.

Compares detected anomaly windows with actual fault injection time windows.
Outputs precision, recall, F1 and generates comparison figures.

Usage:
    python scripts/run_fluxev_on_chaos.py \\
        --input data/chaos_metrics.csv \\
        --labels data/chaos_labels.csv
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


def window_match(
    pred_indices: np.ndarray,
    true_indices: np.ndarray,
    tolerance: int = 5,
) -> tuple[int, int, int]:
    """Match predicted anomaly windows to true windows.

    A true window is "caught" if any prediction falls within ±tolerance of its start.

    Returns:
        (true_windows, caught, predicted_windows)
    """
    # Group true indices into windows
    true_windows = []
    if len(true_indices) > 0:
        ws = true_indices[0]
        for k in range(1, len(true_indices)):
            if true_indices[k] > true_indices[k - 1] + tolerance + 1:
                true_windows.append(ws)
                ws = true_indices[k]
        true_windows.append(ws)

    # Group predicted indices into windows
    pred_windows = []
    if len(pred_indices) > 0:
        ws = pred_indices[0]
        for k in range(1, len(pred_indices)):
            if pred_indices[k] > pred_indices[k - 1] + tolerance + 1:
                pred_windows.append(ws)
                ws = pred_indices[k]
        pred_windows.append(ws)

    # Dilate predictions for matching
    pred_dilated = np.zeros(max(pred_indices.max() + tolerance + 1 if len(pred_indices) > 0 else 1,
                                true_indices.max() + tolerance + 1 if len(true_indices) > 0 else 1),
                            dtype=int)
    for pi in pred_indices:
        lo = max(0, pi - tolerance)
        hi = min(len(pred_dilated), pi + tolerance + 1)
        pred_dilated[lo:hi] = 1

    caught = sum(1 for tw in true_windows if pred_dilated[tw] == 1)

    return len(true_windows), caught, len(pred_windows)


def main() -> None:
    parser = argparse.ArgumentParser(description="FluxEV on chaos data")
    parser.add_argument("--input", required=True, help="Metrics CSV from fault collection")
    parser.add_argument("--labels", required=True, help="Ground-truth labels CSV")
    parser.add_argument("--period", type=int, default=60)
    parser.add_argument("--tolerance", type=int, default=5, help="Window matching tolerance")
    args = parser.parse_args()

    input_path = Path(args.input)
    labels_path = Path(args.labels)
    out_dir = ROOT / "outputs"
    fig_dir = out_dir / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    # Load data
    df = pd.read_csv(input_path, parse_dates=["timestamp"])
    labels_df = pd.read_csv(labels_path, parse_dates=["timestamp"])

    # Merge labels
    df = df.merge(labels_df[["timestamp", "is_anomaly"]], on="timestamp", how="left")
    df["is_anomaly"] = df["is_anomaly"].fillna(0).astype(int)

    # Run FluxEV detection
    detector = FluxEVDetector(l=args.period)
    result = detector.detect(df["value"])

    scored = df.copy()
    scored["fluxev_score"] = result.score
    scored["threshold"] = result.threshold
    scored["predicted_anomaly"] = result.labels
    scored.to_csv(out_dir / "chaos_metrics_with_scores.csv", index=False)

    # Standard point-wise metrics
    y_true = scored["is_anomaly"].astype(int).to_numpy()
    y_pred = scored["predicted_anomaly"].astype(int).to_numpy()
    precision = float(precision_score(y_true, y_pred, zero_division=0))
    recall = float(recall_score(y_true, y_pred, zero_division=0))
    f1 = float(f1_score(y_true, y_pred, zero_division=0))

    # Window-level metrics
    true_indices = np.where(y_true == 1)[0]
    pred_indices = np.where(y_pred == 1)[0]
    n_true_windows, caught, n_pred_windows = window_match(pred_indices, true_indices, args.tolerance)
    window_precision = caught / n_pred_windows if n_pred_windows > 0 else 0.0
    window_recall = caught / n_true_windows if n_true_windows > 0 else 1.0
    window_f1 = (
        2 * window_precision * window_recall / (window_precision + window_recall)
        if (window_precision + window_recall) > 0 else 0.0
    )

    summary = {
        "source": str(input_path),
        "points": int(len(scored)),
        "true_points": int(y_true.sum()),
        "predicted_points": int(y_pred.sum()),
        "threshold": float(result.threshold),
        "point_precision": precision,
        "point_recall": recall,
        "point_f1": f1,
        "window_true": n_true_windows,
        "window_caught": caught,
        "window_predicted": n_pred_windows,
        "window_precision": round(window_precision, 4),
        "window_recall": round(window_recall, 4),
        "window_f1": round(window_f1, 4),
    }
    (out_dir / "chaos_experiment_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # --- Detection result figure ---
    plt.figure(figsize=(12, 4.8))
    plt.plot(scored["timestamp"], result.values, label="latency p95", linewidth=1.4)
    true_pts = scored[scored["is_anomaly"] == 1]
    pred_pts = scored[scored["predicted_anomaly"] == 1]
    plt.scatter(true_pts["timestamp"], true_pts["value"], color="#d62728", s=28, label="true (fault window)")
    plt.scatter(pred_pts["timestamp"], pred_pts["value"], facecolors="none",
                edgecolors="#1f77b4", s=70, label="FluxEV detected")
    plt.title("FluxEV detection on ChaosMesh fault-injected metrics")
    plt.xlabel("Time")
    plt.ylabel("p95 latency (ms)")
    plt.grid(alpha=0.25)
    plt.legend(loc="upper right")
    plt.tight_layout()
    plt.savefig(fig_dir / "chaos_detection_result.png", dpi=180)
    plt.close()

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
