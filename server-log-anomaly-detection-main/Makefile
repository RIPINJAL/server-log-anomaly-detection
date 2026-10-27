COMPOSE := docker compose --env-file .env

.PHONY: up down logs ps config topics apply-index-templates produce run-spark-job run-spark-gpu

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=100

ps:
	$(COMPOSE) ps

config:
	$(COMPOSE) config

topics:
	powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/create-topics.ps1

apply-index-templates:
	powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/apply-index-templates.ps1

produce:
	powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Content .env | ForEach-Object { if ($_ -match '^(?!#)') { $name,$value = $_ -split '=',2; if ($name) { [Environment]::SetEnvironmentVariable($name, $value, 'Process') } } }; python producer/kafka_producer.py"

run-spark-job:
	$(COMPOSE) --profile streaming run --rm spark-detector

run-spark-gpu:
	$(COMPOSE) -f docker-compose.yml -f docker-compose.gpu.yml \
		--profile streaming run --rm \
		-e NVIDIA_VISIBLE_DEVICES=all -e SPARK_GPU_ENABLED=true spark-detector
