import json, pathlib

src = pathlib.Path('kibana/dashboard_export.ndjson')
idx_out = pathlib.Path('kibana/index_patterns.ndjson')
search_out = pathlib.Path('kibana/fixed_recent_anomalies.ndjson')

idx_objs = []
search_obj = None

with src.open('r', encoding='utf-8') as f:
    for line in f:
        line=line.strip()
        if not line:
            continue
        obj=json.loads(line)
        if obj.get('type')=='index-pattern':
            idx_objs.append(obj)
        if obj.get('type')=='search' and obj.get('id')=='2cdc24b7-c660-4b2d-8726-dc8f54c789af':
            # fix searchSourceJSON by removing useRecentSearches if present
            attrs=obj.get('attributes',{})
            ksm=attrs.get('kibanaSavedObjectMeta',{})
            ssj=ksm.get('searchSourceJSON','')
            try:
                ss=json.loads(ssj)
                ss.pop('useRecentSearches',None)
                ksm['searchSourceJSON']=json.dumps(ss)
                attrs['kibanaSavedObjectMeta']=ksm
                obj['attributes']=attrs
                search_obj=obj
            except Exception:
                pass

with idx_out.open('w', encoding='utf-8') as f:
    for o in idx_objs:
        f.write(json.dumps(o)+'\n')

if search_obj:
    with search_out.open('w', encoding='utf-8') as f:
        f.write(json.dumps(search_obj)+'\n')
print('Created', idx_out, 'and', search_out if search_obj else 'no search object')
