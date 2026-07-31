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
            # The PVE node fetches <base>/<image>.qcow2 itself; default to the
            # official Debian cloud images site (needs internet egress from the node).
            download_server_url=os.getenv("PROXMOX_DOWNLOAD_SERVER_URL", "https://cloud.debian.org/images/cloud/trixie/latest"),
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


def _user_data(credentials_for_chisel: str) -> str:
    return f"""#cloud-config
package_update: true
packages:
  - qemu-guest-agent
runcmd:
  - systemctl enable --now qemu-guest-agent
  - curl -fsSL https://get.docker.com -o get-docker.sh && sh get-docker.sh
  - docker run -d --restart always -p 9090:9090 -p 443:443 -p 80:80 docker.io/jpillora/chisel:1 server --reverse --port=9090 --auth='{credentials_for_chisel}'
"""


def _meta_data(vm_name: str) -> str:
    return f"instance-id: {vm_name}\nlocal-hostname: {vm_name}\n"


# Hold strong references so fire-and-forget tasks aren't garbage-collected mid-run.
_background_tasks = set()


def _spawn_background(coro, label: str):
    task = asyncio.create_task(coro)
    _background_tasks.add(task)

    def _done(t):
        _background_tasks.discard(t)
        if not t.cancelled() and t.exception():
            logger.error(f"Background task {label!r} failed: {t.exception()!r}")

    task.add_done_callback(_done)


async def _finalize_cleanup(captain_domain: str, vms: list):
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
    logger.info(f"Background cloud-init/ISO cleanup complete for captain_domain: {captain_domain}")


async def _create_vm_with_vmid_retry(px: ProxmoxClient, node: str, vm_name: str, vcpus: int, memory_mb: int, image: str, iso_filename: str, tags: list) -> str:
    """/cluster/nextid is non-reserving, so a concurrent creator can claim the same
    vmid between our fetch and create. Retry on the resulting conflict."""
    for attempt in range(3):
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
        except httpx.HTTPStatusError as e:
            if attempt < 2 and "already exist" in e.response.text:
                logger.warning(f"vmid {vmid} was taken by a concurrent create, retrying")
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
        image = os.getenv("K3D_LB_VM_IMAGE", "debian-13-generic-amd64")

        datacenter = await waggle.get_datacenter_by_name(os.environ["WAGGLE_DATACENTER_NAME"])
        slot = await waggle.get_slot_by_name(os.environ["WAGGLE_SLOT_NAME"])

        # Idempotent replace: drop any existing nodes + pool for this captain_domain
        await _delete_nodes_locked(captain_domain)

        pool = await waggle.create_pool(datacenter["id"], slot["id"], _pool_name(captain_domain), node_count)
        try:
            placements = await waggle.get_pool_placements(pool["id"])
            if len(placements) != node_count:
                raise RuntimeError(f"Waggle returned {len(placements)} placements for pool {pool['id']}, expected {node_count}")

            vms = []
            cached_nodes = set()
            for suffix, placement in zip(suffixes, placements):
                node = placement["hypervisor_name"]
                vm_name = f"{captain_domain}-{suffix}"
                logger.info(f"Creating k3d-lb node {vm_name} on hypervisor {node} (placement {placement['id']})")
                if node not in cached_nodes:
                    await px.ensure_image_cached(node, image)
                    cached_nodes.add(node)
                iso_bytes = build_cloudinit_iso(
                    _user_data(credentials_for_chisel).encode(),
                    _meta_data(vm_name).encode(),
                )
                iso_filename = await px.upload_iso(node, f"{vm_name}-cloudinit.iso", iso_bytes)
                vmid = await _create_vm_with_vmid_retry(
                    px,
                    node=node,
                    vm_name=vm_name,
                    vcpus=slot["vcpu"],
                    memory_mb=slot["ram_gb"] * 1024,
                    image=image,
                    iso_filename=iso_filename,
                    tags=[CREATOR_TAG, MANAGED_TAG, captain_domain],
                )
                await px.resize_disk(node, vmid, slot["disk_gb"])
                await px.start_vm(node, vmid)
                await waggle.set_placement_vmid(placement["id"], int(vmid))
                vms.append({"vm_name": vm_name, "node": node, "vmid": vmid, "iso_filename": iso_filename})

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
            _spawn_background(_finalize_cleanup(captain_domain, vms), f"k3d-lb cleanup for {captain_domain}")
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

    vms = await px.list_vms_by_tags([CREATOR_TAG, MANAGED_TAG, captain_domain])
    failures = []
    for vm in vms:
        try:
            logger.info(f"Deleting k3d-lb node {vm['name']} (vmid {vm['vmid']} on {vm['node']})")
            await px.delete_vm(vm["node"], vm["vmid"])
        except Exception as e:
            logger.error(f"Failed to delete k3d-lb node {vm['name']} (vmid {vm['vmid']} on {vm['node']}): {e}")
            failures.append(f"{vm['name']} (vmid {vm['vmid']} on {vm['node']}): {e}")

    try:
        deleted = await px.delete_isos_matching(rf"{re.escape(captain_domain)}-exit\d+-cloudinit\.iso")
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
