#!/usr/bin/env python3
"""Collect metrics from Prometheus API and export as CSV.

Usage:
    python scripts/collect_from_prometheus.py \\
        --prometheus http://localhost:9090 \\
        --query 'istio_request_duration_milliseconds_bucket' \\
        --start 2026-06-10T08:00:00Z \\
        --end 2026-06-10T20:00:00Z \\
        --step 60 \\
        --output data/prometheus_metrics.csv
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]


def query_range(
    prometheus_url: str,
    query: str,
    start: str,
    end: str,
    step: str = "60",
) -> pd.DataFrame:
    """Query Prometheus range API and return DataFrame."""
    params = {"query": query, "start": start, "end": end, "step": step}
    resp = requests.get(f"{prometheus_url.rstrip('/')}/api/v1/query_range", params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if data["status"] != "success":
        raise RuntimeError(f"Prometheus query failed: {data}")

    results = data["data"]["result"]
    if not results:
        print("Warning: No results from Prometheus query", file=sys.stderr)
        return pd.DataFrame(columns=["timestamp", "value", "metric"])

    rows = []
    for series in results:
        metric_name = series["metric"].get("__name__", query)
        service = series["metric"].get("destination_service", series["metric"].get("job", "unknown"))
        for ts, val in series["values"]:
            rows.append({
                "timestamp": datetime.fromtimestamp(ts, tz=timezone.utc),
                "service": service,
                "metric": metric_name,
                "value": float(val),
            })

    df = pd.DataFrame(rows)
    return df.sort_values(["timestamp", "service"]).reset_index(drop=True)


def query_instant(prometheus_url: str, query: str) -> pd.DataFrame:
    """Query Prometheus instant API."""
    params = {"query": query}
    resp = requests.get(f"{prometheus_url.rstrip('/')}/api/v1/query", params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if data["status"] != "success":
        raise RuntimeError(f"Prometheus query failed: {data}")

    results = data["data"]["result"]
    rows = []
    for series in results:
        metric_name = series["metric"].get("__name__", query)
        service = series["metric"].get("destination_service", series["metric"].get("job", "unknown"))
        ts, val = series["value"]
        rows.append({
            "timestamp": datetime.fromtimestamp(ts, tz=timezone.utc),
            "service": service,
            "metric": metric_name,
            "value": float(val),
        })

    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect Prometheus metrics")
    parser.add_argument("--prometheus", default="http://localhost:9090", help="Prometheus URL")
    parser.add_argument("--query", default="istio_request_duration_milliseconds_bucket", help="PromQL query")
    parser.add_argument("--start", default=None, help="Start time (ISO 8601, default: 4h ago)")
    parser.add_argument("--end", default=None, help="End time (ISO 8601, default: now)")
    parser.add_argument("--step", default="60", help="Query step in seconds")
    parser.add_argument("--output", default=str(ROOT / "data" / "prometheus_metrics.csv"), help="Output CSV path")
    parser.add_argument("--instant", action="store_true", help="Use instant query (single point)")
    args = parser.parse_args()

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if args.instant:
        df = query_instant(args.prometheus, args.query)
    else:
        if args.start is None:
            now = datetime.now(timezone.utc)
            args.start = (now - pd.Timedelta(hours=4)).isoformat()
        if args.end is None:
            args.end = datetime.now(timezone.utc).isoformat()
        df = query_range(args.prometheus, args.query, args.start, args.end, args.step)

    df.to_csv(out_path, index=False)
    print(f"Collected {len(df)} data points to {out_path}")


if __name__ == "__main__":
    main()
