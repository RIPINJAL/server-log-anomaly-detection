#!/usr/bin/env sh
set -eu

[ -f .env ] && set -a && . ./.env && set +a

bootstrap_server="${KAFKA_HOST:-kafka}:${KAFKA_INTERNAL_PORT:-9092}"
partitions="${KAFKA_PARTITIONS:-3}"
replication_factor="${KAFKA_REPLICATION_FACTOR:-1}"

for topic in "${KAFKA_TOPIC_SERVER_LOGS:-server-logs}" "${KAFKA_TOPIC_ANOMALIES:-anomalies}"; do
  docker compose --env-file .env exec -T kafka /opt/kafka/bin/kafka-topics.sh \
    --bootstrap-server "$bootstrap_server" \
    --create --if-not-exists \
    --topic "$topic" \
    --partitions "$partitions" \
    --replication-factor "$replication_factor"
done
