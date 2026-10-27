import requests
import json

kibana_url = 'http://localhost:5601'
headers = {'kbn-xsrf': 'true', 'Content-Type': 'application/json'}

def create_data_view(id, title, time_field, name):
    url = f'{kibana_url}/api/saved_objects/index-pattern/{id}'
    payload = {
        'attributes': {
            'title': title,
            'timeFieldName': time_field,
            'name': name
        }
    }
    # Check if exists first
    check = requests.get(url, headers=headers)
    if check.status_code == 200:
        print(f"Data view {id} already exists.")
        return
    
    resp = requests.post(url, headers=headers, data=json.dumps(payload))
    if resp.status_code in (200, 201):
        print(f"Created data view {id}")
    else:
        print(f"Failed to create data view {id}: {resp.text}")

create_data_view('server-logs-view', 'server-logs-*', 'timestamp', 'Server Logs')
create_data_view('anomalies-view', 'anomalies-*', 'window_start', 'Anomalies')
