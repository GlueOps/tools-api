# tools-api
This FastAPI app has various utilities to help streamline local development for Platform Engineers that are working on the GlueOps Platform. This tool is not meant for customers or any end users of the GlueOps Platform.

## CLI

The `tools` CLI lets you interact with the API from the command line. Download the latest binary for your platform from [GitHub Releases](https://github.com/GlueOps/tools-api/releases).

```bash
# Authenticate
tools login

# Example: create storage buckets
tools storage-buckets create --captain-domain nonprod.foobar.onglueops.rocks

# See all commands
tools --help
```

The CLI self-updates automatically when the API version changes. See [`cli/`](cli/) for development details.

## API Setup

1. Launch codespace
2. Configure environment variables (see below)
3. Run `devbox run dev` and follow outputted steps to get started.

### Required environment variables:

```bash
AWS_GLUEOPS_ROCKS_ORG_ACCESS_KEY
AWS_GLUEOPS_ROCKS_ORG_SECRET_KEY
HCLOUD_TOKEN
GITHUB_TOKEN
MINIO_S3_ACCESS_KEY_ID
MINIO_S3_SECRET_KEY
HETZNER_STORAGE_REGION=hel1
```
