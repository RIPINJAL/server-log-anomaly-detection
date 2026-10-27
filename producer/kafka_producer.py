"""Publish generated access logs to Kafka."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import TYPE_CHECKING, Any, Iterable, TextIO

if TYPE_CHECKING:
    from confluent_kafka import Producer as KafkaProducer
else:
    KafkaProducer = Any

try:
    from .log_generator import LogGenerator
except ImportError:
    from log_generator import LogGenerator


def build_producer(bootstrap_servers: str) -> KafkaProducer:
    security_protocol = os.getenv("KAFKA_SECURITY_PROTOCOL")
    sasl_mechanism = os.getenv("KAFKA_SASL_MECHANISM", "PLAIN")
    sasl_username = os.getenv("KAFKA_SASL_USERNAME")
    sasl_password = os.getenv("KAFKA_SASL_PASSWORD")
    ssl_ca_file = os.getenv("KAFKA_SSL_CA_FILE")
    try:
        from confluent_kafka import Producer

        config = {
            "bootstrap.servers": bootstrap_servers,
            "acks": "all",
            "message.timeout.ms": 30000,
            "queue.buffering.max.messages": 1000000,
            "queue.buffering.max.kbytes": 1048576,
            "message.send.max.retries": 5,
            "retry.backoff.ms": 200,
        }
        if security_protocol:
            config.update({
                "security.protocol": security_protocol,
                "sasl.mechanisms": sasl_mechanism,
                "sasl.username": sasl_username,
                "sasl.password": sasl_password,
            })
            if ssl_ca_file:
                config["ssl.ca.location"] = ssl_ca_file
        return Producer(config)
    except ImportError:
        from kafka import KafkaProducer

        config = {
            "bootstrap_servers": bootstrap_servers.split(",") if "," in bootstrap_servers else [bootstrap_servers],
            "acks": "all",
            "api_version": (0, 10, 2),
        }
        if security_protocol:
            config.update({
                "security_protocol": security_protocol,
                "sasl_mechanism": sasl_mechanism,
                "sasl_plain_username": sasl_username,
                "sasl_plain_password": sasl_password,
            })
            if ssl_ca_file:
                config["ssl_cafile"] = ssl_ca_file
        return KafkaProducer(**config)


def _send_message(producer: KafkaProducer, topic: str, payload: bytes) -> None:
    if hasattr(producer, "produce"):
        while True:
            try:
                producer.produce(topic, value=payload)
                try:
                    producer.poll(0)
                except TypeError:
                    pass
                return
            except BufferError:
                try:
                    producer.poll(0.1)
                except TypeError:
                    pass
    else:
        producer.send(topic, value=payload)


def publish_records(
    producer: KafkaProducer,
    topic: str,
    records: Iterable[dict[str, object]],
) -> int:
    published = 0
    for record in records:
        payload = json.dumps(record, separators=(",", ":")).encode("utf-8")
        _send_message(producer, topic, payload)
        published += 1
    producer.flush()
    return published


def publish_lines(producer: KafkaProducer, topic: str, lines: Iterable[str]) -> int:
    published = 0
    for line in lines:
        payload = line.encode("utf-8")
        _send_message(producer, topic, payload)
        published += 1
    producer.flush()
    return published


def publish_generator(
    producer: KafkaProducer,
    topic: str,
    generator: LogGenerator,
    count: int | None,
) -> int:
    if generator.output_format == "apache":
        return publish_lines(producer, topic, (generator.render(record) for record in generator.records(count)))
    return publish_records(producer, topic, generator.records(count))


def publish_stdin(producer: KafkaProducer, topic: str, input_stream: TextIO) -> int:
    def records() -> Iterable[dict[str, object]]:
        for line_number, line in enumerate(input_stream, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON on line {line_number}: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"line {line_number} must contain a JSON object")
            yield record

    return publish_records(producer, topic, records())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rate", type=float, default=10.0)
    parser.add_argument("--anomaly-rate", type=float, default=0.01)
    parser.add_argument("--scenario", choices=("brute-force", "error-burst", "ddos", "latency"))
    parser.add_argument("--format", dest="output_format", choices=("json", "apache"), default="json")
    parser.add_argument("--count", type=int, help="stop after this many records; omit for continuous publishing")
    parser.add_argument("--stdin", action="store_true", help="publish JSON records from stdin instead of generating them")
    parser.add_argument("--bootstrap-servers", default=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9094"))
    parser.add_argument("--topic", default=os.getenv("KAFKA_TOPIC_SERVER_LOGS", "server-logs"))
    parser.add_argument("--seed", type=int)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    producer = build_producer(args.bootstrap_servers)
    try:
        if args.stdin:
            published = publish_stdin(producer, args.topic, sys.stdin)
        else:
            generator = LogGenerator(
                rate=args.rate,
                anomaly_rate=args.anomaly_rate,
                scenario=args.scenario,
                output_format=args.output_format,
                seed=args.seed,
            )
            published = publish_generator(producer, args.topic, generator, args.count)
    finally:
        producer.flush()
    print(f"Published {published} records to {args.topic}", file=sys.stderr)


if __name__ == "__main__":
    main()
