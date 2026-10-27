FROM apache/spark:3.5.3-python3

ENV DEBIAN_FRONTEND=noninteractive \
    JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64 \
    SPARK_HOME=/opt/spark \
    PYSPARK_PYTHON=python \
    PYSPARK_DRIVER_PYTHON=python \
    PYTHONUNBUFFERED=1

WORKDIR /app
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends openjdk-17-jre-headless python3 python3-pip python-is-python3 procps \
    && test -x /usr/bin/ps \
    && ln -sf /usr/bin/python3 /usr/local/bin/python \
    && rm -rf /var/lib/apt/lists/*
RUN pip3 install --no-cache-dir kafka-python==2.2.0 elasticsearch==8.15.1
COPY spark_jobs ./spark_jobs

CMD ["sh", "-c", "/opt/spark/bin/spark-submit --master local[2] --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.3 spark_jobs/streaming_detector.py"]
