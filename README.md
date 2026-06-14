# Software Testing and Maintenance - Final Project

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PyTorch](https://img.shields.io/badge/pytorch-2.6.0%2Bcu124-red.svg)](https://pytorch.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A comprehensive software testing and maintenance project for Online Boutique microservices system, implementing two anomaly detection algorithms (FluxEV + Donut) with ChaosMesh fault injection, Prometheus/Grafana monitoring, and an end-to-end validation pipeline.

## Overview

This project demonstrates a complete chaos engineering and anomaly detection pipeline for a production-grade microservices architecture:

- **System Under Test**: [Online Boutique](https://github.com/GoogleCloudPlatform/microservices-demo) (11 microservices)
- **Dual Anomaly Detection**:
  - [FluxEV](https://arxiv.org/abs/2106.08753) (WSDM 2021): Statistical method with EWMA + two-step smoothing + SPOT thresholding
  - [Donut](https://arxiv.org/abs/1802.03903) (WWW 2018): VAE-based unsupervised method with M-ELBO loss, MCMC imputation, and KDE scoring
- **Fault Injection**: ChaosMesh-powered network delay, pod-kill, and CPU stress scenarios
- **Monitoring Stack**: Prometheus + Grafana for real-time metrics collection and visualization
- **Testing Suite**: Selenium (functional) + JMeter (performance) test automation
- **GPU Acceleration**: CUDA support (NVIDIA RTX 4060, PyTorch 2.6.0+cu124)

## Quick Start

### Prerequisites

- Python 3.10+
- Docker 24.0+ & minikube 1.32+ (for full deployment)
- kubectl 1.28+ & Helm 3.13+ (for K8s components)
- (Optional) NVIDIA GPU + CUDA 12.4 (for Donut GPU training)
- (Optional) Apache JMeter 5.6+, Google Chrome 120+

### Installation

```bash
# Clone repository
git clone https://github.com/Anarchy44/software_testing.git
cd software_testing

# Install Python dependencies
pip install -r requirements.txt
```

### Quick Test (No Kubernetes Required)

Run the end-to-end validation pipeline with synthetic data:

```bash
python scripts/run_full_pipeline.py \
    --phases collect,label,detect,compare \
    --skip-prometheus \
    --duration 200 \
    --window-size 60
```

This generates synthetic metrics, runs both FluxEV and Donut detectors, and produces a comparison report in `outputs/chaos/<timestamp>/`.

## Architecture

```
┌──────────────────┐     ┌─────────────────┐     ┌──────────────────┐
│    ChaosMesh     │────▶│   Prometheus     │────▶│  Metrics CSV     │
│  (3 fault types) │     │  (scrape 15s)    │     │  (data/chaos_*)  │
└────────┬─────────┘     └─────────────────┘     └───────┬──────────┘
         │                                               │
         │ kubectl get chaos CRD                         ▼
         │ (real timestamps)                ┌──────────────────────┐
         └─────────────────────────────────▶│  Label Generation    │
                                            │  (real time windows) │
                                            └──────┬───────────────┘
                                                   │
              ┌────────────────────────────────────┴────────────────┐
              ▼                                                     ▼
    ┌─────────────────┐                                   ┌─────────────────┐
    │  FluxEVDetector │                                   │  DonutDetector  │
    │  (EWMA + SPOT)  │                                   │  (VAE + KDE)    │
    └────────┬────────┘                                   └────────┬────────┘
             │                                                     │
             └──────────────────┬──────────────────────────────────┘
                                ▼
                   ┌──────────────────────┐
                   │  Comparison Report   │
                   │  Precision/Recall/F1 │
                   │  Window-level match  │
                   └──────────────────────┘
```

## Project Structure

```
.
├── src/
│   ├── fluxev/                      # FluxEV detector (WSDM 2021)
│   │   └── detector.py              # EWMA + two-step smoothing + SPOT
│   └── donut/                       # Donut detector (WWW 2018)
│       ├── vae.py                   # VAE model (encoder-decoder)
│       ├── melbo.py                 # M-ELBO loss + missing data injection
│       ├── trainer.py               # GPU training with early stopping
│       └── detector.py              # MCMC imputation + KDE scoring
│
├── scripts/                         # Automation scripts
│   ├── run_full_pipeline.py         # End-to-end orchestrator (NEW)
│   ├── run_fault_collection.py      # Fault injection + Prometheus collector
│   ├── run_fluxev_on_chaos.py       # FluxEV on chaos data
│   ├── run_donut_on_chaos.py        # Donut on chaos data (NEW)
│   ├── run_donut_experiment.py      # Donut standalone training/evaluation
│   ├── run_fluxev_experiment.py     # FluxEV standalone experiment
│   ├── run_donut_vs_fluxev.py       # Head-to-head algorithm comparison
│   ├── run_ablation.py              # FluxEV ablation study
│   ├── generate_sample_data.py      # Synthetic KPI data generator
│   ├── build_report.py              # DOCX report generator
│   ├── build_report_pdf.py          # PDF report generator
│   └── *.sh                         # Deployment & testing shell scripts
│
├── k8s/                             # Kubernetes manifests
│   ├── diagnosis-service.yaml       # Custom microservice
│   ├── prometheus-config.yaml       # Prometheus scrape configs
│   ├── prometheus-deployment.yaml   # Prometheus deployment + service
│   ├── grafana-datasource.yaml      # Grafana datasource + dashboards
│   ├── grafana-deployment.yaml      # Grafana deployment
│   └── chaos-experiments/           # Fault injection scenarios
│       ├── network-delay.yaml       # 200ms latency (frontend→cartservice)
│       ├── pod-kill.yaml            # cartservice pod termination
│       └── cpu-stress.yaml          # 80% CPU stress on productcatalog
│
├── services/diagnosis-service/      # Custom anomaly query service
├── tests/                           # Test suites
│   ├── selenium/                    # Functional tests (Edge browser)
│   └── jmeter/                      # Performance test plan
├── outputs/                         # Experiment results
│   ├── donut/                       # Donut model + training history
│   ├── fluxev/                      # FluxEV detection plots
│   ├── chaos/                       # Pipeline run outputs
│   └── figures/                     # Detection result figures
├── data/                            # Input data (CSV)
├── deliverables/                    # Final reports & presentations
├── docs/paper_notes.md              # Research notes
└── requirements.txt                 # Python dependencies
```

## Features

### 1. Dual Algorithm Anomaly Detection

#### FluxEV (WSDM 2021)

Statistical, training-free, online anomaly detection:

1. **EWMA Fluctuation Extraction**: Captures short-term volatility
2. **Two-Step Smoothing**: Suppresses noise while preserving anomaly signals
3. **SPOT + MOM-POT Thresholding**: Automatic threshold via Extreme Value Theory

```bash
# Standalone experiment
python scripts/run_fluxev_experiment.py --input data/sample_prometheus_metrics.csv

# On chaos-injected data
python scripts/run_fluxev_on_chaos.py \
    --input data/chaos_metrics.csv \
    --labels data/chaos_labels.csv
```

#### Donut (WWW 2018)

Deep learning, unsupervised, VAE-based anomaly detection:

1. **VAE Architecture**: Encoder-decoder with Gaussian latent space
2. **M-ELBO Loss**: Missing data injection during training for robustness
3. **MCMC Imputation**: Iterative missing value reconstruction at inference
4. **KDE Scoring**: Kernel density estimation for automatic thresholding

```bash
# Train + evaluate (GPU accelerated)
python scripts/run_donut_experiment.py --input data/sample_prometheus_metrics.csv

# On chaos-injected data
python scripts/run_donut_on_chaos.py \
    --input data/chaos_metrics.csv \
    --labels data/chaos_labels.csv \
    --model outputs/donut/best_model.pt
```

### 2. End-to-End Chaos Validation Pipeline (NEW)

One-command execution of the complete workflow:

```bash
python scripts/run_full_pipeline.py \
    --faults all \
    --duration 15 \
    --phases apply,wait,collect,label,detect,compare
```

Pipeline phases:

| Phase | Description |
|-------|-------------|
| `apply` | kubectl apply ChaosMesh experiments |
| `wait` | Wait for fault duration + warmup buffer |
| `collect` | Query Prometheus for p95 latency, CPU, memory, error rate |
| `label` | Extract real fault timestamps from ChaosMesh CRD Status |
| `detect` | Run FluxEV and Donut detectors in parallel |
| `compare` | Generate comparison report and charts |
| `cleanup` | (Optional) Delete chaos experiments |

Individual phases can be run for debugging:

```bash
python scripts/run_full_pipeline.py --phases detect,compare
```

### 3. Multi-Metric Collection

Beyond p95 latency, the pipeline collects:

| Metric | PromQL Source |
|--------|---------------|
| Request Latency p95 | `istio_request_duration_milliseconds_bucket` |
| Error Rate 5xx | `istio_requests_total{response_code=~"5.."}` |
| Request Rate (RPS) | `istio_requests_total` |
| CPU Usage | `container_cpu_usage_seconds_total` |
| Memory Usage | `container_memory_working_set_bytes` |

### 4. ChaosMesh Fault Injection

Three fault scenarios targeting Online Boutique microservices:

| Scenario | Target | Effect | Duration |
|----------|--------|--------|----------|
| Network Delay | frontend → cartservice | 200ms latency, 50ms jitter | 10m |
| Pod Kill | cartservice | Random pod termination | 3m |
| CPU Stress | productcatalogservice | 80% CPU load (2 workers) | 10m |

### 5. Monitoring & Observability

**Prometheus** scrapes from:
- Istio sidecar proxies (port 15020): latency, request rate, error rate
- cAdvisor: CPU, memory per container
- diagnosis-service: custom anomaly metrics
- Self-monitoring

**Grafana Dashboard** (5 panels):
- Request Latency p95 (timeseries)
- Request Rate by service
- Error Rate 5xx (%)
- CPU Usage by pod
- Memory Usage by pod

### 6. Automated Testing

**Selenium** (Edge browser): Homepage, Browse, Checkout flows
**JMeter**: 50 concurrent users, 30s ramp-up, 5min duration

## Reproduction Guide

### GPU Training Setup (Optional)

```bash
# Install PyTorch with CUDA 12.4
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
```

### Full Deployment on minikube

```bash
# 1. Start cluster
minikube start --driver=docker --cpus=4 --memory=6144

# 2. Deploy Online Boutique
./scripts/deploy_online_boutique.sh

# 3. Build & deploy diagnosis-service
docker build -t diagnosis-service:local ./services/diagnosis-service
minikube image load diagnosis-service:local
kubectl apply -f k8s/diagnosis-service.yaml

# 4. Setup monitoring
./scripts/setup_prometheus.sh

# 5. Inject faults
./scripts/setup_chaosmesh.sh

# 6. Run full validation pipeline
python scripts/run_full_pipeline.py \
    --faults all \
    --duration 30 \
    --phases apply,wait,collect,label,detect,compare

# 7. Verify deployment
python scripts/verify_deployment.py
```

### Data Collection (Standalone)

```bash
# Collect metrics over past N minutes
python scripts/run_fault_collection.py --duration 30

# Collect with specific metrics
python scripts/run_fault_collection.py \
    --duration 15 \
    --metrics request_latency_ms_p95 cpu_usage_cores error_rate_5xx_pct
```

## Key Findings

### FluxEV vs Donut Comparison

| Aspect | FluxEV | Donut |
|--------|--------|-------|
| **Methodology** | Statistical (EWMA + EVT) | Deep Learning (VAE) |
| **Training** | None (online) | Requires training data |
| **GPU** | Not needed | CUDA recommended |
| **Threshold** | Automatic (SPOT + POT) | KDE percentile (auto-fit) |
| **Missing Data** | Linear interpolation | MCMC imputation |
| **Interpretability** | High (explicit steps) | Low (latent space) |
| **Speed** | Fast (vectorized) | Moderate (GPU-dependent) |
| **Paper Reference** | WSDM 2021 | WWW 2018 |

### Ablation Study

Two-step smoothing improves FluxEV F1 score by ~15% compared to no-smoothing baseline.

### Donut GPU Training (RTX 4060)

- Training time: ~4.7s for 100 epochs on 120-dim windows
- Model size: ~300K parameters
- Best F1: 0.888 (Precision=0.799, Recall=1.000)

## Deliverables

Final submission materials:

- [Report PDF](deliverables/software_testing_and_maintenance_final_report.pdf)
- [Report DOCX](deliverables/software_testing_and_maintenance_final_report.docx)
- [Presentation PPTX](deliverables/software_testing_final_presentation.pptx)
- [Research Notes](docs/paper_notes.md)

## Environment Compatibility

| Platform | Status | Notes |
|----------|--------|-------|
| Windows 10/11 | Tested | Git Bash for `.sh` scripts |
| macOS | Compatible | Font paths auto-detected |
| Linux | Compatible | Font paths auto-detected |

## License

This project is for educational purposes as part of the Software Testing and Maintenance course (Spring 2026).

## Acknowledgments

- [Online Boutique](https://github.com/GoogleCloudPlatform/microservices-demo) by Google Cloud
- [FluxEV Paper](https://arxiv.org/abs/2106.08753): "FluxEV: A Fast and Explainable Method for Time Series Anomaly Detection" (WSDM 2021)
- [Donut Paper](https://arxiv.org/abs/1802.03903): "Unsupervised Anomaly Detection via Variational Auto-Encoder" (WWW 2018)
- [ChaosMesh](https://chaos-mesh.org/) by CNCF
