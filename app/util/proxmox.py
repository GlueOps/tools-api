import asyncio
import base64
import io
import ipaddress
import os
import re
import urllib.parse

import httpx
import pycdlib
import glueops.setup_logging

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logger = glueops.setup_logging.configure(level=LOG_LEVEL)

# Tags applied to every VM this module creates; deletion is scoped to VMs
# carrying both of these tags plus the captain_domain tag.
MANAGED_TAG = "glueops-k3d-lb"
CREATOR_TAG = "tools-api"

_http = None


def _storage() -> str:
    return os.environ["PROXMOX_STORAGE"]


def _verify_ssl() -> bool:
    return os.getenv("PROXMOX_VERIFY_SSL", "true").lower() not in ("false", "0", "no")


def _download_timeout() -> float:
    return float(os.getenv("PROXMOX_IMAGE_DOWNLOAD_TIMEOUT", "1800"))


def _base() -> str:
    return f"https://{os.environ['PROXMOX_HOST']}:{os.getenv('PROXMOX_PORT', '8006')}/api2/json"


def _client() -> httpx.AsyncClient:
    global _http
    if _http is None or _http.is_closed:
        if not _verify_ssl():
            logger.warning(f"SSL verification disabled for Proxmox host {os.environ['PROXMOX_HOST']}")
        headers = {"Authorization": f"PVEAPIToken={os.environ['PROXMOX_TOKEN_ID']}={os.environ['PROXMOX_TOKEN_SECRET']}"}
        _http = httpx.AsyncClient(verify=_verify_ssl(), timeout=60.0, headers=headers)
    return _http


def _check(response: httpx.Response):
    if response.status_code >= 400:
        raise httpx.HTTPStatusError(
            f"Proxmox API {response.request.method} {response.request.url.path} "
            f"failed with {response.status_code}: {response.text}",
            request=response.request,
            response=response,
        )


async def _get(path: str, **params):
    r = await _client().get(f"{_base()}{path}", params=params or None)
    _check(r)
    return r.json()["data"]


async def _post(path: str, data=None, files=None):
    r = await _client().post(f"{_base()}{path}", data=data, files=files)
    _check(r)
    return r.json()["data"]


async def _put(path: str, data):
    r = await _client().put(f"{_base()}{path}", data=data)
    _check(r)
    return r.json()["data"]


async def _delete(path: str, **params):
    r = await _client().delete(f"{_base()}{path}", params=params or None)
    _check(r)
    return r.json()["data"]


async def poll_task(upid: str, timeout: float = 600.0):
    task_node = upid.split(":")[1]
    encoded = urllib.parse.quote(upid, safe="")
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        data = await _get(f"/nodes/{task_node}/tasks/{encoded}/status")
        if data["status"] == "stopped":
            if data.get("exitstatus") != "OK":
                raise RuntimeError(f"Proxmox task failed: {data}")
            return
        if asyncio.get_running_loop().time() >= deadline:
            # Best-effort stop so an abandoned task (e.g. a wedged download-url
            # holding its target file) doesn't block every retry with 409s.
            try:
                await _delete(f"/nodes/{task_node}/tasks/{encoded}")
                logger.warning(f"Stopped stalled Proxmox task {upid} after {timeout:.0f}s")
            except Exception as e:
                logger.error(f"Failed to stop stalled Proxmox task {upid}: {e}")
            raise TimeoutError(f"Proxmox task {upid} still running after {timeout:.0f}s; check the task log in the Proxmox UI")
        await asyncio.sleep(3)


async def get_next_vmid() -> str:
    return await _get("/cluster/nextid")


async def ensure_image_cached(node: str, image: str):
    download_url = os.environ["PROXMOX_DOWNLOAD_SERVER_URL"]
    content = await _get(f"/nodes/{node}/storage/{_storage()}/content", content="import")
    volid = f"{_storage()}:import/{image}.qcow2"
    if volid in {v["volid"] for v in (content or [])}:
        logger.info(f"Image {image} already cached on {node}")
        return
    logger.info(f"Downloading {image} to {node}")
    try:
        upid = await _post(f"/nodes/{node}/storage/{_storage()}/download-url", data={
            "url": f"{download_url.rstrip('/')}/{image}.qcow2",
            "filename": f"{image}.qcow2",
            "content": "import",
        })
        await poll_task(upid, timeout=_download_timeout())
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 409:
            # Another download already in progress — wait for it to complete.
            # download-url renames a temp file on completion, so appearance in
            # the content listing means the download finished intact.
            timeout = _download_timeout()
            deadline = asyncio.get_running_loop().time() + timeout
            logger.info(f"Image {image} download already in progress on {node}, waiting...")
            while asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(5)
                content = await _get(f"/nodes/{node}/storage/{_storage()}/content", content="import")
                if volid in {v["volid"] for v in (content or [])}:
                    return
            raise TimeoutError(
                f"Timed out after {timeout:.0f}s waiting for {image} on {node}; the download started by "
                f"another request may have stalled or failed — check that node's task log, then retry."
            )
        raise


def build_cloudinit_iso(user_data: bytes, meta_data: bytes) -> bytes:
    iso = pycdlib.PyCdlib()
    iso.new(vol_ident="cidata", rock_ridge="1.09")
    iso.add_fp(io.BytesIO(user_data), length=len(user_data), iso_path="/USERDATA;1", rr_name="user-data")
    iso.add_fp(io.BytesIO(meta_data), length=len(meta_data), iso_path="/METADATA;1", rr_name="meta-data")
    buf = io.BytesIO()
    iso.write_fp(buf)
    iso.close()
    return buf.getvalue()


async def upload_iso(node: str, vm_name: str, iso_bytes: bytes) -> str:
    iso_filename = f"{vm_name}-cloudinit.iso"
    upid = await _post(
        f"/nodes/{node}/storage/{_storage()}/upload",
        data={"content": "iso"},
        files={"filename": (iso_filename, io.BytesIO(iso_bytes), "application/octet-stream")},
    )
    await poll_task(upid)
    return iso_filename


async def _delete_iso_volid(node: str, volid: str):
    result = await _delete(f"/nodes/{node}/storage/{_storage()}/content/{urllib.parse.quote(volid, safe='')}")
    if isinstance(result, str) and result.startswith("UPID:"):
        await poll_task(result)


async def eject_and_delete_iso(node: str, vmid: str, iso_filename: str):
    try:
        await _put(f"/nodes/{node}/qemu/{vmid}/config", data={"ide2": "none,media=cdrom"})
    except Exception as e:
        logger.error(f"Failed to eject ISO from VM {vmid}: {e}")
    try:
        await _delete_iso_volid(node, f"{_storage()}:iso/{iso_filename}")
    except Exception as e:
        logger.error(f"Failed to delete ISO {iso_filename}: {e}")


async def delete_orphan_isos(captain_domain: str):
    """Best-effort removal of leftover <captain_domain>-exitN-cloudinit.iso volumes on any node.

    Failed creates can leave credential-bearing cloud-init ISOs behind (VM purge never
    removes standalone iso content), so deletion sweeps every online node's storage.
    """
    pattern = re.compile(rf"^{re.escape(_storage())}:iso/{re.escape(captain_domain)}-exit\d+-cloudinit\.iso$")
    seen = set()
    deleted = 0
    for n in (await _get("/nodes")) or []:
        try:
            content = await _get(f"/nodes/{n['node']}/storage/{_storage()}/content", content="iso")
        except (httpx.HTTPStatusError, httpx.TransportError):
            continue  # storage not present/available on this node
        for v in content or []:
            volid = v["volid"]
            if volid in seen or not pattern.match(volid):
                continue  # `seen` dedupes shared storage listed under every node
            seen.add(volid)
            try:
                await _delete_iso_volid(n["node"], volid)
                deleted += 1
            except Exception as e:
                logger.error(f"Failed to delete orphaned ISO {volid}: {e}")
    if deleted:
        logger.info(f"Deleted {deleted} orphaned cloud-init ISO(s) for {captain_domain}")


async def create_vm(node: str, vmid: str, vm_name: str, vcpus: int, memory_mb: int, image: str, iso_filename: str, tags: list):
    net0 = f"virtio,bridge={os.getenv('PROXMOX_BRIDGE', 'vmbr_public')}"
    vlan_tag = os.getenv("PROXMOX_VLAN_TAG")
    if vlan_tag:
        net0 += f",tag={vlan_tag}"
    upid = await _post(f"/nodes/{node}/qemu", data={
        "vmid": vmid,
        "name": vm_name,
        "memory": memory_mb,
        "cores": vcpus,
        "cpu": "x86-64-v2-AES",
        "ostype": "l26",
        "agent": "1",
        "onboot": 1,
        "virtio0": f"{_storage()}:0,import-from={_storage()}:import/{image}.qcow2,iothread=1,format=raw",
        "ide2": f"{_storage()}:iso/{iso_filename},media=cdrom",
        "boot": "order=virtio0",
        "net0": net0,
        "serial0": "socket",
        # Proxmox lowercases tags on write (default tag-style); normalize here so
        # our own matching agrees with what the server stores.
        "tags": ";".join(t.lower() for t in tags),
    })
    await poll_task(upid)


async def resize_disk(node: str, vmid: str, disk_gb: int):
    result = await _put(f"/nodes/{node}/qemu/{vmid}/resize", data={"disk": "virtio0", "size": f"{disk_gb}G"})
    if isinstance(result, str) and result.startswith("UPID:"):
        await poll_task(result)


async def start_vm(node: str, vmid: str):
    upid = await _post(f"/nodes/{node}/qemu/{vmid}/status/start")
    await poll_task(upid)


def _is_missing_vm_error(e: Exception) -> bool:
    return isinstance(e, httpx.HTTPStatusError) and "does not exist" in e.response.text


async def delete_vm(node: str, vmid: str):
    try:
        status_data = await _get(f"/nodes/{node}/qemu/{vmid}/status/current")
        if status_data.get("status") == "running":
            upid = await _post(f"/nodes/{node}/qemu/{vmid}/status/stop")
            await poll_task(upid)
    except Exception as e:
        if _is_missing_vm_error(e):
            logger.info(f"VM {vmid} on {node} already gone, nothing to delete")
            return
        logger.error(f"Failed to stop VM {vmid} before delete: {e}")
    try:
        upid = await _delete(f"/nodes/{node}/qemu/{vmid}", purge=1)
        await poll_task(upid)
    except Exception as e:
        # DELETE /qemu/{vmid} is not idempotent — treat already-gone as success
        if _is_missing_vm_error(e):
            logger.info(f"VM {vmid} on {node} already gone, nothing to delete")
            return
        raise


async def list_vms_by_tags(required_tags: list) -> list:
    """Return [{node, vmid, name}] for every qemu VM carrying all required_tags."""
    resources = await _get("/cluster/resources", type="vm")
    required = {t.lower() for t in required_tags}
    matches = []
    for r in resources or []:
        if r.get("type") != "qemu":
            continue
        # Proxmox accepts both ";" and "," as tag separators, and stores tags lowercased
        vm_tags = {t.lower() for t in re.split(r"[;,]", r.get("tags") or "")}
        if required.issubset(vm_tags):
            matches.append({"node": r["node"], "vmid": str(r["vmid"]), "name": r.get("name", "")})
    return matches


def _decode_agent_output(data: str) -> str:
    # QGA returns out-data/err-data base64-encoded; PVE passes them through undecoded
    try:
        return base64.b64decode(data).decode(errors="replace")
    except (ValueError, TypeError):
        return data


async def _agent_exec(node: str, vmid: str, command: list, timeout: float = 180.0) -> str:
    r = await _client().post(
        f"{_base()}/nodes/{node}/qemu/{vmid}/agent/exec",
        json={"command": command, "input-data": ""},
    )
    _check(r)
    pid = r.json()["data"]["pid"]
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        result = await _get(f"/nodes/{node}/qemu/{vmid}/agent/exec-status", pid=pid)
        if result.get("exited"):
            if result.get("exitcode", 1) != 0:
                raise RuntimeError(f"Command exited {result.get('exitcode')}: {_decode_agent_output(result.get('err-data', ''))!r}")
            return _decode_agent_output(result.get("out-data", "")) + _decode_agent_output(result.get("err-data", ""))
        await asyncio.sleep(3)
    raise TimeoutError(f"Command did not exit within {timeout:.0f}s")


async def wait_for_cloud_init(node: str, vmid: str, agent_timeout: int = 300, cloudinit_timeout: int = 600):
    """Poll guest agent until up, then poll cloud-init completion.

    The debian cloud image installs qemu-guest-agent via cloud-init itself, so the
    agent only appears partway through boot — hence the generous agent_timeout.
    """
    loop = asyncio.get_running_loop()
    agent_end = loop.time() + agent_timeout
    while loop.time() < agent_end:
        try:
            await _get(f"/nodes/{node}/qemu/{vmid}/agent/info")
            logger.info(f"VM {vmid}: guest agent up, polling cloud-init status")
            break
        except (httpx.HTTPStatusError, httpx.TransportError):
            await asyncio.sleep(5)
    else:
        raise RuntimeError(f"VM {vmid}: guest agent not available after {agent_timeout}s")
    cloudinit_end = loop.time() + cloudinit_timeout
    while loop.time() < cloudinit_end:
        try:
            await _agent_exec(node, vmid, ["ls", "/var/lib/cloud/instance/boot-finished"])
            logger.info(f"VM {vmid}: cloud-init complete")
            return
        except (RuntimeError, TimeoutError, httpx.HTTPStatusError, httpx.TransportError) as e:
            logger.debug(f"VM {vmid}: cloud-init not ready: {e}")
        await asyncio.sleep(5)
    logger.warning(f"VM {vmid}: cloud-init did not complete within {cloudinit_timeout}s, continuing anyway")


async def get_vm_ipv4(node: str, vmid: str, timeout: int = 120) -> str:
    """Ask the QEMU guest agent for the VM's primary IPv4 address.

    Guest-agent data is guest-controlled (including the ip-address-type field), and the
    returned value ends up in a manifest the operator pastes into a shell — so the
    address is parsed with ipaddress and only the normalized form is ever returned.
    """
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    skip_prefixes = ("lo", "docker", "br-", "veth")
    while loop.time() < end:
        try:
            data = await _get(f"/nodes/{node}/qemu/{vmid}/agent/network-get-interfaces")
            for iface in data.get("result", []):
                if iface.get("name", "").startswith(skip_prefixes):
                    continue
                for addr in iface.get("ip-addresses", []):
                    if addr.get("ip-address-type") != "ipv4":
                        continue
                    try:
                        ip = ipaddress.IPv4Address(addr.get("ip-address", ""))
                    except ValueError:
                        logger.warning(f"VM {vmid}: guest agent reported non-IPv4 string {addr.get('ip-address')!r}, skipping")
                        continue
                    if ip.is_loopback or ip.is_link_local or ip.is_unspecified:
                        continue
                    logger.info(f"VM {vmid}: found IPv4 {ip} on interface {iface['name']}")
                    return str(ip)
        except (httpx.HTTPStatusError, httpx.TransportError) as e:
            logger.debug(f"VM {vmid}: guest agent network query not ready: {e}")
        await asyncio.sleep(5)
    raise RuntimeError(f"Could not determine IPv4 address for VM {vmid} within {timeout}s")
