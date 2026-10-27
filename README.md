# Server Log Anomaly Detection

A portfolio-grade real-time streaming analytics pipeline for synthetic web access logs. The pipeline generates JSON logs, publishes them to Apache Kafka, detects windowed anomalies with PySpark Structured Streaming, persists raw events and findings in Elasticsearch, and visualizes them in Kibana.

## Architecture

```text
Python log generator
        |
        v
Kafka: server-logs ---> PySpark Structured Streaming ---> Kafka: anomalies
                              |                         \
                              v                          v
                     Elasticsearch: server-logs-*   Elasticsearch: anomalies-*
                              |
                              v
                         Kibana dashboards
```

## Prerequisites

- Docker Desktop with at least 6 GB memory assigned
- Python 3.11 for local scripts and tests
- GNU Make, or equivalent commands from the Makefile
- `curl` for Elasticsearch checks
- Python dependencies installed with `python -m pip install -r requirements.txt`
- Optional GPU mode: NVIDIA GPU, current NVIDIA driver, Docker Desktop GPU support, and a working `docker run --rm --gpus all nvidia/cuda:12.2.2-base-ubuntu22.04 nvidia-smi`

The Compose stack uses Kafka 3.8.1 in KRaft mode, Elasticsearch 8.15.3, and Kibana 8.15.3. Elasticsearch security is disabled only for local development.

## Quick Start

From this directory:

```powershell
Copy-Item .env.example .env
docker compose up -d
docker compose ps
```

Wait until Kafka, Elasticsearch, and Kibana show healthy status. Then create the topics and mappings:

```powershell
make topics
make apply-index-templates
```

On Windows without a POSIX shell, use these equivalent commands:

```powershell
docker compose exec -T kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:9092 --create --if-not-exists --topic server-logs --partitions 3 --replication-factor 1
docker compose exec -T kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:9092 --create --if-not-exists --topic anomalies --partitions 3 --replication-factor 1
$serverTemplate = Get-Content elastic_config/index_templates/server-logs-template.json -Raw
$anomalyTemplate = Get-Content elastic_config/index_templates/anomalies-template.json -Raw
Invoke-RestMethod -Method Put -Uri http://localhost:9200/_index_template/server-logs-template -ContentType 'application/json' -Body $serverTemplate
Invoke-RestMethod -Method Put -Uri http://localhost:9200/_index_template/anomalies-template -ContentType 'application/json' -Body $anomalyTemplate
```

Generate a visible brute-force test stream in one terminal:

```powershell
python producer/kafka_producer.py --scenario brute-force --rate 100 --count 140
```

Run the containerized streaming detector in another terminal:

```powershell
make run-spark-job
```

The Spark container uses Python 3.11 and Java 17, downloads the Spark 3.5.3 Kafka connector through `--packages`, and connects to Kafka/Elasticsearch using container hostnames. It prints each flagged anomaly as JSON while writing raw events and findings to Elasticsearch.

### GPU Spark mode

GPU acceleration uses the NVIDIA RAPIDS Accelerator for Apache Spark. The RAPIDS plugin is included in the Spark submit dependencies, but it is enabled only when requested so the normal local setup does not require a GPU. After verifying `nvidia-smi` through Docker, run:

```powershell
make run-spark-gpu
```

This applies the GPU Compose override and sets `NVIDIA_VISIBLE_DEVICES=all` plus `SPARK_GPU_ENABLED=true`. The detector logs `Spark RAPIDS GPU acceleration enabled` at startup. Set `SPARK_GPU_AMOUNT` and `SPARK_GPU_TASK_AMOUNT` in `.env` when allocating a different GPU fraction. Without NVIDIA Container Toolkit support, use `make run-spark-job`; that is the supported CPU fallback.

Run Make commands from the repository directory (`server-log-anomaly-detection`), because that is where the Makefile and Compose files live.

Check Elasticsearch:

```powershell
curl http://localhost:9200/_cluster/health
curl http://localhost:9200/server-logs-*/_search
curl http://localhost:9200/anomalies-*/_search
```

Open Kibana at http://localhost:5601.

Stop the stack with `make down`; persistent volumes remain unless removed explicitly with `docker compose down -v`.

## Generator Scenarios

```powershell
python producer/log_generator.py --scenario latency --count 10
python producer/log_generator.py --scenario error-burst --count 40
python producer/log_generator.py --scenario brute-force --count 140
python producer/log_generator.py --scenario ddos --count 200
```

Generate Apache Combined Log Format lines instead of JSON:

```powershell
python producer/log_generator.py --format apache --count 10
```

JSON remains the default format used by the Kafka and Spark pipeline. Apache-format output is intended for web-server log demonstrations or file-based ingestion.

### Import Python application logs

The importer supports timestamped Python logs in this format:

```text
2026-08-01 12:00:00.123 | INFO | app.worker:run:42 - Application started
```

From PowerShell, import a matching log file directly into Elasticsearch and review
the warning and three-sigma traffic findings in the dashboard:

```powershell
python scripts/import_app_logs.py C:\path\to\app.log.txt
```

Application records are stored in `app-logs-*`, and findings are stored in
`anomalies-*`. The importer redacts email addresses before indexing and uses
stable document IDs, so importing the same file again updates rather than
duplicates its records. The dashboard shows application-log and warning counts
alongside findings from both application logs and the streaming detector.

Send continuous Apache access-log lines directly to Kafka:

```powershell
python producer/kafka_producer.py --format apache --rate 10
```

Omit `--count` for continuous generation. Press `Ctrl+C` to stop the producer. Spark accepts both JSON records and Apache Combined Log Format lines; Apache lines use `0` for latency because standard Combined Format does not include response time.

Useful options are `--rate`, `--anomaly-rate`, `--count`, and `--seed`. Without `--scenario`, anomaly bursts are selected probabilistically using `--anomaly-rate`.

## Kafka Verification

The host producer uses `localhost:9094`; containers use `kafka:9092`. Consume from inside the Kafka container:

```powershell
docker compose exec kafka /opt/kafka/bin/kafka-console-consumer.sh `
  --bootstrap-server kafka:9092 `
  --topic server-logs `
  --from-beginning
```

Consume detected anomalies similarly:

```powershell
docker compose exec kafka /opt/kafka/bin/kafka-console-consumer.sh `
  --bootstrap-server kafka:9092 `
  --topic anomalies `
  --from-beginning
```

## Tests

```powershell
python -m pytest -q
```

The tests cover strict rule thresholds, valid log shape, deterministic scenario injection, the brute-force detector threshold, and JSON-lines output.

## Kibana Dashboard

The file `kibana/dashboard_export.ndjson` is a placeholder because Kibana saved-object exports contain generated IDs and version-specific metadata. Build the dashboard manually, then export it from **Stack Management > Saved Objects > Export** and replace the placeholder with the resulting NDJSON.

1. Create a data view named `server-logs-*` with `timestamp` as the time field.
2. Create a second data view named `anomalies-*` with `window_start` as the time field.
3. Add a Lens area or line chart for request volume using `Count of records` over `timestamp`.
4. Add a bar or donut chart for `status_code` using `server-logs-*`.
5. Add percentile latency visualizations using the numeric `latency_ms` field, such as 50th, 95th, and 99th percentiles.
6. Add a data table from `anomalies-*` showing `window_start`, `anomaly_type`, `severity`, `client_ip`, `latency_ms`, `request_count`, and `message`.
7. Apply severity colors: critical red, high orange, medium yellow, and low blue.
8. Set the dashboard time picker to the last 15 minutes and refresh every 5 seconds for a live view.

## Known Gotchas

- **Spark cannot reach Kafka:** `localhost:9094` is for processes running on the host. A Spark process inside Docker must use `kafka:9092`. Set `KAFKA_BOOTSTRAP_SERVERS` for the execution context.
- **Schema mismatches become nulls:** Spark's `from_json` returns null fields instead of raising a useful exception for many mismatches. The detector filters records with null timestamps, IPs, status codes, or latency; inspect the producer JSON and `LOG_SCHEMA` together when records disappear.
- **Windows never close:** event-time windows require a watermark and advancing event timestamps. The detector uses a two-minute watermark; stale timestamps can remain pending, while an overly aggressive watermark can discard late events.
- **Latency mapped as text:** Elasticsearch must receive explicit numeric mappings. The templates map `latency_ms`, mean latency, standard deviation, and rates as `float`, and counts/status codes as integer types so Kibana aggregations work.
- **Kibana starts after Elasticsearch:** Compose waits for Elasticsearch health before starting Kibana, but first startup can still take a minute while Elasticsearch initializes.
- **Kafka topic creation:** automatic topic creation is disabled. Run `make topics` before starting the producer or Spark job.
- **Java version:** the supplied Spark image uses Java 17. A host-run Spark 3.5 process requires a supported Java runtime; Java 25 can fail during Hadoop initialization with `Subject.getSubject is not supported`.

## Project Layout

```text
producer/       generator and Kafka producer
spark_jobs/     Structured Streaming detector, rules, and sinks
elastic_config/  explicit index templates
kibana/         dashboard export placeholder
scripts/        readiness, topic, and template helpers
tests/          unit tests
```

### Kibana Dashboard Setup

1. Open Kibana at http://localhost:5601
2. The project uses two data views:
   - server-logs-*
   - nomalies-*
3. A pre-configured dashboard named **Real-Time Server Log Anomaly Detection** is provided.
4. To import the dashboard:
   - Navigate to **Stack Management** > **Saved Objects** in Kibana.
   - Click **Import** in the top right.
   - Select the file kibana/dashboard_export.ndjson.
   - Ensure the import resolves without errors (the exported NDJSON contains the required data views and visualizations).
   - Once imported, go to **Dashboard** and open **Real-Time Server Log Anomaly Detection**.
