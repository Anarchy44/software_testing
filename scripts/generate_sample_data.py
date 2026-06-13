from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"


def main() -> None:
    rng = np.random.default_rng(20260610)
    n = 720
    t = np.arange(n)
    seasonal = 180 + 36 * np.sin(2 * np.pi * t / 60) + 12 * np.sin(2 * np.pi * t / 15)
    trend = 0.025 * t
    noise = rng.normal(0, 4.5, n)
    latency = seasonal + trend + noise

    labels = np.zeros(n, dtype=int)
    anomaly_windows = {
        185: 84,
        332: -76,
        486: 96,
        612: 92,
    }
    for idx, delta in anomaly_windows.items():
        latency[idx : idx + 5] += delta
        # Label transition edges (FluxEV detects std-dev change points)
        labels[idx] = 1       # rise edge
        labels[idx + 5] = 1   # fall-back edge

    # A short missing segment to exercise preprocessing.
    latency[250:254] = np.nan

    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-06-10 08:00:00", periods=n, freq="min"),
            "service": "frontend",
            "metric": "request_latency_ms_p95",
            "value": latency,
            "is_anomaly": labels,
        }
    )
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(DATA_DIR / "sample_prometheus_metrics.csv", index=False)
    print(f"wrote {DATA_DIR / 'sample_prometheus_metrics.csv'}")


if __name__ == "__main__":
    main()
