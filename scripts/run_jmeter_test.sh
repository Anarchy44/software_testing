#!/usr/bin/env bash
# run_jmeter_test.sh - Run JMeter performance test on Online Boutique
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT" || exit 1

JMETER_TEST="$PROJECT_ROOT/tests/jmeter/online_boutique_test.jmx"
OUTPUT_DIR="$PROJECT_ROOT/outputs/jmeter"
mkdir -p "$OUTPUT_DIR"

# Check if JMeter is installed
if ! command -v jmeter &> /dev/null; then
    echo "JMeter not found. Please install JMeter 5.6+ and ensure 'jmeter' is in PATH."
    echo "  Download: https://jmeter.apache.org/download_jmeter.cgi"
    exit 1
fi

# Port-forward frontend if not already accessible
FRONTEND_URL="http://localhost:8081"
if ! curl -s -o /dev/null -w "%{http_code}" "$FRONTEND_URL" | grep -q 200; then
    echo "Starting port-forward to frontend..."
    kubectl port-forward svc/frontend 8081:80 &
    PF_PID=$!
    sleep 3
    trap "kill $PF_PID 2>/dev/null" EXIT
fi

echo "Running JMeter test plan..."
jmeter -n \
    -t "$JMETER_TEST" \
    -l "$OUTPUT_DIR/results.jtl" \
    -e -o "$OUTPUT_DIR/report" \
    -Jfrontend.base_url="$FRONTEND_URL"

echo "JMeter test complete. Results in $OUTPUT_DIR/"
echo "  JTL log: $OUTPUT_DIR/results.jtl"
echo "  HTML report: $OUTPUT_DIR/report/index.html"
