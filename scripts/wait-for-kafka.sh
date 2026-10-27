#!/usr/bin/env sh
set -eu

[ -f .env ] && set -a && . ./.env && set +a

bootstrap_server="${KAFKA_HOST:-kafka}:${KAFKA_INTERNAL_PORT:-9092}"
retries="${KAFKA_WAIT_RETRIES:-30}"

until docker compose --env-file .env exec -T kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server "$bootstrap_server" --list >/dev/null 2>&1; do
  retries=$((retries - 1))
  if [ "$retries" -le 0 ]; then
    echo "Kafka did not become ready" >&2
    exit 1
  fi
  sleep 2
done

echo "Kafka is ready"
