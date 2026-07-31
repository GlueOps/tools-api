import asyncio
import os
import re

import httpx
from fastapi import HTTPException
from glueops.proxmox import ProxmoxClient, build_cloudinit_iso
from glueops.waggle import WaggleClient
import util.chisel
import glueops.setup_logging

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logger = glueops.setup_logging.configure(level=LOG_LEVEL)

POOL_NAME_PREFIX = "k3d-lb-"

# Tags applied to every VM we create; deletion requires all of them (plus the
# captain_domain tag) so we can never touch VMs another tool created.
MANAGED_TAG = "glueops-k3d-lb"
CREATOR_TAG = "tools-api"

# Cached image volumes we own; the checksum suffix makes each release distinct,
# so stale ones are pruned by this prefix after a successful create.
IMAGE_PREFIX = "tools-api-k3d-lb-"

# Serializes create/delete per captain_domain so a concurrent POST/DELETE for the
# same domain can't interleave (single-worker FastAPI, so an asyncio.Lock suffices).
_domain_locks = {}

_proxmox_client = None
_waggle_client = None


def _proxmox() -> ProxmoxClient:
    global _proxmox_client
    if _proxmox_client is None:
        _proxmox_client = ProxmoxClient(
            host=os.environ["PROXMOX_HOST"],
            token_id=os.environ["PROXMOX_TOKEN_ID"],
            token_secret=os.environ["PROXMOX_TOKEN_SECRET"],
            storage=os.environ["PROXMOX_STORAGE"],
            port=int(os.getenv("PROXMOX_PORT", "8006")),
            verify_ssl=os.getenv("PROXMOX_VERIFY_SSL", "true").lower() not in ("false", "0", "no"),
            # The PVE node fetches <base>/<image>.qcow2 itself (needs egress).
            # Must stay paired with K3D_LB_VM_IMAGE's default: the prebuilt image
            # only exists on the proxmox-images-chisel releases, and its
            # SHA256SUMS there is what enables checksum verification.
            download_server_url=os.getenv(
                "PROXMOX_DOWNLOAD_SERVER_URL",
                "https://github.com/GlueOps/proxmox-images-chisel/releases/latest/download",
            ),
            download_timeout=float(os.getenv("PROXMOX_IMAGE_DOWNLOAD_TIMEOUT", "1800")),
        )
    return _proxmox_client


def _waggle() -> WaggleClient:
    global _waggle_client
    if _waggle_client is None:
        _waggle_client = WaggleClient(os.environ["WAGGLE_API_URL"], os.environ["WAGGLE_API_KEY"])
    return _waggle_client


def _domain_lock(captain_domain: str) -> asyncio.Lock:
    return _domain_locks.setdefault(captain_domain, asyncio.Lock())


def _pool_name(captain_domain: str) -> str:
    return f"{POOL_NAME_PREFIX}{captain_domain}"


def _iso_filename(vm_name: str) -> str:
    # tools-api- prefix marks the ISO as ours (storage volumes can't carry tags,
    # so the filename is the only identity an ISO has)
    return f"{CREATOR_TAG}-{vm_name}-cloudinit.iso"


def _user_data(credentials_for_chisel: str) -> str:
    # K3D_LB_VM_IMAGE (GlueOps/proxmox-images-chisel) bakes in qemu-guest-agent,
    # docker, and the chisel image, so the fast path here is just `docker run`:
    # no package_update/packages stage, which would otherwise cost an apt-get
    # update on every boot even when nothing needs installing.
    #
    # The `command -v` guards only fire on an image lacking them (e.g. a stock
    # Debian cloud image) — that still works, just slower. Installing docker on
    # an image that already has docker.io breaks the boot: get.docker.com pulls
    # docker-ce over it, dpkg fails on the conflict, and cloud-init abandons the
    # rest of runcmd before chisel ever starts.
    return f"""#cloud-config
runcmd:
  - command -v qemu-ga >/dev/null || (apt-get update && apt-get install -y qemu-guest-agent)
  - systemctl enable --now qemu-guest-agent
  - command -v docker >/dev/null || (curl -fsSL https://get.docker.com -o get-docker.sh && sh get-docker.sh)
  - docker run -d --restart always -p 9090:9090 -p 443:443 -p 80:80 docker.io/jpillora/chisel:1 server --reverse --port=9090 --auth='{credentials_for_chisel}'
"""


def _meta_data(vm_name: str) -> str:
    return f"instance-id: {vm_name}\nlocal-hostname: {vm_name}\n"


async def _fetch_expected_sha256(download_server_url: str, filename: str):
    """Look up filename's digest in the download server's SHA256SUMS manifest.

    Returns None when no manifest is published (e.g. the plain Debian mirror
    default) so image caching degrades to the previous unverified behavior
    rather than failing.
    """
    url = f"{download_server_url.rstrip('/')}/SHA256SUMS"
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as c:
            r = await c.get(url)
            if r.status_code >= 400:
                logger.info(f"No SHA256SUMS at {url} ({r.status_code}); skipping image checksum verification")
                return None
            for line in r.text.splitlines():
                parts = line.split()
                if len(parts) == 2 and parts[1].lstrip("*") == filename:
                    logger.info(f"Expected {filename} sha256: {parts[0]}")
                    return parts[0]
    except httpx.HTTPError as e:
        logger.warning(f"Could not fetch {url}: {e}; skipping image checksum verification")
        return None
    logger.warning(f"{filename} not listed in {url}; skipping image checksum verification")
    return None


# One background cleanup task per captain_domain (strong refs so they aren't
# garbage-collected mid-run). A newer create/delete for the same domain must
# cancel the previous run's task: it holds stale (vmid, iso_filename) pairs,
# and the deterministic ISO filenames may meanwhile belong to the successor.
_cleanup_tasks = {}


def _spawn_cleanup(captain_domain: str, coro):
    task = asyncio.create_task(coro)
    _cleanup_tasks[captain_domain] = task

    def _done(t):
        if _cleanup_tasks.get(captain_domain) is t:
            del _cleanup_tasks[captain_domain]
        if not t.cancelled() and t.exception():
            logger.error(f"Background cleanup for {captain_domain!r} failed: {t.exception()!r}")

    task.add_done_callback(_done)


async def _cancel_stale_cleanup(captain_domain: str):
    """Called under the domain lock before any create/delete touches VMs/ISOs."""
    task = _cleanup_tasks.get(captain_domain)
    if task is None or task.done():
        return
    logger.info(f"Cancelling superseded background cleanup for {captain_domain}")
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.warning(f"Superseded cleanup for {captain_domain} raised during cancel: {e}")


async def _finalize_cleanup(captain_domain: str, vms: list, cached_image=None):
    """Wait for cloud-init to finish, then eject and delete each cloud-init ISO.

    Runs after the create response has been returned; deleting the ISO while
    cloud-init is still reading it would break provisioning, hence the wait.
    """
    px = _proxmox()

    async def one(vm):
        try:
            await px.wait_for_cloud_init(vm["node"], vm["vmid"])
        except Exception as e:
            logger.warning(f"Cloud-init wait failed for {vm['vm_name']} (vmid {vm['vmid']}): {e}; ejecting ISO anyway")
        await px.eject_and_delete_iso(vm["node"], vm["vmid"], vm["iso_filename"])

    await asyncio.gather(*(one(vm) for vm in vms))

    # Every image release leaves the previous checksum-keyed volume cached on
    # each node (~700MB). Prune here rather than in the create path: by now our
    # own imports are done, and a concurrent create for another captain_domain
    # would be importing the current image, which is the one we keep.
    if cached_image:
        try:
            pruned = await px.prune_import_images(rf"{re.escape(IMAGE_PREFIX)}.*\.qcow2", keep=cached_image)
            if pruned:
                logger.info(f"Pruned {pruned} stale k3d-lb image(s) from the import cache")
        except Exception as e:
            logger.warning(f"Stale image prune failed: {e}")

    logger.info(f"Background cloud-init/ISO cleanup complete for captain_domain: {captain_domain}")


def _is_vmid_conflict(e: Exception) -> bool:
    """Proxmox reports a vmid collision two ways depending on when the loser
    loses: 'config file already exists' (pre-check) or
    'close (rename) atomic file ... failed: File exists' (tight race at the
    atomic rename). Both mean the same thing: someone else claimed the vmid."""
    if not isinstance(e, httpx.HTTPStatusError):
        return False
    return "already exist" in e.response.text or "File exists" in e.response.text


def _is_transient_lock_timeout(e: Exception) -> bool:
    """Parallel creates on one node/storage can hit pmxcfs/flock contention:
    'cfs-lock ... got lock request timeout' / \"can't lock file ... got timeout\".
    These surface as HTTP errors from the synchronous part of the create call,
    or as RuntimeError('Proxmox task failed: ...') via poll_task when the lock
    is taken inside the worker. Both are transient — retrying is correct."""
    if isinstance(e, httpx.HTTPStatusError):
        text = e.response.text
    elif isinstance(e, RuntimeError):
        text = str(e)
    else:
        return False
    return "got lock request timeout" in text or "- got timeout" in text


async def _create_vm_with_vmid_retry(px: ProxmoxClient, node: str, vm_name: str, vcpus: int, memory_mb: int, image: str, iso_filename: str, tags: list, attempts: int = 3) -> str:
    """/cluster/nextid is non-reserving, so concurrent creators (our own parallel
    builds, or anything external) can claim the same vmid between our fetch and
    create. The collision fails clean at config-create time (nothing is left
    behind), so retry immediately: by the time the loser sees the error the
    winner's config already exists, so the refetched nextid has moved on. Lock
    timeouts are self-rate-limited (PVE waits ~10s internally before returning
    them), so they retry immediately too."""
    for attempt in range(attempts):
        vmid = await px.get_next_vmid()
        try:
            await px.create_vm(
                node=node,
                vmid=vmid,
                vm_name=vm_name,
                vcpus=vcpus,
                memory_mb=memory_mb,
                image=image,
                iso_filename=iso_filename,
                tags=tags,
                bridge=os.getenv("PROXMOX_BRIDGE", "vmbr_public"),
                vlan_tag=os.getenv("PROXMOX_VLAN_TAG") or None,
            )
            return vmid
        except (httpx.HTTPStatusError, RuntimeError) as e:
            if attempt < attempts - 1 and (_is_vmid_conflict(e) or _is_transient_lock_timeout(e)):
                reason = "was taken by a concurrent create" if _is_vmid_conflict(e) else "hit a transient Proxmox lock timeout"
                logger.warning(f"vmid {vmid} {reason}, retrying {vm_name} immediately")
                continue
            raise


async def create_nodes(request) -> str:
    # Lowercase up front: Proxmox lowercases tags on write, so every derived name
    # (tags, VM names, ISO filenames, pool name) must agree for delete to find them.
    captain_domain = request.captain_domain.strip().lower()
    node_count = request.node_count
    px = _proxmox()
    waggle = _waggle()
    async with _domain_lock(captain_domain):
        logger.info(f"Starting k3d-lb node creation for captain_domain: {captain_domain}")

        credentials_for_chisel = util.chisel.generate_credentials()
        suffixes = util.chisel.get_suffixes(node_count)
        image = os.getenv("K3D_LB_VM_IMAGE", "tools-api-k3d-lb-chisel-debian-13-amd64")
        checksum = await _fetch_expected_sha256(px.download_server_url, f"{image}.qcow2")
        # Cache under a checksum-derived name so a node re-downloads when the
        # release changes instead of reusing whatever it first cached forever.
        cache_name = f"{image}-{checksum[:12]}" if checksum else image

        datacenter = await waggle.get_datacenter_by_name(os.environ["WAGGLE_DATACENTER_NAME"])
        slot = await waggle.get_slot_by_name(os.environ["WAGGLE_SLOT_NAME"])

        # Idempotent replace: drop any existing nodes + pool for this captain_domain
        await _delete_nodes_locked(captain_domain)

        pool = await waggle.create_pool(datacenter["id"], slot["id"], _pool_name(captain_domain), node_count)
        try:
            placements = await waggle.get_pool_placements(pool["id"])
            if len(placements) != node_count:
                raise RuntimeError(f"Waggle returned {len(placements)} placements for pool {pool['id']}, expected {node_count}")

            # Build all VMs concurrently. vmid collisions between our own builds
            # (or external creators) fail clean at config-create time and are
            # retried with backoff inside _create_vm_with_vmid_retry, so no lock
            # is needed. The image-cache step is deduped per node via a shared
            # task that every build on that node awaits.
            cache_tasks = {}
            for placement in placements:
                node = placement["hypervisor_name"]
                if node not in cache_tasks:
                    cache_tasks[node] = asyncio.create_task(
                        px.ensure_image_cached(node, image, checksum=checksum, cache_name=cache_name)
                    )
            create_attempts = 3 + 2 * node_count

            async def build(suffix, placement) -> dict:
                node = placement["hypervisor_name"]
                vm_name = f"{captain_domain}-{suffix}"
                logger.info(f"Creating k3d-lb node {vm_name} on hypervisor {node} (placement {placement['id']})")
                cached_image = await cache_tasks[node]
                iso_bytes = build_cloudinit_iso(
                    _user_data(credentials_for_chisel).encode(),
                    _meta_data(vm_name).encode(),
                )
                iso_filename = await px.upload_iso(node, _iso_filename(vm_name), iso_bytes)
                vmid = await _create_vm_with_vmid_retry(
                    px,
                    node=node,
                    vm_name=vm_name,
                    vcpus=slot["vcpu"],
                    memory_mb=slot["ram_gb"] * 1024,
                    image=cached_image,
                    iso_filename=iso_filename,
                    tags=[CREATOR_TAG, MANAGED_TAG, captain_domain],
                    attempts=create_attempts,
                )
                await px.resize_disk(node, vmid, slot["disk_gb"])
                await px.start_vm(node, vmid)
                await waggle.set_placement_vmid(placement["id"], int(vmid))
                return {"vm_name": vm_name, "node": node, "vmid": vmid, "iso_filename": iso_filename}

            build_results = await asyncio.gather(
                *(build(suffix, placement) for suffix, placement in zip(suffixes, placements)),
                return_exceptions=True,
            )
            build_failures = [
                f"{captain_domain}-{suffix}: {r}"
                for suffix, r in zip(suffixes, build_results) if isinstance(r, BaseException)
            ]
            if build_failures:
                raise RuntimeError(f"VM build failed for {len(build_failures)}/{len(placements)} node(s): " + "; ".join(build_failures))
            vms = list(build_results)

            # Return as soon as every VM's IP is known: the guest agent comes up
            # during cloud-init's package phase, well before the docker install
            # finishes, and the chisel operator retries until the server is
            # reachable — same semantics as the Hetzner endpoint, which returns
            # before its VMs have even booted. get_vm_ipv4 polls through
            # agent-not-yet-running errors, so it alone gates on agent + DHCP.
            results = await asyncio.gather(
                *(px.get_vm_ipv4(vm["node"], vm["vmid"], timeout=300) for vm in vms),
                return_exceptions=True,
            )
            failures = [
                f"{vm['vm_name']} (vmid {vm['vmid']}): {r}"
                for vm, r in zip(vms, results) if isinstance(r, BaseException)
            ]
            if failures:
                raise RuntimeError(f"IP discovery failed for {len(failures)}/{len(vms)} node(s): " + "; ".join(failures))
            ip_addresses = {vm["vm_name"]: ip for vm, ip in zip(vms, results)}
            logger.info(f"All k3d-lb nodes created successfully. IP addresses: {ip_addresses}")

            # Cloud-init wait + ISO eject/delete happen in the background so the
            # response isn't gated on the docker install. If this task dies, the
            # orphan-ISO sweep in delete_nodes cleans up on the next POST/DELETE.
            _spawn_cleanup(captain_domain, _finalize_cleanup(captain_domain, vms, cache_name))
        except Exception as e:
            logger.error(f"Error creating k3d-lb nodes for {captain_domain}: {str(e)}")
            raise HTTPException(status_code=500, detail=(
                f"Error creating k3d-lb nodes for {captain_domain}: {e}. "
                "Partially created VMs are tagged and the Waggle pool is named deterministically; "
                "re-run POST /v1/k3d-lb-nodes to replace them, or DELETE /v1/k3d-lb-nodes to clean up."
            )) from e

        return util.chisel.create_chisel_yaml(captain_domain, credentials_for_chisel, ip_addresses, suffixes)


async def delete_nodes(captain_domain: str):
    captain_domain = captain_domain.strip().lower()
    async with _domain_lock(captain_domain):
        await _delete_nodes_locked(captain_domain)


async def _delete_nodes_locked(captain_domain: str):
    logger.info(f"Starting deletion of existing k3d-lb nodes for captain_domain: {captain_domain}")
    px = _proxmox()
    waggle = _waggle()

    # A previous run's background cleanup may still be polling stale vmids and
    # would otherwise delete ISOs by (reused) filename after we recreate them.
    await _cancel_stale_cleanup(captain_domain)

    vms = await px.list_vms_by_tags([CREATOR_TAG, MANAGED_TAG, captain_domain])

    async def delete_one(vm):
        logger.info(f"Deleting k3d-lb node {vm['name']} (vmid {vm['vmid']} on {vm['node']})")
        for attempt in range(3):
            try:
                await px.delete_vm(vm["node"], vm["vmid"])
                return
            except Exception as e:
                # Concurrent destroys on one node can hit pmxcfs/flock contention;
                # PVE already waited internally, so retry straight away.
                if attempt < 2 and _is_transient_lock_timeout(e):
                    logger.warning(f"Delete of {vm['name']} hit a transient Proxmox lock timeout, retrying")
                    continue
                raise

    # Delete all VMs concurrently — sequential deletes cost the full stop+destroy
    # task round-trip per VM, which dominates the request for a full-width pool.
    results = await asyncio.gather(*(delete_one(vm) for vm in vms), return_exceptions=True)
    failures = []
    for vm, r in zip(vms, results):
        if isinstance(r, BaseException):
            logger.error(f"Failed to delete k3d-lb node {vm['name']} (vmid {vm['vmid']} on {vm['node']}): {r}")
            failures.append(f"{vm['name']} (vmid {vm['vmid']} on {vm['node']}): {r}")

    try:
        # The library skips any ISO still referenced by a VM config.
        deleted = await px.delete_isos_matching(rf"{CREATOR_TAG}-{re.escape(captain_domain)}-exit\d+-cloudinit\.iso")
        if deleted:
            logger.info(f"Deleted {deleted} orphaned cloud-init ISO(s) for {captain_domain}")
    except Exception as e:
        logger.error(f"Orphaned ISO sweep failed for {captain_domain}: {e}")

    if failures:
        # Keep the Waggle pool: the surviving VMs still consume real capacity, so
        # releasing their placements would let Waggle over-book the hypervisors.
        raise RuntimeError(
            f"Deleted {len(vms) - len(failures)} of {len(vms)} k3d-lb VM(s) for {captain_domain}; failed: "
            + "; ".join(failures)
            + ". The Waggle pool was kept so capacity stays accounted; re-run DELETE /v1/k3d-lb-nodes after resolving."
        )

    pools = await waggle.find_pools_by_name(_pool_name(captain_domain))
    for pool in pools:
        await waggle.delete_pool(pool["id"])

    logger.info(f"Completed deletion of {len(vms)} k3d-lb node(s) and {len(pools)} Waggle pool(s) for captain_domain: {captain_domain}")
