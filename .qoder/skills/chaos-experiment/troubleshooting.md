# Chaos Experiment Troubleshooting

Detailed fixes for common issues encountered during fault injection experiments.

## Donut Issues

### ZeroDivisionError in train_epoch

```
ZeroDivisionError: division by zero
  File ".../src/donut/trainer.py", line 113, in train_epoch
    "train_loss": sum(total_losses) / len(total_losses),
```

**Root cause**: DataLoader with `drop_last=True` yields 0 batches when `n_samples < batch_size`.

**Fix** (applied in trainer.py): Auto-adjust batch_size and only `drop_last` when enough samples:

```python
# trainer.py fit() method
drop = len(X_train) > batch_size
train_loader = DataLoader(
    train_dataset, batch_size=min(batch_size, len(X_train)),
    shuffle=True, drop_last=drop,
)
```

Also guards against empty `total_losses`:

```python
n = len(total_losses) or 1
return {"train_loss": sum(total_losses) / n, ...}
```

### DonutVAE Dimension Mismatch

```
RuntimeError: size mismatch for encoder.0.weight: copying a param with shape
torch.Size([500, 60]) from checkpoint, the shape in current model is torch.Size([500, 30]).
```

**Root cause**: Pre-trained model at `outputs/donut/best_model.pt` was trained with a different `window_size` (and thus different `input_dim`).

**Fix**: Delete old model before running with new window_size:

```bash
rm -f outputs/donut/best_model.pt
python scripts/run_donut_on_chaos.py --window-size 30 --train ...
```

### Minimum Data Requirements

Donut needs enough windows for training and KDE fitting:
- For `window_size=W` and `N` data points: yields `N - W + 1` windows
- Minimum 10 windows recommended for KDE fitting
- Rule of thumb: `window_size ≤ N/3`

## FluxEV Issues

### SPOT Threshold Returns 0 (All Predictions Zero)

```
FluxEV: predicted_points=0, threshold=0.0, point_f1=0.0
```

**Root cause**: SPOT (Streaming Peaks-Over-Threshold) requires `k` warmup points for GPD fitting. Default `k=1000` exceeds small datasets.

**Fix**: Use percentile-based fallback when SPOT fails:

```python
import numpy as np
from fluxev import FluxEVDetector

detector = FluxEVDetector(s=3, alpha=0.3, d=1, p=2, l=10, k=10, risk=0.1)
result = detector.detect(values)

if result.threshold == 0.0 or result.labels.sum() == 0:
    thresh = np.percentile(result.score, 75)
    result.labels = (result.score > thresh).astype(int)
    result.threshold = float(thresh)
```

### FluxEV Parameter Selection for Small Datasets

| Param | Default | Small Data (<100 pts) | Purpose |
|-------|---------|----------------------|---------|
| `s` | 10 | 3-5 | EWMA smoothing window |
| `k` | 1000 | min(N/2, 20) | POT initialization points |
| `p` | 5 | 2-3 | Period comparison count |
| `l` | — | ~N/4 | Period length (required) |
| `risk` | 0.01 | 0.05-0.1 | FPR coefficient |

## Prometheus/Data Issues

### No Prometheus Data

```bash
curl -s "http://localhost:9090/api/v1/query?query=up" | python -m json.tool
```

If `"result": []`:
1. Check port-forward: `jobs -l` or `ps aux | grep port-forward`
2. Check Prometheus pod: `kubectl logs -n monitoring deploy/prometheus --tail=20`
3. Check loadgenerator is sending traffic: `kubectl logs -l app=loadgenerator -n default --tail=3`
4. Verify scrape targets: `kubectl port-forward -n monitoring svc/prometheus 9090:9090` then visit `/targets`

### Too Few Data Points for Donut

With 60s step and 15min window → only 15 points. Not enough for Donut.

**Fix**: Reduce Prometheus query `step` parameter:
- `step=15` for windows < 60 min
- `step=30` for windows 60-180 min
- `step=60` for windows > 180 min

### Data After minikube Restart

After `minikube start`, Prometheus returns no historical data because its TSDB uses `emptyDir` volume. Only data from the current session is available.

**Workaround**: After restart, wait 5+ minutes for Prometheus to accumulate new scrape data before collecting.

## minikube Issues

### All Pods in Error After Start

Fresh `minikube start` shows all pods as Error for the first ~30s.

**Fix**: Wait 60-90 seconds after start, then verify:
```bash
sleep 60 && kubectl get pods -A | grep -v Running | grep -v Completed
```

If some pods still Error after 2min, check resource pressure:
```bash
minikube ssh -- top -bn1 | head -5
```

### Cannot Connect to Cluster

```
Unable to connect to the server: dial tcp 127.0.0.1:61128: connectex: No connection...
```

**Fix**: Restart minikube or check Docker:
```bash
minikube status
minikube start  # If stopped
docker ps       # Verify Docker is running
```

## Comparison Report Template

Manual comparison generation when `run_full_pipeline.py --phases compare` doesn't apply:

```python
import json, pandas as pd, numpy as np
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Load data
df = pd.read_csv("data/chaos_real_metrics.csv", parse_dates=["timestamp"])
labels = pd.read_csv("data/chaos_real_labels.csv", parse_dates=["timestamp"])
fluxev = pd.read_csv("outputs/chaos_real_fluxev_scores.csv", parse_dates=["timestamp"])
donut = pd.read_csv("outputs/chaos_metrics_donut_scores.csv", parse_dates=["timestamp"])

# Merge
merged = df.merge(labels[["timestamp","is_anomaly"]], on="timestamp", how="left")
merged["is_anomaly"] = merged["is_anomaly"].fillna(0).astype(int)

# Figure: side-by-side
fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
for ax, scores_df, color, title_pref in [
    (axes[0], fluxev, "#1f77b4", "FluxEV"),
    (axes[1], donut, "#2ca02c", "Donut"),
]:
    ax.plot(merged["timestamp"], merged["value"], "b-", lw=1.2)
    ax.fill_between(merged["timestamp"], 0, merged["value"].max()*1.1,
                    where=(merged["is_anomaly"]==1), alpha=0.12, color="red")
    pred = merged.merge(scores_df[["timestamp","predicted_anomaly"]], on="timestamp")
    pred_pts = pred[pred["predicted_anomaly"] == 1]
    ax.scatter(pred_pts["timestamp"], pred_pts["value"],
               facecolors="none", edgecolors=color, s=80, lw=1.5)
    ax.set_ylabel("p95 latency (ms)")
    ax.set_title(f"{title_pref} Detection", fontsize=11)
    ax.grid(alpha=0.25)

plt.tight_layout()
plt.savefig("outputs/figures/chaos_real_comparison.png", dpi=180)
plt.close()
```
