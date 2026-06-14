#!/usr/bin/env python3
"""Unified end-to-end pipeline: ChaosMesh fault injection → Prometheus metrics
collection → FluxEV + Donut anomaly detection → Results comparison.

Pipeline phases:
    apply   — kubectl apply chaos experiments
    wait    — wait for fault duration + warmup buffer
    collect — query Prometheus for metrics
    label   — extract real fault timestamps from ChaosMesh CRD Status
    detect  — run FluxEV and Donut detectors
    compare — generate comparison report and figures
    cleanup — optionally delete chaos experiments

Usage:
    # Full pipeline with all fault types
    python scripts/run_full_pipeline.py \
        --faults all \
        --duration 15 \
        --phases apply,wait,collect,label,detect,compare

    # Single phases for debugging
    python scripts/run_full_pipeline.py --phases detect,compare

    # Specific fault type only
    python scripts/run_full_pipeline.py --faults network-delay --duration 10
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
CHAOS_DIR = ROOT / "k8s" / "chaos-experiments"

# ── Fault type → YAML mapping ──────────────────────────────────────────
FAULT_CONFIGS = {
    "network-delay": CHAOS_DIR / "network-delay.yaml",
    "pod-kill": CHAOS_DIR / "pod-kill.yaml",
    "cpu-stress": CHAOS_DIR / "cpu-stress.yaml",
}

# ── PromQL queries ─────────────────────────────────────────────────────
METRIC_QUERIES = {
    "request_latency_ms_p95": (
        "histogram_quantile(0.95, "
        "sum(rate(istio_request_duration_milliseconds_bucket{reporter=\"source\"}[2m])) by (le))"
    ),
}


# ═══════════════════════════════════════════════════════════════════════
# Phase: apply — kubectl apply chaos experiments
# ═══════════════════════════════════════════════════════════════════════
def phase_apply(faults: list[str]) -> list[str]:
    """Apply ChaosMesh experiments via kubectl.

    Returns list of applied experiment names.
    """
    applied = []
    for fault_type in faults:
        yaml_path = FAULT_CONFIGS.get(fault_type)
        if not yaml_path or not yaml_path.exists():
            print(f"  [SKIP] Unknown fault type '{fault_type}', no YAML found")
            continue

        print(f"  Applying {fault_type} from {yaml_path}...")
        r = subprocess.run(
            ["kubectl", "apply", "-f", str(yaml_path)],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode == 0:
            print(f"    OK: {r.stdout.strip().splitlines()[-1]}")
            applied.append(fault_type)
        else:
            print(f"    FAILED: {r.stderr.strip()}", file=sys.stderr)

    return applied


# ═══════════════════════════════════════════════════════════════════════
# Phase: wait — wait for fault injection to take effect
# ═══════════════════════════════════════════════════════════════════════
def parse_duration_seconds(dur: str) -> int:
    """Parse Kubernetes duration to seconds."""
    dur = dur.strip().lower()
    total = 0
    for m in re.finditer(r"(\d+)(h|m|s)", dur):
        v, u = int(m.group(1)), m.group(2)
        total += {"h": 3600, "m": 60, "s": 1}[u] * v
    return total


def phase_wait(faults: list[str], buffer_min: int = 2) -> None:
    """Wait for chaos experiments to complete + buffer.

    Reads experiment duration from YAML files and waits accordingly.
    Also adds warmup time for metrics to reflect the anomalies.
    """
    max_dur_s = 0
    for fault_type in faults:
        yaml_path = FAULT_CONFIGS.get(fault_type)
        if not yaml_path or not yaml_path.exists():
            continue
        content = yaml_path.read_text()
        match = re.search(r"duration:\s*(\S+)", content)
        if match:
            dur_s = parse_duration_seconds(match.group(1))
            max_dur_s = max(max_dur_s, dur_s)

    wait_s = max_dur_s + buffer_min * 60
    wait_min = wait_s / 60
    print(f"  Max fault duration: {max_dur_s}s")
    print(f"  Waiting {wait_min:.1f} minutes (duration + {buffer_min}min buffer)...")

    for remaining in range(int(wait_s), 0, -10):
        mins = remaining // 60
        secs = remaining % 60
        print(f"  {mins:2d}:{secs:02d} remaining...", end="\r")
        time.sleep(min(10, remaining))
    print("  Wait complete.                     ")


# ═══════════════════════════════════════════════════════════════════════
# Phase: collect — collect Prometheus metrics
# ═══════════════════════════════════════════════════════════════════════
def phase_collect(
    output_dir: Path,
    prometheus_url: str,
    duration_min: int,
    skip_prometheus: bool = False,
) -> Path:
    """Collect metrics from Prometheus and save to CSV.

    Returns path to metrics CSV.
    """
    metrics_path = output_dir / "chaos_metrics.csv"

    if skip_prometheus:
        print("  Generating synthetic fallback data...")
        _gen_synthetic_metrics(metrics_path, duration_min)
        return metrics_path

    print(f"  Querying Prometheus at {prometheus_url}...")
    end = datetime.now(timezone.utc)
    start = end - pd.Timedelta(minutes=duration_min)

    all_rows = []
    for metric_name, query in METRIC_QUERIES.items():
        params = {
            "query": query,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "step": "60",
        }
        try:
            resp = requests.get(
                f"{prometheus_url.rstrip('/')}/api/v1/query_range",
                params=params, timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
        except (requests.ConnectionError, requests.Timeout) as exc:
            print(f"  Prometheus unavailable: {exc}", file=sys.stderr)
            break

        if data.get("status") != "success" or not data.get("data", {}).get("result"):
            print(f"  No data for {metric_name}")
            continue

        for series in data["data"]["result"]:
            service = series["metric"].get("destination_service", "unknown")
            for ts, val in series["values"]:
                all_rows.append({
                    "timestamp": datetime.fromtimestamp(ts, tz=timezone.utc),
                    "service": service,
                    "metric": metric_name,
                    "value": float(val),
                })

    if not all_rows:
        print("  No Prometheus data. Generating synthetic fallback...")
        _gen_synthetic_metrics(metrics_path, duration_min)
    else:
        df = pd.DataFrame(all_rows).sort_values(["metric", "timestamp"])
        df.to_csv(metrics_path, index=False)
        print(f"  Metrics saved: {metrics_path} ({len(df)} points)")

    return metrics_path


def _gen_synthetic_metrics(path: Path, duration_min: int) -> None:
    """Generate synthetic metrics for testing."""
    rng = np.random.default_rng(20260610)
    n = duration_min
    t = np.arange(n)
    seasonal = 180 + 36 * np.sin(2 * np.pi * t / 60) + 12 * np.sin(2 * np.pi * t / 15)
    noise = rng.normal(0, 4.5, n)
    latency = seasonal + noise

    w1_s, w1_e = n // 4, int(n * 0.35)
    w2_s, w2_e = int(n * 0.65), int(n * 0.75)
    spike = min(3, w1_e - w1_s, w2_e - w2_s)
    latency[w1_s:w1_s + spike] += 80
    latency[w2_s:w2_s + spike] -= 60

    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-06-10 08:00:00", periods=n, freq="min"),
        "service": "frontend",
        "metric": "request_latency_ms_p95",
        "value": latency,
    })
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


# ═══════════════════════════════════════════════════════════════════════
# Phase: label — generate labels from ChaosMesh CRD Status
# ═══════════════════════════════════════════════════════════════════════
def phase_label(output_dir: Path, metrics_path: Path) -> Path:
    """Generate ground-truth labels from ChaosMesh event timestamps.

    Returns path to labels CSV.
    """
    labels_path = output_dir / "chaos_labels.csv"
    df = pd.read_csv(metrics_path, parse_dates=["timestamp"])

    # Import the label generation logic from run_fault_collection
    sys.path.insert(0, str(SCRIPTS_DIR))
    from run_fault_collection import get_chaos_events, generate_labels

    events = get_chaos_events()
    labels = generate_labels(df, 30, events)

    labels.to_csv(labels_path, index=False)
    anomaly_count = labels["is_anomaly"].sum()
    fault_types = labels[labels["fault_type"] != ""]["fault_type"].unique().tolist()
    print(f"  Labels saved: {labels_path} ({anomaly_count} anomaly points, types: {fault_types})")

    return labels_path


# ═══════════════════════════════════════════════════════════════════════
# Phase: detect — run FluxEV and Donut detectors
# ═══════════════════════════════════════════════════════════════════════
def phase_detect(
    output_dir: Path,
    metrics_path: Path,
    labels_path: Path,
    donut_window_size: int = 120,
) -> tuple[Path, Path]:
    """Run both FluxEV and Donut detectors.

    Returns (fluxev_output_json, donut_output_json) paths.
    """
    # Run FluxEV detection
    print("\n  --- FluxEV Detection ---")
    fluxev_result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "run_fluxev_on_chaos.py"),
            "--input", str(metrics_path),
            "--labels", str(labels_path),
        ],
        capture_output=True, text=True, timeout=300,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
    )
    if fluxev_result.returncode != 0:
        print(f"  FluxEV failed: {fluxev_result.stderr[:500]}", file=sys.stderr)
        fluxev_summary = {"algorithm": "FluxEV", "error": fluxev_result.stderr[:200]}
        fluxev_json = output_dir / "chaos_fluxev_summary.json"
        fluxev_json.write_text(json.dumps(fluxev_summary, indent=2))
    else:
        print(fluxev_result.stdout.strip()[-500:])
        # The FluxEV script writes to outputs/chaos_experiment_summary.json
        fluxev_json = ROOT / "outputs" / "chaos_experiment_summary.json"
        if not fluxev_json.exists():
            fluxev_json = output_dir / "chaos_fluxev_summary.json"
            fluxev_json.write_text(fluxev_result.stdout.strip())

    # Copy scored CSV to run-specific dir
    scored_csv = ROOT / "outputs" / "chaos_metrics_with_scores.csv"
    if scored_csv.exists():
        import shutil
        shutil.copy(scored_csv, output_dir / "chaos_metrics_fluxev_scores.csv")

    # Run Donut detection
    print("\n  --- Donut Detection ---")
    donut_result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "run_donut_on_chaos.py"),
            "--input", str(metrics_path),
            "--labels", str(labels_path),
            "--window-size", str(donut_window_size),
        ],
        capture_output=True, text=True, timeout=600,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
    )
    if donut_result.returncode != 0:
        print(f"  Donut failed: {donut_result.stderr[:500]}", file=sys.stderr)
        donut_summary = {"algorithm": "Donut", "error": donut_result.stderr[:200]}
        donut_json = output_dir / "chaos_donut_summary.json"
        donut_json.write_text(json.dumps(donut_summary, indent=2))
    else:
        print(donut_result.stdout.strip()[-500:])
        donut_json = ROOT / "outputs" / "chaos_donut_summary.json"
        if not donut_json.exists():
            donut_json = output_dir / "chaos_donut_summary.json"
            donut_json.write_text(donut_result.stdout.strip())

    # Copy Donut scored CSV
    donut_scored = ROOT / "outputs" / "chaos_metrics_donut_scores.csv"
    if donut_scored.exists():
        import shutil
        shutil.copy(donut_scored, output_dir / "chaos_metrics_donut_scores.csv")

    return fluxev_json, donut_json


# ═══════════════════════════════════════════════════════════════════════
# Phase: compare — generate comparison report
# ═══════════════════════════════════════════════════════════════════════
def phase_compare(
    output_dir: Path,
    fluxev_json: Path,
    donut_json: Path,
) -> None:
    """Generate comparison report between FluxEV and Donut results."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # Load summaries
    summaries = {}
    for label, path in [("FluxEV", fluxev_json), ("Donut", donut_json)]:
        if path.exists():
            try:
                summaries[label] = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                summaries[label] = {"error": "Failed to parse result JSON"}
        else:
            summaries[label] = {"error": f"Result file not found: {path}"}

    comparison = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fluxev": summaries.get("FluxEV", {}),
        "donut": summaries.get("Donut", {}),
    }

    # Print comparison table
    print("\n" + "=" * 60)
    print("  Algorithm Comparison: FluxEV vs Donut")
    print("=" * 60)
    header = f"{'Metric':<20} {'FluxEV':<15} {'Donut':<15}"
    print(header)
    print("-" * 50)

    metrics_to_compare = [
        ("point_precision", "Precision (point)"),
        ("point_recall", "Recall (point)"),
        ("point_f1", "F1 (point)"),
        ("window_precision", "Precision (window)"),
        ("window_recall", "Recall (window)"),
        ("window_f1", "F1 (window)"),
        ("threshold", "Anomaly threshold"),
    ]

    for key, display in metrics_to_compare:
        f_val = summaries.get("FluxEV", {}).get(key, "N/A")
        d_val = summaries.get("Donut", {}).get(key, "N/A")
        f_str = f"{f_val:.4f}" if isinstance(f_val, (int, float)) else str(f_val)
        d_str = f"{d_val:.4f}" if isinstance(d_val, (int, float)) else str(d_val)
        print(f"  {display:<20} {f_str:<15} {d_str:<15}")

    # Save comparison JSON
    comp_path = output_dir / "comparison_report.json"
    comp_path.write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  Comparison saved: {comp_path}")

    # Generate comparison bar chart
    _generate_comparison_chart(summaries, output_dir)


def _generate_comparison_chart(
    summaries: dict,
    output_dir: Path,
) -> None:
    """Generate bar chart comparing FluxEV vs Donut metrics."""
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    labels = ["FluxEV", "Donut"]
    colors = ["#1f77b4", "#2ca02c"]

    # Chart 1: Point-wise metrics
    point_metrics = ["point_precision", "point_recall", "point_f1"]
    x = np.arange(len(point_metrics))
    width = 0.35

    for i, algo in enumerate(labels):
        vals = []
        for m in point_metrics:
            v = summaries.get(algo, {}).get(m)
            vals.append(float(v) if isinstance(v, (int, float)) else 0.0)
        axes[0].bar(x + i * width, vals, width, label=algo, color=colors[i])

    axes[0].set_ylabel("Score")
    axes[0].set_title("Point-wise Metrics")
    axes[0].set_xticks(x + width / 2)
    axes[0].set_xticklabels(["Precision", "Recall", "F1"])
    axes[0].set_ylim(0, 1.0)
    axes[0].legend()
    axes[0].grid(axis="y", alpha=0.3)

    # Chart 2: Window-level metrics
    window_metrics = ["window_precision", "window_recall", "window_f1"]
    x = np.arange(len(window_metrics))

    for i, algo in enumerate(labels):
        vals = []
        for m in window_metrics:
            v = summaries.get(algo, {}).get(m)
            vals.append(float(v) if isinstance(v, (int, float)) else 0.0)
        axes[1].bar(x + i * width, vals, width, label=algo, color=colors[i])

    axes[1].set_ylabel("Score")
    axes[1].set_title("Window-level Metrics")
    axes[1].set_xticks(x + width / 2)
    axes[1].set_xticklabels(["Precision", "Recall", "F1"])
    axes[1].set_ylim(0, 1.0)
    axes[1].legend()
    axes[1].grid(axis="y", alpha=0.3)

    fig.suptitle("FluxEV vs Donut: Anomaly Detection on ChaosMesh Fault-Injected Data",
                 fontsize=13, fontweight="bold")
    plt.tight_layout()
    fig_path = output_dir / "comparison_chart.png"
    plt.savefig(fig_path, dpi=180, bbox_inches="tight")
    plt.close()
    print(f"  Chart saved: {fig_path}")


# ═══════════════════════════════════════════════════════════════════════
# Phase: cleanup — delete chaos experiments
# ═══════════════════════════════════════════════════════════════════════
def phase_cleanup(faults: list[str]) -> None:
    """Delete ChaosMesh experiments."""
    for fault_type in faults:
        yaml_path = FAULT_CONFIGS.get(fault_type)
        if not yaml_path or not yaml_path.exists():
            continue
        print(f"  Deleting {fault_type}...")
        r = subprocess.run(
            ["kubectl", "delete", "-f", str(yaml_path), "--ignore-not-found"],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode == 0:
            print(f"    OK")


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Unified ChaosMesh + Prometheus + FluxEV/Donut pipeline",
    )
    parser.add_argument(
        "--phases", default="apply,wait,collect,label,detect,compare",
        help="Comma-separated phases to execute (default: all)",
    )
    parser.add_argument(
        "--faults", default="all",
        help="Comma-separated fault types (network-delay,pod-kill,cpu-stress) or 'all'",
    )
    parser.add_argument("--duration", type=int, default=10, help="Observation duration (minutes)")
    parser.add_argument("--prometheus", default="http://localhost:9090", help="Prometheus URL")
    parser.add_argument("--buffer", type=int, default=2, help="Wait buffer after faults (minutes)")
    parser.add_argument("--window-size", type=int, default=120, help="Donut window size")
    parser.add_argument("--skip-prometheus", action="store_true", help="Use synthetic data")
    parser.add_argument("--output-dir", default=None, help="Custom output directory")
    args = parser.parse_args()

    phases = [p.strip() for p in args.phases.split(",")]

    if args.faults == "all":
        faults = list(FAULT_CONFIGS.keys())
    else:
        faults = [f.strip() for f in args.faults.split(",")]

    # Timestamped output directory
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir) if args.output_dir else (ROOT / "outputs" / "chaos" / ts)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("  ChaosMesh Fault Injection Validation Pipeline")
    print("=" * 60)
    print(f"  Phases: {phases}")
    print(f"  Faults: {faults}")
    print(f"  Duration: {args.duration} min")
    print(f"  Output: {output_dir}")
    print()

    applied_faults = faults
    metrics_path = output_dir / "chaos_metrics.csv"
    labels_path = output_dir / "chaos_labels.csv"
    fluxev_json = output_dir / "chaos_fluxev_summary.json"
    donut_json = output_dir / "chaos_donut_summary.json"

    # Start Prometheus port-forward if needed
    pf_proc = None
    if "collect" in phases and not args.skip_prometheus:
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
        for phase in phases:
            print(f"\n{'─' * 40}")
            print(f"  PHASE: {phase}")
            print(f"{'─' * 40}")

            if phase == "apply":
                applied_faults = phase_apply(faults)

            elif phase == "wait":
                phase_wait(applied_faults, args.buffer)

            elif phase == "collect":
                metrics_path = phase_collect(
                    output_dir, args.prometheus, args.duration, args.skip_prometheus,
                )

            elif phase == "label":
                labels_path = phase_label(output_dir, metrics_path)

            elif phase == "detect":
                fluxev_json, donut_json = phase_detect(
                    output_dir, metrics_path, labels_path, args.window_size,
                )

            elif phase == "compare":
                phase_compare(output_dir, fluxev_json, donut_json)

            elif phase == "cleanup":
                phase_cleanup(applied_faults)

            else:
                print(f"  Unknown phase: {phase}")

    finally:
        if pf_proc:
            pf_proc.terminate()
            pf_proc.wait(timeout=5)

    print(f"\n{'=' * 60}")
    print(f"  Pipeline complete. Results: {output_dir}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
