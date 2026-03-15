# AGENTS.md

This file provides guidance to AI coding assistants when working with code in this repository.

## Project Overview

tools-api is a FastAPI service providing internal REST APIs for GlueOps platform engineers. It manages AWS accounts, cloud storage (MinIO), Hetzner infrastructure (Chisel load balancers), GitHub organization setup, Kubernetes/ArgoCD manifest generation, and Opsgenie alerting.

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
- **`app/schemas/schemas.py`** — Pydantic request/response models for all endpoints.
- **`app/util/`** — Business logic modules, one per domain: `storage.py` (MinIO), `github.py`, `hetzner.py`, `aws_setup_test_account_credentials.py`, `chisel.py`, `captain_manifests.py`, `opsgenie.py`.
- **`app/templates/captain_manifests/`** — Jinja2 templates (`.yaml.j2`) for generating Kubernetes manifests (Namespace, AppProject, ApplicationSet).

All routes are defined directly in `main.py` (no router separation). Each route delegates to a corresponding util module.

GitHub workflow endpoints (`github.py`) dispatch workflows via the GitHub API and poll for the resulting run ID. They return JSON with `status_code`, `all_jobs_url`, `run_id`, and `run_url`. A separate `/v1/github/workflow-run-status` endpoint accepts any GitHub Actions run URL and returns its current status. All GitHub API calls use a centralized `_get_headers()` with the `X-GitHub-Api-Version` header.

## Key Dependencies

- **`glueops-helpers`** — Internal library (installed from GitHub) providing `setup_logging` and shared utilities.
- **`minio`** — S3-compatible storage client.
- **`boto3`** — AWS SDK (account credential management via STS/Organizations).
- **`hcloud`** — Hetzner Cloud API client (Chisel node provisioning).

## CI/CD

GitHub Actions workflow (`.github/workflows/container_image.yaml`) builds and pushes Docker images to GHCR on any push.
