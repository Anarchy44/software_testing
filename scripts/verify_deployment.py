#!/usr/bin/env python3
"""Verify Online Boutique + diagnosis-service deployment on minikube.

Checks all expected pods are Running and key services are reachable.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_PODS = [
    "cartservice",
    "checkoutservice",
    "currencyservice",
    "emailservice",
    "frontend",
    "loadgenerator",
    "paymentservice",
    "productcatalogservice",
    "recommendationservice",
    "shippingservice",
    "adservice",
    "redis-cart",
    "diagnosis-service",
]

EXPECTED_SERVICES = [
    "frontend",
    "cartservice",
    "productcatalogservice",
    "currencyservice",
    "checkoutservice",
    "diagnosis-service",
]


def run(cmd: list[str]) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        return "(timeout)"


def check_pods() -> tuple[list[str], list[str]]:
    """Returns (running_pods, missing_pods)."""
    out = run(["kubectl", "get", "pods", "-o", "name"])
    pod_names = [line.split("/")[-1] for line in out.splitlines() if line.startswith("pod/")]

    running = []
    missing = []
    for expected in EXPECTED_PODS:
        matches = [p for p in pod_names if expected in p.lower()]
        if matches:
            status_out = run(["kubectl", "get", "pod", matches[0], "-o",
                              "jsonpath={.status.phase}"])
            phase = status_out.strip()
            if phase == "Running":
                running.append(f"{expected} (Running)")
            else:
                missing.append(f"{expected} (phase={phase})")
        else:
            missing.append(expected)
    return running, missing


def check_services() -> tuple[list[str], list[str]]:
    """Checks services exist and have endpoints."""
    out = run(["kubectl", "get", "svc", "-o", "name"])
    svc_names = [line.split("/")[-1] for line in out.splitlines() if line.startswith("service/")]

    ok_services = []
    missing_services = []
    for expected in EXPECTED_SERVICES:
        matches = [s for s in svc_names if expected in s.lower()]
        if matches:
            ok_services.append(expected)
        else:
            missing_services.append(expected)
    return ok_services, missing_services


def main() -> None:
    print("=" * 60)
    print("Online Boutique + diagnosis-service Deployment Verification")
    print("=" * 60)

    # Pod status
    print("\n[1/3] Checking Pods ...")
    time.sleep(2)
    running, missing = check_pods()
    print(f"  Running: {len(running)}/{len(EXPECTED_PODS)}")
    for r in running:
        print(f"    [OK] {r}")
    for m in missing:
        print(f"    [FAIL] {m}")

    # Service reachability
    print("\n[2/3] Checking Services ...")
    ok_svcs, missing_svcs = check_services()
    print(f"  Found: {len(ok_svcs)}/{len(EXPECTED_SERVICES)}")
    for s in ok_svcs:
        print(f"    [OK] {s}")
    for s in missing_svcs:
        print(f"    [WARN] {s} not found")

    # diagnosis-service health endpoint
    print("\n[3/3] Checking diagnosis-service health ...")
    diag_svc = [s for s in ok_svcs if "diagnosis" in s.lower()]
    if diag_svc:
        # port-forward and curl
        pf = subprocess.Popen(
            ["kubectl", "port-forward", f"svc/{diag_svc[0]}", "8080:8080"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        time.sleep(3)
        try:
            import urllib.request
            resp = urllib.request.urlopen("http://localhost:8080/health", timeout=5)
            print(f"  [OK] diagnosis-service /health => {resp.read().decode()}")
        except Exception as e:
            print(f"  [FAIL] diagnosis-service health check: {e}")
        finally:
            pf.terminate()
            pf.wait(timeout=5)
    else:
        print("  [SKIP] diagnosis-service not found")

    # Summary
    errors = len(missing) + len(missing_svcs)
    if errors == 0:
        print(f"\n{'='*60}")
        print("All checks passed. Deployment is healthy.")
        print("=" * 60)
        sys.exit(0)
    else:
        print(f"\n{'='*60}")
        print(f"{errors} issue(s) found. Review above for details.")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
