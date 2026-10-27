"""
Kibana Dashboard Generator — Lens Format for Kibana 8.15.3
===========================================================
ROOT CAUSE OF BROKEN PANELS:
  1. Legacy `visualization` type is unreliable in Kibana 8.15.3 for
     agg-based panels — Lens is the native, supported format.
  2. `useRecentSearches` field in searchSourceJSON is invalid in 8.x.
  3. `.keyword` suffix used on ip-type and already-keyword fields.
  4. Time range too narrow — data is Sept 2026, needs now-30d.

FIX:
  - Use `lens` saved-object type for ALL chart and metric panels.
  - Use fixed `search` saved-object (no useRecentSearches) for table.
  - Use EXACT field names from verified ES mappings (no .keyword).
  - Set dashboard timeFrom=now-30d.

Verified ES field types:
  server-logs-*:
    client_ip   → ip       (terms agg directly, NO .keyword)
    latency_ms  → float
    method      → keyword  (NO .keyword sub-field)
    status_code → integer
    timestamp   → date

  anomalies-*:
    anomaly_type       → keyword  (NO .keyword sub-field)
    client_ip          → ip       (NO .keyword)
    severity           → keyword  (NO .keyword)
    unauthorized_count → long
    window_start       → date
    window_end         → date
    message            → text     (display only, not aggregatable)
"""

import json
import sys
import uuid
import requests

KIBANA_URL = "http://localhost:5601"
KIBANA_HEADERS = {"kbn-xsrf": "true"}
NDJSON_PATH = "kibana/dashboard_export.ndjson"
DASH_ID = "real-time-server-log-anomaly-detection"

SL_DV = "server-logs-view"
AN_DV = "anomalies-view"

objects = []   # all saved objects
panels = []    # dashboard panelsJSON entries
dash_refs = [] # dashboard references array
panel_idx = [0]


def gid():
    return str(uuid.uuid4())


def _register(obj_id, obj_type, x, y, w, h):
    """Add a panel entry and a dashboard reference."""
    panel_idx[0] += 1
    i = str(panel_idx[0])
    panels.append({
        "gridData": {"x": x, "y": y, "w": w, "h": h, "i": i},
        "panelIndex": i,
        "embeddableConfig": {},
        "panelRefName": f"panel_{i}",
        "version": "8.15.3",
    })
    dash_refs.append({
        "name": f"panel_{i}",
        "type": obj_type,
        "id": obj_id,
    })


# ─── Data Views ───────────────────────────────────────────────────────────────

objects.append({
    "id": SL_DV,
    "type": "index-pattern",
    "attributes": {
        "title": "server-logs-*",
        "timeFieldName": "timestamp",
        "name": "Server Logs",
    },
})

objects.append({
    "id": AN_DV,
    "type": "index-pattern",
    "attributes": {
        "title": "anomalies-*",
        "timeFieldName": "window_start",
        "name": "Anomalies",
    },
})


# ─── Lens helpers ─────────────────────────────────────────────────────────────

def lens_count(title, dv_id, x, y, w, h):
    """Metric: Count of records."""
    oid, lid, cid = gid(), gid(), gid()
    objects.append({
        "id": oid, "type": "lens",
        "attributes": {
            "title": title, "description": "",
            "visualizationType": "lnsMetric",
            "state": {
                "datasourceStates": {"formBased": {"layers": {lid: {
                    "columns": {cid: {
                        "label": "Count of records",
                        "dataType": "number", "isBucketed": False,
                        "operationType": "count", "scale": "ratio",
                        "sourceField": "___records___",
                    }},
                    "columnOrder": [cid], "incompleteColumns": {},
                }}}},
                "filters": [],
                "query": {"language": "kuery", "query": ""},
                "visualization": {
                    "layerId": lid, "layerType": "data",
                    "metricAccessor": cid,
                },
            },
        },
        "references": [{"type": "index-pattern", "id": dv_id,
                         "name": f"indexpattern-datasource-layer-{lid}"}],
    })
    _register(oid, "lens", x, y, w, h)


def lens_agg_metric(title, dv_id, op, field, x, y, w, h):
    """Metric: numeric aggregation (avg, sum, etc.) on a field."""
    oid, lid, cid = gid(), gid(), gid()
    objects.append({
        "id": oid, "type": "lens",
        "attributes": {
            "title": title, "description": "",
            "visualizationType": "lnsMetric",
            "state": {
                "datasourceStates": {"formBased": {"layers": {lid: {
                    "columns": {cid: {
                        "label": f"{op}({field})",
                        "dataType": "number", "isBucketed": False,
                        "operationType": op, "scale": "ratio",
                        "sourceField": field,
                    }},
                    "columnOrder": [cid], "incompleteColumns": {},
                }}}},
                "filters": [],
                "query": {"language": "kuery", "query": ""},
                "visualization": {
                    "layerId": lid, "layerType": "data",
                    "metricAccessor": cid,
                },
            },
        },
        "references": [{"type": "index-pattern", "id": dv_id,
                         "name": f"indexpattern-datasource-layer-{lid}"}],
    })
    _register(oid, "lens", x, y, w, h)


def lens_line(title, dv_id, time_field, x, y, w, h):
    """Line chart: count of records over time."""
    oid, lid, dc, cc = gid(), gid(), gid(), gid()
    objects.append({
        "id": oid, "type": "lens",
        "attributes": {
            "title": title, "description": "",
            "visualizationType": "lnsXY",
            "state": {
                "datasourceStates": {"formBased": {"layers": {lid: {
                    "columns": {
                        dc: {
                            "label": time_field, "dataType": "date",
                            "isBucketed": True, "operationType": "date_histogram",
                            "scale": "interval", "sourceField": time_field,
                            "params": {"interval": "auto", "includeEmptyRows": True},
                        },
                        cc: {
                            "label": "Count of records", "dataType": "number",
                            "isBucketed": False, "operationType": "count",
                            "scale": "ratio", "sourceField": "___records___",
                        },
                    },
                    "columnOrder": [dc, cc], "incompleteColumns": {},
                }}}},
                "filters": [],
                "query": {"language": "kuery", "query": ""},
                "visualization": {
                    "legend": {"isVisible": True, "position": "right"},
                    "valueLabels": "hide", "fittingFunction": "None",
                    "axisTitlesVisibilitySettings": {"x": True, "yLeft": True, "yRight": True},
                    "tickLabelsVisibilitySettings": {"x": True, "yLeft": True, "yRight": False},
                    "labelsOrientation": {"x": 0, "yLeft": 0, "yRight": 0},
                    "gridlinesVisibilitySettings": {"x": True, "yLeft": True, "yRight": True},
                    "preferredSeriesType": "line",
                    "layers": [{
                        "layerId": lid, "layerType": "data",
                        "accessors": [cc], "xAccessor": dc,
                        "seriesType": "line", "showGridlines": False,
                    }],
                },
            },
        },
        "references": [{"type": "index-pattern", "id": dv_id,
                         "name": f"indexpattern-datasource-layer-{lid}"}],
    })
    _register(oid, "lens", x, y, w, h)


def lens_donut(title, dv_id, field, size, x, y, w, h):
    """Donut chart: terms breakdown of a field."""
    oid, lid, sc, cc = gid(), gid(), gid(), gid()
    objects.append({
        "id": oid, "type": "lens",
        "attributes": {
            "title": title, "description": "",
            "visualizationType": "lnsPie",
            "state": {
                "datasourceStates": {"formBased": {"layers": {lid: {
                    "columns": {
                        sc: {
                            "label": field, "dataType": "string",
                            "isBucketed": True, "operationType": "terms",
                            "scale": "ordinal", "sourceField": field,
                            "params": {
                                "size": size,
                                "orderBy": {"type": "column", "columnId": cc},
                                "orderDirection": "desc",
                                "otherBucket": True, "missingBucket": False,
                            },
                        },
                        cc: {
                            "label": "Count of records", "dataType": "number",
                            "isBucketed": False, "operationType": "count",
                            "scale": "ratio", "sourceField": "___records___",
                        },
                    },
                    "columnOrder": [sc, cc], "incompleteColumns": {},
                }}}},
                "filters": [],
                "query": {"language": "kuery", "query": ""},
                "visualization": {
                    "shape": "donut",
                    "layers": [{
                        "layerId": lid, "layerType": "data",
                        "groups": [sc], "metric": cc,
                        "numberDisplay": "percent",
                        "categoryDisplay": "default",
                        "legendDisplay": "default",
                        "nestedLegend": False,
                    }],
                },
            },
        },
        "references": [{"type": "index-pattern", "id": dv_id,
                         "name": f"indexpattern-datasource-layer-{lid}"}],
    })
    _register(oid, "lens", x, y, w, h)


def lens_bar_h(title, dv_id, field, size, x, y, w, h):
    """Horizontal bar chart: top N by count for a terms field."""
    oid, lid, xc, yc = gid(), gid(), gid(), gid()
    objects.append({
        "id": oid, "type": "lens",
        "attributes": {
            "title": title, "description": "",
            "visualizationType": "lnsXY",
            "state": {
                "datasourceStates": {"formBased": {"layers": {lid: {
                    "columns": {
                        xc: {
                            "label": field, "dataType": "string",
                            "isBucketed": True, "operationType": "terms",
                            "scale": "ordinal", "sourceField": field,
                            "params": {
                                "size": size,
                                "orderBy": {"type": "column", "columnId": yc},
                                "orderDirection": "desc",
                                "otherBucket": True, "missingBucket": False,
                            },
                        },
                        yc: {
                            "label": "Count of records", "dataType": "number",
                            "isBucketed": False, "operationType": "count",
                            "scale": "ratio", "sourceField": "___records___",
                        },
                    },
                    "columnOrder": [xc, yc], "incompleteColumns": {},
                }}}},
                "filters": [],
                "query": {"language": "kuery", "query": ""},
                "visualization": {
                    "legend": {"isVisible": True, "position": "right"},
                    "valueLabels": "hide", "fittingFunction": "None",
                    "axisTitlesVisibilitySettings": {"x": True, "yLeft": True, "yRight": True},
                    "tickLabelsVisibilitySettings": {"x": True, "yLeft": True, "yRight": False},
                    "labelsOrientation": {"x": 0, "yLeft": 0, "yRight": 0},
                    "gridlinesVisibilitySettings": {"x": True, "yLeft": True, "yRight": True},
                    "preferredSeriesType": "bar_horizontal",
                    "layers": [{
                        "layerId": lid, "layerType": "data",
                        "accessors": [yc], "xAccessor": xc,
                        "seriesType": "bar_horizontal", "showGridlines": False,
                    }],
                },
            },
        },
        "references": [{"type": "index-pattern", "id": dv_id,
                         "name": f"indexpattern-datasource-layer-{lid}"}],
    })
    _register(oid, "lens", x, y, w, h)


def saved_search_fixed(title, dv_id, columns, sort_field, x, y, w, h):
    """
    Discover saved-search for raw document table.
    FIXES: removed 'useRecentSearches' which caused error in Kibana 8.15.3.
    """
    sid = gid()
    objects.append({
        "id": sid, "type": "search",
        "attributes": {
            "title": title,
            "description": "",
            "hits": 0,
            "columns": columns,
            "sort": [[sort_field, "desc"]],
            "version": 1,
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": json.dumps({
                    "query": {"query": "", "language": "kuery"},
                    "filter": [],
                    "indexRefName": "kibanaSavedObjectMeta.searchSourceJSON.index",
                    "highlightAll": True,
                    # NOTE: 'useRecentSearches' intentionally REMOVED — causes
                    # "Unknown key for a VALUE_BOOLEAN" error in Kibana 8.15.3
                })
            },
        },
        "references": [{
            "name": "kibanaSavedObjectMeta.searchSourceJSON.index",
            "type": "index-pattern",
            "id": dv_id,
        }],
    })
    _register(sid, "search", x, y, w, h)


# ─── Build all panels ─────────────────────────────────────────────────────────
#
# Layout (48 grid columns × rows):
#
#  y=0   h=8   [Total Requests 0-16][Avg Latency 16-32][Total Anomalies 32-48]
#  y=8   h=12  [Requests Over Time                                       0-48]
#  y=20  h=12  [HTTP Status Dist 0-24]          [HTTP Methods         24-48]
#  y=32  h=12  [Top Client IPs                                         0-48]
#  y=44  h=10  [Unauth Attempts 0-16][Severity 16-32][Anomalies by Type 32-48]
#  y=54  h=12  [Top Attacking IPs                                      0-48]
#  y=66  h=14  [Recent Anomalies Table                                  0-48]

# ROW 0 — top metrics
lens_count      ("Total Requests",           SL_DV,                    0,  0, 16, 8)
lens_agg_metric ("Average Latency (ms)",     SL_DV, "avg", "latency_ms",  16, 0, 16, 8)
lens_count      ("Total Anomalies",          AN_DV,                   32,  0, 16, 8)

# ROW 1 — server-log time series
lens_line       ("Requests Over Time",       SL_DV, "timestamp",       0,  8, 48, 12)

# ROW 2 — server-log breakdown charts
lens_donut      ("HTTP Status Distribution", SL_DV, "status_code", 10,  0, 20, 24, 12)
lens_donut      ("HTTP Methods",             SL_DV, "method",       5, 24, 20, 24, 12)

# ROW 3 — server-log top IPs
lens_bar_h      ("Top Client IPs",           SL_DV, "client_ip",   10,  0, 32, 48, 12)

# ROW 4 — anomaly metrics
lens_agg_metric ("Unauthorized Attempts",    AN_DV, "sum", "unauthorized_count",  0, 44, 16, 10)
lens_donut      ("Severity Distribution",    AN_DV, "severity",     5, 16, 44, 16, 10)
lens_donut      ("Anomalies by Type",        AN_DV, "anomaly_type", 10, 32, 44, 16, 10)

# ROW 5 — anomaly top attacking IPs
lens_bar_h      ("Top Attacking IPs",        AN_DV, "client_ip",   10,  0, 54, 48, 12)

# ROW 6 — recent anomalies raw documents table
saved_search_fixed(
    "Recent Anomalies Table",
    AN_DV,
    columns=["window_start", "anomaly_type", "severity", "client_ip", "message", "unauthorized_count"],
    sort_field="window_start",
    x=0, y=66, w=48, h=14,
)


# ─── Dashboard object ─────────────────────────────────────────────────────────

objects.append({
    "id": DASH_ID,
    "type": "dashboard",
    "attributes": {
        "title": "Real-Time Server Log Anomaly Detection",
        "description": "Real-time monitoring of server logs and detected anomalies.",
        "panelsJSON": json.dumps(panels),
        "optionsJSON": json.dumps({
            "useMargins": True,
            "hidePanelTitles": False,
            "syncColors": False,
        }),
        "version": 1,
        "timeRestore": True,
        # Data is from Sept 8–21 2026. now-30d = Aug 27–Sep 26. Fully covered.
        "timeFrom": "now-30d",
        "timeTo": "now",
        "kibanaSavedObjectMeta": {
            "searchSourceJSON": json.dumps({
                "query": {"query": "", "language": "kuery"},
                "filter": [],
            })
        },
    },
    "references": dash_refs,
})


# ─── Write NDJSON ─────────────────────────────────────────────────────────────

with open(NDJSON_PATH, "w", encoding="utf-8") as f:
    for obj in objects:
        f.write(json.dumps(obj) + "\n")

type_counts = {}
for o in objects:
    type_counts[o["type"]] = type_counts.get(o["type"], 0) + 1

print(f"Written {len(objects)} saved objects to {NDJSON_PATH}")
for t, n in sorted(type_counts.items()):
    print(f"  {t:20s}: {n}")


# ─── Import into Kibana ───────────────────────────────────────────────────────

print("\nImporting into Kibana (overwrite=true) ...")
with open(NDJSON_PATH, "rb") as f:
    resp = requests.post(
        f"{KIBANA_URL}/api/saved_objects/_import?overwrite=true",
        headers=KIBANA_HEADERS,
        files={"file": (NDJSON_PATH, f, "application/ndjson")},
    )

result = resp.json()
if not result.get("success"):
    print("IMPORT FAILED:")
    print(json.dumps(result, indent=2))
    sys.exit(1)

print(f"SUCCESS — imported {result['successCount']} objects")
for r in result.get("successResults", []):
    print(f"  [{r['type']:15s}] {r['meta']['title']}")

if result.get("errors"):
    print("\nERRORS during import:")
    for e in result["errors"]:
        print(f"  ERROR: {e}")
    sys.exit(1)


# ─── Verify dashboard exists in Kibana ────────────────────────────────────────

print("\nVerifying dashboard in Kibana ...")
check = requests.get(
    f"{KIBANA_URL}/api/saved_objects/dashboard/{DASH_ID}",
    headers=KIBANA_HEADERS,
).json()

print(f"  Title     : {check['attributes']['title']}")
print(f"  Time from : {check['attributes']['timeFrom']}")
print(f"  Time to   : {check['attributes']['timeTo']}")
print(f"  References: {len(check['references'])} panel refs")

panels_in_dash = json.loads(check["attributes"]["panelsJSON"])
print(f"  Panels    : {len(panels_in_dash)}")

# Check for any anomaly-panel references
anomaly_panel_refs = [r for r in check["references"] if r["type"] in ("lens", "search")]
print(f"  Lens/Search refs: {len(anomaly_panel_refs)}")

print(f"\nDashboard URL:")
print(f"  {KIBANA_URL}/app/dashboards#/view/{DASH_ID}")
