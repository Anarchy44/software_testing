#!/usr/bin/env python3
"""Run Donut anomaly detection experiment.

Trains a Donut VAE model on KPI time series data and evaluates anomaly
detection performance. Compares with FluxEV results.

Usage:
    python scripts/run_donut_experiment.py --input data/sample_prometheus_metrics.csv

Reference:
    "Unsupervised Anomaly Detection via Variational Auto-Encoder for
    Seasonal KPIs in Web Applications" (WWW 2018)
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import matplotlib.pyplot as plt

# Add src to path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from donut import DonutVAE, DonutTrainer, DonutDetector


def load_and_preprocess_data(input_path: Path, window_size: int = 120):
    """Load KPI data and create sliding windows.

    Args:
        input_path: Path to CSV file with 'value' column
        window_size: Size of sliding window

    Returns:
        Tuple of (windows, labels, original_data)
    """
    # Load data
    df = pd.read_csv(input_path)

    # Extract values (assume 'value' or first numeric column)
    if "value" in df.columns:
        values = df["value"].values
    else:
        values = df.select_dtypes(include=[np.number]).iloc[:, 0].values

    # Normalize to [0, 1]
    min_val, max_val = values.min(), values.max()
    values_norm = (values - min_val) / (max_val - min_val + 1e-8)

    # Create sliding windows
    n_windows = len(values_norm) - window_size + 1
    windows = []
    labels = []

    for i in range(n_windows):
        window = values_norm[i : i + window_size]
        windows.append(window)

        # Label based on ground truth if available
        if "is_anomaly" in df.columns:
            label = df["is_anomaly"].iloc[i : i + window_size].max()
        else:
            # Heuristic: mark windows with extreme values as anomalous
            label = 1 if (window.max() > 0.95 or window.min() < 0.05) else 0
        labels.append(label)

    windows = np.array(windows, dtype=np.float32)
    labels = np.array(labels, dtype=np.float32)

    return windows, labels, {"min": min_val, "max": max_val}


def train_model(X_train: torch.Tensor, X_val: torch.Tensor | None = None):
    """Train Donut VAE model.

    Args:
        X_train: Training data
        X_val: Optional validation data

    Returns:
        Trained model and training history
    """
    input_dim = X_train.size(1)

    # Create model
    model = DonutVAE(
        input_dim=input_dim,
        hidden_dim=500,
        latent_dim=5,
        dropout=0.1,
    )

    print(f"Model architecture:")
    print(f"  Input dim: {input_dim}")
    print(f"  Hidden dim: 500")
    print(f"  Latent dim: 5")
    print(f"  Parameters: {sum(p.numel() for p in model.parameters()):,}")

    # Create trainer
    trainer = DonutTrainer(
        model=model,
        lr=1e-3,
        weight_decay=1e-5,
        missing_rate=0.1,
        beta=1.0,
        device="auto",
    )

    # Train
    history = trainer.fit(
        X_train=X_train,
        X_val=X_val,
        batch_size=64,
        epochs=100,
        patience=15,
        verbose=True,
    )

    return model, trainer, history


def evaluate_model(model, detector, X_test: np.ndarray, y_test: np.ndarray):
    """Evaluate anomaly detection performance.

    Args:
        model: Trained DonutVAE
        detector: DonutDetector instance
        X_test: Test windows
        y_test: Ground truth labels

    Returns:
        Dictionary of metrics
    """
    X_tensor = torch.tensor(X_test, dtype=torch.float32)

    # Detect anomalies
    scores, predictions = detector.detect(X_tensor)

    # Compute metrics
    tp = np.sum((predictions == 1) & (y_test == 1))
    fp = np.sum((predictions == 1) & (y_test == 0))
    fn = np.sum((predictions == 0) & (y_test == 1))
    tn = np.sum((predictions == 0) & (y_test == 0))

    precision = tp / (tp + fp + 1e-8)
    recall = tp / (tp + fn + 1e-8)
    f1 = 2 * precision * recall / (precision + recall + 1e-8)

    metrics = {
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "true_positives": int(tp),
        "false_positives": int(fp),
        "true_negatives": int(tn),
        "false_negatives": int(fn),
        "threshold": float(detector.threshold) if detector.threshold else None,
    }

    return metrics, scores, predictions


def plot_results(
    history: dict,
    scores: np.ndarray,
    predictions: np.ndarray,
    y_test: np.ndarray,
    output_dir: Path,
):
    """Plot training and detection results.

    Args:
        history: Training history
        scores: Anomaly scores
        predictions: Predicted labels
        y_test: Ground truth labels
        output_dir: Output directory for plots
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Plot 1: Training loss curve
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))

    axes[0].plot(history["epoch"], history["train_loss"], label="Train Loss")
    axes[0].set_xlabel("Epoch")
    axes[0].set_ylabel("Loss")
    axes[0].set_title("Training Loss Curve")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)

    # Plot 2: Anomaly scores distribution
    axes[1].hist(scores[y_test == 0], bins=50, alpha=0.5, label="Normal", density=True)
    if np.any(y_test == 1):
        axes[1].hist(
            scores[y_test == 1], bins=50, alpha=0.5, label="Anomaly", density=True
        )
    axes[1].set_xlabel("Anomaly Score")
    axes[1].set_ylabel("Density")
    axes[1].set_title("Score Distribution")
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)

    # Plot 3: Precision-Recall vs Threshold
    thresholds = np.percentile(scores, np.arange(50, 100, 2))
    precisions = []
    recalls = []
    for thresh in thresholds:
        preds = (scores > thresh).astype(int)
        tp = np.sum((preds == 1) & (y_test == 1))
        fp = np.sum((preds == 1) & (y_test == 0))
        fn = np.sum((preds == 0) & (y_test == 1))
        prec = tp / (tp + fp + 1e-8)
        rec = tp / (tp + fn + 1e-8)
        precisions.append(prec)
        recalls.append(rec)

    axes[2].plot(thresholds, precisions, label="Precision")
    axes[2].plot(thresholds, recalls, label="Recall")
    axes[2].set_xlabel("Threshold")
    axes[2].set_ylabel("Score")
    axes[2].set_title("Precision-Recall vs Threshold")
    axes[2].legend()
    axes[2].grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_dir / "donut_training_and_detection.png", dpi=300, bbox_inches="tight")
    plt.close()

    # Plot 4: Anomaly score timeline
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(scores, label="Anomaly Score", color="steelblue")
    ax.axhline(
        y=np.median(scores), color="r", linestyle="--", label=f"Median ({np.median(scores):.2f})"
    )
    if np.any(y_test == 1):
        anomaly_indices = np.where(y_test == 1)[0]
        ax.scatter(
            anomaly_indices,
            scores[anomaly_indices],
            color="red",
            s=50,
            marker="x",
            label="True Anomaly",
            zorder=5,
        )
    ax.set_xlabel("Window Index")
    ax.set_ylabel("Anomaly Score")
    ax.set_title("Donut Anomaly Scores Over Time")
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_dir / "donut_score_timeline.png", dpi=300, bbox_inches="tight")
    plt.close()

    print(f"Plots saved to {output_dir}")


def main():
    parser = argparse.ArgumentParser(description="Run Donut anomaly detection experiment")
    parser.add_argument(
        "--input",
        type=str,
        default=str(ROOT / "data" / "sample_prometheus_metrics.csv"),
        help="Input CSV file with KPI data",
    )
    parser.add_argument("--window-size", type=int, default=120, help="Sliding window size")
    parser.add_argument("--epochs", type=int, default=100, help="Training epochs")
    parser.add_argument("--batch-size", type=int, default=64, help="Batch size")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    # Set random seeds
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    input_path = Path(args.input)
    out_dir = ROOT / "outputs" / "donut"
    fig_dir = out_dir / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Donut Anomaly Detection Experiment")
    print("=" * 60)

    # 1. Load and preprocess data
    print("\n[1/4] Loading and preprocessing data...")
    windows, labels, norm_params = load_and_preprocess_data(input_path, args.window_size)
    print(f"  Total windows: {len(windows)}")
    print(f"  Anomalous windows: {labels.sum()} ({100*labels.mean():.1f}%)")

    # Split into train/test (80/20)
    n_train = int(0.8 * len(windows))
    X_train = windows[:n_train]
    y_train = labels[:n_train]
    X_test = windows[n_train:]
    y_test = labels[n_train:]

    print(f"  Train: {len(X_train)}, Test: {len(X_test)}")

    # Convert to tensors
    X_train_tensor = torch.tensor(X_train, dtype=torch.float32)
    X_test_tensor = torch.tensor(X_test, dtype=torch.float32)

    # 2. Train model
    print("\n[2/4] Training Donut VAE model...")
    model, trainer, history = train_model(X_train_tensor, None)

    # Save training history
    history_path = out_dir / "training_history.json"
    with open(history_path, "w") as f:
        json.dump(history, f, indent=2)
    print(f"  Training history saved to {history_path}")

    # 3. Create detector and fit KDE
    print("\n[3/4] Fitting KDE threshold estimator...")
    detector = DonutDetector(
        model=model,
        device="auto",
        n_samples=100,
        use_kde=True,
    )
    detector.fit_kde(X_train_tensor, percentile=95.0)
    print(f"  Threshold: {detector.threshold:.4f}")

    # 4. Evaluate on test set
    print("\n[4/4] Evaluating on test set...")
    metrics, scores, predictions = evaluate_model(model, detector, X_test, y_test)

    print("\nResults:")
    print(f"  Precision: {metrics['precision']:.4f}")
    print(f"  Recall:    {metrics['recall']:.4f}")
    print(f"  F1 Score:  {metrics['f1']:.4f}")
    print(f"  TP: {metrics['true_positives']}, FP: {metrics['false_positives']}")
    print(f"  TN: {metrics['true_negatives']}, FN: {metrics['false_negatives']}")

    # Save results
    results = {
        "algorithm": "Donut",
        "window_size": args.window_size,
        "epochs": args.epochs,
        "training_samples": len(X_train),
        "test_samples": len(X_test),
        **metrics,
    }

    results_path = out_dir / "experiment_summary.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {results_path}")

    # Plot results
    print("\nGenerating plots...")
    plot_results(history, scores, predictions, y_test, fig_dir)

    print("\n" + "=" * 60)
    print("Experiment complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
