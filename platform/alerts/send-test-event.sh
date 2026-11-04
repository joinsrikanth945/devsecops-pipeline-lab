#!/usr/bin/env bash
# Send one clearly labelled test event to the receiver (used in the chapter 9 demos).
# Usage: ./send-test-event.sh [high|review|status] [event-id]
#   Give the same event-id twice to see duplicate suppression.
set -euo pipefail
cd "$(dirname "$0")"
kind="${1:-high}"
token="$(grep '^RECEIVER_TOKEN=' .env | cut -d= -f2-)"
repo="$(grep '^ALLOWED_REPOSITORY=' .env | cut -d= -f2-)"
id="${2:-demo-$(date +%s)-$kind}"
case "$kind" in
  high)   counts='{"critical":1,"high":2,"medium":0,"low":0}' ;;
  review) counts='{"critical":0,"high":0,"medium":3,"low":1}' ;;
  status) counts='{"critical":0,"high":0,"medium":0,"low":0}' ;;
  *) echo "use high, review or status"; exit 1 ;;
esac
curl -sS -X POST http://127.0.0.1:8000/events \
  -H "Authorization: Bearer $token" -H 'Content-Type: application/json' \
  -d "{\"events\":[{\"event_id\":\"$id\",\"kind\":\"scan\",\"scanner\":\"demo\",\"status\":\"ok\",\"repository\":\"${repo:-demo/demo}\",\"branch\":\"demo\",\"commit\":\"demo\",\"mode\":\"demo\",\"counts\":$counts}]}"
echo
echo "sent $id"
