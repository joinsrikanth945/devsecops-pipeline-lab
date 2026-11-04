"""Alerts receiver: accepts scan events over HTTP and writes them to Kafka.

POST /events   Authorization: Bearer <RECEIVER_TOKEN>
               body {"events": [ {...}, ... ]}   (1 to 20 events)
GET  /health   liveness check

Routing (topic chosen from the event):
  scan event with critical or high findings  -> security.high
  scan event with medium or low findings     -> security.review
  scan event with nothing found, or a status -> pipeline.status
  scan event whose scanner errored           -> pipeline.status
The HTTP answer is 202 only after Kafka confirms every message.
"""
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from confluent_kafka import Producer

TOKEN = os.environ["RECEIVER_TOKEN"]
BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "kafka:9092")
ALLOWED_REPO = os.environ.get("ALLOWED_REPOSITORY", "")      # empty = accept any
MAX_BODY = 64 * 1024
REQUIRED = {"event_id", "kind", "repository", "branch"}


def route(event):
    if event.get("kind") != "scan" or event.get("status") != "ok":
        return "pipeline.status"
    counts = event.get("counts") or {}
    if counts.get("critical", 0) + counts.get("high", 0) > 0:
        return "security.high"
    if counts.get("medium", 0) + counts.get("low", 0) > 0:
        return "security.review"
    return "pipeline.status"


def validate(event):
    if not isinstance(event, dict) or not REQUIRED.issubset(event):
        raise ValueError("event is missing required fields")
    if ALLOWED_REPO and event["repository"] != ALLOWED_REPO:
        raise ValueError("repository not allowed")
    if not isinstance(event["event_id"], str) or not 1 <= len(event["event_id"]) <= 128:
        raise ValueError("bad event_id")
    return event


def publish(producer, events):
    """Send all events and wait until Kafka acknowledges each one."""
    failures = []

    def on_delivery(err, msg):
        if err is not None:
            failures.append(str(err))

    for event in events:
        producer.produce(route(event), key=event["event_id"], value=json.dumps(event).encode(),
                         on_delivery=on_delivery)
    remaining = producer.flush(15)
    if remaining or failures:
        raise RuntimeError(f"Kafka did not confirm {remaining or len(failures)} message(s)")
    return len(events)


class Handler(BaseHTTPRequestHandler):
    producer = None

    def reply(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self.reply(200, {"status": "ok"})
        else:
            self.reply(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/events":
            return self.reply(404, {"error": "not found"})
        if not hmac.compare_digest(self.headers.get("Authorization", ""), f"Bearer {TOKEN}"):
            return self.reply(401, {"error": "unauthorized"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= MAX_BODY:
                raise ValueError("body size")
            data = json.loads(self.rfile.read(size))
            events = data.get("events") if isinstance(data, dict) else None
            if not isinstance(events, list) or not 1 <= len(events) <= 20:
                raise ValueError("events must be a list of 1 to 20 items")
            events = [validate(e) for e in events]
        except (ValueError, json.JSONDecodeError) as exc:
            return self.reply(400, {"error": str(exc)})
        try:
            accepted = publish(self.producer, events)
        except RuntimeError as exc:
            return self.reply(503, {"error": str(exc)})
        self.reply(202, {"accepted": accepted})

    def log_message(self, fmt, *args):
        print("receiver:", fmt % args, flush=True)


def main():
    Handler.producer = Producer({"bootstrap.servers": BOOTSTRAP, "acks": "all", "enable.idempotence": True})
    print(f"receiver listening on :8000, Kafka at {BOOTSTRAP}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()


if __name__ == "__main__":
    main()
