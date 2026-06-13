"""Pytest configuration for Selenium tests."""

from __future__ import annotations

import os

import pytest


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "selenium: Selenium browser-based functional tests")
    # Check availability
    try:
        from selenium import webdriver  # noqa: F401
    except ImportError:
        pytest.exit("selenium not installed. Run: pip install selenium", returncode=1)

    # Check frontend URL accessibility
    url = os.environ.get("FRONTEND_URL", "http://localhost:8081")
    import urllib.request
    try:
        urllib.request.urlopen(url, timeout=5)
    except Exception:
        print(f"\n[WARNING] Frontend at {url} is not accessible. Tests may fail.")
        print("  Start port-forward: kubectl port-forward svc/frontend 8081:80\n")
