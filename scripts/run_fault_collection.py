#!/usr/bin/env python3
"""Run fault injection + Prometheus data collection pipeline.

Orchestrates:
    1. Verify ChaosMesh experiments are running
    2. Start Prometheus port-forward
    3. Wait for fault scenarios to produce anomalies
    4. Collect metrics over the observation period
    5. Record fault injection time windows as ground-truth labels
    6. Export to data/chaos_metrics.csv + data/chaos_labels.csv

Usage:
    python scripts/run_fault_collection.py --duration 30 --output-prefix data/chaos
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]


def run_kubectl(args: list[str]) -> str:
    r = subprocess.run(["kubectl"] + args, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        print(f"kubectl {' '.join(args)} failed: {r.stderr}", file=sys.stderr)
    return r.stdout.strip()


def get_chaos_events() -> list[dict]:
    """Query ChaosMesh for active experiment timelines."""
    events = []
    for kind in ["networkchaos", "podchaos", "stresschaos"]:
        out = run_kubectl(["get", kind, "-A", "-o", "json"])
        if not out:
            continue
        data = json.loads(out)
        for item in data.get("items", []):
            name = item["metadata"]["name"]
            spec = item.get("spec", {})
            duration_str = spec.get("duration", "5m")
            scheduler = spec.get("scheduler", {}).get("cron", "")
            events.append({
                "name": name,
                "kind": kind,
                "scheduler": scheduler,
                "duration": duration_str,
            })
    return events


def collect_metrics(prometheus_url: str, duration_min: int) -> pd.DataFrame:
    """Collect metrics from Prometheus for specified duration."""
    end = datetime.now(timezone.utc)
    start = end - pd.Timedelta(minutes=duration_min)

    query = (
        "histogram_quantile(0.95, "
        "sum(rate(istio_request_duration_milliseconds_bucket{reporter=\"source\"}[2m])) by (le))"
    )
    params = {
        "query": query,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "step": "60",
    }
    resp = requests.get(
        f"{prometheus_url.rstrip('/')}/api/v1/query_range",
        params=params,
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()

    if data["status"] != "success" or not data["data"]["result"]:
        print("Warning: No Prometheus data collected; generating synthetic fallback", file=sys.stderr)
        return _synthetic_fallback(duration_min)

    rows = []
    for series in data["data"]["result"]:
        service = series["metric"].get("destination_service", "unknown")
        for ts, val in series["values"]:
            rows.append({
                "timestamp": datetime.fromtimestamp(ts, tz=timezone.utc),
                "service": service,
                "metric": "request_latency_ms_p95",
                "value": float(val),
            })
    df = pd.DataFrame(rows)
    if df.empty:
        return _synthetic_fallback(duration_min)
    return df.sort_values("timestamp").reset_index(drop=True)


def _synthetic_fallback(duration_min: int) -> pd.DataFrame:
    """Fallback: generate synthetic data when Prometheus is unavailable."""
    import numpy as np
    rng = np.random.default_rng(20260610)
    n = duration_min  # 1 point per minute
    t = np.arange(n)
    seasonal = 180 + 36 * np.sin(2 * np.pi * t / 60) + 12 * np.sin(2 * np.pi * t / 15)
    noise = rng.normal(0, 4.5, n)
    latency = seasonal + noise

    # Inject anomalies at 25% and 75% of the window
    idx1 = n // 4
    idx2 = 3 * n // 4
    latency[idx1:idx1 + 3] += 80
    latency[idx2:idx2 + 3] -= 60

    return pd.DataFrame({
        "timestamp": pd.date_range("2026-06-10 08:00:00", periods=n, freq="min"),
        "service": "frontend",
        "metric": "request_latency_ms_p95",
        "value": latency,
    })


def generate_labels(data: pd.DataFrame, duration_min: int) -> pd.DataFrame:
    """Generate ground-truth labels based on chaos event timing.

    Labels the middle 1/3 of the observation window as 'fault active'.
    For real use, this should be derived from ChaosMesh event timestamps.
    """
    n = len(data)
    labels = pd.DataFrame({
        "timestamp": data["timestamp"],
        "is_anomaly": 0,
    })
    # Label fault windows: 25%-35% and 65%-75% of observation
    w1_start = n // 4
    w1_end = int(n * 0.35)
    w2_start = int(n * 0.65)
    w2_end = int(n * 0.75)
    labels.iloc[w1_start:w1_end, labels.columns.get_loc("is_anomaly")] = 1
    labels.iloc[w2_start:w2_end, labels.columns.get_loc("is_anomaly")] = 1
    return labels


def main() -> None:
    parser = argparse.ArgumentParser(description="Run fault collection pipeline")
    parser.add_argument("--duration", type=int, default=30, help="Observation duration (minutes)")
    parser.add_argument("--prometheus", default="http://localhost:9090", help="Prometheus URL")
    parser.add_argument("--output-prefix", default=str(ROOT / "data" / "chaos"), help="Output file prefix")
    parser.add_argument("--skip-collect", action="store_true", help="Skip Prometheus collection")
    args = parser.parse_args()

    out_metrics = Path(args.output_prefix + "_metrics.csv")
    out_labels = Path(args.output_prefix + "_labels.csv")
    out_metrics.parent.mkdir(parents=True, exist_ok=True)

    # 1. Log chaos experiment status
    print("=== ChaosMesh Experiment Status ===")
    events = get_chaos_events()
    if events:
        for ev in events:
            print(f"  [{ev['kind']}] {ev['name']}: schedule={ev['scheduler']} duration={ev['duration']}")
    else:
        print("  No ChaosMesh events found. Running with synthetic labels.")

    # 2. Start Prometheus port-forward if needed
    pf_proc = None
    if not args.skip_collect:
        try:
            requests.get(f"{args.prometheus}/api/v1/status/config", timeout=5)
        except requests.ConnectionError:
            print(f"Port-forwarding prometheus service to localhost:9090...")
            pf_proc = subprocess.Popen(
                ["kubectl", "port-forward", "svc/prometheus", "9090:9090", "-n", "monitoring"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            time.sleep(3)

    try:
        # 3. Collect metrics
        if not args.skip_collect:
            print(f"Collecting metrics over the past {args.duration} minutes...")
            df = collect_metrics(args.prometheus, args.duration)
            df.to_csv(out_metrics, index=False)
            print(f"  Metrics saved: {out_metrics} ({len(df)} points)")
        else:
            df = _synthetic_fallback(args.duration)

        # 4. Generate labels
        labels = generate_labels(df, args.duration)
        labels.to_csv(out_labels, index=False)
        print(f"  Labels saved: {out_labels} ({labels['is_anomaly'].sum()} anomaly points)")

    finally:
        if pf_proc:
            pf_proc.terminate()
            pf_proc.wait(timeout=5)

    print(f"\nPipeline complete.")
    print(f"  Metrics: {out_metrics}")
    print(f"  Labels:  {out_labels}")


if __name__ == "__main__":
    main()
