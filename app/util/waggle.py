import os
import httpx
import glueops.setup_logging

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logger = glueops.setup_logging.configure(level=LOG_LEVEL)


def _base_url() -> str:
    base = os.environ["WAGGLE_API_URL"].rstrip("/")
    if not base.endswith("/api/v1"):
        base += "/api/v1"
    return base


_http = None


def _client() -> httpx.AsyncClient:
    global _http
    if _http is None or _http.is_closed:
        _http = httpx.AsyncClient(
            base_url=_base_url(),
            headers={"Authorization": f"Bearer {os.environ['WAGGLE_API_KEY']}"},
            timeout=30.0,
        )
    return _http


def _check(response: httpx.Response):
    if response.status_code >= 400:
        raise RuntimeError(
            f"Waggle API {response.request.method} {response.request.url.path} "
            f"failed with {response.status_code}: {response.text}"
        )


async def _get(path: str, **params):
    r = await _client().get(path, params=params or None)
    _check(r)
    return r.json()


async def _post(path: str, body: dict):
    r = await _client().post(path, json=body)
    _check(r)
    return r.json()


async def _patch(path: str, body: dict):
    r = await _client().patch(path, json=body)
    _check(r)
    return r.json() if r.content else None


async def _delete(path: str):
    r = await _client().delete(path)
    _check(r)


async def get_datacenter_by_name(name: str) -> dict:
    data = await _get("/datacenters")
    for datacenter in data.get("items") or []:
        if datacenter["name"] == name:
            return datacenter
    raise ValueError(f"Datacenter {name!r} not found in Waggle. It must be created (and discovered) before using this endpoint.")


async def get_slot_by_name(name: str) -> dict:
    data = await _get("/slots", name=name)
    slots = data.get("items") or []
    if not slots:
        raise ValueError(f"Slot {name!r} not found in Waggle. It must be created before using this endpoint.")
    return slots[0]


async def find_pools_by_name(name: str) -> list:
    data = await _get("/pools")
    return [pool for pool in (data.get("items") or []) if pool["name"] == name]


async def create_pool(datacenter_id: str, slot_id: str, name: str, desired_count: int) -> dict:
    logger.info(f"Creating Waggle pool {name!r} with desired_count={desired_count}")
    return await _post("/pools", {
        "datacenter_id": datacenter_id,
        "slot_id": slot_id,
        "name": name,
        "desired_count": desired_count,
    })


async def get_pool_placements(pool_id: str) -> list:
    data = await _get(f"/pools/{pool_id}/placements")
    return data.get("items") or []


async def set_placement_vmid(placement_id: str, vmid: int):
    logger.info(f"Recording vmid {vmid} on Waggle placement {placement_id}")
    await _patch(f"/placements/{placement_id}", {"vmid": vmid})


async def delete_pool(pool_id: str):
    logger.info(f"Deleting Waggle pool {pool_id}")
    await _delete(f"/pools/{pool_id}")
