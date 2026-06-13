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


def auto_params(n_points: int, period: int = 60) -> dict:
    """Auto-scale FluxEV parameters for small datasets.

    Paper defaults assume millions of points. For smaller datasets,
    reduce window sizes and period count so that enough points
    remain for calibration and detection.
    """
    if n_points >= 5000:
        # Paper defaults for large datasets
        return {"s": 10, "alpha": 0.3, "d": 2, "p": 5, "k": 1000}

    if n_points >= 1000:
        return {"s": 8, "alpha": 0.35, "d": 1, "p": 3, "k": 300}

    if n_points >= 400:
        return {"s": 5, "alpha": 0.4, "d": 1, "p": 2, "k": 150}

    # Very small dataset
    return {"s": 3, "alpha": 0.5, "d": 1, "p": 2, "k": 50}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(ROOT / "data" / "sample_prometheus_metrics.csv"))
    parser.add_argument("--period", type=int, default=60, help="Period length l")
    parser.add_argument("--s", type=int, default=None, help="EWMA / first-smooth window (auto if unset)")
    parser.add_argument("--alpha", type=float, default=None, help="EWMA decay factor")
    parser.add_argument("--d", type=int, default=None, help="Drift half-window")
    parser.add_argument("--p", type=int, default=None, help="Number of past periods")
    parser.add_argument("--k", type=int, default=None, help="POT initialization points")
    parser.add_argument("--risk", type=float, default=0.01, help="False-positive risk")
    parser.add_argument("--base-quantile", type=float, default=0.98, help="POT base quantile")
    parser.add_argument("--no-auto", action="store_true", help="Use paper defaults (s=10,d=2,p=5,k=1000)")
    args = parser.parse_args()

    input_path = Path(args.input)
    out_dir = ROOT / "outputs" / "fluxev"
    fig_dir = out_dir / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(input_path, parse_dates=["timestamp"])
    n_points = len(df)

    # Build detector parameters
    if args.no_auto:
        params = {"s": args.s or 10, "alpha": args.alpha or 0.3, "d": args.d or 2,
                  "p": args.p or 5, "k": args.k or 1000}
    else:
        params = auto_params(n_points, args.period)
    if args.s is not None:
        params["s"] = args.s
    if args.alpha is not None:
        params["alpha"] = args.alpha
    if args.d is not None:
        params["d"] = args.d
    if args.p is not None:
        params["p"] = args.p
    if args.k is not None:
        params["k"] = args.k

    warmup_expected = 2 * params["s"] + params["d"] + args.period * (params["p"] - 1)
    print(f"Data points: {n_points}")
    print(f"Parameters: l={args.period} s={params['s']} alpha={params['alpha']} "
          f"d={params['d']} p={params['p']} k={params['k']} risk={args.risk} "
          f"base_quantile={args.base_quantile}")
    print(f"Startup cost (warmup): {warmup_expected} points")
    print(f"Pot calibration budget: {params['k']} points")

    detector = FluxEVDetector(
        l=args.period,
        s=params["s"],
        alpha=params["alpha"],
        d=params["d"],
        p=params["p"],
        k=params["k"],
        risk=args.risk,
        base_quantile=args.base_quantile,
    )
    result = detector.detect(df["value"])

    scored = df.copy()
    scored["fluxev_score"] = result.score
    scored["fluxev_F"] = result.F
    scored["fluxev_S"] = result.S
    scored["threshold"] = result.threshold
    scored["predicted_anomaly"] = result.labels
    scored.to_csv(out_dir / "metrics_with_scores.csv", index=False)

    y_true = scored["is_anomaly"].astype(int).to_numpy()
    y_pred = scored["predicted_anomaly"].astype(int).to_numpy()
    precision = float(precision_score(y_true, y_pred, zero_division=0))
    recall = float(recall_score(y_true, y_pred, zero_division=0))
    f1 = float(f1_score(y_true, y_pred, zero_division=0))

    # Adjusted recall: count anomaly windows caught (FluxEV detects edges, not plateaus)
    tolerance = 4
    true_indices = np.where(y_true == 1)[0]
    true_windows_list = []
    if len(true_indices) > 0:
        ws = true_indices[0]
        for k in range(1, len(true_indices)):
            if true_indices[k] > true_indices[k - 1] + tolerance + 1:
                true_windows_list.append(ws)
                ws = true_indices[k]
        true_windows_list.append(ws)
    y_pred_dilated = np.zeros_like(y_pred)
    pred_indices = np.where(y_pred == 1)[0]
    for pi in pred_indices:
        lo = max(0, pi - tolerance)
        hi = min(len(y_pred_dilated), pi + tolerance + 1)
        y_pred_dilated[lo:hi] = 1
    adjusted_caught = sum(1 for tw in true_windows_list if y_pred_dilated[tw] == 1)
    adjusted_recall = adjusted_caught / len(true_windows_list) if true_windows_list else 1.0

    summary = {
        "input": str(input_path),
        "points": int(len(scored)),
        "true_anomalies": int(y_true.sum()),
        "predicted_anomalies": int(y_pred.sum()),
        "threshold": float(result.threshold),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "adjusted_recall": round(adjusted_recall, 4),
        "true_windows": len(true_windows_list),
        "params": {
            "s": params["s"],
            "alpha": params["alpha"],
            "d": params["d"],
            "p": params["p"],
            "l": args.period,
            "k": params["k"],
            "risk": args.risk,
            "base_quantile": args.base_quantile,
        },
    }
    (out_dir / "experiment_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # --- Figure 1: Detection result ---
    plt.figure(figsize=(12, 4.8))
    plt.plot(scored["timestamp"], result.values, label="latency p95", linewidth=1.4)
    true_points = scored[scored["is_anomaly"] == 1]
    pred_points = scored[scored["predicted_anomaly"] == 1]
    plt.scatter(true_points["timestamp"], true_points["value"], color="#d62728", s=28, label="true anomaly")
    plt.scatter(pred_points["timestamp"], pred_points["value"], facecolors="none",
                edgecolors="#1f77b4", s=70, label="FluxEV detected")
    plt.title("FluxEV anomaly detection (paper-aligned) on Prometheus-like latency KPI")
    plt.xlabel("Time")
    plt.ylabel("p95 latency (ms)")
    plt.grid(alpha=0.25)
    plt.legend(loc="upper right")
    plt.tight_layout()
    plt.savefig(fig_dir / "fluxev_detection_result.png", dpi=180)
    plt.close()

    # --- Figure 2: Score + threshold ---
    plt.figure(figsize=(12, 4.2))
    plt.plot(scored["timestamp"], result.score, color="#2ca02c", label="FluxEV score S", linewidth=1.3)
    plt.axhline(result.threshold, color="#d62728", linestyle="--",
                label=f"threshold={result.threshold:.3f}")
    plt.title("Anomaly score S (after two-step smoothing) and automatic threshold")
    plt.xlabel("Time")
    plt.ylabel("score S")
    plt.grid(alpha=0.25)
    plt.legend(loc="upper right")
    plt.tight_layout()
    plt.savefig(fig_dir / "fluxev_score_threshold.png", dpi=180)
    plt.close()

    # --- Figure 3: F (first-step smoothing) vs S (second-step) ---
    plt.figure(figsize=(12, 4.2))
    plt.plot(scored["timestamp"], result.F, color="#ff7f0e", label="F (after 1st smooth)", linewidth=1.0, alpha=0.8)
    plt.plot(scored["timestamp"], result.S, color="#2ca02c", label="S (after 2nd smooth)", linewidth=1.3)
    plt.axhline(result.threshold, color="#d62728", linestyle="--",
                label=f"threshold={result.threshold:.3f}")
    plt.title("Fluctuation F (first-step) vs anomaly score S (second-step)")
    plt.xlabel("Time")
    plt.ylabel("value")
    plt.grid(alpha=0.25)
    plt.legend(loc="upper right")
    plt.tight_layout()
    plt.savefig(fig_dir / "fluxev_F_vs_S.png", dpi=180)
    plt.close()

    # --- Figure 4: Score distribution histogram ---
    plt.figure(figsize=(10, 4.0))
    warmup = detector.warmup
    scores_detect = result.S[warmup:]
    plt.hist(scores_detect, bins=60, color="#2ca02c", alpha=0.7, edgecolor="white")
    plt.axvline(result.threshold, color="#d62728", linestyle="--",
                label=f"threshold={result.threshold:.3f}")
    plt.title("Score S distribution (post-warmup) — should be mostly near-zero with extreme tail")
    plt.xlabel("score S")
    plt.ylabel("frequency")
    plt.legend()
    plt.tight_layout()
    plt.savefig(fig_dir / "fluxev_score_distribution.png", dpi=180)
    plt.close()

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
