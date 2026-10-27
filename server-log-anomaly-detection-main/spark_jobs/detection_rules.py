"""Pure anomaly detection rules used by the streaming detector and tests."""

from __future__ import annotations

from typing import Any


def _result(anomaly_type: str, severity: str, message: str) -> dict[str, str]:
    return {"anomaly_type": anomaly_type, "severity": severity, "message": message}


def latency_sigma_rule(latency_ms: float, mean_latency_ms: float, stddev_latency_ms: float) -> dict[str, str] | None:
    threshold = mean_latency_ms + 3 * stddev_latency_ms
    if latency_ms > threshold:
        return _result("latency_spike", "high", f"latency {latency_ms:.2f}ms exceeds 3-sigma threshold {threshold:.2f}ms")
    return None


def unauthorized_threshold_rule(unauthorized_count: int, threshold: int = 100) -> dict[str, str] | None:
    if unauthorized_count > threshold:
        return _result("brute_force", "critical", f"{unauthorized_count} HTTP 401/403 responses from one IP")
    return None


def error_rate_rule(error_count: int, request_count: int, threshold: float = 0.01) -> dict[str, str] | None:
    if request_count > 0 and error_count / request_count > threshold:
        rate = error_count / request_count
        return _result("error_burst", "high", f"HTTP 500 rate is {rate:.2%}")
    return None


def traffic_surge_rule(request_count: int, trailing_baseline: float, multiplier: float = 5.0) -> dict[str, str] | None:
    if trailing_baseline > 0 and request_count > multiplier * trailing_baseline:
        return _result("traffic_surge", "critical", f"{request_count} requests exceeds baseline {trailing_baseline:.2f} by more than {multiplier:g}x")
    return None


def classify_latency(row: dict[str, Any]) -> dict[str, str] | None:
    return latency_sigma_rule(
        float(row["latency_ms"]),
        float(row["mean_latency_ms"]),
        float(row["stddev_latency_ms"]),
    )
