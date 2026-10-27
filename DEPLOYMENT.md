# Free Self-Hosted Deployment

Run the complete application on one Docker-capable VM. This avoids paid managed Kafka and Elasticsearch services:

```text
One VM             Kafka, Elasticsearch, Kibana, Spark, and producer
Browser            Kibana dashboard at one link
```

## Deploy to a VM

Use an Ubuntu VM with at least 6 GB RAM for a small demonstration. Oracle Cloud Always Free may be suitable if you are eligible; cloud providers can change their free-tier limits. Allow SSH and HTTP/HTTPS only. Do not expose Kafka port 9094 publicly.

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin git
sudo usermod -aG docker "$USER"
newgrp docker
git clone <your-repository-url>
cd server-log-anomaly-detection
cp .env.example .env
```

Start the complete stack:

```bash
docker compose up -d
docker compose ps
docker compose exec -T kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:9092 --create --if-not-exists --topic server-logs --partitions 3 --replication-factor 1
docker compose exec -T kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:9092 --create --if-not-exists --topic anomalies --partitions 3 --replication-factor 1
```

Apply the Elasticsearch templates and start Spark:

```bash
./scripts/apply-index-templates.sh
docker compose --profile streaming up -d --build spark-detector
docker compose logs -f spark-detector
```

Kibana is the single browser link for the project: `http://<VM-IP>:5601`. Elasticsearch remains a backend service; restrict port 9200 with the VM firewall.

## 3. Run the producer

Run the producer on the VM:

```bash
python producer/kafka_producer.py --scenario brute-force --rate 10
```

For a portfolio demo, use a finite run:

```bash
python producer/kafka_producer.py --scenario brute-force --rate 100 --count 140
```

## Optional dashboard

The custom dashboard is in `dashboard/`, but Vercel cannot securely connect directly to an unauthenticated Elasticsearch instance. For a free deployment, use Kibana on the VM. Deploy the custom dashboard to Vercel only after adding an authenticated HTTPS API proxy in front of Elasticsearch.

The dashboard polls `/api/summary` every 10 seconds and displays indexed logs, anomaly count, and latest findings.

## Local development remains unchanged

The same stack can be tested locally with:

```powershell
docker compose up -d
make topics
make apply-index-templates
make run-spark-job
```

Do not commit `.env`, API keys, or generated `dashboard/node_modules/` files. Revoke the Elastic API key that was previously placed in `.env.cloud.example` and create a new one only if you later use Elastic Cloud.
