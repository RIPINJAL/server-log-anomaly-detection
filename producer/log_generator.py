"""Generate synthetic JSON web access logs with injectable anomaly scenarios."""

from __future__ import annotations

import argparse
import json
import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterator, TextIO


METHODS = ("GET", "POST", "PUT", "DELETE")
NORMAL_URLS = ("/", "/products", "/search", "/api/orders", "/health")
ANOMALY_SCENARIOS = ("brute-force", "error-burst", "ddos", "latency")
OUTPUT_FORMATS = ("json", "apache")


@dataclass
class LogGenerator:
    """Produce normal traffic and deterministic scenario-specific anomalies."""

    rate: float = 10.0
    anomaly_rate: float = 0.01
    scenario: str | None = None
    output_format: str = "json"
    seed: int | None = None
    _random: random.Random = field(init=False, repr=False)
    _burst_remaining: int = field(default=0, init=False, repr=False)
    _burst_ip: str = field(default="", init=False, repr=False)
    _current_scenario: str | None = field(default=None, init=False, repr=False)
    _ddos_pool: tuple[str, ...] = field(default=(), init=False, repr=False)

    def __post_init__(self) -> None:
        if self.rate <= 0:
            raise ValueError("rate must be greater than zero")
        if not 0 <= self.anomaly_rate <= 1:
            raise ValueError("anomaly_rate must be between zero and one")
        if self.scenario is not None and self.scenario not in ANOMALY_SCENARIOS:
            raise ValueError(f"unsupported scenario: {self.scenario}")
        if self.output_format not in OUTPUT_FORMATS:
            raise ValueError(f"unsupported output format: {self.output_format}")
        self._random = random.Random(self.seed)
        self._ddos_pool = tuple(self._random_ip() for _ in range(5))

    def _random_ip(self) -> str:
        return ".".join(str(self._random.randint(1, 254)) for _ in range(4))

    def _normal_log(self) -> dict[str, object]:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "client_ip": self._random_ip(),
            "method": self._random.choice(METHODS),
            "url": self._random.choice(NORMAL_URLS),
            "status_code": self._random.choices((200, 201, 204, 301, 404), weights=(70, 10, 5, 5, 10))[0],
            "latency_ms": round(max(1.0, self._random.gauss(120, 25)), 2),
            "user_id": f"user-{self._random.randint(1000, 9999)}",
        }

    def _start_burst(self, scenario: str) -> None:
        self._burst_ip = self._random_ip()
        self._current_scenario = scenario
        self._burst_remaining = {
            "brute-force": self._random.randint(110, 140),
            "error-burst": self._random.randint(20, 40),
            "ddos": self._random.randint(100, 200),
            "latency": 1,
        }[scenario]

    def _apply_anomaly(self, log: dict[str, object], scenario: str) -> dict[str, object]:
        if scenario == "latency":
            log["latency_ms"] = round(self._random.uniform(50, 100) * float(log["latency_ms"]), 2)
        elif scenario == "error-burst":
            log["client_ip"] = self._burst_ip
            log["status_code"] = 500
        elif scenario == "brute-force":
            log["client_ip"] = self._burst_ip
            log["method"] = "POST"
            log["url"] = "/login"
            log["status_code"] = 401
            log["latency_ms"] = round(self._random.uniform(40, 100), 2)
        elif scenario == "ddos":
            log["client_ip"] = self._random.choice(self._ddos_pool)
            log["url"] = self._random.choice(("/", "/api/search", "/login"))
        return log

    def next_log(self) -> dict[str, object]:
        """Return one log record, potentially belonging to an anomaly burst."""
        scenario = self.scenario
        if self._burst_remaining == 0 and (self.scenario is not None or self._random.random() < self.anomaly_rate):
            scenario = scenario or self._random.choice(ANOMALY_SCENARIOS)
            self._start_burst(scenario)
        elif self._burst_remaining > 0 and scenario is None:
            scenario = self._active_scenario

        log = self._normal_log()
        if self._burst_remaining > 0:
            log = self._apply_anomaly(log, scenario or "latency")
            self._burst_remaining -= 1
        return log

    @property
    def _active_scenario(self) -> str:
        if self._burst_remaining == 0:
            return "latency"
        if self.scenario:
            return self.scenario
        return self._current_scenario or "latency"

    def records(self, count: int | None = None) -> Iterator[dict[str, object]]:
        produced = 0
        while count is None or produced < count:
            yield self.next_log()
            produced += 1

    def _apache_line(self, record: dict[str, object]) -> str:
        timestamp = datetime.fromisoformat(str(record["timestamp"]).replace("Z", "+00:00"))
        apache_timestamp = timestamp.strftime("%d/%b/%Y:%H:%M:%S %z")
        return (
            f'{record["client_ip"]} - {record["user_id"]} [{apache_timestamp}] '
            f'"{record["method"]} {record["url"]} HTTP/1.1" '
            f'{record["status_code"]} {self._random.randint(256, 8192)} "-" "server-log-generator/1.0"'
        )

    def render(self, record: dict[str, object]) -> str:
        if self.output_format == "apache":
            return self._apache_line(record)
        return json.dumps(record, separators=(",", ":"))

    def run(self, output: TextIO, count: int | None = None) -> None:
        interval = 1 / self.rate
        for record in self.records(count):
            output.write(self.render(record) + "\n")
            output.flush()
            if count is None:
                time.sleep(interval)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rate", type=float, default=10.0, help="normal records per second")
    parser.add_argument("--anomaly-rate", type=float, default=0.01, help="probability of starting an anomaly burst")
    parser.add_argument("--scenario", choices=ANOMALY_SCENARIOS, help="force one anomaly scenario")
    parser.add_argument("--format", dest="output_format", choices=OUTPUT_FORMATS, default="json", help="output format")
    parser.add_argument("--count", type=int, help="stop after this many records instead of running forever")
    parser.add_argument("--seed", type=int, help="seed the generator for repeatable output")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    generator = LogGenerator(
        rate=args.rate,
        anomaly_rate=args.anomaly_rate,
        scenario=args.scenario,
        output_format=args.output_format,
        seed=args.seed,
    )
    generator.run(output=__import__("sys").stdout, count=args.count)


if __name__ == "__main__":
    main()
