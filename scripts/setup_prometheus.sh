#!/usr/bin/env bash
# setup_prometheus.sh - Deploy Prometheus to minikube monitoring namespace
set -euo pipefail

echo "=== Setting up Prometheus ==="

# Create monitoring namespace if not exists
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -

# Apply configmap with scrape config
kubectl apply -f k8s/prometheus-config.yaml

# Apply deployment + service + RBAC
kubectl apply -f k8s/prometheus-deployment.yaml

# Wait for pod ready
echo "Waiting for Prometheus pod to be ready..."
kubectl wait --for=condition=ready pod -l app=prometheus -n monitoring --timeout=120s

echo "Prometheus deployed successfully."
echo "Access via: kubectl port-forward -n monitoring svc/prometheus 9090:9090"
