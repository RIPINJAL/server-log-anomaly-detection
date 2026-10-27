import json
from io import StringIO

from elasticsearch import helpers as es_helpers

from spark_jobs import es_sink
from producer.kafka_producer import publish_lines
from producer.log_generator import LogGenerator


REQUIRED_FIELDS = {
    "timestamp",
    "client_ip",
    "method",
    "url",
    "status_code",
    "latency_ms",
    "user_id",
}


def test_normal_records_have_required_json_fields():
    records = list(LogGenerator(anomaly_rate=0, seed=4).records(20))
    assert all(REQUIRED_FIELDS <= record.keys() for record in records)
    assert all(isinstance(record["status_code"], int) for record in records)
    assert all(isinstance(record["latency_ms"], float) for record in records)


def test_forced_latency_scenario_injects_large_latency():
    records = list(LogGenerator(scenario="latency", seed=4).records(1))
    assert records[0]["latency_ms"] > 5000


def test_forced_brute_force_scenario_exceeds_detector_threshold_from_one_ip():
    records = list(LogGenerator(scenario="brute-force", seed=11).records(110))
    failures = [record for record in records if record["url"] == "/login" and record["status_code"] == 401]
    assert len(failures) == 110
    assert len({record["client_ip"] for record in failures}) == 1


def test_forced_error_burst_and_ddos_shapes():
    errors = list(LogGenerator(scenario="error-burst", seed=2).records(20))
    assert all(record["status_code"] == 500 for record in errors)
    assert len({record["client_ip"] for record in errors}) == 1

    ddos = list(LogGenerator(scenario="ddos", seed=2).records(100))
    assert len({record["client_ip"] for record in ddos}) <= 5


def test_run_writes_one_valid_json_object_per_line():
    output = StringIO()
    LogGenerator(anomaly_rate=0, seed=3).run(output, count=3)
    lines = output.getvalue().splitlines()
    assert len(lines) == 3
    assert all(REQUIRED_FIELDS <= json.loads(line).keys() for line in lines)


def test_run_writes_apache_combined_log_lines():
    output = StringIO()
    LogGenerator(anomaly_rate=0, output_format="apache", seed=3).run(output, count=1)
    line = output.getvalue().strip()
    assert ' "GET ' in line or ' "POST ' in line or ' "PUT ' in line or ' "DELETE ' in line
    assert " HTTP/1.1\" " in line
    assert line.endswith('"server-log-generator/1.0"')


def test_publish_lines_polls_async_kafka_producer():
    class FakeProducer:
        def __init__(self):
            self.sent = []
            self.polled = []

        def produce(self, topic, value):
            self.sent.append((topic, value))

        def poll(self, timeout):
            self.polled.append(timeout)

        def flush(self):
            pass

    producer = FakeProducer()
    published = publish_lines(producer, "server-logs", ["a", "b"])

    assert published == 2
    assert len(producer.sent) == 2
    assert producer.polled == [0, 0]


def test_publish_lines_retries_when_queue_is_full():
    class FakeProducer:
        def __init__(self):
            self.sent = []
            self.poll_times = []
            self.produce_calls = 0

        def produce(self, topic, value):
            self.produce_calls += 1
            if self.produce_calls == 1:
                raise BufferError("Local: Queue full")
            self.sent.append((topic, value))

        def poll(self, timeout):
            self.poll_times.append(timeout)

        def flush(self):
            pass

    producer = FakeProducer()
    published = publish_lines(producer, "server-logs", ["a"])

    assert published == 1
    assert producer.sent == [("server-logs", b"a")]
    assert producer.poll_times == [0.1, 0]


def test_bulk_index_documents_uses_retry_and_timeout_settings(monkeypatch):
    received = {}

    def fake_bulk(client, actions, **kwargs):
        received["kwargs"] = kwargs
        return 2, []

    monkeypatch.setattr(es_helpers, "bulk", fake_bulk)

    assert es_sink.bulk_index_documents({"client": True}, [{"timestamp": "2024-01-01T00:00:00Z", "message": "ok"}], "anomalies") == 2
    assert received["kwargs"]["request_timeout"] == 120
    assert received["kwargs"]["max_retries"] == 5
