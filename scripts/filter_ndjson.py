import json, pathlib, sys

input_path = pathlib.Path('kibana/dashboard_export.ndjson')
output_path = pathlib.Path('kibana/lens_dashboard.ndjson')

keep_types = {'lens', 'dashboard'}

with input_path.open('r', encoding='utf-8') as fin, output_path.open('w', encoding='utf-8') as fout:
    for line in fin:
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if obj.get('type') in keep_types:
            fout.write(json.dumps(obj) + '\n')
print('Filtered objects written to', output_path)
