"""Alerts worker: reads Kafka and posts messages to Mattermost.

  python app.py          consume security.high, security.review, pipeline.status
  python app.py replay   re-deliver everything waiting in security.dead-letter

Delivery rules
- An offset is committed only after the message was posted (or parked), so a
  stopped worker loses nothing: messages wait in Kafka and show up as lag.
- Each post is tried 3 times. If Mattermost still fails, the message goes to
  security.dead-letter and the worker moves on.
- Delivered event IDs are stored in SQLite, so a repeated event is skipped.
"""
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request

from confluent_kafka import Consumer, Producer

BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "kafka:9092")
TOPICS = ["security.high", "security.review", "pipeline.status"]
DEAD_LETTER = "security.dead-letter"
WEBHOOKS = {
    "security.high": os.environ["MM_WEBHOOK_HIGH"],
    "security.review": os.environ["MM_WEBHOOK_REVIEW"],
    "pipeline.status": os.environ["MM_WEBHOOK_STATUS"],
}
DB_PATH = os.environ.get("STATE_DB", "/state/delivered.sqlite")
ICONS = {"PASS": "white_check_mark", "ADVISORY": "warning", "BLOCKED": "no_entry", "ERROR": "x"}


def open_db():
    db = sqlite3.connect(DB_PATH)
    db.execute("CREATE TABLE IF NOT EXISTS delivered (event_id TEXT PRIMARY KEY, at REAL)")
    return db


def already_delivered(db, event_id):
    return db.execute("SELECT 1 FROM delivered WHERE event_id = ?", (event_id,)).fetchone() is not None


def mark_delivered(db, event_id):
    db.execute("INSERT OR IGNORE INTO delivered VALUES (?, ?)", (event_id, time.time()))
    db.commit()


def format_message(event):
    where = f"`{event.get('repository')}` · branch `{event.get('branch')}` · commit `{event.get('commit')}`"
    link = f" · [workflow run]({event['run_url']})" if event.get("run_url") else ""
    if event.get("kind") == "status":
        result = event.get("result", "ERROR")
        return f":{ICONS.get(result, 'grey_question')}: **Pipeline result: {result}** ({event.get('mode')} mode)\n{where}{link}"
    if event.get("status") != "ok":
        return f":x: **{event.get('scanner')} scanner failed**: no results, coverage unknown\n{where}{link}"
    c = event.get("counts", {})
    counts = " · ".join(f"{k} {c.get(k, 0)}" for k in ("critical", "high", "medium", "low"))
    return f"**{event.get('scanner')} findings**: {counts}\n{where}{link}\nCandidates only: triage them in DefectDojo."


def post(url, text):
    body = json.dumps({"text": text, "username": "security-bot"}).encode()
    request = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        if response.status != 200:
            raise RuntimeError(f"Mattermost answered HTTP {response.status}")


def deliver(url, event, tries=3):
    for attempt in range(1, tries + 1):
        try:
            post(url, format_message(event))
            return True
        except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
            print(f"post failed (attempt {attempt}/{tries}): {exc}", flush=True)
            time.sleep(2 * attempt)
    return False


def handle(msg, db, dead_letter_producer):
    """Process one Kafka message. Returns True when its offset may be committed."""
    topic = msg.topic()
    try:
        event = json.loads(msg.value())
    except (TypeError, json.JSONDecodeError):
        print("unreadable message skipped", flush=True)
        return True
    event_id = event.get("event_id", "")
    if already_delivered(db, event_id):
        print(f"duplicate {event_id} skipped", flush=True)
        return True
    if deliver(WEBHOOKS[topic], event):
        mark_delivered(db, event_id)
        print(f"delivered {event_id} to {topic}", flush=True)
        return True
    # Park it: keep the original topic so replay knows which channel it was for.
    dead_letter_producer.produce(DEAD_LETTER, key=event_id, value=msg.value(),
                                 headers={"original-topic": topic})
    dead_letter_producer.flush(10)
    print(f"parked {event_id} in {DEAD_LETTER}", flush=True)
    return True


def consume():
    db = open_db()
    consumer = Consumer({
        "bootstrap.servers": BOOTSTRAP,
        "group.id": "mattermost-notifier",
        "enable.auto.commit": False,
        "auto.offset.reset": "earliest",
    })
    producer = Producer({"bootstrap.servers": BOOTSTRAP, "acks": "all"})
    consumer.subscribe(TOPICS)
    print(f"worker consuming {TOPICS}", flush=True)
    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                print(f"Kafka error: {msg.error()}", flush=True)
                continue
            if handle(msg, db, producer):
                consumer.commit(message=msg, asynchronous=False)
    finally:
        consumer.close()


def replay():
    db = open_db()
    consumer = Consumer({
        "bootstrap.servers": BOOTSTRAP,
        "group.id": "dead-letter-replay",
        "enable.auto.commit": False,
        "auto.offset.reset": "earliest",
    })
    consumer.subscribe([DEAD_LETTER])
    idle, replayed = 0, 0
    while idle < 10:                       # stop after about 10 quiet seconds
        msg = consumer.poll(1.0)
        if msg is None or msg.error():
            idle += 1
            continue
        idle = 0
        headers = dict(msg.headers() or [])
        topic = headers.get("original-topic", b"pipeline.status").decode()
        event = json.loads(msg.value())
        if not already_delivered(db, event.get("event_id", "")):
            if not deliver(WEBHOOKS.get(topic, WEBHOOKS["pipeline.status"]), event):
                print("Mattermost still failing: stopping replay, message stays in the dead-letter topic.")
                break
            mark_delivered(db, event.get("event_id", ""))
            replayed += 1
        consumer.commit(message=msg, asynchronous=False)
    consumer.close()
    print(f"replayed {replayed} message(s)")


if __name__ == "__main__":
    replay() if sys.argv[1:] == ["replay"] else consume()
