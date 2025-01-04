# tools-api
This FastAPI app has various utilities to help streamline local development for Platform Engineers that are working on the GlueOps Platform. This tool is not meant for customers or any end users of the GlueOps Platform.

## Setup

1. Launch codespace
2. Configure environment variables (see below)
3. Run `devbox run dev` and follow outputted steps to get started.

### Required environment variables:

```bash
AWS_GLUEOPS_ROCKS_ORG_ACCESS_KEY
AWS_GLUEOPS_ROCKS_ORG_SECRET_KEY
AWS_LIGHTSAIL_ACCESS_KEY
AWS_LIGHTSAIL_SECRET_KEY
GITHUB_TOKEN
MINIO_S3_ACCESS_KEY_ID
MINIO_S3_SECRET_KEY
```