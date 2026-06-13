#!/usr/bin/env bash
# setup_istio.sh — Install Istio with demo profile and enable sidecar injection
# Prerequisites: minikube running, kubectl configured
# Supports: Linux, macOS, Windows (Git Bash / MSYS2)

set -euo pipefail

ISTIO_VERSION="1.22.0"
ISTIO_DIR="istio-${ISTIO_VERSION}"

# ── Platform detection ──
OS="linux"
EXT="tar.gz"
case "$(uname -s)" in
  Darwin)  OS="osx" ;;
  MINGW*|MSYS*|CYGWIN*) OS="win"; EXT="zip" ;;
esac

ARCHIVE="istio-${ISTIO_VERSION}-${OS}.${EXT}"

echo "=== Step 1: Download istioctl (if needed) ==="
if ! command -v istioctl &>/dev/null; then
  if [ ! -d "$ISTIO_DIR" ]; then
    echo "Detected platform: ${OS}"
    echo "Downloading Istio ${ISTIO_VERSION}..."
    curl -L "https://github.com/istio/istio/releases/download/${ISTIO_VERSION}/${ARCHIVE}" -o "${ARCHIVE}"
    if [ "$EXT" = "zip" ]; then
      unzip -q "${ARCHIVE}"
    else
      tar xzf "${ARCHIVE}"
    fi
    rm -f "${ARCHIVE}"
  fi
  export PATH="$PWD/${ISTIO_DIR}/bin:$PATH"
  echo "istioctl path: $(which istioctl)"
fi

echo "=== Step 2: Install Istio (demo profile) ==="
istioctl install --set profile=demo -y --set meshConfig.enablePrometheusMerge=true

echo "=== Step 3: Enable sidecar injection on default namespace ==="
kubectl label namespace default istio-injection=enabled --overwrite

echo "=== Step 4: Restart deployments to inject sidecars ==="
kubectl rollout restart deployment -n default

echo "=== Step 5: Wait for pods to be ready (2/2 containers) ==="
echo "Waiting for pods to restart with istio-proxy sidecar..."
kubectl wait --for=condition=ready pod --all -n default --timeout=300s || true

echo ""
echo "=== Done. Checking pod status ==="
kubectl get pods -n default

echo ""
echo "Verification: each pod should show 2/2 in the READY column (app + istio-proxy)"
echo "If pods are stuck, check: kubectl describe pod <pod-name> -n default"
