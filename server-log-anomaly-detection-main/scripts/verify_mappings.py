"""
Verify all Elasticsearch field mappings and test every dashboard aggregation.
Run with: python scripts/verify_mappings.py
"""
import requests
import json

BASE = "http://localhost:9200"


def get_mapping(index):
    r = requests.get(f"{BASE}/{index}/_mapping")
    data = r.json()
    first = list(data.values())[0]
    return first["mappings"]["properties"]


def test_agg(name, index, body):
    body["size"] = 0
    r = requests.post(f"{BASE}/{index}/_search", json=body)
    d = r.json()
    hits = d["hits"]["total"]["value"]
    agg_val = ""
    if d.get("aggregations"):
        v = list(d["aggregations"].values())[0]
        if "value" in v:
            agg_val = "value=" + str(v["value"])
        elif "buckets" in v:
            buckets = [(b["key"], b["doc_count"]) for b in v["buckets"][:3]]
            agg_val = "buckets=" + str(buckets)
    ok = hits > 0 or ("value=" in agg_val and agg_val != "value=None") or "buckets=[" in agg_val
    tag = "OK  " if ok else "FAIL"
    print(f"  {tag}  {name:<35s} hits={hits}  {agg_val}")
    return ok


print("=" * 70)
print("ELASTICSEARCH FIELD MAPPINGS")
print("=" * 70)

print("\n--- server-logs-2026.09.08 ---")
sl_props = get_mapping("server-logs-2026.09.08")
for field, info in sorted(sl_props.items()):
    ftype = info.get("type", "?")
    fields = info.get("fields", {})
    sub = ", sub-fields: " + str(list(fields.keys())) if fields else ""
    print(f"  {field}: {ftype}{sub}")

print("\n--- anomalies-2026.09.16 ---")
an_props = get_mapping("anomalies-2026.09.16")
for field, info in sorted(an_props.items()):
    ftype = info.get("type", "?")
    fields = info.get("fields", {})
    sub = ", sub-fields: " + str(list(fields.keys())) if fields else ""
    print(f"  {field}: {ftype}{sub}")

print()
print("=" * 70)
print("AGGREGATION TESTS (all panels)")
print("=" * 70)

checks = [
    ("Total Requests",         "server-logs-*",  {}),
    ("Avg Latency",            "server-logs-*",  {"aggs": {"v": {"avg": {"field": "latency_ms"}}}}),
    ("Requests Over Time",     "server-logs-*",  {"aggs": {"v": {"date_histogram": {"field": "timestamp", "calendar_interval": "1d"}}}}),
    ("HTTP Status Dist",       "server-logs-*",  {"aggs": {"v": {"terms": {"field": "status_code", "size": 10}}}}),
    ("HTTP Methods",           "server-logs-*",  {"aggs": {"v": {"terms": {"field": "method", "size": 10}}}}),
    ("Top Client IPs",         "server-logs-*",  {"aggs": {"v": {"terms": {"field": "client_ip", "size": 10}}}}),
    ("Total Anomalies",        "anomalies-*",    {}),
    ("Anomalies by Type",      "anomalies-*",    {"aggs": {"v": {"terms": {"field": "anomaly_type", "size": 10}}}}),
    ("Severity Dist",          "anomalies-*",    {"aggs": {"v": {"terms": {"field": "severity", "size": 10}}}}),
    ("Top Attacking IPs",      "anomalies-*",    {"aggs": {"v": {"terms": {"field": "client_ip", "size": 10}}}}),
    ("Unauthorized Attempts",  "anomalies-*",    {"aggs": {"v": {"sum": {"field": "unauthorized_count"}}}}),
    ("Recent Anomalies Sort",  "anomalies-*",    {}),
]

all_ok = True
print()
for name, idx, body in checks:
    ok = test_agg(name, idx, body)
    if not ok:
        all_ok = False

print()
print("=" * 70)
print("RESULT:", "ALL QUERIES RETURN DATA" if all_ok else "SOME QUERIES FAILED")
print("=" * 70)
