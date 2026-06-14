#!/usr/bin/env bash
# run_donut_demo.sh - Quick demo script for Donut anomaly detection
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT" || exit 1

echo "=========================================="
echo "Donut Anomaly Detection Demo"
echo "=========================================="
echo ""

# Check if sample data exists
SAMPLE_DATA="data/sample_prometheus_metrics.csv"
if [ ! -f "$SAMPLE_DATA" ]; then
    echo "Sample data not found. Generating..."
    python scripts/generate_sample_data.py
fi

# Check PyTorch installation
if ! python -c "import torch" 2>/dev/null; then
    echo "PyTorch not installed. Installing dependencies..."
    pip install -r requirements_gpu.txt
fi

# Run Donut experiment
echo ""
echo "Running Donut experiment..."
echo "Output will be saved to outputs/donut/"
echo ""

python scripts/run_donut_experiment.py --input "$SAMPLE_DATA"

echo ""
echo "=========================================="
echo "Demo complete! Results in outputs/donut/"
echo "=========================================="
echo ""
echo "To compare with FluxEV:"
echo "  python scripts/run_donut_vs_fluxev.py --input $SAMPLE_DATA"
echo ""
echo "View results:"
echo "  - outputs/donut/experiment_summary.json"
echo "  - outputs/donut/figures/donut_training_and_detection.png"
echo "  - outputs/donut/figures/donut_score_timeline.png"
