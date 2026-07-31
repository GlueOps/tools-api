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

### Required for `/v1/k3d-lb-nodes` (Chisel nodes on Proxmox via Waggle):

```bash
# Waggle (placement oracle) — datacenter and slot must already exist in Waggle
WAGGLE_API_URL=                   # base URL of the Waggle server (with or without /api/v1)
WAGGLE_API_KEY=                   # org API key (wgl_...)
WAGGLE_DATACENTER_NAME=           # name of the pre-configured datacenter
WAGGLE_SLOT_NAME=                 # name of the pre-configured slot (VM size)

# Proxmox (VM provisioning)
PROXMOX_HOST=
PROXMOX_PORT=8006                 # optional, default: 8006
PROXMOX_TOKEN_ID=                 # e.g. automation@pve!tools-api
PROXMOX_TOKEN_SECRET=
PROXMOX_STORAGE=                  # storage for VM disks, cloud-init ISOs, and cached images
PROXMOX_BRIDGE=vmbr_public        # optional, default: vmbr_public (the public bridge)
PROXMOX_VLAN_TAG=                 # optional, omit for no VLAN tag (untagged on the bridge)
PROXMOX_VERIFY_SSL=true           # optional, default: true
PROXMOX_DOWNLOAD_SERVER_URL=https://github.com/GlueOps/proxmox-images-chisel/releases/latest/download
                                  # base URL hosting <image>.qcow2 (and optionally SHA256SUMS, which is
                                  #  used to verify the download and to key the per-node image cache)
                                  # (the PVE node downloads <base>/<image>.qcow2 itself, so it needs
                                  #  internet egress; point at an internal mirror to avoid that)
PROXMOX_IMAGE_DOWNLOAD_TIMEOUT=1800  # optional, seconds to wait for image downloads (default: 1800)
K3D_LB_VM_IMAGE=tools-api-k3d-lb-chisel-debian-13-amd64  # optional, default shown
```
