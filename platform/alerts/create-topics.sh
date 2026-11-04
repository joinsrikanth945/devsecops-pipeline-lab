#!/usr/bin/env bash
# Create the four alert topics. Safe to run again (--if-not-exists).
set -euo pipefail
cd "$(dirname "$0")"
for topic in security.high security.review pipeline.status security.dead-letter; do
  docker compose exec -T kafka /opt/kafka/bin/kafka-topics.sh \
    --bootstrap-server kafka:9092 --create --if-not-exists \
    --topic "$topic" --partitions 1 --replication-factor 1
done
docker compose exec -T kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:9092 --list
