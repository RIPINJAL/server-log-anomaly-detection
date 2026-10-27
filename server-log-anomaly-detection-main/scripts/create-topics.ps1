$ErrorActionPreference = 'Stop'

$envPath = Join-Path $PSScriptRoot '..\.env'
if (Test-Path $envPath) {
    Get-Content $envPath | ForEach-Object {
        if ($_ -match '^[^#\s][^=]*=') {
            $parts = $_ -split '=', 2
            $name = $parts[0].Trim()
            $value = $parts[1].Trim()
            if ($name) {
                [Environment]::SetEnvironmentVariable($name, $value, 'Process')
            }
        }
    }
}

$kafkaHost = if ($env:KAFKA_HOST) { $env:KAFKA_HOST } else { 'kafka' }
$kafkaPort = if ($env:KAFKA_INTERNAL_PORT) { $env:KAFKA_INTERNAL_PORT } else { '9092' }
$bootstrap = "${kafkaHost}:${kafkaPort}"
$partitions = if ($env:KAFKA_PARTITIONS) { $env:KAFKA_PARTITIONS } else { '3' }
$replication = if ($env:KAFKA_REPLICATION_FACTOR) { $env:KAFKA_REPLICATION_FACTOR } else { '1' }
$topics = @(
    $(if ($env:KAFKA_TOPIC_SERVER_LOGS) { $env:KAFKA_TOPIC_SERVER_LOGS } else { 'server-logs' }),
    $(if ($env:KAFKA_TOPIC_ANOMALIES) { $env:KAFKA_TOPIC_ANOMALIES } else { 'anomalies' })
)

foreach ($topic in $topics) {
    docker compose exec -T kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server $bootstrap --create --if-not-exists --topic $topic --partitions $partitions --replication-factor $replication
}
