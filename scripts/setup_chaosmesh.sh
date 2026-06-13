#!/usr/bin/env bash
# setup_chaosmesh.sh - Install ChaosMesh via Helm on minikube
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT" || exit 1

echo "=== Setting up ChaosMesh ==="

# Add chaos-mesh helm repo
helm repo add chaos-mesh https://charts.chaos-mesh.org 2>/dev/null || true
helm repo update

# Install ChaosMesh
kubectl create namespace chaos-mesh --dry-run=client -o yaml | kubectl apply -f -

helm upgrade --install chaos-mesh chaos-mesh/chaos-mesh \
  --namespace chaos-mesh \
  --set chaosDaemon.runtime=containerd \
  --set chaosDaemon.socketPath=/run/containerd/containerd.sock \
  --version 2.7.0 \
  --wait \
  --timeout 10m

# Wait for pods ready
echo "Waiting for ChaosMesh pods..."
kubectl wait --for=condition=ready pod -l app.kubernetes.io/instance=chaos-mesh -n chaos-mesh --timeout=180s

# Apply the chaos experiments (they will run per schedule)
kubectl apply -f "$PROJECT_ROOT/k8s/chaos-experiments/network-delay.yaml"
kubectl apply -f "$PROJECT_ROOT/k8s/chaos-experiments/pod-kill.yaml"
kubectl apply -f "$PROJECT_ROOT/k8s/chaos-experiments/cpu-stress.yaml"

echo "ChaosMesh installed and experiments applied."
echo "Check: kubectl get networkchaos,podchaos,stresschaos -A"
