#!/usr/bin/env python3
"""Send the scan summary to the alerts receiver as events.

One event per scanner (with its severity counts) plus one pipeline-status
event. Event IDs are derived from the run, so re-sending the same run cannot
create duplicate chat messages: the worker skips IDs it has already delivered.

Environment:
  ALERTS_URL     e.g. http://127.0.0.1:8000
  ALERTS_TOKEN   shared secret, the same value as RECEIVER_TOKEN in platform/alerts/.env
  RUN_URL        link to the workflow run (set by the workflow)
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPORTS = Path(os.environ.get("REPORTS_DIR", "reports"))


def build_events(summary):
    run = f"{summary.get('run_id') or 'local'}-{summary.get('run_attempt') or '1'}"
    base = {
        "repository": summary.get("repository", ""),
        "branch": summary.get("branch", ""),
        "commit": summary.get("commit", "")[:12],
        "run_url": os.environ.get("RUN_URL", ""),
        "mode": summary.get("mode", ""),
    }
    events = []
    for scanner, data in summary.get("scanners", {}).items():
        events.append(dict(base, event_id=f"{run}-{scanner}", kind="scan", scanner=scanner,
                           status=data.get("status"), counts=data.get("counts", {})))
    events.append(dict(base, event_id=f"{run}-status", kind="status", result=summary.get("result", "ERROR")))
    return events


def send(url, token, events):
    body = json.dumps({"events": events}).encode()
    request = urllib.request.Request(
        url.rstrip("/") + "/events", data=body, method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.status, json.loads(response.read() or b"{}")


def main():
    url, token = os.environ.get("ALERTS_URL", ""), os.environ.get("ALERTS_TOKEN", "")
    if not url or not token:
        print("ALERTS_URL or ALERTS_TOKEN not set: skipping alerts.")
        return 0
    summary_path = REPORTS / "summary.json"
    if not summary_path.is_file():
        print("reports/summary.json missing: run gate.py summarize first.")
        return 1
    events = build_events(json.loads(summary_path.read_text(encoding="utf-8")))

    for attempt in range(1, 4):
        try:
            status, data = send(url, token, events)
            if status == 202 and data.get("accepted") == len(events):
                print(f"Queued {len(events)} events in Kafka.")
                return 0
            print(f"Attempt {attempt}: unexpected answer HTTP {status} {data}")
        except urllib.error.HTTPError as exc:
            print(f"Attempt {attempt}: HTTP {exc.code}")
            if exc.code in (400, 401):
                return 1                    # retrying will not fix a bad token or payload
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"Attempt {attempt}: receiver not reachable ({exc})")
        time.sleep(3 * attempt)
    return 1


if __name__ == "__main__":
    sys.exit(main())
