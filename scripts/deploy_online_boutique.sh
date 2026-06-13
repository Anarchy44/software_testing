#!/usr/bin/env bash
# deploy_online_boutique.sh - Deploy Online Boutique to minikube (Linux/Mac)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT" || exit 1

REPO_URL="${ONLINE_BOUTIQUE_REPO_URL:-https://github.com/GoogleCloudPlatform/microservices-demo.git}"
RELEASE_DIR="$PROJECT_ROOT/third_party/microservices-demo"

echo "=== Deploying Online Boutique ==="

# Clone repo if not present
if [ ! -d "$RELEASE_DIR" ]; then
    echo "Cloning $REPO_URL ..."
    git clone --depth 1 "$REPO_URL" "$RELEASE_DIR"
fi

cd "$RELEASE_DIR"

# Deploy to minikube
echo "Applying Kubernetes manifests..."
kubectl apply -f ./release/kubernetes-manifests.yaml

echo "Waiting for deployments to be ready..."
kubectl wait --for=condition=available deployment --all -n default --timeout=300s

echo "Online Boutique deployed."
echo "Frontend: kubectl port-forward svc/frontend 8081:80"
