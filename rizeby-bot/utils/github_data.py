"""Load JSON files from the TOKERIZE GitHub repo — same data as the web app."""
import httpx

RAW_BASE = "https://raw.githubusercontent.com/hcftrize/TOKERIZE/main"

MCAP_HISTORY_URL  = f"{RAW_BASE}/rize-data-hub/mcap-history.json"
BOND_CREATED_URL  = f"{RAW_BASE}/bond-created.json"
BOND_BROKEN_URL   = f"{RAW_BASE}/bond-broken.json"
BOND_LIFECYCLE_URL = f"{RAW_BASE}/bond-lifecycle.json"
BOND_STATES_URL   = f"{RAW_BASE}/bond-states.json"
CIPS_URL          = f"{RAW_BASE}/canton-ecosystem/cips.json"
ENTITIES_URL      = "https://raw.githubusercontent.com/hcftrize/TOKERIZE/dev/canton-ecosystem/entities.json"

_cache: dict = {}


async def load_json(url: str, cache_key: str = None) -> dict | list | None:
    key = cache_key or url
    if key in _cache:
        return _cache[key]
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
            _cache[key] = data
            return data
    except Exception:
        return None


async def get_mcap_history():
    return await load_json(MCAP_HISTORY_URL, "mcap")

async def get_bond_created():
    return await load_json(BOND_CREATED_URL, "bond_created")

async def get_bond_broken():
    return await load_json(BOND_BROKEN_URL, "bond_broken")

async def get_bond_lifecycle():
    return await load_json(BOND_LIFECYCLE_URL, "bond_lifecycle")

async def get_bond_states():
    return await load_json(BOND_STATES_URL, "bond_states")

async def get_cips():
    return await load_json(CIPS_URL, "cips")

async def get_entities():
    return await load_json(ENTITIES_URL, "entities")
