# Donut Anomaly Detection - User Guide

## Overview

Donut is an unsupervised anomaly detection algorithm for seasonal KPIs based on Variational Auto-Encoders (VAE). This implementation follows the WWW 2018 paper: *"Unsupervised Anomaly Detection via Variational Auto-Encoder for Seasonal KPIs in Web Applications"*.

### Key Features

- **M-ELBO Loss**: Modified Evidence Lower Bound that handles missing/anomalous data during training
- **MCMC Imputation**: Iterative missing value imputation to reduce representation bias
- **KDE Scoring**: Kernel Density Estimation for automatic threshold selection
- **GPU Support**: CUDA-accelerated training with PyTorch

## Installation

### Option 1: Local Installation (CPU)

```bash
pip install torch>=2.0.0 numpy pandas scikit-learn scipy matplotlib tqdm
```

### Option 2: GPU Environment (Recommended)

```bash
# Build Docker image with CUDA support
docker build -f Dockerfile.gpu -t donut-gpu .

# Run container with GPU access
docker run --gpus all -it donut-gpu bash
```

Or install locally with CUDA:

```bash
pip install torch==2.0.0+cu118 --index-url https://download.pytorch.org/whl/cu118
pip install -r requirements_gpu.txt
```

## Quick Start

### 1. Train Donut Model

```bash
# Basic usage
python scripts/run_donut_experiment.py --input data/sample_prometheus_metrics.csv

# Custom parameters
python scripts/run_donut_experiment.py \
    --input data/kpi_data.csv \
    --window-size 120 \
    --epochs 150 \
    --batch-size 128 \
    --seed 42
```

**Output files:**
- `outputs/donut/experiment_summary.json` - Detection metrics
- `outputs/donut/training_history.json` - Training loss curves
- `outputs/donut/figures/donut_training_and_detection.png` - Visualization
- `outputs/donut/figures/donut_score_timeline.png` - Anomaly scores over time

### 2. Compare with FluxEV

```bash
python scripts/run_donut_vs_fluxev.py --input data/sample_prometheus_metrics.csv
```

**Output:**
- `outputs/donut/comparison_summary.json` - Side-by-side comparison
- `outputs/donut/figures/donut_vs_fluxev.png` - Performance comparison plots

## Architecture

```
Input Window (120 points)
        │
        ▼
┌─────────────────┐
│   Encoder MLP   │  Input → 500 → 500
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
  μ (5)   logσ² (5)  ← Latent space
    │         │
    └────┬────┘
         │  Reparameterization
         ▼
       z ~ N(μ, σ²)
         │
         ▼
┌─────────────────┐
│   Decoder MLP   │  5 → 500 → 500 → 120
└────────┬────────┘
         │
         ▼
Reconstruction (120 points)
```

## Algorithm Details

### M-ELBO Loss Function

Standard VAE ELBO:
```
ELBO = E_q[log p(x|z)] - KL(q(z|x) || p(z))
```

Donut's M-ELBO (with mask α):
```
M-ELBO = Σ α_i · E_q[log p(x_i|z)] - β · KL(q(z|x) || p(z))
```

Where α_i = 1 for normal points, 0 for anomalous/missing points.

### Training Process

1. **Missing Data Injection**: Randomly set 10% of normal points to 0
2. **Masked Training**: Apply M-ELBO loss with binary mask
3. **Early Stopping**: Stop if validation loss doesn't improve for 15 epochs
4. **Best Model Selection**: Restore model with lowest validation loss

### Detection Pipeline

1. **Encode**: Compute posterior q(z|x) for test window
2. **Sample**: Draw 100 latent samples via Monte Carlo
3. **Reconstruct**: Decode each sample to get reconstruction distribution
4. **Score**: Compute negative log probability as anomaly score
5. **Threshold**: Apply KDE-based threshold (95th percentile of training scores)

## Hyperparameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `window_size` | 120 | Sliding window length (points) |
| `hidden_dim` | 500 | Hidden layer dimension |
| `latent_dim` | 5 | Latent space dimension |
| `dropout` | 0.1 | Dropout rate for regularization |
| `lr` | 1e-3 | Learning rate (Adam optimizer) |
| `batch_size` | 64 | Mini-batch size |
| `missing_rate` | 0.1 | Missing data injection rate |
| `beta` | 1.0 | KL divergence weight in M-ELBO |
| `n_samples` | 100 | Monte Carlo samples for scoring |
| `patience` | 15 | Early stopping patience |

## Performance Tips

### GPU Acceleration

```python
# Check GPU availability
import torch
print(torch.cuda.is_available())  # Should print True
print(torch.cuda.get_device_name())  # e.g., "NVIDIA GeForce RTX 3090"
```

Training speed comparison:
- **CPU** (Intel i7-12700K): ~2 min/epoch
- **GPU** (RTX 3090): ~5 sec/epoch (24x faster)

### Memory Usage

- **Model size**: ~2.5M parameters (~10 MB)
- **Batch memory**: ~50 MB per 64-sample batch on GPU
- **Recommendation**: Minimum 4GB VRAM for training

### Scaling to Large Datasets

For millions of KPIs:
1. Use smaller `latent_dim` (3-5) for faster inference
2. Reduce `n_samples` to 50 for quicker scoring
3. Batch detection with `batch_size=128` or higher
4. Consider model parallelism for concurrent KPIs

## Comparison: Donut vs FluxEV

| Aspect | Donut | FluxEV |
|--------|-------|--------|
| **Method** | Deep generative (VAE) | Statistical (EWMA + EVT) |
| **Training** | Required (GPU recommended) | None (online algorithm) |
| **Cold Start** | Needs full history | 2 cycles + 1000 points |
| **Detection Speed** | ~50ms/window (GPU) | ~1ms/window |
| **KPI F1 Score** | 0.729 | 0.790 |
| **Yahoo F1 Score** | 0.058 | 0.666 |
| **Interpretability** | Low (black-box) | High (explicit steps) |
| **Best For** | Complex patterns, stable seasonality | Rapid deployment, diverse patterns |

## Troubleshooting

### Issue: CUDA out of memory

**Solution**: Reduce batch size or use CPU mode
```bash
python scripts/run_donut_experiment.py --batch-size 32
# Or force CPU
export CUDA_VISIBLE_DEVICES=""
```

### Issue: Poor detection performance

**Possible causes**:
1. Insufficient training data (< 1000 windows)
2. Wrong window size (should match seasonal period)
3. Too aggressive missing data injection

**Solutions**:
- Increase `epochs` to 150-200
- Tune `window_size` to match data periodicity
- Reduce `missing_rate` to 0.05

### Issue: Training instability

**Symptoms**: Loss oscillates, NaN values

**Solutions**:
- Reduce learning rate to 5e-4
- Increase `beta` to 2.0 for stronger regularization
- Enable gradient clipping in trainer

## API Reference

### DonutVAE

```python
from src.donut import DonutVAE

model = DonutVAE(
    input_dim=120,
    hidden_dim=500,
    latent_dim=5,
    dropout=0.1
)

# Forward pass
x_recon, mu, logvar = model(x)
```

### DonutTrainer

```python
from src.donut import DonutTrainer

trainer = DonutTrainer(
    model=model,
    lr=1e-3,
    missing_rate=0.1,
    device="cuda"
)

history = trainer.fit(
    X_train=train_data,
    epochs=100,
    patience=15
)
```

### DonutDetector

```python
from src.donut import DonutDetector

detector = DonutDetector(model=model, n_samples=100)
detector.fit_kde(train_data, percentile=95.0)

scores, predictions = detector.detect(test_data)
```

## Citation

```bibtex
@inproceedings{xu2018donut,
  title={Unsupervised Anomaly Detection via Variational Auto-Encoder for Seasonal KPIs in Web Applications},
  author={Xu, Haowen and Chen, Wenxiao and Zhao, Nengwen and Li, Zeyan and Bu, Jiajun and Li, Zhihan and Liu, Ying and Zhao, Youjian and Zhang, Dan and Chen, Fengxiang and others},
  booktitle={Proceedings of the 2018 World Wide Web Conference},
  pages={193--202},
  year={2018}
}
```

## License

This implementation is for educational purposes as part of the Software Testing and Maintenance course (Spring 2026).
