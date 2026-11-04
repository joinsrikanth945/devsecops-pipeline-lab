# DevSecOps Pipeline from Scratch: lab files

Companion files for the YouTube series **DevSecOps Pipeline from Scratch** by **SreeKode Labs** (Sreekanth Dara).
One Azure VM, one self-hosted GitHub runner, and a pipeline that scans, gates, records, alerts and deploys, built step by step in 10 chapters.

**New here? Start here (3 minutes):** https://youtu.be/_VwZdpLILKo

## Read this first: why there is no workflow and no runner here

This repository has **no `.github/workflows` folder and no runner, on purpose.**
A self-hosted runner runs code on your own machine. If one is attached to a public repository, strangers can try to run code on it through pull requests.

So you do **not** run anything from this repository. You:

1. Create **your own private** repository.
2. Attach **your own** runner to it (Chapter 3 shows how).
3. Copy the stage file for your chapter, for example `stages/pipeline-ch04.yml`, to `.github/workflows/pipeline.yml` in **your** repository.

## Three safety rules

1. **Never attach a self-hosted runner to a public repository.** Keep your own copy private.
2. **Never reuse anything shown on screen** and never commit secrets. Create your own tokens, keep them in GitHub secrets, and keep `.env` files out of Git.
3. **Juice Shop is vulnerable on purpose.** Never expose it to the internet. Stop (deallocate) the VM when you are not working: a stopped VM does not pay for compute.

## Chapters

| # | Chapter | Video | Tag | Main files |
| --- | --- | --- | --- | --- |
| 1 | Why DevSecOps, and the project tour | https://youtu.be/IDKYHoaV_4s | `ch01` | `docs/architecture.md` |
| 2 | The lab host on Azure | https://youtu.be/gupKcqbS1QU | `ch02` | `host/setup-host.sh` |
| 3 | GitHub repo and a self-hosted runner | https://youtu.be/RnnUcwzE2LQ | `ch03` | `host/install-runner.sh` |
| 4 | Secret scanning with Gitleaks | https://youtu.be/Rwe-htF-m5k | `ch04` | `stages/pipeline-ch04.yml`, `demo/` |
| 5 | Code scanning with Semgrep | https://youtu.be/0RqRLQ2OoUQ | `ch05` | `stages/pipeline-ch05.yml` |
| 6 | Image scanning and SBOM with Trivy | https://youtu.be/NO07gyp3utI | `ch06` | `stages/pipeline-ch06.yml` |
| 7 | Security gates by branch | https://youtu.be/YeCwEcBu8PM | `ch07` | `stages/pipeline-ch07.yml`, `scripts/gate.py`, `tests/` |
| 8 | DefectDojo | https://youtu.be/pjNg2jr-vlA | `ch08` | `stages/pipeline-ch08.yml`, `scripts/dojo_import.py`, `platform/defectdojo/` |
| 9 | Reliable alerts with Kafka and Mattermost | https://youtu.be/glH7Y5EUxEg | `ch09` | `stages/pipeline-ch09.yml`, `platform/alerts/`, `scripts/publish_events.py` |
| 10 | Gated deployment and wrap-up | https://youtu.be/4wC_cmyX3wQ | `ch10` | `stages/pipeline-ch10.yml` |

Playlist: https://www.youtube.com/playlist?list=PLVCW7S-Aw930

## How to follow along

1. Watch the chapter video, then open its note in `docs/chapters/` (for example `ch05.md`): commands, what you should see, and common mistakes.
2. Each tag shows this repository as it stands at the end of that chapter. Copy this repository's address with the green Code button, then:

        git clone ADDRESS_FROM_THE_CODE_BUTTON
        git checkout ch05

3. Replace `OWNER/REPOSITORY` and `YOUR-REPOSITORY` in the notes with your own private repository name.
4. Replace `VM_PUBLIC_IP` with your own VM address. Restrict SSH to your own IP address.

## What you need

- A GitHub account and an Azure account (a pay-as-you-go subscription).
- Basic Git and terminal skills.
- Budget: the VM is the main cost. In the portal the 2-vCPU size (F2as v6) was about $106 a month if left running all month and the 4-vCPU size (F4as v6) about $213. Run it only while you work, deallocate it afterwards, and set an Azure budget alert before you start.

## Folders

| Folder | What is in it |
| --- | --- |
| `stages/` | One pipeline file per chapter (copy one into your own `.github/workflows/`) |
| `scripts/` | The gate, the DefectDojo upload and the alert publisher |
| `platform/` | DefectDojo settings and the alerts stack (receiver, Kafka, worker, Mattermost) |
| `host/` | Scripts that prepare the VM and install the runner |
| `tests/` | Unit tests for the gate and the alerts, with sample scanner reports |
| `demo/` | The Chapter 4 planted-secret demo (fake values only) |
| `docs/` | The architecture map and one note per chapter |

## Important

This is a **learning setup, not a production design**. Harden it before real use. Questions? Comment on the chapter video and say which step you are on.

Licence: MIT.
