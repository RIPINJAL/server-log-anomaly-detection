"""Import timestamped Python application logs into Elasticsearch."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean, pstdev
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


LOG_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)"
    r"\s+\|\s+(?P<level>[A-Z]+)\s+\|\s+"
    r"(?P<logger>[^:]+):(?P<function>[^:]+):(?P<source_line>\d+)"
    r"\s+-\s+(?P<message>.*)$"
)
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)


def parse_log_line(line: str, source_file: str, line_number: int) -> dict[str, Any]:
    match = LOG_PATTERN.match(line.rstrip("\r\n"))
    if not match:
        raise ValueError(f"unrecognized log format at line {line_number}")

    values = match.groupdict()
    timestamp = datetime.fromisoformat(values["timestamp"])
    return {
        "timestamp": timestamp.isoformat(),
        "log_level": values["level"],
        "logger": values["logger"],
        "function": values["function"],
        "source_file": source_file,
        "source_line": int(values["source_line"]),
        "message": EMAIL_PATTERN.sub("[redacted email]", values["message"]),
    }


def detect_sample_anomalies(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for document in documents:
        level = document["log_level"]
        if level not in {"WARNING", "ERROR", "CRITICAL"}:
            continue
        findings.append(
            {
                "timestamp": document["timestamp"],
                "window_start": document["timestamp"],
                "window_end": document["timestamp"],
                "anomaly_type": "application_warning" if level == "WARNING" else "application_error",
                "severity": {"WARNING": "medium", "ERROR": "high", "CRITICAL": "critical"}[level],
                "logger": document["logger"],
                "function": document["function"],
                "source_file": document["source_file"],
                "source_line": document["source_line"],
                "message": (
                    f"{document['source_file']}:{document['source_line']} "
                    f"[{document['logger']}] {document['message']}"
                ),
            }
        )

    counts_by_minute: Counter[datetime] = Counter()
    for document in documents:
        timestamp = datetime.fromisoformat(document["timestamp"])
        minute = timestamp.replace(second=0, microsecond=0)
        counts_by_minute[minute] += 1

    if len(counts_by_minute) < 2:
        return findings

    volumes = list(counts_by_minute.values())
    threshold = mean(volumes) + 3 * pstdev(volumes)
    for minute, count in counts_by_minute.items():
        if count <= threshold:
            continue
        findings.append(
            {
                "timestamp": minute.isoformat(),
                "window_start": minute.isoformat(),
                "window_end": (minute + timedelta(minutes=1)).isoformat(),
                "anomaly_type": "traffic_surge",
                "severity": "high",
                "event_count": count,
                "source_file": documents[0]["source_file"],
                "message": (
                    f"{count} log events in one minute exceeded the sample's "
                    f"3-sigma traffic threshold of {threshold:.2f}"
                ),
            }
        )
    return findings


def _request(
    url: str,
    method: str,
    body: bytes | None = None,
    content_type: str = "application/json",
) -> dict[str, Any]:
    headers = {"Content-Type": content_type}
    api_key = os.getenv("ELASTICSEARCH_API_KEY")
    username = os.getenv("ELASTICSEARCH_USERNAME")
    password = os.getenv("ELASTICSEARCH_PASSWORD")
    if api_key:
        headers["Authorization"] = f"ApiKey {api_key}"
    elif username:
        import base64

        token = base64.b64encode(f"{username}:{password or ''}".encode()).decode()
        headers["Authorization"] = f"Basic {token}"

    request = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            result = response.read()
    except (HTTPError, URLError) as exc:
        detail = exc.read().decode("utf-8", errors="replace") if isinstance(exc, HTTPError) else str(exc)
        raise RuntimeError(f"Elasticsearch request failed for {url}: {detail}") from exc
    return json.loads(result) if result else {}


def _document_id(document: dict[str, Any], source_file: str) -> str:
    identity = "\0".join(
        (
            source_file,
            document["timestamp"],
            str(document["source_line"]),
            document["logger"],
            document["message"],
        )
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def index_documents(
    documents: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    elasticsearch_url: str,
) -> None:
    template_path = Path(__file__).parents[1] / "elastic_config" / "index_templates" / "application-logs-template.json"
    template = json.loads(template_path.read_text(encoding="utf-8"))
    base_url = elasticsearch_url.rstrip("/")
    _request(
        f"{base_url}/_index_template/application-logs-template",
        "PUT",
        json.dumps(template).encode("utf-8"),
    )

    source_file = documents[0]["source_file"]
    actions: list[str] = []
    for document in documents:
        date = datetime.fromisoformat(document["timestamp"]).strftime("%Y.%m.%d")
        actions.append(json.dumps({"index": {"_index": f"app-logs-{date}", "_id": _document_id(document, source_file)}}))
        actions.append(json.dumps(document, ensure_ascii=False))
    for finding in findings:
        identity = json.dumps(finding, sort_keys=True, ensure_ascii=False)
        finding_id = hashlib.sha256(f"{source_file}\0{identity}".encode("utf-8")).hexdigest()
        date = datetime.fromisoformat(finding["timestamp"]).strftime("%Y.%m.%d")
        actions.append(json.dumps({"index": {"_index": f"anomalies-{date}", "_id": finding_id}}))
        actions.append(json.dumps(finding, ensure_ascii=False))

    payload = ("\n".join(actions) + "\n").encode("utf-8")
    result = _request(
        f"{base_url}/_bulk?refresh=wait_for",
        "POST",
        payload,
        "application/x-ndjson",
    )
    if result.get("errors"):
        errors = [
            item.get("index", {}).get("error")
            for item in result.get("items", [])
            if item.get("index", {}).get("error")
        ]
        raise RuntimeError(f"Elasticsearch bulk indexing failed: {errors[:3]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log_file", type=Path)
    parser.add_argument(
        "--elasticsearch-url",
        default=os.getenv("ELASTICSEARCH_URL", "http://localhost:9200"),
    )
    args = parser.parse_args()

    source_file = args.log_file.name
    documents = [
        parse_log_line(line, source_file, line_number)
        for line_number, line in enumerate(args.log_file.read_text(encoding="utf-8").splitlines(), start=1)
        if line.strip()
    ]
    if not documents:
        raise ValueError(f"no log records found in {args.log_file}")

    findings = detect_sample_anomalies(documents)
    index_documents(documents, findings, args.elasticsearch_url)
    print(f"Indexed {len(documents)} application logs and {len(findings)} anomalies from {source_file}.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Import failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
