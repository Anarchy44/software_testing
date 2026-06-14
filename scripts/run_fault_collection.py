#!/usr/bin/env python3
"""Run fault injection + Prometheus data collection pipeline.

Orchestrates:
    1. Verify ChaosMesh experiments are running
    2. Start Prometheus port-forward
    3. Wait for fault scenarios to produce anomalies
    4. Collect metrics over the observation period
    5. Record fault injection time windows as ground-truth labels
       (extracted from ChaosMesh CRD Status when available)
    6. Export to data/chaos_metrics.csv + data/chaos_labels.csv

Usage:
    python scripts/run_fault_collection.py --duration 30 --output-prefix data/chaos
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]

# ── PromQL queries for multi-metric collection ──────────────────────────
METRIC_QUERIES = {
    "request_latency_ms_p95": (
        "histogram_quantile(0.95, "
        "sum(rate(istio_request_duration_milliseconds_bucket{reporter=\"source\"}[2m])) by (le))"
    ),
    "error_rate_5xx_pct": (
        "sum(rate(istio_requests_total{reporter=\"source\", response_code=~\"5..\"}[2m]))"
        " / sum(rate(istio_requests_total{reporter=\"source\"}[2m])) * 100"
    ),
    "request_rate_rps": (
        "sum(rate(istio_requests_total{reporter=\"source\"}[2m])) by (destination_service)"
    ),
    "cpu_usage_cores": (
        "sum(rate(container_cpu_usage_seconds_total{namespace=\"default\"}[2m])) by (pod)"
    ),
    "memory_usage_bytes": (
        "sum(container_memory_working_set_bytes{namespace=\"default\"}) by (pod)"
    ),
}

# ChaosMesh CRD kinds to query
CHAOS_KINDS = ["networkchaos", "podchaos", "stresschaos"]


def run_kubectl(args: list[str]) -> str:
    """Run kubectl command, return stdout or empty string on failure."""
    r = subprocess.run(["kubectl"] + args, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        print(f"kubectl {' '.join(args)} failed: {r.stderr}", file=sys.stderr)
    return r.stdout.strip()


def parse_duration_to_seconds(duration_str: str) -> int:
    """Parse Kubernetes duration string (e.g. '3m', '1h', '10m30s') to seconds."""
    duration_str = duration_str.strip().lower()
    total = 0
    pattern = re.compile(r"(\d+)(h|m|s)")
    for match in pattern.finditer(duration_str):
        value = int(match.group(1))
        unit = match.group(2)
        if unit == "h":
            total += value * 3600
        elif unit == "m":
            total += value * 60
        elif unit == "s":
            total += value
    return total


def get_chaos_events() -> list[dict]:
    """Query ChaosMesh CRD Status for real experiment timelines.

    Extracts:
      - name, kind (networkchaos/podchaos/stresschaos)
      - spec.duration
      - status.conditions[].startTime (when experiment actually started)
      - status.conditions[].endTime (when experiment ended, if completed)
      - fault_type label for classification

    Returns:
        List of dicts with chaos event details including real timestamps.
    """
    events = []
    for kind in CHAOS_KINDS:
        out = run_kubectl(["get", kind, "-A", "-o", "json"])
        if not out:
            continue
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            continue

        for item in data.get("items", []):
            name = item["metadata"]["name"]
            namespace = item["metadata"].get("namespace", "default")
            spec = item.get("spec", {})
            status = item.get("status", {})
            duration_str = spec.get("duration", "5m")
            scheduler = spec.get("scheduler", {}).get("cron", "")

            # Try to extract real start/end times from CRD status
            start_time = None
            end_time = None
            conditions = status.get("conditions", [])
            for cond in conditions:
                cond_type = cond.get("type", "")
                if cond_type in ("AllRecovered", "Selected", "AllInjected") and "startTime" in cond:
                    parsed = _parse_iso_time(cond["startTime"])
                    if parsed:
                        start_time = parsed
                elif cond_type in ("AllRecovered", "AllInjected") and "endTime" in cond:
                    parsed = _parse_iso_time(cond["endTime"])
                    if parsed:
                        end_time = parsed

            # Fallback: if no startTime in conditions, check experiment status
            if not start_time:
                experiment = status.get("experiment", {})
                if "startTime" in experiment:
                    start_time = _parse_iso_time(experiment["startTime"])
                if "endTime" in experiment:
                    end_time = _parse_iso_time(experiment["endTime"])

            # Map kind to fault_type label
            fault_type_map = {
                "networkchaos": "network-delay",
                "podchaos": "pod-kill",
                "stresschaos": "cpu-stress",
            }

            events.append({
                "name": name,
                "namespace": namespace,
                "kind": kind,
                "fault_type": fault_type_map.get(kind, kind),
                "scheduler": scheduler,
                "duration": duration_str,
                "duration_seconds": parse_duration_to_seconds(duration_str),
                "start_time": start_time,
                "end_time": end_time,
            })
    return events


def _parse_iso_time(time_str: str) -> Optional[datetime]:
    """Parse ISO 8601 timestamp from ChaosMesh CRD."""
    if not time_str:
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
    ):
        try:
            dt = datetime.strptime(time_str, fmt)
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        except ValueError:
            continue
    return None


def _parse_metrics_to_df(data: dict, metric_name: str) -> pd.DataFrame:
    """Parse Prometheus query_range response into DataFrame."""
    rows = []
    for series in data["data"]["result"]:
        service = series["metric"].get(
            "destination_service",
            series["metric"].get("pod", series["metric"].get("instance", "unknown")),
        )
        for ts, val in series["values"]:
            rows.append({
                "timestamp": datetime.fromtimestamp(ts, tz=timezone.utc),
                "service": service,
                "metric": metric_name,
                "value": float(val),
            })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values("timestamp").reset_index(drop=True)


def collect_metrics(
    prometheus_url: str,
    duration_min: int,
    metrics: list[str] | None = None,
) -> pd.DataFrame:
    """Collect metrics from Prometheus for specified duration.

    Args:
        prometheus_url: Prometheus API URL
        duration_min: Duration of observation window in minutes
        metrics: List of metric names to collect (from METRIC_QUERIES keys).
                 Defaults to ["request_latency_ms_p95"].

    Returns:
        DataFrame with columns [timestamp, service, metric, value]
    """
    if metrics is None:
        metrics = ["request_latency_ms_p95"]

    end = datetime.now(timezone.utc)
    start = end - pd.Timedelta(minutes=duration_min)

    all_rows = []
    for metric_name in metrics:
        query = METRIC_QUERIES.get(metric_name)
        if not query:
            print(f"Warning: unknown metric '{metric_name}', skipping", file=sys.stderr)
            continue

        params = {
            "query": query,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "step": "60",
        }
        try:
            resp = requests.get(
                f"{prometheus_url.rstrip('/')}/api/v1/query_range",
                params=params,
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
            print(f"Warning: Prometheus query for '{metric_name}' failed: {exc}", file=sys.stderr)
            continue

        if data.get("status") != "success" or not data.get("data", {}).get("result"):
            print(f"Warning: no data for metric '{metric_name}'", file=sys.stderr)
            continue

        df_metric = _parse_metrics_to_df(data, metric_name)
        if df_metric is not None and not df_metric.empty:
            all_rows.append(df_metric)

    if not all_rows:
        print("Warning: No Prometheus data collected; generating synthetic fallback", file=sys.stderr)
        return _synthetic_fallback(duration_min)

    combined = pd.concat(all_rows, ignore_index=True)
    return combined.sort_values(["metric", "timestamp"]).reset_index(drop=True)


def _synthetic_fallback(duration_min: int) -> pd.DataFrame:
    """Fallback: generate synthetic data when Prometheus is unavailable."""
    import numpy as np
    rng = np.random.default_rng(20260610)
    n = duration_min  # 1 point per minute
    t = np.arange(n)
    seasonal = 180 + 36 * np.sin(2 * np.pi * t / 60) + 12 * np.sin(2 * np.pi * t / 15)
    noise = rng.normal(0, 4.5, n)
    latency = seasonal + noise

    # Inject synthetic fault windows (aligned with generate_labels fallback)
    w1_start = n // 4
    w1_end = int(n * 0.35)
    w2_start = int(n * 0.65)
    w2_end = int(n * 0.75)
    spike_len = min(3, w1_end - w1_start, w2_end - w2_start)
    latency[w1_start:w1_start + spike_len] += 80
    latency[w2_start:w2_start + spike_len] -= 60

    return pd.DataFrame({
        "timestamp": pd.date_range("2026-06-10 08:00:00", periods=n, freq="min"),
        "service": "frontend",
        "metric": "request_latency_ms_p95",
        "value": latency,
    })


def generate_labels(
    data: pd.DataFrame,
    duration_min: int,
    chaos_events: list[dict] | None = None,
) -> pd.DataFrame:
    """Generate ground-truth labels based on ChaosMesh event timestamps.

    When ChaosMesh CRD Status provides real start_time/end_time, those are used.
    Otherwise falls back to synthetic windows (25%-35% and 65%-75% of observation).

    Args:
        data: Collected metrics DataFrame
        duration_min: Observation duration in minutes
        chaos_events: List of chaos event dicts from get_chaos_events()

    Returns:
        DataFrame with columns [timestamp, is_anomaly, fault_type]
    """
    n = len(data)
    labels = pd.DataFrame({
        "timestamp": data["timestamp"],
        "is_anomaly": 0,
        "fault_type": "",
    })

    # Get unique timestamps in order
    timestamps = data["timestamp"].sort_values().reset_index(drop=True)
    t_min = timestamps.iloc[0]
    t_max = timestamps.iloc[-1]

    real_windows_found = False

    if chaos_events:
        for ev in chaos_events:
            start = ev.get("start_time")
            end = ev.get("end_time")
            fault_type = ev.get("fault_type", ev["kind"])

            if start is not None:
                real_windows_found = True
                # If end_time not available, estimate from start + duration
                if end is None:
                    dur_s = ev.get("duration_seconds", 300)
                    end = start + pd.Timedelta(seconds=dur_s)

                # Mask points within [start, end]
                mask = (timestamps >= start) & (timestamps <= end)
                labels.loc[mask, "is_anomaly"] = 1
                labels.loc[mask, "fault_type"] = fault_type
            elif end is not None:
                # Only end_time available: estimate start from end - duration
                dur_s = ev.get("duration_seconds", 300)
                start = end - pd.Timedelta(seconds=dur_s)
                mask = (timestamps >= start) & (timestamps <= end)
                labels.loc[mask, "is_anomaly"] = 1
                labels.loc[mask, "fault_type"] = fault_type
                real_windows_found = True

    if not real_windows_found:
        print("Warning: No real ChaosMesh timestamps available. "
              "Using synthetic label windows (25%-35%, 65%-75%).", file=sys.stderr)
        # Fallback: synthetic windows
        w1_start = n // 4
        w1_end = int(n * 0.35)
        w2_start = int(n * 0.65)
        w2_end = int(n * 0.75)
        labels.iloc[w1_start:w1_end, labels.columns.get_loc("is_anomaly")] = 1
        labels.iloc[w1_start:w1_end, labels.columns.get_loc("fault_type")] = "synthetic-fault"
        labels.iloc[w2_start:w2_end, labels.columns.get_loc("is_anomaly")] = 1
        labels.iloc[w2_start:w2_end, labels.columns.get_loc("fault_type")] = "synthetic-fault"

    return labels


def main() -> None:
    parser = argparse.ArgumentParser(description="Run fault collection pipeline")
    parser.add_argument("--duration", type=int, default=30, help="Observation duration (minutes)")
    parser.add_argument("--prometheus", default="http://localhost:9090", help="Prometheus URL")
    parser.add_argument("--output-prefix", default=str(ROOT / "data" / "chaos"), help="Output file prefix")
    parser.add_argument("--skip-collect", action="store_true", help="Skip Prometheus collection")
    parser.add_argument(
        "--metrics", nargs="*",
        default=["request_latency_ms_p95"],
        choices=list(METRIC_QUERIES.keys()),
        help="Metrics to collect (default: request_latency_ms_p95)",
    )
    args = parser.parse_args()

    out_metrics = Path(args.output_prefix + "_metrics.csv")
    out_labels = Path(args.output_prefix + "_labels.csv")
    out_metrics.parent.mkdir(parents=True, exist_ok=True)

    # 1. Log chaos experiment status with real timestamps
    print("=== ChaosMesh Experiment Status ===")
    events = get_chaos_events()
    if events:
        for ev in events:
            start_str = ev["start_time"].isoformat() if ev["start_time"] else "unknown"
            end_str = ev["end_time"].isoformat() if ev["end_time"] else "N/A"
            print(f"  [{ev['fault_type']}] {ev['name']}: "
                  f"start={start_str} end={end_str} duration={ev['duration']}")
    else:
        print("  No ChaosMesh events found. Running with synthetic labels.")

    # 2. Start Prometheus port-forward if needed
    pf_proc = None
    if not args.skip_collect:
        try:
            requests.get(f"{args.prometheus}/api/v1/status/config", timeout=5)
        except requests.ConnectionError:
            print("Port-forwarding prometheus service to localhost:9090...")
            pf_proc = subprocess.Popen(
                ["kubectl", "port-forward", "svc/prometheus", "9090:9090", "-n", "monitoring"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            time.sleep(3)

    try:
        # 3. Collect metrics
        if not args.skip_collect:
            print(f"Collecting metrics over the past {args.duration} minutes...")
            print(f"  Metric(s): {', '.join(args.metrics)}")
            df = collect_metrics(args.prometheus, args.duration, args.metrics)
            df.to_csv(out_metrics, index=False)
            print(f"  Metrics saved: {out_metrics} ({len(df)} points)")
        else:
            df = _synthetic_fallback(args.duration)

        # 4. Generate labels from real ChaosMesh timestamps (or synthetic fallback)
        labels = generate_labels(df, args.duration, events)
        labels.to_csv(out_labels, index=False)
        anomaly_count = labels["is_anomaly"].sum()
        fault_types = labels[labels["fault_type"] != ""]["fault_type"].unique().tolist()
        print(f"  Labels saved: {out_labels} ({anomaly_count} anomaly points, "
              f"fault_types: {fault_types})")

    finally:
        if pf_proc:
            pf_proc.terminate()
            pf_proc.wait(timeout=5)

    print(f"\nPipeline complete.")
    print(f"  Metrics: {out_metrics}")
    print(f"  Labels:  {out_labels}")


if __name__ == "__main__":
    main()
