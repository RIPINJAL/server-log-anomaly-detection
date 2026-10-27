import json
from pathlib import Path

obj = {
    "id": "fixed-recent-anomalies-search",
    "type": "search",
    "attributes": {
        "title": "Recent Anomalies Table",
        "description": "",
        "hits": 0,
        "columns": [
            "window_start",
            "window_end",
            "anomaly_type",
            "severity",
            "client_ip",
            "unauthorized_count",
            "message"
        ],
        "sort": [
            ["window_start", "desc"]
        ],
        "version": 1,
        "kibanaSavedObjectMeta": {
            "searchSourceJSON": json.dumps({
                "query": {
                    "query": "",
                    "language": "kuery"
                },
                "filter": [],
                "indexRefName": "kibanaSavedObjectMeta.searchSourceJSON.index"
            },
            separators=(",", ":"))
        }
    },
    "references": [
        {
            "name": "kibanaSavedObjectMeta.searchSourceJSON.index",
            "type": "index-pattern",
            "id": "anomalies-view"
        }
    ]
}

Path("kibana/fixed_recent_anomalies.ndjson").write_text(
    json.dumps(obj, separators=(",", ":")) + "\n",
    encoding="utf-8"
)

print("Created valid fixed_recent_anomalies.ndjson")
