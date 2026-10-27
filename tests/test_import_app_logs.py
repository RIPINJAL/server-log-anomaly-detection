from datetime import datetime

import pytest

from scripts.import_app_logs import detect_sample_anomalies, parse_log_line


def test_parse_log_line_preserves_fields_and_redacts_email():
    document = parse_log_line(
        "2026-08-01 12:00:00.123 | INFO     | app.worker:run:42 - Contact test@example.com",
        "app.log.txt",
        7,
    )

    assert document == {
        "timestamp": "2026-08-01T12:00:00.123000",
        "log_level": "INFO",
        "logger": "app.worker",
        "function": "run",
        "source_file": "app.log.txt",
        "source_line": 42,
        "message": "Contact [redacted email]",
    }


def test_parse_log_line_rejects_unrecognized_format():
    with pytest.raises(ValueError, match="line 3"):
        parse_log_line("not a structured log", "app.log.txt", 3)


def test_sample_analyzer_flags_warning_and_three_sigma_traffic_surge():
    documents = [
        {
            "timestamp": datetime(2026, 8, 1, 12, minute).isoformat(),
            "log_level": "INFO",
            "logger": "app.worker",
            "function": "run",
            "source_file": "app.log.txt",
            "source_line": 1,
            "message": "Started",
        }
        for minute in range(20)
    ]
    documents.extend(
        [
            {
                "timestamp": datetime(2026, 8, 1, 12, 0, second).isoformat(),
                "log_level": "INFO",
                "logger": "app.worker",
                "function": "run",
                "source_file": "app.log.txt",
                "source_line": 2,
                "message": "Started",
            }
            for second in range(100)
        ]
    )
    documents.append(
        {
            "timestamp": "2026-08-01T12:04:30",
            "log_level": "WARNING",
            "logger": "app.worker",
            "function": "run",
            "source_file": "app.log.txt",
            "source_line": 108,
            "message": "Warning raised",
        }
    )

    findings = detect_sample_anomalies(documents)

    assert sum(item["anomaly_type"] == "application_warning" for item in findings) == 1
    surge = [item for item in findings if item["anomaly_type"] == "traffic_surge"]
    assert len(surge) == 1
    assert surge[0]["event_count"] == 101
