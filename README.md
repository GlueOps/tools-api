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
GITHUB_TOKEN
RUSTFS_ENDPOINT=rustfs.glueopshosted.rocks   # host[:port], no scheme
RUSTFS_ACCESS_KEY_ID              # admin creds: used to manage buckets and per-bucket IAM users
RUSTFS_SECRET_KEY
RUSTFS_REGION=us-east-1           # optional, default: us-east-1
RUSTFS_USE_SSL=true               # optional, default: true
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

### Optional: reach Proxmox over Tailscale

When `TS_AUTHKEY` is set, the container's entrypoint (`entrypoint.sh`) joins the tailnet using userspace networking (no `NET_ADMIN` or `/dev/net/tun` needed) and forwards `127.0.0.1:$PROXMOX_PORT` to `$PROXMOX_HOST:$PROXMOX_PORT` over Tailscale (`socat` + `tailscale nc`), where `PROXMOX_HOST` is the Proxmox host's Tailscale IPv4 address. The API is then pointed at `127.0.0.1`; all other traffic (GitHub, AWS, RustFS, Waggle) does not go through Tailscale. Without `TS_AUTHKEY` the container just runs `fastapi run` and uses `PROXMOX_HOST` directly.

```bash
TS_AUTHKEY=                       # OAuth client secret (tskey-client-...) recommended, or a reusable, tagged auth key
PROXMOX_HOST=                     # with TS_AUTHKEY: Tailscale IPv4 of the Proxmox host (100.x.y.z)
TS_HOSTNAME=tools-api             # optional, default shown
TS_EXTRA_ARGS=                    # optional, extra flags for `tailscale up`; required with an OAuth client secret: --advertise-tags=tag:tools-api
PROXMOX_VERIFY_SSL=false          # only with the tunnel: the cert won't match 127.0.0.1, and WireGuard already authenticates the host
```

State is in memory, so every container start logs in again with `TS_AUTHKEY`, and the node is always ephemeral (it is removed from the tailnet when the container stops). Auth keys expire after at most 90 days, after which the next restart fails. An OAuth client secret (with the `auth_keys` scope and ownership of the tag) does not expire, which is why it is the recommended option. With a plain auth key, use a reusable, tagged key and rotate it before it expires.

`PROXMOX_HOST` must be the Proxmox host's Tailscale `100.x` address: any other address is dialed directly instead of over Tailscale, and with `PROXMOX_VERIFY_SSL=false` that connection is unprotected.

The node runs with `--shields-up`, so other tailnet devices cannot connect to the container. The tailnet ACLs are still the real boundary: allow `tag:tools-api` to reach only the Proxmox host on `PROXMOX_PORT`, and grant nothing inbound to it. If `tailscaled`, the forwarder, or the API exits, the container exits so it can be restarted.

## Integration test

`tests/integration/test_storage_buckets.py` creates the storage buckets through the API, fills the loki bucket with data, calls the endpoint again for the same captain domain, and prints how long the recreate took. It checks that the old empty buckets were deleted and that the old loki bucket was kept with a lifecycle rule expiring its data. The API also logs the time the retire step took on its own (`Retired N bucket(s) in Xs`).

Start RustFS and the API with the same `RUSTFS_*` env vars (the test uses them to upload the data), then:

```bash
docker run -d --name rustfs -p 9000:9000 -p 9001:9001 \
  -e RUSTFS_ACCESS_KEY=rustfsadmin -e RUSTFS_SECRET_KEY=rustfsadmin rustfs/rustfs:latest
pipenv install --dev
pytest -s tests/integration
```

```bash
TOOLS_API_URL=http://localhost:8080                          # optional, default shown
STORAGE_TEST_CAPTAIN_DOMAIN=storage-timing-test.example.com  # optional, default shown
STORAGE_TEST_OBJECT_COUNT=100000                             # optional, default shown
STORAGE_TEST_OBJECT_SIZE_KB=16                               # optional, default shown (~1.5 GiB total)
STORAGE_TEST_UPLOAD_WORKERS=32                               # optional, default shown
STORAGE_TEST_UPLOAD_MAX_RETRIES=8                            # optional, retries per object on 5xx
STORAGE_TEST_API_TIMEOUT=3600                                # optional, seconds to wait for each API call
```

The test is skipped when the `RUSTFS_*` env vars are not set.
