# AGENTS.md

This file provides guidance to AI coding assistants when working with code in this repository.

## Project Overview

tools-api is a Go API service (using the Huma framework on Chi router) providing internal REST APIs for GlueOps platform engineers. It manages AWS accounts, cloud storage (MinIO), Hetzner infrastructure (Chisel load balancers), GitHub organization setup, Kubernetes/ArgoCD manifest generation, and Opsgenie alerting.

A companion Go CLI (`cli/`) allows engineers to interact with the API from headless Linux machines. See [`cli/.ai/AGENTS.md`](../cli/.ai/AGENTS.md) for CLI-specific guidance.

## Development Setup

All builds use Docker — no local Go toolchain is required.

```bash
# Build the server
docker build -t tools-api .

# Run the server
docker run --rm -p 8000:8000 tools-api

# Run Go commands via Docker
docker run --rm -v "$(pwd):/app" -w /app golang:1.24-alpine go build ./...
docker run --rm -v "$(pwd):/app" -w /app golang:1.24-alpine go test ./...
```

Required environment variables: `AWS_GLUEOPS_ROCKS_ORG_ACCESS_KEY`, `AWS_GLUEOPS_ROCKS_ORG_SECRET_KEY`, `HCLOUD_TOKEN`, `GITHUB_TOKEN`, `MINIO_S3_ACCESS_KEY_ID`, `MINIO_S3_SECRET_KEY`, `HETZNER_STORAGE_REGION`. Optional: `LOG_LEVEL` (default `INFO`).

Environment variables are NOT required at startup — the app fails lazily when an endpoint is called without the needed env var.

## Build

```bash
docker build -t tools-api .
```

The Dockerfile uses a multi-stage build: `golang:1.24-alpine` for compilation, `alpine:3.21` for runtime. Build args: `VERSION`, `COMMIT_SHA`, `SHORT_SHA`, `BUILD_TIMESTAMP`, `GIT_REF` (injected via ldflags into `internal/version`).

## Architecture

- **`cmd/server/main.go`** — Go API server entry point. Uses Huma framework on Chi router. Defines all API routes, audit logging middleware, custom error handling, graceful shutdown (SIGTERM/SIGINT). Health endpoint (`/health`) and root redirect (`/ → /docs`) are registered directly on Chi (excluded from OpenAPI).
- **`pkg/handlers/`** — HTTP handler functions for each domain: `storage.go`, `aws.go`, `github.go`, `chisel.go`, `opsgenie.go`, `captain.go`, `health.go`, `version.go`.
- **`pkg/types/`** — Shared request/response type definitions (`types.go`). These are the single source of truth for API contracts.
- **`pkg/`** — Business logic modules, one per domain: `storage/`, `aws/`, `github/`, `hetzner/`, `chisel/`, `captain/`, `opsgenie/`.
- **`pkg/util/`** — Utility functions (e.g., `plaintext.go` for plain-text response helpers).
- **`internal/version/`** — Build-time injected version variables (ldflags).
- **`cli/`** — Go CLI binary. See [`cli/.ai/AGENTS.md`](../cli/.ai/AGENTS.md).

### Key Design Decisions

- **Plain-text endpoints** — Five endpoints return `Content-Type: text/plain` (storage buckets, AWS credentials, chisel, opsgenie manifest, captain manifests). These use custom Huma response handling to avoid JSON wrapping.
- **Error responses** — Custom error format `{"status": N, "detail": "..."}` via `huma.NewError` override. Stack traces logged server-side only, never in responses.
- **Graceful shutdown** — Handles SIGTERM/SIGINT with 25-second timeout for in-flight requests.
- **Audit logging** — Middleware logs every request with `X-Forwarded-User` and `X-Forwarded-Email` from oauth2-proxy.

## Key Dependencies

- **`github.com/danielgtaylor/huma/v2`** — API framework (OpenAPI 3.1, validation, docs).
- **`github.com/go-chi/chi/v5`** — HTTP router.
- **`github.com/aws/aws-sdk-go-v2`** — AWS SDK (account credential management via STS/Organizations).
- **`github.com/hetznercloud/hcloud-go/v2`** — Hetzner Cloud API client.
- **`github.com/minio/minio-go/v7`** — S3-compatible storage client.

## CI/CD

- **`.github/workflows/container_image.yaml`** — Runs golangci-lint and govulncheck, then builds and pushes Docker images to GHCR on any push.
- **`.github/workflows/cli_release.yaml`** — Builds CLI binaries on every push, uploads as workflow artifacts, and creates a GitHub Release tagged with `github.ref_name`. Cross-compiles for linux/amd64, linux/arm64, darwin/amd64, darwin/arm64.
