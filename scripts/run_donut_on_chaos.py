#!/usr/bin/env python3
"""Run Donut anomaly detection on chaos/fault injection data.

Loads chaos metrics, preprocesses for Donut (min-max normalization + sliding windows),
loads or trains a Donut VAE model, and evaluates detection performance against
ground-truth labels.

Usage:
    # With pre-trained model
    python scripts/run_donut_on_chaos.py \\
        --input data/chaos_metrics.csv \\
        --labels data/chaos_labels.csv \\
        --model outputs/donut/best_model.pt

    # Train from scratch on chaos data (self-supervised)
    python scripts/run_donut_on_chaos.py \\
        --input data/chaos_metrics.csv \\
        --labels data/chaos_labels.csv \\
        --train
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from donut import DonutVAE, DonutTrainer, DonutDetector


def window_match(
    pred_indices: np.ndarray,
    true_indices: np.ndarray,
    tolerance: int = 5,
) -> tuple[int, int, int]:
    """Match predicted anomaly windows to true windows.

    A true window is "caught" if any prediction falls within +-tolerance of its start.

    Returns:
        (true_windows, caught, predicted_windows)
    """
    true_windows = []
    if len(true_indices) > 0:
        ws = true_indices[0]
        for k in range(1, len(true_indices)):
            if true_indices[k] > true_indices[k - 1] + tolerance + 1:
                true_windows.append(ws)
                ws = true_indices[k]
        true_windows.append(ws)

    pred_windows = []
    if len(pred_indices) > 0:
        ws = pred_indices[0]
        for k in range(1, len(pred_indices)):
            if pred_indices[k] > pred_indices[k - 1] + tolerance + 1:
                pred_windows.append(ws)
                ws = pred_indices[k]
        pred_windows.append(ws)

    pred_dilated = np.zeros(
        max(pred_indices.max() + tolerance + 1 if len(pred_indices) > 0 else 1,
            true_indices.max() + tolerance + 1 if len(true_indices) > 0 else 1),
        dtype=int,
    )
    for pi in pred_indices:
        lo = max(0, pi - tolerance)
        hi = min(len(pred_dilated), pi + tolerance + 1)
        pred_dilated[lo:hi] = 1

    caught = sum(1 for tw in true_windows if pred_dilated[tw] == 1)
    return len(true_windows), caught, len(pred_windows)


def build_windows(
    values: np.ndarray,
    window_size: int = 120,
) -> np.ndarray:
    """Build sliding windows from 1-D time series.

    Args:
        values: 1-D array of normalized values (shape: n_points,)
        window_size: Number of points per window

    Returns:
        2-D array (n_windows, window_size)
    """
    n = len(values)
    n_windows = n - window_size + 1
    if n_windows < 1:
        raise ValueError(
            f"Need at least {window_size} points, got {n}. "
            f"Reduce window_size or increase data duration."
        )
    windows = np.lib.stride_tricks.sliding_window_view(values, window_size)
    return windows.astype(np.float32)


def map_windows_to_points(
    window_predictions: np.ndarray,
    n_points: int,
    window_size: int = 120,
) -> np.ndarray:
    """Map window-level predictions back to point-level.

    Uses center-point strategy: each window's prediction is assigned to
    the center time point of that window. For the first/last half-window
    edges, predictions are duplicated.

    Args:
        window_predictions: Binary predictions (n_windows,)
        n_points: Total number of time points
        window_size: Window size used for sliding

    Returns:
        Point-level binary predictions (n_points,)
    """
    n_windows = len(window_predictions)
    half = window_size // 2
    point_preds = np.zeros(n_points, dtype=int)

    for i in range(n_windows):
        center = i + half
        point_preds[center] = max(point_preds[center], window_predictions[i])

    # Fill edges: first half-window uses first window prediction
    point_preds[:half] = window_predictions[0]
    # Last half-window uses last window prediction
    point_preds[n_windows + half:] = window_predictions[-1]

    return point_preds


def load_and_preprocess(
    input_path: Path,
    labels_path: Path,
    window_size: int = 120,
) -> tuple[torch.Tensor, np.ndarray, pd.DataFrame, dict]:
    """Load chaos metrics and labels, preprocess for Donut.

    Returns:
        (X_windows, y_point_labels, merged_df, norm_params)
    """
    # Load data
    df = pd.read_csv(input_path, parse_dates=["timestamp"])
    labels_df = pd.read_csv(labels_path, parse_dates=["timestamp"])

    # Merge labels onto metrics
    df = df.merge(
        labels_df[["timestamp", "is_anomaly"]],
        on="timestamp", how="left",
    )
    df["is_anomaly"] = df["is_anomaly"].fillna(0).astype(int)

    # Extract values
    values = df["value"].values.astype(np.float64)

    # Min-max normalize to [0, 1]
    min_val, max_val = values.min(), values.max()
    values_norm = (values - min_val) / (max_val - min_val + 1e-8)

    # Build sliding windows
    windows = build_windows(values_norm, window_size)

    # Point-level ground truth
    y_point = df["is_anomaly"].values.astype(int)

    X_tensor = torch.tensor(windows, dtype=torch.float32)
    norm_params = {"min": float(min_val), "max": float(max_val)}

    return X_tensor, y_point, df, norm_params


def train_model(X_train: torch.Tensor) -> tuple[DonutVAE, dict]:
    """Train a Donut VAE model from scratch.

    Args:
        X_train: Training windows tensor (n_windows, window_size)

    Returns:
        (trained_model, training_history)
    """
    input_dim = X_train.size(1)
    model = DonutVAE(
        input_dim=input_dim,
        hidden_dim=500,
        latent_dim=5,
        dropout=0.1,
    )

    trainer = DonutTrainer(
        model=model,
        lr=1e-3,
        weight_decay=1e-5,
        missing_rate=0.1,
        beta=1.0,
        device="auto",
    )

    print(f"  Training on {len(X_train)} windows, input_dim={input_dim}")
    history = trainer.fit(
        X_train=X_train,
        X_val=None,
        batch_size=64,
        epochs=100,
        patience=15,
        verbose=False,
    )

    # Save model
    out_dir = ROOT / "outputs" / "donut"
    out_dir.mkdir(parents=True, exist_ok=True)
    model_path = out_dir / "best_model.pt"
    torch.save(model.state_dict(), model_path)
    print(f"  Model saved to {model_path}")

    return model, history


def load_model(
    model_path: Path,
    input_dim: int,
) -> DonutVAE:
    """Load a pre-trained Donut VAE model.

    Args:
        model_path: Path to .pt checkpoint
        input_dim: Expected input dimension (window_size)

    Returns:
        Loaded DonutVAE model in eval mode
    """
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = DonutVAE(input_dim=input_dim, hidden_dim=500, latent_dim=5, dropout=0.1)
    state_dict = torch.load(model_path, map_location=device, weights_only=True)
    model.load_state_dict(state_dict)
    model.to(device)
    model.eval()
    return model


def main() -> None:
    parser = argparse.ArgumentParser(description="Donut on chaos data")
    parser.add_argument("--input", required=True, help="Metrics CSV from fault collection")
    parser.add_argument("--labels", required=True, help="Ground-truth labels CSV")
    parser.add_argument(
        "--model", type=str, default=None,
        help="Path to pre-trained Donut VAE model (.pt). Defaults to outputs/donut/best_model.pt",
    )
    parser.add_argument("--train", action="store_true", help="Train from scratch if no model available")
    parser.add_argument("--window-size", type=int, default=120, help="Sliding window size")
    parser.add_argument("--epochs", type=int, default=100, help="Training epochs (if training)")
    parser.add_argument("--tolerance", type=int, default=5, help="Window matching tolerance")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    input_path = Path(args.input)
    labels_path = Path(args.labels)
    out_dir = ROOT / "outputs"
    fig_dir = out_dir / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load and preprocess
    print("=== Loading chaos data ===")
    X_windows, y_point, df, norm_params = load_and_preprocess(
        input_path, labels_path, args.window_size,
    )
    print(f"  Points: {len(df)}, Window size: {args.window_size}")
    print(f"  Windows: {len(X_windows)}, Anomaly points: {y_point.sum()}")

    # 2. Load or train model
    model_path = Path(args.model) if args.model else (ROOT / "outputs" / "donut" / "best_model.pt")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    if model_path.exists():
        print(f"\n=== Loading pre-trained model: {model_path} ===")
        model = load_model(model_path, X_windows.size(1))
    elif args.train:
        print("\n=== No pre-trained model found. Training from scratch ===")
        model, history = train_model(X_windows)
    else:
        print("\n=== No pre-trained model found. Training from scratch (auto) ===")
        model, history = train_model(X_windows)

    # 3. Create detector and detect
    print("\n=== Running Donut detection ===")
    detector = DonutDetector(
        model=model,
        device="auto",
        n_samples=100,
        use_kde=True,
    )
    # Fit KDE on all windows (self-supervised threshold)
    detector.fit_kde(X_windows, percentile=95.0)
    print(f"  KDE threshold: {detector.threshold:.4f}")

    # Detect on all windows
    window_scores, window_predictions = detector.detect(X_windows)
    print(f"  Window-level anomalies: {window_predictions.sum()}/{len(window_predictions)}")

    # 4. Map window predictions to point-level
    point_predictions = map_windows_to_points(
        window_predictions, len(y_point), args.window_size,
    )
    # Map window scores to points (center-point)
    point_scores = np.zeros(len(y_point), dtype=np.float32)
    half = args.window_size // 2
    n_windows = len(window_scores)
    for i in range(n_windows):
        center = i + half
        point_scores[center] = max(point_scores[center], window_scores[i])
    point_scores[:half] = window_scores[0]
    point_scores[n_windows + half:] = window_scores[-1]

    # Save scored results
    scored = df.copy()
    scored["donut_score"] = point_scores
    scored["donut_threshold"] = detector.threshold if detector.threshold else 0.0
    scored["predicted_anomaly"] = point_predictions
    scored.to_csv(out_dir / "chaos_metrics_donut_scores.csv", index=False)

    # 5. Compute metrics
    y_true = y_point
    y_pred = point_predictions

    tp = int(np.sum((y_pred == 1) & (y_true == 1)))
    fp = int(np.sum((y_pred == 1) & (y_true == 0)))
    fn = int(np.sum((y_pred == 0) & (y_true == 1)))
    tn = int(np.sum((y_pred == 0) & (y_true == 0)))

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    # Window-level metrics
    true_indices = np.where(y_true == 1)[0]
    pred_indices = np.where(y_pred == 1)[0]
    n_true_windows, caught, n_pred_windows = window_match(
        pred_indices, true_indices, args.tolerance,
    )
    window_precision = caught / n_pred_windows if n_pred_windows > 0 else 0.0
    window_recall = caught / n_true_windows if n_true_windows > 0 else 1.0
    window_f1 = (
        2 * window_precision * window_recall / (window_precision + window_recall)
        if (window_precision + window_recall) > 0 else 0.0
    )

    summary = {
        "algorithm": "Donut",
        "source": str(input_path),
        "window_size": args.window_size,
        "points": int(len(scored)),
        "true_points": int(y_true.sum()),
        "predicted_points": int(y_pred.sum()),
        "threshold": float(detector.threshold) if detector.threshold else 0.0,
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "point_precision": round(precision, 4),
        "point_recall": round(recall, 4),
        "point_f1": round(f1, 4),
        "window_true": n_true_windows,
        "window_caught": caught,
        "window_predicted": n_pred_windows,
        "window_precision": round(window_precision, 4),
        "window_recall": round(window_recall, 4),
        "window_f1": round(window_f1, 4),
    }
    (out_dir / "chaos_donut_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8",
    )

    print(f"\n=== Donut Results ===")
    print(f"  Point-wise:  P={precision:.4f} R={recall:.4f} F1={f1:.4f}")
    print(f"  Window-level: P={window_precision:.4f} R={window_recall:.4f} F1={window_f1:.4f}")
    print(f"  TP={tp} FP={fp} TN={tn} FN={fn}")

    # 6. Detection result figure
    plt.figure(figsize=(12, 4.8))
    plt.plot(scored["timestamp"], scored["value"], label="latency p95", linewidth=1.4)
    true_pts = scored[scored["is_anomaly"] == 1]
    pred_pts = scored[scored["predicted_anomaly"] == 1]
    plt.scatter(
        true_pts["timestamp"], true_pts["value"],
        color="#d62728", s=28, label="true (fault window)",
    )
    plt.scatter(
        pred_pts["timestamp"], pred_pts["value"],
        facecolors="none", edgecolors="#2ca02c", s=70, label="Donut detected",
    )
    plt.title("Donut detection on ChaosMesh fault-injected metrics")
    plt.xlabel("Time")
    plt.ylabel("p95 latency (ms)")
    plt.grid(alpha=0.25)
    plt.legend(loc="upper right")
    plt.tight_layout()
    plt.savefig(fig_dir / "chaos_donut_detection_result.png", dpi=180)
    plt.close()
    print(f"  Figure saved to {fig_dir / 'chaos_donut_detection_result.png'}")

    # Also output JSON to stdout for pipeline consumption
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
