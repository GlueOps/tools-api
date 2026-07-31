import asyncio
import os

import httpx
from fastapi import HTTPException
import util.chisel
from util import proxmox, waggle
import glueops.setup_logging

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logger = glueops.setup_logging.configure(level=LOG_LEVEL)

POOL_NAME_PREFIX = "k3d-lb-"

# Serializes create/delete per captain_domain so a concurrent POST/DELETE for the
# same domain can't interleave (single-worker FastAPI, so an asyncio.Lock suffices).
_domain_locks = {}


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


async def _create_vm_with_vmid_retry(node: str, vm_name: str, vcpus: int, memory_mb: int, image: str, iso_filename: str, tags: list) -> str:
    """/cluster/nextid is non-reserving, so a concurrent creator can claim the same
    vmid between our fetch and create. Retry on the resulting conflict."""
    for attempt in range(3):
        vmid = await proxmox.get_next_vmid()
        try:
            await proxmox.create_vm(
                node=node,
                vmid=vmid,
                vm_name=vm_name,
                vcpus=vcpus,
                memory_mb=memory_mb,
                image=image,
                iso_filename=iso_filename,
                tags=tags,
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
                    await proxmox.ensure_image_cached(node, image)
                    cached_nodes.add(node)
                iso_bytes = proxmox.build_cloudinit_iso(
                    _user_data(credentials_for_chisel).encode(),
                    _meta_data(vm_name).encode(),
                )
                iso_filename = await proxmox.upload_iso(node, vm_name, iso_bytes)
                vmid = await _create_vm_with_vmid_retry(
                    node=node,
                    vm_name=vm_name,
                    vcpus=slot["vcpu"],
                    memory_mb=slot["ram_gb"] * 1024,
                    image=image,
                    iso_filename=iso_filename,
                    tags=[proxmox.CREATOR_TAG, proxmox.MANAGED_TAG, captain_domain],
                )
                await proxmox.resize_disk(node, vmid, slot["disk_gb"])
                await proxmox.start_vm(node, vmid)
                await waggle.set_placement_vmid(placement["id"], int(vmid))
                vms.append({"vm_name": vm_name, "node": node, "vmid": vmid, "iso_filename": iso_filename})

            # Boot/cloud-init/IP discovery runs concurrently across all nodes.
            async def finalize(vm) -> str:
                try:
                    await proxmox.wait_for_cloud_init(vm["node"], vm["vmid"])
                    return await proxmox.get_vm_ipv4(vm["node"], vm["vmid"])
                finally:
                    await proxmox.eject_and_delete_iso(vm["node"], vm["vmid"], vm["iso_filename"])

            # return_exceptions=True (not TaskGroup): every finalize runs to its bounded
            # completion, so healthy VMs still clean up their ISOs and no task outlives
            # the request; errors are aggregated below.
            results = await asyncio.gather(*(finalize(vm) for vm in vms), return_exceptions=True)
            failures = [
                f"{vm['vm_name']} (vmid {vm['vmid']}): {r}"
                for vm, r in zip(vms, results) if isinstance(r, BaseException)
            ]
            if failures:
                raise RuntimeError(f"Node finalization failed for {len(failures)}/{len(vms)} node(s): " + "; ".join(failures))
            ip_addresses = {vm["vm_name"]: ip for vm, ip in zip(vms, results)}
            logger.info(f"All k3d-lb nodes created successfully. IP addresses: {ip_addresses}")
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

    vms = await proxmox.list_vms_by_tags([proxmox.CREATOR_TAG, proxmox.MANAGED_TAG, captain_domain])
    failures = []
    for vm in vms:
        try:
            logger.info(f"Deleting k3d-lb node {vm['name']} (vmid {vm['vmid']} on {vm['node']})")
            await proxmox.delete_vm(vm["node"], vm["vmid"])
        except Exception as e:
            logger.error(f"Failed to delete k3d-lb node {vm['name']} (vmid {vm['vmid']} on {vm['node']}): {e}")
            failures.append(f"{vm['name']} (vmid {vm['vmid']} on {vm['node']}): {e}")

    try:
        await proxmox.delete_orphan_isos(captain_domain)
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
