#!/usr/bin/env python3
"""Upload scanner reports to DefectDojo with its re-import API.

Re-import keeps one test per scanner and branch, so repeated runs update the
same findings instead of creating duplicates. Products and engagements are
created automatically on first use (auto_create_context).

Environment:
  DOJO_URL       e.g. http://127.0.0.1:8080   (no trailing slash needed)
  DOJO_API_KEY   API v2 key of a DefectDojo user
  DOJO_PRODUCT   product name (default: OWASP Juice Shop)
"""
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

REPORTS = Path(os.environ.get("REPORTS_DIR", "reports"))

# report file -> DefectDojo parser name and a stable test title
UPLOADS = [
    ("gitleaks.json", "Gitleaks Scan", "Secrets (Gitleaks)"),
    ("semgrep.json", "Semgrep JSON Report", "SAST (Semgrep)"),
    ("trivy.json", "Trivy Scan", "Image (Trivy)"),
]


def multipart(fields, file_field, filename, content):
    """Build a multipart/form-data body with the standard library only."""
    boundary = uuid.uuid4().hex
    parts = []
    for key, value in fields.items():
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n".encode()
        )
    parts.append(
        (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; filename=\"{filename}\"\r\n"
         "Content-Type: application/json\r\n\r\n").encode() + content + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def upload(base_url, api_key, fields, path):
    body, content_type = multipart(fields, "file", path.name, path.read_bytes())
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/v2/reimport-scan/",
        data=body,
        method="POST",
        headers={"Authorization": f"Token {api_key}", "Content-Type": content_type},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.status, json.loads(response.read() or b"{}")


def main():
    base_url = os.environ.get("DOJO_URL", "")
    api_key = os.environ.get("DOJO_API_KEY", "")
    if not base_url or not api_key:
        print("DOJO_URL or DOJO_API_KEY not set: skipping DefectDojo upload.")
        return 0

    ref = os.environ.get("GITHUB_REF", "")
    branch = ref.removeprefix("refs/heads/") or "local"
    common = {
        "product_type_name": "Tutorial",
        "product_name": os.environ.get("DOJO_PRODUCT", "OWASP Juice Shop"),
        "engagement_name": f"branch: {branch}",
        "auto_create_context": "true",
        "active": "true",
        "verified": "false",           # scanner output is a candidate until a person triages it
        "close_old_findings": "true",  # a finding gone from the new report is closed
        "branch_tag": branch,
        "commit_hash": os.environ.get("GITHUB_SHA", ""),
        "build_id": os.environ.get("GITHUB_RUN_ID", ""),
    }

    failures = 0
    for filename, scan_type, title in UPLOADS:
        path = REPORTS / filename
        if not path.is_file():
            print(f"{filename}: not found, skipped")
            continue
        fields = dict(common, scan_type=scan_type, test_title=title)
        try:
            status, data = upload(base_url, api_key, fields, path)
            stats = data.get("statistics", {}).get("after", {}).get("total", {})
            print(f"{title}: HTTP {status}, test {data.get('test_id', data.get('test'))}, active total {stats.get('active', 'n/a')}")
        except urllib.error.HTTPError as exc:
            failures += 1
            detail = exc.read()[:300].decode(errors="replace")
            print(f"{title}: upload failed, HTTP {exc.code}: {detail}")
        except (urllib.error.URLError, TimeoutError) as exc:
            failures += 1
            print(f"{title}: DefectDojo not reachable ({exc})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
