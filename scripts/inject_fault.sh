#!/usr/bin/env bash
# inject_fault.sh — Manually inject a ChaosMesh fault experiment
# Usage: bash scripts/inject_fault.sh <network-delay|pod-kill|cpu-stress>

set -euo pipefail

FAULT=${1:-}

if [ -z "$FAULT" ]; then
  echo "Usage: bash scripts/inject_fault.sh <network-delay|pod-kill|cpu-stress>"
  echo ""
  echo "Available faults:"
  echo "  network-delay  — Inject 200ms latency from frontend → cartservice"
  echo "  pod-kill       — Kill one cartservice pod"
  echo "  cpu-stress     — Stress CPU on productcatalogservice (80% load)"
  echo ""
  exit 1
fi

FAULT_FILE="k8s/chaos-experiments/${FAULT}.yaml"

if [ ! -f "$FAULT_FILE" ]; then
  echo "ERROR: Fault file not found: $FAULT_FILE"
  exit 1
fi

echo "=== Injecting fault: ${FAULT} ==="
kubectl apply -f "$FAULT_FILE"

echo ""
echo "Fault injected. Check status:"
echo "  kubectl get networkchaos,podchaos,stresschaos -n default"

FALLBACK_NAME=""
if [ "$FAULT" = "network-delay" ]; then
  FALLBACK_NAME="frontend-to-cartservice-delay"
elif [ "$FAULT" = "pod-kill" ]; then
  FALLBACK_NAME="cartservice-pod-kill"
elif [ "$FAULT" = "cpu-stress" ]; then
  FALLBACK_NAME="productcatalog-cpu-stress"
fi

echo ""
echo "To check this experiment:"
echo "  kubectl describe networkchaos/${FALLBACK_NAME} -n default 2>/dev/null || kubectl describe podchaos/${FALLBACK_NAME} -n default 2>/dev/null || kubectl describe stresschaos/${FALLBACK_NAME} -n default 2>/dev/null"
echo ""
echo "To remove this fault:"
echo "  kubectl delete -f ${FAULT_FILE}"