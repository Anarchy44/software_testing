---
name: chaos-experiment
description: Execute ChaosMesh fault injection experiments on a live Kubernetes cluster, collect Prometheus monitoring data, and validate FluxEV and Donut anomaly detection algorithms end-to-end. Use when the user wants to run fault injection, inject chaos, validate anomaly detection algorithms, collect real monitoring metrics from Prometheus, run the chaos pipeline, or compare algorithm performance on fault-injected data.
---

# ChaosMesh Fault Injection Experiment

End-to-end workflow for injecting faults into Online Boutique microservices via ChaosMesh, collecting real Prometheus metrics, and evaluating FluxEV + Donut anomaly detectors.

## Prerequisites

- minikube running (`minikube status` shows Running)
- Online Boutique, Istio, Prometheus, Grafana, ChaosMesh deployed
- Python 3.10+ with `pip install -r requirements.txt`

## Quick Start (One Command)

```bash
# Full pipeline — skips apply/wait if cluster already has faults running
python scripts/run_full_pipeline.py \
    --phases collect,label,detect,compare \
    --duration 15 \
    --window-size 30
```

## Workflow

### Phase 1: Prepare Cluster

Start the cluster if stopped (pods take ~60s to stabilize after restart):

```bash
minikube start --driver=docker --cpus=4 --memory=6144
# Wait for all pods Running
kubectl get pods -A | grep -v Running | grep -v Completed
```

Verify all components:

| Namespace | Expected |
|-----------|----------|
| default | 11 Online Boutique services (2/2 Running) |
| istio-system | istiod + ingress/egress gateways |
| chaos-testing | chaos-controller-manager, chaos-daemon, chaos-dashboard, chaos-dns-server |
| monitoring | prometheus, grafana |

Loadgenerator should be generating traffic (~7 req/s). Check: `kubectl logs -l app=loadgenerator -n default --tail=3`

### Phase 2: Inject Fault

Choose a fault type:

| Fault | YAML | Effect |
|-------|------|--------|
| `network-delay` | `k8s/chaos-experiments/network-delay.yaml` | 200ms latency frontend→cartservice |
| `pod-kill` | `k8s/chaos-experiments/pod-kill.yaml` | Kill 1 cartservice pod |
| `cpu-stress` | `k8s/chaos-experiments/cpu-stress.yaml` | 80% CPU on productcatalog |

Clear old experiments first, then inject fresh:

```bash
kubectl delete networkchaos,podchaos,stresschaos --all -n default
kubectl apply -f k8s/chaos-experiments/network-delay.yaml
# Record injection time for labels
date -u +%H:%M:%S
```

**Key decision** — choose wait time:
- Fault duration is in the YAML `spec.duration` field
- Wait = duration + 2min buffer for metrics to accumulate
- Network-delay (10m) → wait ~12min

### Phase 3: Port-Forward Prometheus

```bash
kubectl port-forward -n monitoring svc/prometheus 9090:9090 &
```

Verify data exists:

```bash
curl -s "http://localhost:9090/api/v1/query?query=sum(rate(istio_requests_total[2m]))"
```

### Phase 4: Collect Metrics

Use step=15s for higher resolution (default 60s gives too few points for small windows):

```python
import requests, pandas as pd
from datetime import datetime, timezone, timedelta

end = datetime.now(timezone.utc)
start = end - timedelta(minutes=30)

query = (
    'histogram_quantile(0.95, '
    'sum(rate(istio_request_duration_milliseconds_bucket{reporter="source"}[2m])) by (le))'
)
params = {"query": query, "start": start.isoformat(), "end": end.isoformat(), "step": "15"}
resp = requests.get("http://localhost:9090/api/v1/query_range", params=params, timeout=120)
data = resp.json()

rows = []
for series in data["data"]["result"]:
    for ts, val in series["values"]:
        rows.append({
            "timestamp": datetime.fromtimestamp(ts, tz=timezone.utc),
            "service": "unknown",
            "metric": "request_latency_ms_p95",
            "value": float(val),
        })
df = pd.DataFrame(rows).sort_values("timestamp")
df.to_csv("data/chaos_real_metrics.csv", index=False)
```

Or use the collection script with multi-metric support:

```bash
python scripts/run_fault_collection.py \
    --duration 30 \
    --output-prefix data/chaos_real \
    --metrics request_latency_ms_p95 cpu_usage_cores error_rate_5xx_pct
```

### Phase 5: Generate Labels from Real Timestamps

Labels MUST be derived from the actual fault injection time window, NOT synthetic windows.

```python
import pandas as pd
from datetime import datetime, timezone

df = pd.read_csv("data/chaos_real_metrics.csv", parse_dates=["timestamp"])

# Set fault_start/fault_end to the actual injection time (from Phase 2)
fault_start = datetime(2026, 6, 14, 8, 32, 0, tzinfo=timezone.utc)
fault_end = datetime(2026, 6, 14, 8, 42, 0, tzinfo=timezone.utc)

labels = pd.DataFrame({
    "timestamp": df["timestamp"],
    "is_anomaly": 0,
    "fault_type": "",
})
mask = (df["timestamp"] >= fault_start) & (df["timestamp"] <= fault_end)
labels.loc[mask, "is_anomaly"] = 1
labels.loc[mask, "fault_type"] = "network-delay"
labels.to_csv("data/chaos_real_labels.csv", index=False)
```

### Phase 6: Run Detection

Both detectors on the collected data:

```bash
# FluxEV — requires period param (~1/4 of total points)
set PYTHONPATH=src
python scripts/run_fluxev_on_chaos.py \
    --input data/chaos_real_metrics.csv \
    --labels data/chaos_real_labels.csv \
    --period 10

# Donut — window_size must leave >= 10 windows for training
python scripts/run_donut_on_chaos.py \
    --input data/chaos_real_metrics.csv \
    --labels data/chaos_real_labels.csv \
    --window-size 30 \
    --train
```

### Phase 7: Generate Comparison Report

```bash
python scripts/run_full_pipeline.py --phases compare
```

Or manually: see [troubleshooting.md](troubleshooting.md) for the comparison script template.

### Cleanup

```bash
kubectl delete networkchaos,podchaos,stresschaos --all -n default
kill %1  # Stop port-forward
```

## Key Parameters Quick Reference

| Parameter | Guideline |
|-----------|-----------|
| `--duration` | Observation window (min). Should cover fault_period + 10min baseline |
| `--window-size` | Donut sliding window. Set to ~1/3 of total data points |
| `--period` (FluxEV) | ~1/4 of total data points |
| `step` (Prometheus) | 15s for < 30min, 60s for > 1hr |
| Donut `batch_size` | Auto-adjusted when samples < default (64) |

## Output Files

```
data/
├── chaos_real_metrics.csv          # Raw Prometheus metrics
└── chaos_real_labels.csv           # Ground-truth from fault timestamps

outputs/
├── chaos_real_fluxev_scores.csv    # FluxEV scores + predictions
├── chaos_metrics_donut_scores.csv  # Donut scores + predictions
├── chaos_real_comparison_report.json  # Comparison JSON
└── figures/
    └── chaos_real_comparison.png   # Detection comparison chart
```

## Troubleshooting

For common issues and fixes, see [troubleshooting.md](troubleshooting.md). Quick reference:

| Symptom | Fix |
|---------|-----|
| Donut `ZeroDivisionError` | `drop_last=True` with small data → already fixed in trainer |
| Donut dimension mismatch | Delete `outputs/donut/best_model.pt` and retrain with correct window_size |
| FluxEV threshold=0 | Dataset too small for SPOT → use 75th percentile fallback |
| All pods Error after restart | Wait 60s for cluster stabilization |
| Prometheus no data | Verify port-forward is active, check loadgenerator is sending traffic |
| Too few data points | Reduce Prometheus step to 15s, or collect longer duration |
