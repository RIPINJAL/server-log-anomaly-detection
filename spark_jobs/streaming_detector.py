"""Consume server logs from Kafka and print windowed anomaly findings."""

from __future__ import annotations

import json
import os
from collections import deque
from datetime import datetime
from typing import Any

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import (
    avg,
    col,
    coalesce,
    count,
    from_json,
    lit,
    regexp_extract,
    sum as spark_sum,
    to_timestamp,
    window,
)
from pyspark.sql.types import DoubleType, IntegerType, StringType, StructField, StructType, TimestampType

try:
    from .detection_rules import (
        classify_latency,
        error_rate_rule,
        traffic_surge_rule,
        unauthorized_threshold_rule,
    )
    from .es_sink import bulk_index_documents, create_anomaly_producer, create_es_client, publish_anomalies
except ImportError:
    from detection_rules import classify_latency, error_rate_rule, traffic_surge_rule, unauthorized_threshold_rule
    from es_sink import bulk_index_documents, create_anomaly_producer, create_es_client, publish_anomalies


LOG_SCHEMA = StructType(
    [
        StructField("timestamp", TimestampType(), nullable=False),
        StructField("client_ip", StringType(), nullable=False),
        StructField("method", StringType(), nullable=False),
        StructField("url", StringType(), nullable=False),
        StructField("status_code", IntegerType(), nullable=False),
        StructField("latency_ms", DoubleType(), nullable=False),
        StructField("user_id", StringType(), nullable=True),
    ]
)


def parse_kafka_logs(raw_stream: DataFrame) -> DataFrame:
    raw = raw_stream.select(col("value").cast("string").alias("raw"))
    json_log = from_json(col("raw"), LOG_SCHEMA)
    apache_timestamp = to_timestamp(
        regexp_extract(col("raw"), r"^\S+ \S+ \S+ \[([^\]]+)\]", 1),
        "dd/MMM/yyyy:HH:mm:ss Z",
    )
    parsed = raw.select(
        coalesce(json_log["timestamp"], apache_timestamp).alias("timestamp"),
        coalesce(json_log["client_ip"], regexp_extract(col("raw"), r"^(\S+)", 1)).alias("client_ip"),
        coalesce(json_log["method"], regexp_extract(col("raw"), r'\"(\S+) [^\"]+ HTTP/[^\"]+\"', 1)).alias("method"),
        coalesce(json_log["url"], regexp_extract(col("raw"), r'\"\S+ ([^\"]+) HTTP/[^\"]+\"', 1)).alias("url"),
        coalesce(json_log["status_code"], regexp_extract(col("raw"), r'HTTP/[^\"]+\" (\d{3}) ', 1).cast("int")).alias("status_code"),
        coalesce(json_log["latency_ms"], lit(0.0)).alias("latency_ms"),
        coalesce(json_log["user_id"], regexp_extract(col("raw"), r"^\S+ \S+ (\S+)", 1)).alias("user_id"),
    )
    return parsed.filter(
        col("timestamp").isNotNull()
        & col("client_ip").isNotNull()
        & col("status_code").isNotNull()
        & col("latency_ms").isNotNull()
    ).withWatermark("timestamp", "2 minutes")


def _window_key(row: Any) -> tuple[datetime, datetime]:
    return row.window.start, row.window.end


def detect_batch(batch_df: DataFrame, batch_id: int, baseline_history: deque[tuple[datetime, int]]) -> list[dict[str, Any]]:
    """Aggregate one micro-batch and return classified findings for console output."""
    if batch_df.rdd.isEmpty():
        return []

    windowed = window(col("timestamp"), "1 minute", "10 seconds")
    traffic_rows = (
        batch_df.groupBy(windowed.alias("window"))
        .agg(
            count(lit(1)).alias("request_count"),
            spark_sum((col("status_code") == 500).cast("int")).alias("error_count"),
        )
        .collect()
    )
    unauthorized_rows = (
        batch_df.filter(col("status_code").isin(401, 403))
        .groupBy(windowed.alias("window"), "client_ip")
        .agg(count(lit(1)).alias("unauthorized_count"))
        .collect()
    )
    latency_rows = (
        batch_df.groupBy(windowed.alias("window"))
        .agg(avg("latency_ms").alias("mean_latency_ms"),
             (spark_sum(col("latency_ms") * col("latency_ms")) / count(lit(1))).alias("mean_square_latency"),
             count(lit(1)).alias("latency_count"))
        .collect()
    )
    latency_records = { _window_key(row): row for row in latency_rows }
    findings: list[dict[str, Any]] = []

    for row in traffic_rows:
        key = _window_key(row)
        request_count = int(row.request_count)
        error_count = int(row.error_count or 0)
        trailing_counts = [count_value for start, count_value in baseline_history if start < key[0] and (key[0] - start).total_seconds() <= 300]
        baseline = sum(trailing_counts) / len(trailing_counts) if trailing_counts else 0.0
        for rule_result in (error_rate_rule(error_count, request_count), traffic_surge_rule(request_count, baseline)):
            if rule_result:
                findings.append({
                    **rule_result,
                    "window_start": key[0].isoformat(),
                    "window_end": key[1].isoformat(),
                    "request_count": request_count,
                    "error_count": error_count,
                    "error_rate": error_count / request_count if request_count else 0.0,
                })
        baseline_history.append((key[0], request_count))

    for row in unauthorized_rows:
        result = unauthorized_threshold_rule(int(row.unauthorized_count))
        if result:
            key = _window_key(row)
            findings.append({**result, "window_start": key[0].isoformat(), "window_end": key[1].isoformat(), "client_ip": row.client_ip, "unauthorized_count": int(row.unauthorized_count)})

    for row in batch_df.select("timestamp", "client_ip", "latency_ms").collect():
        matching = next((stats for key, stats in latency_records.items() if key[0] <= row.timestamp < key[1]), None)
        if matching:
            mean = float(matching.mean_latency_ms)
            variance = max(0.0, float(matching.mean_square_latency) - mean * mean)
            result = classify_latency({"latency_ms": row.latency_ms, "mean_latency_ms": mean, "stddev_latency_ms": variance**0.5})
            if result:
                findings.append({**result, "timestamp": row.timestamp.isoformat(), "client_ip": row.client_ip, "latency_ms": float(row.latency_ms), "mean_latency_ms": mean, "stddev_latency_ms": variance**0.5})
    return findings


def main() -> None:
    builder = SparkSession.builder.appName(os.getenv("SPARK_APP_NAME", "server-log-anomaly-detector"))
    if os.getenv("SPARK_GPU_ENABLED", "false").lower() == "true":
        builder = (
            builder.config("spark.plugins", "com.nvidia.spark.SQLPlugin")
            .config("spark.rapids.sql.enabled", "true")
            .config("spark.driver.resource.gpu.amount", os.getenv("SPARK_GPU_AMOUNT", "1"))
            .config("spark.task.resource.gpu.amount", os.getenv("SPARK_GPU_TASK_AMOUNT", "0.25"))
            .config("spark.rapids.sql.concurrentGpuTasks", "2")
        )
        print("Spark RAPIDS GPU acceleration enabled", flush=True)
    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel(os.getenv("SPARK_LOG_LEVEL", "WARN"))
    kafka_options = {
        "kafka.bootstrap.servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
        "subscribe": os.getenv("KAFKA_TOPIC_SERVER_LOGS", "server-logs"),
        "startingOffsets": os.getenv("KAFKA_STARTING_OFFSETS", "latest"),
        "failOnDataLoss": "false",
    }
    security_protocol = os.getenv("KAFKA_SECURITY_PROTOCOL")
    if security_protocol:
        kafka_options.update({
            "kafka.security.protocol": security_protocol,
            "kafka.sasl.mechanism": os.getenv("KAFKA_SASL_MECHANISM", "PLAIN"),
            "kafka.sasl.jaas.config": (
                "org.apache.kafka.common.security.plain.PlainLoginModule required "
                f'username="{os.environ["KAFKA_SASL_USERNAME"]}" '
                f'password="{os.environ["KAFKA_SASL_PASSWORD"]}";'
            ),
        })
        if os.getenv("KAFKA_SSL_CA_FILE"):
            kafka_options["kafka.ssl.truststore.location"] = os.environ["KAFKA_SSL_CA_FILE"]
    raw_stream = spark.readStream.format("kafka").options(**kafka_options).load()
    logs = parse_kafka_logs(raw_stream)
    baseline_history: deque[tuple[datetime, int]] = deque(maxlen=60)
    elasticsearch_enabled = os.getenv("SPARK_ELASTICSEARCH_ENABLED", "true").lower() == "true"
    es_client = create_es_client() if elasticsearch_enabled else None
    anomaly_topic = os.getenv("KAFKA_TOPIC_ANOMALIES", "anomalies")
    anomaly_producer = create_anomaly_producer(
        os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
        anomaly_topic,
    )

    def print_findings(batch_df: DataFrame, batch_id: int) -> None:
        raw_documents = [row.asDict(recursive=True) for row in batch_df.collect()]
        if not raw_documents:
            return
        if es_client is not None:
            bulk_index_documents(es_client, raw_documents, "server-logs")
        findings = detect_batch(batch_df, batch_id, baseline_history)
        if es_client is not None and findings:
            bulk_index_documents(es_client, findings, "anomalies")
        publish_anomalies(anomaly_producer, anomaly_topic, findings)
        for finding in findings:
            print(json.dumps(finding, default=str), flush=True)

    checkpoint = os.getenv("SPARK_CHECKPOINT_LOCATION", "/tmp/server-log-anomaly-checkpoint")
    query = logs.writeStream.foreachBatch(print_findings).option("checkpointLocation", checkpoint).start()
    try:
        query.awaitTermination()
    finally:
        anomaly_producer.flush()
        if es_client is not None:
            es_client.close()


if __name__ == "__main__":
    main()
