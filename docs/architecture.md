# Architecture

One Azure VM hosts everything. GitHub never connects in: the self-hosted
runner on the VM polls GitHub for jobs over an outbound HTTPS connection.

| Component | Where it runs | Port (VM localhost) | Role |
| --- | --- | --- | --- |
| GitHub runner | VM, as a system service | none | Runs workflow jobs |
| Gitleaks, Semgrep, Trivy | throw-away containers | none | Produce JSON reports |
| `gate.py` | runner (Python) | none | Summarises reports, applies branch policy |
| DefectDojo | official compose project | 8080 | Stores and de-duplicates findings |
| Receiver | `alerts` compose | 8000 | HTTP in, Kafka out (token protected) |
| Kafka | `alerts` compose | internal | Durable event queue, topics by severity |
| Worker | `alerts` compose | none | Kafka in, Mattermost out, retries, dead-letter |
| Kafka UI | `alerts` compose | 8081 | Inspect topics and consumer lag |
| Mattermost | `alerts` compose | 8065 | Chat channels for alerts |
| Staging | plain container | 3000 | The scanned Juice Shop image |

## Data flow for one push

1. The workflow checks out this repo (full history) and the Juice Shop source.
2. Gitleaks scans this repo's history; Semgrep scans `app/`; Trivy scans the
   Juice Shop image by digest and writes an SBOM.
3. `gate.py summarize` turns the three reports into `reports/summary.json`.
4. `dojo_import.py` re-imports each report into DefectDojo.
5. `publish_events.py` sends one event per scanner plus a status event.
6. The receiver routes them to `security.high`, `security.review` or
   `pipeline.status`; the worker posts each to its Mattermost channel.
7. `gate.py enforce` passes or fails the job.
8. Only if the job passed, the deploy job runs the same image digest as staging.

## Topics and channels

| Kafka topic | Gets | Mattermost channel |
| --- | --- | --- |
| `security.high` | scans with critical or high findings | security-alerts |
| `security.review` | scans with medium or low findings | security-review |
| `pipeline.status` | clean scans, scanner errors, pipeline result | pipeline-status |
| `security.dead-letter` | messages Mattermost refused 3 times | (replayed by hand) |
