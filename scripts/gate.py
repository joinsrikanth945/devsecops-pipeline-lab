#!/usr/bin/env python3
"""Summarise scanner reports and apply the branch security policy.

Usage:
  gate.py summarize   read reports/, write reports/summary.json, never fails on findings
  gate.py enforce     read reports/summary.json and exit 0 (pass/advisory) or 1 (blocked)

A missing or unreadable report is an ERROR and fails on every branch:
"we could not scan" must never look like "nothing was found".
"""
import json
import os
import sys
from pathlib import Path

REPORTS = Path(os.environ.get("REPORTS_DIR", "reports"))
SUMMARY = REPORTS / "summary.json"

# Branches where findings are shown but do not fail the run.
ADVISORY_BRANCHES = {b.strip() for b in os.environ.get("ADVISORY_BRANCHES", "testing").split(",") if b.strip()}

# What blocks on a strict branch. Override with repository variables if you like.
BLOCK_SECRETS = int(os.environ.get("BLOCK_ON_SECRETS", "1"))            # any secret
BLOCK_SAST = os.environ.get("BLOCK_ON_SAST", "high")                     # high | medium | none
BLOCK_IMAGE = os.environ.get("BLOCK_ON_IMAGE", "critical")               # critical | high | none

LEVELS = ["critical", "high", "medium", "low", "info"]


def empty_counts():
    return {level: 0 for level in LEVELS}


def load_json(name):
    path = REPORTS / name
    if not path.is_file():
        raise ValueError(f"{name} is missing")
    try:
        return json.loads(path.read_text(encoding="utf-8") or "null")
    except json.JSONDecodeError as exc:
        raise ValueError(f"{name} is not valid JSON ({exc.msg})") from None


def count_gitleaks(data):
    # Gitleaks writes a JSON list, one object per leak. An empty scan may write [] or null.
    if data is None:
        data = []
    if not isinstance(data, list):
        raise ValueError("gitleaks.json is not a list")
    counts = empty_counts()
    counts["high"] = len(data)          # every leaked secret is treated as high
    return counts


def count_semgrep(data):
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise ValueError("semgrep.json has no results list")
    mapping = {"ERROR": "high", "WARNING": "medium", "INFO": "low"}
    counts = empty_counts()
    for result in data["results"]:
        severity = str(result.get("extra", {}).get("severity", "INFO")).upper()
        counts[mapping.get(severity, "low")] += 1
    return counts


def count_trivy(data):
    if not isinstance(data, dict) or ("Results" not in data and "ArtifactName" not in data):
        raise ValueError("trivy.json is not a Trivy report")
    counts = empty_counts()
    for result in data.get("Results") or []:
        for vuln in result.get("Vulnerabilities") or []:
            level = str(vuln.get("Severity", "UNKNOWN")).lower()
            counts[level if level in counts else "info"] += 1
    return counts


SCANNERS = {
    "secrets": ("gitleaks.json", count_gitleaks),
    "sast": ("semgrep.json", count_semgrep),
    "image": ("trivy.json", count_trivy),
}


def is_blocking(scanner, counts):
    if scanner == "secrets":
        return BLOCK_SECRETS and counts["high"] > 0
    if scanner == "sast":
        if BLOCK_SAST == "high":
            return counts["high"] > 0
        if BLOCK_SAST == "medium":
            return counts["high"] + counts["medium"] > 0
        return False
    if scanner == "image":
        if BLOCK_IMAGE == "critical":
            return counts["critical"] > 0
        if BLOCK_IMAGE == "high":
            return counts["critical"] + counts["high"] > 0
        return False
    return False


def branch_and_mode():
    event = os.environ.get("GITHUB_EVENT_NAME", "local")
    ref = os.environ.get("GITHUB_REF", "")
    branch = ref.removeprefix("refs/heads/") if ref.startswith("refs/heads/") else ref
    # Only a direct push to an advisory branch gets the advisory exception.
    advisory = event == "push" and branch in ADVISORY_BRANCHES
    return branch, ("advisory" if advisory else "blocking")


def summarize():
    branch, mode = branch_and_mode()
    scanners = {}
    for name, (filename, counter) in SCANNERS.items():
        if os.environ.get(f"SKIP_{name.upper()}") == "1":
            continue
        try:
            counts = counter(load_json(filename))
            scanners[name] = {"status": "ok", "counts": counts, "blocking": bool(is_blocking(name, counts))}
        except ValueError as exc:
            scanners[name] = {"status": "error", "reason": str(exc), "counts": empty_counts(), "blocking": True}

    errors = [n for n, s in scanners.items() if s["status"] == "error"]
    blocking = [n for n, s in scanners.items() if s["blocking"] and s["status"] == "ok"]
    if errors:
        result = "ERROR"
    elif blocking and mode == "blocking":
        result = "BLOCKED"
    elif blocking:
        result = "ADVISORY"
    else:
        result = "PASS"

    summary = {
        "result": result,
        "mode": mode,
        "branch": branch,
        "commit": os.environ.get("GITHUB_SHA", ""),
        "run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", "1"),
        "repository": os.environ.get("GITHUB_REPOSITORY", ""),
        "scanners": scanners,
    }
    REPORTS.mkdir(exist_ok=True)
    SUMMARY.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    write_step_summary(summary)
    print(f"Security result: {result} (mode {mode}, branch {branch or 'n/a'})")
    return summary


def write_step_summary(summary):
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if not target:
        return
    lines = [
        f"## Security result: {summary['result']}",
        f"Branch `{summary['branch']}` runs in **{summary['mode']}** mode.",
        "",
        "| Scanner | Status | Critical | High | Medium | Low | Blocks? |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name, s in summary["scanners"].items():
        c = s["counts"]
        status = s["status"] if s["status"] == "ok" else f"error: {s.get('reason', '')}"
        lines.append(f"| {name} | {status} | {c['critical']} | {c['high']} | {c['medium']} | {c['low']} | {'yes' if s['blocking'] else 'no'} |")
    with open(target, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def enforce():
    if not SUMMARY.is_file():
        print("No summary.json: run 'gate.py summarize' first. Failing.")
        return 1
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    result = summary.get("result")
    if result in ("PASS", "ADVISORY"):
        if result == "ADVISORY":
            print("Findings recorded, but this branch is advisory: passing.")
        return 0
    print(f"Gate result {result}: failing the run.")
    return 1


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "summarize":
        summarize()
        sys.exit(0)
    if command == "enforce":
        sys.exit(enforce())
    print(__doc__)
    sys.exit(2)
