from pathlib import Path

p = Path("kibana/fixed_recent_anomalies.ndjson")

s = p.read_text(encoding="utf-8-sig").strip()

# Remove the escaping of the OUTER JSON object only.
# The inner searchSourceJSON escaping must remain intact.
if s.startswith(r"{\""):
    s = s.replace(r'\"', '"')

p.write_text(s + "\n", encoding="utf-8", newline="")

print("Fixed outer JSON escaping.")
