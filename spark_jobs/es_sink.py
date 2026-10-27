"""Elasticsearch and Kafka sinks for streaming log batches."""

from __future__ import annotations

import os
from collections.abc import Iterable
from datetime import datetime
from typing import Any


def index_name(prefix: str, timestamp: str | datetime | None = None) -> str:
    if timestamp is None:
        date = datetime.utcnow().date()
    elif isinstance(timestamp, datetime):
        date = timestamp.date()
    else:
        date = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).date()
    return f"{prefix}-{date:%Y.%m.%d}"


def create_es_client() -> Any:
    from elasticsearch import Elasticsearch

    url = os.getenv("ELASTICSEARCH_URL")
    if not url:
        host = os.getenv("ELASTICSEARCH_HOST", "localhost")
        port = os.getenv("ELASTICSEARCH_PORT", "9200")
        url = f"http://{host}:{port}"
    config: dict[str, Any] = {
        "request_timeout": 120,
        "max_retries": 5,
        "retry_on_timeout": True,
        "verify_certs": os.getenv("ELASTICSEARCH_VERIFY_CERTS", "true").lower() == "true",
    }
    api_key = os.getenv("ELASTICSEARCH_API_KEY")
    if api_key:
        config["api_key"] = api_key
    elif os.getenv("ELASTICSEARCH_USERNAME") and os.getenv("ELASTICSEARCH_PASSWORD"):
        config["basic_auth"] = (
            os.environ["ELASTICSEARCH_USERNAME"],
            os.environ["ELASTICSEARCH_PASSWORD"],
        )
    return Elasticsearch(
        url,
        **config,
    )


def bulk_index_documents(client: Any, documents: Iterable[dict[str, Any]], prefix: str) -> int:
    from elasticsearch.helpers import bulk

    actions = (
        {"_index": index_name(prefix, document.get("timestamp")), "_source": document}
        for document in documents
    )
    success, _ = bulk(
        client,
        actions,
        raise_on_error=True,
        request_timeout=120,
        max_retries=5,
    )
    return int(success)


def create_anomaly_producer(bootstrap_servers: str, topic: str) -> Any:
    from kafka import KafkaProducer

    config: dict[str, Any] = {
        "bootstrap_servers": bootstrap_servers.split(",") if "," in bootstrap_servers else [bootstrap_servers],
        "acks": "all",
        "api_version": (0, 10, 2),
        "value_serializer": lambda value: value if isinstance(value, bytes) else __import__("json").dumps(value).encode("utf-8"),
    }
    security_protocol = os.getenv("KAFKA_SECURITY_PROTOCOL")
    if security_protocol:
        config.update({
            "security_protocol": security_protocol,
            "sasl_mechanism": os.getenv("KAFKA_SASL_MECHANISM", "PLAIN"),
            "sasl_plain_username": os.getenv("KAFKA_SASL_USERNAME"),
            "sasl_plain_password": os.getenv("KAFKA_SASL_PASSWORD"),
        })
        if os.getenv("KAFKA_SSL_CA_FILE"):
            config["ssl_cafile"] = os.environ["KAFKA_SSL_CA_FILE"]
    return KafkaProducer(**config)


def publish_anomalies(producer: Any, topic: str, findings: Iterable[dict[str, Any]]) -> int:
    published = 0
    for finding in findings:
        payload = __import__("json").dumps(finding, separators=(",", ":")).encode("utf-8")
        producer.send(topic, value=payload)
        published += 1
    producer.flush()
    return published
