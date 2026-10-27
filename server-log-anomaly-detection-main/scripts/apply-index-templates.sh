#!/usr/bin/env sh
set -eu

[ -f .env ] && set -a && . ./.env && set +a

es_url="http://${ELASTICSEARCH_EXTERNAL_HOST:-localhost}:${ELASTICSEARCH_PORT:-9200}"

curl --fail-with-body -X PUT "$es_url/_index_template/server-logs-template" \
  -H 'Content-Type: application/json' \
  --data-binary @elastic_config/index_templates/server-logs-template.json

echo
curl --fail-with-body -X PUT "$es_url/_index_template/anomalies-template" \
  -H 'Content-Type: application/json' \
  --data-binary @elastic_config/index_templates/anomalies-template.json

echo
