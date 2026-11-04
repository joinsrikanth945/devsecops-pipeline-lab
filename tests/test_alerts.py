"""Tests for the alerts receiver, worker and event publisher, without Kafka.

Kafka and Mattermost are replaced by small fakes, so the routing, retry,
dead-letter and duplicate rules can be checked on any machine.
Needs:  pip install confluent-kafka   (the tests are skipped without it)
"""
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent

try:
    import confluent_kafka  # noqa: F401
    HAVE_KAFKA = True
except ImportError:
    HAVE_KAFKA = False


def load(path, name, env):
    with mock.patch.dict(os.environ, env):
        spec = importlib.util.spec_from_file_location(name, ROOT / path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class FakeMessage:
    def __init__(self, topic, value):
        self._topic, self._value = topic, value

    def topic(self):
        return self._topic

    def value(self):
        return self._value


class FakeProducer:
    def __init__(self):
        self.sent = []

    def produce(self, topic, key=None, value=None, headers=None, on_delivery=None):
        self.sent.append((topic, key, value, headers))
        if on_delivery:
            on_delivery(None, None)

    def flush(self, timeout=None):
        return 0


@unittest.skipUnless(HAVE_KAFKA, "confluent-kafka not installed")
class ReceiverTest(unittest.TestCase):
    def setUp(self):
        self.r = load("platform/alerts/receiver/app.py", "receiver",
                      {"RECEIVER_TOKEN": "t", "ALLOWED_REPOSITORY": "me/repo"})

    def event(self, **kw):
        base = {"event_id": "1-1-sast", "kind": "scan", "status": "ok", "repository": "me/repo",
                "branch": "main", "counts": {"critical": 0, "high": 0, "medium": 0, "low": 0}}
        base.update(kw)
        return base

    def test_routing_by_severity(self):
        self.assertEqual(self.r.route(self.event(counts={"high": 2})), "security.high")
        self.assertEqual(self.r.route(self.event(counts={"critical": 1})), "security.high")
        self.assertEqual(self.r.route(self.event(counts={"medium": 1})), "security.review")
        self.assertEqual(self.r.route(self.event()), "pipeline.status")
        self.assertEqual(self.r.route(self.event(status="error", counts={"high": 5})), "pipeline.status")
        self.assertEqual(self.r.route({"kind": "status"}), "pipeline.status")

    def test_validation(self):
        self.r.validate(self.event())
        with self.assertRaises(ValueError):
            self.r.validate(self.event(repository="someone/else"))
        with self.assertRaises(ValueError):
            self.r.validate({"kind": "scan"})

    def test_publish_waits_for_every_ack(self):
        producer = FakeProducer()
        self.assertEqual(self.r.publish(producer, [self.event(), self.event(event_id="x", counts={"high": 1})]), 2)
        self.assertEqual([t for t, *_ in producer.sent], ["pipeline.status", "security.high"])

    def test_publish_raises_when_kafka_does_not_confirm(self):
        producer = FakeProducer()
        producer.flush = lambda timeout=None: 1
        with self.assertRaises(RuntimeError):
            self.r.publish(producer, [self.event()])


@unittest.skipUnless(HAVE_KAFKA, "confluent-kafka not installed")
class WorkerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        env = {"MM_WEBHOOK_HIGH": "http://mm/high", "MM_WEBHOOK_REVIEW": "http://mm/review",
               "MM_WEBHOOK_STATUS": "http://mm/status", "STATE_DB": os.path.join(self.tmp, "d.sqlite")}
        self.env = mock.patch.dict(os.environ, env)
        self.env.start()
        self.w = load("platform/alerts/worker/app.py", "worker", env)
        self.w.time.sleep = lambda s: None          # no waiting between retries in tests
        self.db = self.w.open_db()
        self.posts = []

    def tearDown(self):
        self.db.close()
        self.env.stop()

    def msg(self, topic="security.high", event_id="run1-sast", **kw):
        event = {"event_id": event_id, "kind": "scan", "scanner": "sast", "status": "ok",
                 "repository": "me/repo", "branch": "main", "commit": "abc",
                 "counts": {"critical": 0, "high": 3, "medium": 1, "low": 0}}
        event.update(kw)
        return FakeMessage(topic, json.dumps(event).encode())

    def test_delivers_to_the_topic_channel_once(self):
        self.w.post = lambda url, text: self.posts.append((url, text))
        dlq = FakeProducer()
        self.assertTrue(self.w.handle(self.msg(), self.db, dlq))
        self.assertTrue(self.w.handle(self.msg(), self.db, dlq))   # same event again
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(self.posts[0][0], "http://mm/high")
        self.assertIn("high 3", self.posts[0][1])
        self.assertEqual(dlq.sent, [])

    def test_failed_post_goes_to_dead_letter_after_three_tries(self):
        calls = []

        def broken(url, text):
            calls.append(url)
            raise RuntimeError("Mattermost down")

        self.w.post = broken
        dlq = FakeProducer()
        self.assertTrue(self.w.handle(self.msg(event_id="run2-sast"), self.db, dlq))
        self.assertEqual(len(calls), 3)
        self.assertEqual(dlq.sent[0][0], "security.dead-letter")
        self.assertEqual(dlq.sent[0][3], {"original-topic": "security.high"})
        self.assertFalse(self.w.already_delivered(self.db, "run2-sast"))

    def test_messages_read_well(self):
        status = self.w.format_message({"kind": "status", "result": "BLOCKED", "mode": "blocking",
                                        "repository": "me/repo", "branch": "main", "commit": "abc",
                                        "run_url": "https://example.test/run/1"})
        self.assertIn("Pipeline result: BLOCKED", status)
        self.assertIn("[workflow run](https://example.test/run/1)", status)
        error = self.w.format_message({"kind": "scan", "scanner": "image", "status": "error",
                                       "repository": "r", "branch": "b", "commit": "c"})
        self.assertIn("scanner failed", error)


class PublisherTest(unittest.TestCase):
    def test_one_event_per_scanner_plus_status(self):
        p = load("scripts/publish_events.py", "publisher", {})
        summary = {"run_id": "42", "run_attempt": "1", "repository": "me/repo", "branch": "testing",
                   "commit": "0123456789abcdef", "mode": "advisory", "result": "ADVISORY",
                   "scanners": {"secrets": {"status": "ok", "counts": {"high": 1}},
                                "image": {"status": "error", "counts": {}}}}
        events = p.build_events(summary)
        self.assertEqual([e["event_id"] for e in events], ["42-1-secrets", "42-1-image", "42-1-status"])
        self.assertEqual(events[0]["commit"], "0123456789ab")
        self.assertEqual(events[-1]["result"], "ADVISORY")


if __name__ == "__main__":
    unittest.main()
