from spark_jobs.detection_rules import (
    error_rate_rule,
    latency_sigma_rule,
    traffic_surge_rule,
    unauthorized_threshold_rule,
)


def test_window_summary_data_flags_known_anomalous_windows():
    window = {
        "request_count": 120,
        "error_count": 3,
        "unauthorized_count": 150,
        "trailing_baseline": 10,
        "latency_ms": 131,
        "mean_latency_ms": 100,
        "stddev_latency_ms": 10,
    }

    assert error_rate_rule(window["error_count"], window["request_count"])["anomaly_type"] == "error_burst"
    assert unauthorized_threshold_rule(window["unauthorized_count"])["anomaly_type"] == "brute_force"
    assert traffic_surge_rule(window["request_count"], window["trailing_baseline"])["anomaly_type"] == "traffic_surge"
    assert latency_sigma_rule(window["latency_ms"], window["mean_latency_ms"], window["stddev_latency_ms"])["anomaly_type"] == "latency_spike"


def test_latency_sigma_rule_flags_only_above_three_sigma():
    assert latency_sigma_rule(131, 100, 10)["anomaly_type"] == "latency_spike"
    assert latency_sigma_rule(130, 100, 10) is None


def test_unauthorized_rule_uses_strict_threshold():
    assert unauthorized_threshold_rule(101)["anomaly_type"] == "brute_force"
    assert unauthorized_threshold_rule(100) is None


def test_error_rate_rule_uses_strict_one_percent_threshold():
    assert error_rate_rule(2, 100)["anomaly_type"] == "error_burst"
    assert error_rate_rule(1, 100) is None
    assert error_rate_rule(0, 0) is None


def test_traffic_surge_rule_uses_strict_five_x_threshold():
    assert traffic_surge_rule(51, 10)["anomaly_type"] == "traffic_surge"
    assert traffic_surge_rule(50, 10) is None
    assert traffic_surge_rule(100, 0) is None
