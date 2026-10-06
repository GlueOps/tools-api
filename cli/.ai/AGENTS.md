# AGENTS.md — CLI

This file provides guidance to AI coding assistants when working with the `tools` CLI.

## Overview

`tools` is a Go CLI that wraps the GlueOps Tools API. It authenticates via Dex device code flow through oauth2-proxy and self-updates when the API version changes.

All Go builds use Docker (`golang:1.24-alpine`, pinned by digest in the Makefile) — no local Go toolchain is required.

## Build

```bash
cd cli

# Build for current platform
make build

# Build for all release platforms (linux/darwin × amd64/arm64)
make build-all

# Regenerate OpenAPI client after API changes
make generate

# Clean build artifacts
make clean
```

## Regenerating the API Client

When the API changes (new endpoints, schema changes, updated descriptions/examples), run:

```bash
cd cli
make generate
```

This does three things:
1. Builds the tools-api Docker image and exports the OpenAPI spec to `openapi.json`
2. Runs `oapi-codegen` (pinned to v2.6.0) via Docker to regenerate `api/generated.go`
3. Copies `openapi.json` to `internal/spec/openapi.json` for embedding

The generated client (`api/generated.go`) and both copies of `openapi.json` are committed to the repo.

## Architecture

### File Structure

```
cli/
├── main.go                         # Entry point
├── go.mod / go.sum                 # Go module (github.com/GlueOps/tools-api/cli)
├── Makefile                        # Docker-based build targets
├── openapi.json                    # Exported OpenAPI spec from FastAPI
├── oapi-codegen.yaml               # oapi-codegen config (generates types + client)
├── api/
│   └── generated.go                # Auto-generated typed client — DO NOT EDIT
├── cmd/
│   ├── root.go                     # Root command, persistent flags, auth/update pre-run
│   ├── client.go                   # Authenticated API client helper + response handler (pretty-prints JSON)
│   ├── version.go                  # tools version
│   ├── login.go                    # tools login (device code flow)
│   ├── logout.go                   # tools logout
│   ├── storage_buckets.go          # tools storage-buckets create
│   ├── aws.go                      # tools aws setup-credentials, aws nuke-account
│   ├── nuke.go                     # tools nuke captain-domain-data
│   ├── github.go                   # tools github reset-org, github workflow-status
│   ├── chisel.go                   # tools chisel create, chisel delete
│   ├── opsgenie.go                 # tools opsgenie create
│   └── captain_manifests.go        # tools captain-manifests generate
└── internal/
    ├── auth/
    │   ├── device_flow.go          # Dex device code flow (issuer: dex.toolshosted.com)
    │   └── token.go                # Token storage/refresh (~/.config/glueops/tools-cli/tokens.json)
    ├── config/
    │   └── config.go               # Config dir management (~/.config/glueops/tools-cli/)
    ├── spec/
    │   ├── spec.go                 # Embedded OpenAPI spec parser (examples, summaries, descriptions)
    │   └── openapi.json            # Embedded copy of OpenAPI spec (go:embed)
    ├── updater/
    │   └── updater.go              # Self-update from GitHub releases when API version changes
    └── version/
        └── version.go              # Build-time injected version vars (ldflags)
```

### Key Design Decisions

- **OpenAPI as single source of truth** — CLI flag descriptions, command summaries, and long descriptions are all read from the embedded `openapi.json` at compile time via `internal/spec`. When API docstrings or schema examples change, `make generate` + rebuild picks them up automatically without editing Go code.
- **Auto-generated API client** — `api/generated.go` is produced by `oapi-codegen` from the OpenAPI spec. Each command file in `cmd/` constructs requests using generated types and calls generated client methods.
- **Auth via PersistentPreRunE** — `root.go` checks for a valid token before every command except `login`, `logout`, `version`, `completion`, `help`, and the root command itself (so `tools --help` works without login). Expired tokens are automatically refreshed.
- **Self-update** — On every invocation, the CLI checks `GET /version` on the API. If the version differs (and isn't a placeholder like `UNKNOWN` or `dev`), it downloads the matching binary from GitHub releases and replaces itself.
- **Config directory** — `~/.config/glueops/tools-cli/` stores `tokens.json`.

### Adding a New Command

1. Add the endpoint to `app/main.py` and schema to `app/schemas/schemas.py`
2. Run `cd cli && make generate` to update the client and spec
3. Create `cli/cmd/<command>.go`:
   - Use `spec.Summary()` and `spec.Description()` for `Short`/`Long`
   - Use `spec.FlagDesc()` for flag descriptions
   - Use `newClient()` from `client.go` to get an authenticated client
   - Use `handleResponse()` to print the response
4. Register the command with `rootCmd` in `init()`

### Key Dependencies

- **`github.com/spf13/cobra`** — CLI framework
- **`github.com/oapi-codegen/runtime`** — Runtime helpers for the generated client

### Auth Details

- Dex issuer: `https://dex.toolshosted.com`
- Client ID: `tools-cli`
- Scopes: `openid email profile offline_access`
- Default API URL: `https://tools.toolshosted.rocks` (overridable via `--api-url`)

## CI/CD

`.github/workflows/cli_release.yaml` builds CLI binaries on every push:
- Cross-compiles for linux/amd64, linux/arm64, darwin/amd64, darwin/arm64 via Docker
- Uploads binaries as workflow artifacts
- Creates a GitHub Release tagged with `github.ref_name` (rolling `main` release for branch pushes, versioned releases for tag pushes)
- Version is injected via ldflags from the git ref
