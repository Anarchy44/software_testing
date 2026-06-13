from __future__ import annotations

import csv
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

DATA_PATH = Path(os.environ.get("DIAGNOSIS_DATA", "/app/data/metrics_with_scores.csv"))
REQUEST_COUNT = 0
START_TIME = time.time()


def load_rows() -> list[dict[str, str]]:
    if not DATA_PATH.exists():
        return []
    with DATA_PATH.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def json_response(handler: BaseHTTPRequestHandler, payload, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def metrics_text(rows: list[dict[str, str]]) -> str:
    """Build Prometheus exposition format metrics."""
    lines = []

    # Counter: total HTTP requests
    lines.append("# HELP diagnosis_requests_total Total number of HTTP requests served.")
    lines.append("# TYPE diagnosis_requests_total counter")
    lines.append(f"diagnosis_requests_total {REQUEST_COUNT}")

    # Gauge: number of data points loaded
    lines.append("# HELP diagnosis_data_points Number of data points in the loaded CSV.")
    lines.append("# TYPE diagnosis_data_points gauge")
    lines.append(f"diagnosis_data_points {len(rows)}")

    # Gauge: predicted anomalies
    predicted = sum(1 for row in rows if row.get("predicted_anomaly") == "1")
    lines.append("# HELP diagnosis_predicted_anomalies Number of predicted anomalies.")
    lines.append("# TYPE diagnosis_predicted_anomalies gauge")
    lines.append(f"diagnosis_predicted_anomalies {predicted}")

    # Gauge: threshold
    threshold = float(rows[0].get("threshold", "0")) if rows else 0.0
    lines.append("# HELP diagnosis_threshold Current anomaly detection threshold.")
    lines.append("# TYPE diagnosis_threshold gauge")
    lines.append(f"diagnosis_threshold {threshold}")

    # Gauge: uptime in seconds
    uptime = time.time() - START_TIME
    lines.append("# HELP diagnosis_uptime_seconds Service uptime in seconds.")
    lines.append("# TYPE diagnosis_uptime_seconds gauge")
    lines.append(f"diagnosis_uptime_seconds {uptime:.1f}")

    return "\n".join(lines) + "\n"


def text_response(handler: BaseHTTPRequestHandler, text: str, content_type: str = "text/plain; charset=utf-8") -> None:
    body = text.encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        global REQUEST_COUNT
        REQUEST_COUNT += 1

        parsed = urlparse(self.path)

        # Prometheus metrics endpoint
        if parsed.path == "/metrics":
            rows = load_rows()
            text_response(self, metrics_text(rows))
            return

        if parsed.path == "/health":
            json_response(self, {"status": "ok", "data_exists": DATA_PATH.exists()})
            return

        rows = load_rows()
        if parsed.path == "/summary":
            if not rows:
                json_response(self, {"status": "empty", "message": "metrics file not found"}, 404)
                return
            threshold = rows[0].get("threshold", "0")
            predicted = sum(1 for row in rows if row.get("predicted_anomaly") == "1")
            json_response(
                self,
                {
                    "status": "ok",
                    "points": len(rows),
                    "predicted_anomalies": predicted,
                    "threshold": float(threshold),
                    "metric": rows[0].get("metric", "unknown"),
                },
            )
            return

        if parsed.path == "/anomalies":
            limit = int(parse_qs(parsed.query).get("limit", ["20"])[0])
            anomalies = [row for row in rows if row.get("predicted_anomaly") == "1"][: min(limit, 100)]
            json_response(self, anomalies)
            return

        json_response(self, {"error": "not found"}, 404)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()