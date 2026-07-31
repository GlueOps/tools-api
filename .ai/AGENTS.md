# AGENTS.md

This file provides guidance to AI coding assistants when working with code in this repository.

## Project Overview

tools-api is a FastAPI service providing internal REST APIs for GlueOps platform engineers. It manages AWS accounts, cloud storage (MinIO), Hetzner infrastructure (Chisel load balancers), GitHub organization setup, Kubernetes/ArgoCD manifest generation, and alerting integrations (Opsgenie, incident.io).

A companion Go CLI (`cli/`) allows engineers to interact with the API from headless Linux machines. See [`cli/.ai/AGENTS.md`](../cli/.ai/AGENTS.md) for CLI-specific guidance.

## Development Setup

```bash
# Enter development shell (launches pipenv shell via devbox)
devbox run dev

# Install dependencies
pipenv install

# Run dev server (hot reload)
fastapi dev

# Run production server
fastapi run
```

Required environment variables: `AWS_GLUEOPS_ROCKS_ORG_ACCESS_KEY`, `AWS_GLUEOPS_ROCKS_ORG_SECRET_KEY`, `HCLOUD_TOKEN`, `GITHUB_TOKEN`, `MINIO_S3_ACCESS_KEY_ID`, `MINIO_S3_SECRET_KEY`, `HETZNER_STORAGE_REGION=hel1`.

## Build

```bash
docker build -t tools-api .
```

The Dockerfile uses `python:3.14-slim` as base, installs dependencies via pipenv (`--system`), and accepts build args: `VERSION`, `COMMIT_SHA`, `SHORT_SHA`, `BUILD_TIMESTAMP`, `GIT_REF`. Devbox is used for local development only (Python 3.13 via nixpkgs), not in container builds.

## Architecture

- **`app/main.py`** — FastAPI app entry point. Defines all API routes, global exception handler, health/version endpoints. Routes redirect `/` to `/docs`.
- **`app/schemas/schemas.py`** — Pydantic request/response models for all endpoints (including `VersionResponse` for `/version`). Examples and descriptions defined here are the single source of truth — the CLI reads them from the embedded OpenAPI spec at compile time.
- **`app/util/`** — Business logic modules, one per domain: `storage.py` (MinIO), `github.py`, `hetzner.py`, `aws_setup_test_account_credentials.py`, `chisel.py`, `k3d_lb.py`, `captain_manifests.py`, `opsgenie.py`, `incidentio.py`. The alerting modules (`opsgenie.py`, `incidentio.py`) follow the same pattern: a single `create_<x>alerts_manifest(request)` function returning an ArgoCD Application YAML as a plain f-string template. New alerting integrations should follow the same shape.
- **`app/templates/captain_manifests/`** — Jinja2 templates (`.yaml.j2`) for generating Kubernetes manifests (Namespace, AppProject, ApplicationSet).
- **`cli/`** — Go CLI binary. See [`cli/.ai/AGENTS.md`](../cli/.ai/AGENTS.md).

All routes are defined directly in `main.py` (no router separation). Each route delegates to a corresponding util module.

GitHub workflow endpoints (`github.py`) dispatch workflows via the GitHub API and poll for the resulting run ID. They return JSON with `status_code`, `all_jobs_url`, `run_id`, and `run_url`. A separate `/v1/github/workflow-run-status` endpoint accepts any GitHub Actions run URL and returns its current status. All GitHub API calls use a centralized `_get_headers()` with the `X-GitHub-Api-Version` header.

The `/v1/k3d-lb-nodes` endpoints (`k3d_lb.py`) are the Proxmox-backed equivalent of `/v1/chisel` (Hetzner). Flow: Waggle (placement oracle) is consulted first — a pool named `k3d-lb-<captain_domain>` is created against a pre-existing datacenter and slot, which yields placements (one hypervisor per VM). The VMs are then created via the Proxmox REST API: cached debian-13 qcow2 import, cloud-init NoCloud ISO (docker + chisel server), guest-agent-based IP discovery, and each Proxmox `vmid` is backfilled onto its Waggle placement. The API clients (`ProxmoxClient`, `WaggleClient`) live in the shared `glueops-helpers` library (v0.7.0+); `k3d_lb.py` constructs them from env vars and keeps only the orchestration, tag constants, and pool naming. VMs are tagged `tools-api;glueops-k3d-lb;<captain_domain>` in Proxmox (captain_domain is lowercased at the entry points because Proxmox lowercases tags); deletion is driven by those tags (all three required) plus removal of the Waggle pool, and also sweeps orphaned cloud-init ISOs. The create endpoint reuses `chisel.py` for credentials/suffixes/manifest generation; delete is tag/pool-driven. Requires Proxmox VE 8.4+ (qcow2 via the `import` content type of download-url). See README for the `WAGGLE_*` / `PROXMOX_*` env vars.

## Key Dependencies

- **`glueops-helpers`** — Internal library (installed from GitHub) providing `setup_logging`, `ProxmoxClient`, `WaggleClient`, and shared utilities.
- **`minio`** — S3-compatible storage client.
- **`boto3`** — AWS SDK (account credential management via STS/Organizations).
- **`hcloud`** — Hetzner Cloud API client (Chisel node provisioning).
- **`httpx`** — Async HTTP client (also used by the glueops-helpers Proxmox/Waggle clients).

## CI/CD

- **`.github/workflows/container_image.yaml`** — Builds and pushes Docker images to GHCR on any push.
- **`.github/workflows/cli_release.yaml`** — Builds CLI binaries on every push, uploads as workflow artifacts, and creates a GitHub Release tagged with `github.ref_name`. Cross-compiles for linux/amd64, linux/arm64, darwin/amd64, darwin/arm64.
