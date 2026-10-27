const ES_DEFAULT = process.env.ELASTICSEARCH_URL || "http://localhost:9200";
const API_KEY = process.env.ELASTICSEARCH_API_KEY;
const USER = process.env.ELASTICSEARCH_USERNAME;
const PASS = process.env.ELASTICSEARCH_PASSWORD;

function authHeaders() {
  const h = { "content-type": "application/json" };
  if (API_KEY) h.authorization = `ApiKey ${API_KEY}`;
  else if (USER) h.authorization = "Basic " + Buffer.from(`${USER}:${PASS || ""}`).toString("base64");
  return h;
}

async function es(path, body, esUrl = ES_DEFAULT) {
  const url = `${esUrl.replace(/\/$/, "")}/${path}`;
  const r = await fetch(url, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(body),
  });
  const t = await r.text();
  if (!r.ok) throw new Error(`Elasticsearch ${r.status} (${path}): ${t.slice(0, 300)}`);
  return JSON.parse(t);
}

const terms = (field, size = 10) => ({ terms: { field, size } });

async function getDashboardData(esUrl = ES_DEFAULT) {
  const [reqs, anom, unauth, appLogs, appWarnings, status, methods, ips, types, severity, attackers, recent, trend] =
    await Promise.all([
      es("server-logs-*/_count", { query: { match_all: {} } }, esUrl).catch(() => ({ count: 0 })),
      es("anomalies-*/_count", { query: { match_all: {} } }, esUrl).catch(() => ({ count: 0 })),
      es("server-logs-*/_count", { query: { terms: { status_code: [401, 403] } } }, esUrl).catch(() => ({ count: 0 })),
      es("app-logs-*/_count", { query: { match_all: {} } }, esUrl).catch(() => ({ count: 0 })),
      es("app-logs-*/_count", { query: { term: { log_level: "WARNING" } } }, esUrl).catch(() => ({ count: 0 })),
      es("server-logs-*/_search", { size: 0, aggs: { x: terms("status_code", 12) } }, esUrl).catch(() => ({ aggregations: { x: { buckets: [] } } })),
      es("server-logs-*/_search", { size: 0, aggs: { x: terms("method", 10) } }, esUrl).catch(() => ({ aggregations: { x: { buckets: [] } } })),
      es("server-logs-*/_search", { size: 0, aggs: { x: terms("client_ip", 10) } }, esUrl).catch(() => ({ aggregations: { x: { buckets: [] } } })),
      es("anomalies-*/_search", { size: 0, aggs: { x: terms("anomaly_type", 10) } }, esUrl).catch(() => ({ aggregations: { x: { buckets: [] } } })),
      es("anomalies-*/_search", { size: 0, aggs: { x: terms("severity", 10) } }, esUrl).catch(() => ({ aggregations: { x: { buckets: [] } } })),
      es("anomalies-*/_search", { size: 0, aggs: { x: terms("client_ip", 10) } }, esUrl).catch(() => ({ aggregations: { x: { buckets: [] } } })),
      es("anomalies-*/_search", {
        size: 15,
        sort: [{ "window_start": { order: "desc" } }],
        _source: ["window_start", "window_end", "anomaly_type", "severity", "client_ip", "unauthorized_count", "message"]
      }, esUrl).catch(() => ({ hits: { hits: [] } })),
      es("server-logs-*/_search", {
        size: 0,
        aggs: { x: { date_histogram: { field: "timestamp", fixed_interval: "1h", min_doc_count: 0 } } }
      }, esUrl).catch(() => ({ aggregations: { x: { buckets: [] } } }))
    ]);

  const avg = await es("server-logs-*/_search", { size: 0, aggs: { x: { avg: { field: "latency_ms" } } } }, esUrl)
    .catch(() => ({ aggregations: { x: { value: 0 } } }));

  const b = a => a.aggregations?.x?.buckets || [];

  return {
    kpis: {
      totalRequests: reqs.count || 0,
      totalAnomalies: anom.count || 0,
      unauthorizedAttempts: unauth.count || 0,
      applicationLogs: appLogs.count || 0,
      applicationWarnings: appWarnings.count || 0,
      avgLatency: avg.aggregations?.x?.value || 0
    },
    statusDistribution: b(status).map(x => ({ label: String(x.key), value: x.doc_count })),
    methods: b(methods).map(x => ({ label: String(x.key), value: x.doc_count })),
    topClientIps: b(ips).map(x => ({ label: String(x.key), value: x.doc_count })),
    anomalyTypes: b(types).map(x => ({ label: String(x.key), value: x.doc_count })),
    severity: b(severity).map(x => ({ label: String(x.key), value: x.doc_count })),
    topAttackers: b(attackers).map(x => ({ label: String(x.key), value: x.doc_count })),
    requestsOverTime: b(trend).slice(-24).map(x => ({
      label: new Date(x.key_as_string || x.key).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit" }),
      value: x.doc_count
    })),
    recentAnomalies: recent.hits?.hits?.map(x => x._source) || []
  };
}

module.exports = {
  getDashboardData,
  handler: async function (req, res) {
    try {
      const data = await getDashboardData();
      res.setHeader("Cache-Control", "no-store");
      res.setHeader("Content-Type", "application/json");
      if (typeof res.status === "function") {
        return res.status(200).json(data);
      } else {
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify(data));
      }
    } catch (e) {
      if (typeof res.status === "function") {
        return res.status(502).json({ error: e.message });
      } else {
        res.writeHead(502, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: e.message }));
      }
    }
  }
};
