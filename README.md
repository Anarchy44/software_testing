# Software Testing and Maintenance - Final Project

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A comprehensive software testing and maintenance project for Online Boutique microservices system, implementing FluxEV anomaly detection algorithm with ChaosMesh fault injection, Selenium functional tests, and JMeter performance benchmarks.

## Overview

This project demonstrates a complete testing and monitoring pipeline for a production-grade microservices architecture:

- **System Under Test**: [Online Boutique](https://github.com/GoogleCloudPlatform/microservices-demo) (11 microservices, more complex than SockShop)
- **Anomaly Detection**: Lightweight implementation of [FluxEV](https://arxiv.org/abs/2106.08753) algorithm with two-step smoothing mechanism
- **Fault Injection**: ChaosMesh-powered network latency, pod termination, and CPU stress scenarios
- **Monitoring Stack**: Prometheus + Grafana for real-time metrics collection and visualization
- **Testing Suite**: Selenium (functional) + JMeter (performance) test automation

## Quick Start

### Prerequisites

- Python 3.10+
- Docker 24.0+ & minikube 1.32+
- kubectl 1.28+ & Helm 3.13+
- (Optional) Apache JMeter 5.6+, Google Chrome 120+

### Installation

```bash
# Clone repository
git clone https://github.com/Anarchy44/software_testing.git
cd software_testing

# Install Python dependencies
pip install -r requirements.txt
```

### Run FluxEV Experiment (Standalone Mode)

No Kubernetes required — generates synthetic KPI data and runs anomaly detection:

```bash
# Generate sample Prometheus-style metrics
python scripts/generate_sample_data.py

# Run FluxEV anomaly detection
export PYTHONPATH="$PWD/src"
python scripts/run_fluxev_experiment.py --input data/sample_prometheus_metrics.csv
```

Expected output in `outputs/fluxev/`:

```json
{
  "precision": 1.000,
  "recall": 0.875,
  "f1": 0.933
}
```

## Project Structure

```
.
├── src/fluxev/                   # FluxEV detector implementation
│   └── detector.py               # Core algorithm: EWMA + SPOT thresholding
├── services/diagnosis-service/   # Custom microservice for anomaly queries
│   ├── app.py                    # HTTP API (/health, /summary, /anomalies)
│   └── Dockerfile                # Container image definition
├── scripts/                      # Automation scripts
│   ├── generate_sample_data.py   # Synthetic KPI data generator
│   ├── run_fluxev_experiment.py  # Main experiment runner
│   ├── run_ablation.py           # Ablation study (two-step smoothing)
│   ├── build_report.py           # DOCX report generator
│   ├── build_report_pdf.py       # PDF report generator
│   └── *.sh                      # Deployment & testing shell scripts
├── tests/                        # Test suites
│   ├── selenium/                 # Functional tests (Edge browser)
│   │   ├── conftest.py           # pytest fixtures
│   │   └── test_frontend.py      # Homepage/Browse/Checkout tests
│   └── jmeter/                   # Performance test plan
│       └── online_boutique_test.jmx  # 50 concurrent users, 5min duration
├── k8s/                          # Kubernetes manifests
│   ├── diagnosis-service.yaml    # Custom service deployment
│   ├── prometheus-*.yaml         # Monitoring stack
│   ├── grafana-*.yaml            # Visualization dashboards
│   └── chaos-experiments/        # Fault injection scenarios
├── outputs/                      # Experiment results
│   ├── fluxev/figures/           # Detection plots & score distributions
│   ├── ablation/figures/         # Ablation comparison charts
│   └── jmeter/                   # Performance test reports
├── deliverables/                 # Final reports & presentations
├── docs/paper_notes.md           # Research notes (FluxEV vs Donut)
└── requirements.txt              # Python dependencies
```

## Features

### 1. FluxEV Anomaly Detection

Implements the four-stage FluxEV pipeline from the paper:

1. **EWMA-based Fluctuation Extraction**: Captures short-term volatility in KPI time series
2. **Two-Step Smoothing**: Suppresses noise while preserving true anomaly signals
3. **SPOT + MOM-POT Thresholding**: Automatic threshold selection using Extreme Value Theory
4. **Parameter Sensitivity Analysis**: Validates robustness across different window sizes

Run ablation study to verify two-step smoothing contribution:

```bash
python scripts/run_ablation.py --input data/sample_prometheus_metrics.csv
```

### 2. ChaosMesh Fault Injection

Three fault scenarios targeting Online Boutique microservices:

| Scenario | Target | Effect |
|----------|--------|--------|
| Network Delay | frontend → cartservice | 200ms latency injection |
| Pod Kill | cartservice | Random pod termination |
| CPU Stress | productcatalogservice | 80% CPU load |

Deploy fault experiments:

```bash
./scripts/setup_chaosmesh.sh
```

### 3. Monitoring & Observability

**Prometheus Configuration**: Scrapes Istio sidecar metrics (`istio_request_duration_milliseconds_bucket`) with 2-minute rate windows.

**Grafana Dashboards**: Pre-configured panels for:
- Request latency P95/P99 by service
- Error rate trends
- Anomaly detection scores (via diagnosis-service)

Access dashboards:

```bash
kubectl port-forward svc/prometheus 9090:9090 -n monitoring
kubectl port-forward svc/grafana 3000:3000 -n monitoring
```

### 4. Automated Testing

**Selenium Tests** (Edge browser):

```bash
# Port-forward frontend service
kubectl port-forward svc/frontend 8081:80 -n default

# Run functional tests
pytest tests/selenium/ -v
```

Test coverage:
- Homepage loads with visible products
- Product detail page navigation
- Complete checkout flow (Add to Cart → Checkout)

**JMeter Performance Test**:

```bash
./scripts/run_jmeter_test.sh
```

Test plan: 50 virtual users, 30s ramp-up, 5min duration, targeting Homepage/Cart/Product pages.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Online Boutique                     │
│  (frontend, cartservice, productcatalogservice, ...) │
└──────────────┬──────────────────────────────────────┘
               │ Istio sidecar proxies (envoy)
               ▼
┌─────────────────────────────────────────────────────┐
│              Prometheus (monitoring)                 │
│  Scrapes: istio_request_duration_milliseconds_bucket │
└──────────────┬──────────────────────────────────────┘
               │ Query_range API
               ▼
┌─────────────────────────────────────────────────────┐
│          FluxEV Detector (offline analysis)          │
│  EWMA → Two-Step Smoothing → SPOT Thresholding      │
└──────────────┬──────────────────────────────────────┘
               │ Results CSV
               ▼
┌─────────────────────────────────────────────────────┐
│           diagnosis-service (K8s deployment)         │
│  GET /summary, GET /anomalies, GET /metrics         │
└─────────────────────────────────────────────────────┘
```

## Reproduction Guide

### Full Deployment on minikube

```bash
# 1. Start cluster
minikube start --driver=docker --cpus=4 --memory=6144

# 2. Deploy Online Boutique
export ONLINE_BOUTIQUE_REPO_URL="https://github.com/GoogleCloudPlatform/microservices-demo.git"
./scripts/deploy_online_boutique.sh

# 3. Build & deploy diagnosis-service
docker build -t diagnosis-service:local ./services/diagnosis-service
minikube image load diagnosis-service:local
kubectl apply -f k8s/diagnosis-service.yaml

# 4. Setup monitoring
./scripts/setup_prometheus.sh

# 5. Inject faults
./scripts/setup_chaosmesh.sh

# 6. Collect metrics
python scripts/run_fault_collection.py --duration 30

# 7. Verify deployment
python scripts/verify_deployment.py
```

### Generate Reports

```bash
# Generate evidence screenshots
python scripts/generate_evidence_assets.py

# Build DOCX report
python scripts/build_report.py

# Build PDF report
python scripts/build_report_pdf.py
```

Outputs saved to `deliverables/`.

## Key Findings

### FluxEV vs Donut Comparison

| Aspect | FluxEV | Donut |
|--------|--------|-------|
| Methodology | Statistical (EWMA + EVT) | Deep Learning (VAE) |
| Threshold Selection | Automatic (SPOT + POT) | Manual (fixed percentile) |
| Missing Data Handling | Linear interpolation bias correction | MCMC imputation |
| Training Requirement | None (online algorithm) | Requires labeled training data |
| Interpretability | High (explicit smoothing steps) | Low (black-box latent space) |

### Ablation Study Results

Two-step smoothing improves F1 score by ~15% compared to no-smoothing baseline, demonstrating its effectiveness in suppressing noise while retaining true anomaly signals.

## Deliverables

Final submission materials:

- [Report PDF](deliverables/software_testing_and_maintenance_final_report.pdf)
- [Report DOCX](deliverables/software_testing_and_maintenance_final_report.docx)
- [Presentation PPTX](deliverables/software_testing_final_presentation.pptx)
- [Research Notes](docs/paper_notes.md) (FluxEV & Donut paper analysis)

## Environment Compatibility

| Platform | Status | Notes |
|----------|--------|-------|
| Windows 10/11 | Tested | Use PowerShell 7 for `.ps1` scripts, Git Bash for `.sh` |
| macOS | Compatible | Font paths auto-detected (PingFang.ttc) |
| Linux | Compatible | Font paths auto-detected (NotoSansCJK) |

Cross-platform font registration implemented in `build_report_pdf.py` and `generate_evidence_assets.py`.

## License

This project is for educational purposes as part of the Software Testing and Maintenance course (Spring 2026).

## Acknowledgments

- [Online Boutique](https://github.com/GoogleCloudPlatform/microservices-demo) by Google Cloud
- [FluxEV Paper](https://arxiv.org/abs/2106.08753): "FluxEV: A Fast and Explainable Method for Time Series Anomaly Detection"
- [ChaosMesh](https://chaos-mesh.org/) by CNCF
- [Donut Paper](https://arxiv.org/abs/1802.03903): "Unsupervised Anomaly Detection via Variational Auto-Encoder"
