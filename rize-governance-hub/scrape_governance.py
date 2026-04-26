#!/usr/bin/env python3
"""
Bootstrap scraper — ALL 6 RIZE governance subgraphs.
Full erasure + rewrite on each run.
Usage:
  python3 scrape_governance.py                  # all 6
  python3 scrape_governance.py bond-broken      # single

Fixes vs previous version:
  - Schema matching: uses fuzzy best-match instead of exact lowercase lookup
    (Goldsky exposes 'bondBrokenEvents' not 'bondBrokens')
  - Ormi 429: unlimited retries with progressive backoff (30s → 60s → 120s)
    and pre-flight warm-up pause before introspection
  - Fallback hardcoded entity names if schema discovery fails entirely
"""

import json, time, sys, os, urllib.request, urllib.error
from datetime import datetime, timezone

ENDPOINTS = {
    "pool-config":     "https://api.goldsky.com/api/public/project_cmocpxhlpgzgs01y06xr9dto2/subgraphs/tokerize-pool-config/1.0.0/gn",
    "bond-lifecycle":  "https://api.goldsky.com/api/public/project_cmocnm0h8gx3n01y7hpoe4kxv/subgraphs/tokerize-bond-lifecycle/1.0.0/gn",
    "bond-broken":     "https://api.goldsky.com/api/public/project_cmocqkq31mv0m010y19bu6obd/subgraphs/tokerize-bond-broken/1.0.0/gn",
    "nft-transfers":   "https://api.goldsky.com/api/public/project_cmocqwx6tnlbf010yce109jo9/subgraphs/tokerize-nft-transfers/1.0.0/gn",
    "bond-timemarker": "https://api.subgraph.ormilabs.com/api/public/ac2ecb60-44a8-4df2-83cb-08bd1bced775/subgraphs/tokerize-bond-timemarker/1.0.0/gn",
    "bond-created":    "https://api.subgraph.ormilabs.com/api/public/a9ede79c-2a5c-4bb8-9208-ac30662368b5/subgraphs/tokerize-bond-created/1.0.0/gn",
}

# Keys = canonical "intent" name (what we want to query), lowercase, no spaces.
# Values = fields to request.
# The real GraphQL entity name is resolved at runtime via schema discovery.
FIELDS = {
    "pool-config": {
        "poolUpdatedEvents":          "id blockNumber blockTimestamp transactionHash poolId maxMultiplier fullMaturityPeriod warmupPeriod distributionPeriod",
        "releaseWarmupUpdatedEvents": "id blockNumber blockTimestamp transactionHash warmupPeriod",
        "migratorAddedEvents":        "id blockNumber blockTimestamp transactionHash migrator",
        "migratorRemovedEvents":      "id blockNumber blockTimestamp transactionHash migrator",
    },
    "bond-lifecycle": {
        "tokensReleasedEvents":   "id blockNumber blockTimestamp transactionHash bondId amount to",
        "bondMigratedEvents":     "id blockNumber blockTimestamp transactionHash bondId fromPool toPool amount",
        "vestingUpdatedEvents":   "id blockNumber blockTimestamp transactionHash bondId vestingEnd",
        "vestedTokenClawedEvents":"id blockNumber blockTimestamp transactionHash bondId amount",
    },
    "bond-broken": {
        "bondBrokenEvents": "id blockNumber blockTimestamp transactionHash bondId amount owner date",
    },
    "nft-transfers": {
        "nftTransferEvents": "id blockNumber blockTimestamp transactionHash from to tokenId transferCount",
    },
    "bond-timemarker": {
        "bondTimeMarkerEvents": "id blockNumber blockTimestamp transactionHash bondId timeMarker amount poolId",
    },
    "bond-created": {
        "bondCreatedEvents":   "id blockNumber blockTimestamp transactionHash bondId amount owner poolId",
        "bondIncreasedEvents": "id blockNumber blockTimestamp transactionHash bondId amount owner poolId",
    },
}

# Hardcoded fallback entity names (used if schema discovery fails entirely).
# Derived from Goldsky/Ormi conventions observed in actual schema introspection.
FALLBACK_NAMES = {
    "pool-config":    ["poolUpdatedEvents", "releaseWarmupUpdatedEvents", "migratorAddedEvents", "migratorRemovedEvents"],
    "bond-lifecycle": ["tokensReleasedEvents", "bondMigratedEvents", "vestingUpdatedEvents", "vestedTokenClawedEvents"],
    "bond-broken":    ["bondBrokenEvents"],
    "nft-transfers":  ["nftTransferEvents"],
    "bond-timemarker":["bondTimeMarkerEvents"],
    "bond-created":   ["bondCreatedEvents", "bondIncreasedEvents"],
}

HEADERS = {
    "Content-Type": "application/json",
    "Accept":       "application/json",
    "User-Agent":   "Mozilla/5.0 (compatible; TokerizeBot/1.0; +https://tokerize.top)",
    "Origin":       "https://tokerize.top",
    "Referer":      "https://tokerize.top/",
}


# ── HTTP / GQL helpers ────────────────────────────────────────────────────────

def gql(endpoint, query, is_ormi=False, max_429_retries=8):
    """
    Execute a GraphQL query.
    - On 429: progressive backoff (30s, 60s, 90s … capped at 120s), up to max_429_retries.
    - On other HTTP errors or network failures: exponential backoff, 4 retries.
    Returns parsed data dict or None on failure.
    """
    payload = json.dumps({"query": query}).encode()
    req = urllib.request.Request(endpoint, data=payload, headers=HEADERS, method="POST")

    network_retries = 0
    rate_retries    = 0

    while True:
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                data = json.loads(r.read())

            if "errors" in data:
                msg = data["errors"][0].get("message", "?")
                print(f"    GQL error: {msg}", flush=True)
                return None

            return data.get("data", {})

        except urllib.error.HTTPError as e:
            if e.code == 429:
                rate_retries += 1
                if rate_retries > max_429_retries:
                    print(f"    429 — too many retries ({max_429_retries}), giving up", flush=True)
                    return None
                wait = min(30 * rate_retries, 120)
                print(f"    429 — rate limited, attempt {rate_retries}/{max_429_retries}, waiting {wait}s…", flush=True)
                time.sleep(wait)

            else:
                network_retries += 1
                if network_retries > 4:
                    print(f"    HTTP {e.code} — too many retries, giving up", flush=True)
                    return None
                wait = 2 ** (network_retries - 1)
                print(f"    HTTP {e.code} — retry {network_retries}/4 in {wait}s", flush=True)
                time.sleep(wait)

        except Exception as e:
            network_retries += 1
            if network_retries > 4:
                print(f"    Network error — too many retries, giving up ({e})", flush=True)
                return None
            wait = 2 ** (network_retries - 1)
            print(f"    Network error ({e}) — retry {network_retries}/4 in {wait}s", flush=True)
            time.sleep(wait)


# ── Schema discovery ──────────────────────────────────────────────────────────

def discover_schema(endpoint, is_ormi=False):
    """
    Return list of real queryable entity names (excluding internal __ fields).
    For Ormi, pause before attempting to reduce initial 429 risk.
    """
    if is_ormi:
        print(f"    [Ormi] pausing 10s before introspection to avoid 429…", flush=True)
        time.sleep(10)

    q = "{ __schema { queryType { fields { name } } } }"
    data = gql(endpoint, q, is_ormi=is_ormi)
    if not data:
        return []

    fields = data.get("__schema", {}).get("queryType", {}).get("fields", [])
    names  = [f["name"] for f in fields if not f["name"].startswith("_")]
    return names


def best_match(want, available_names):
    """
    Find the best matching real entity name for a desired key.

    Strategy (in order):
    1. Exact match (case-sensitive)
    2. Exact match (case-insensitive)
    3. Available name that ends with 's' and whose lowercase == want.lower()
       (covers 'bondBrokenEvents' vs 'bondBrokenEvent')
    4. Available name whose lowercase contains want.lower() stripped of trailing 's'
    5. Available name whose stripped lowercase is contained in want.lower()
    6. None (fallback: use want as-is)

    We prefer plural names (ending in 's') since those are the collection queries.
    """
    # Filter to plural names first (collection queries)
    plural = [n for n in available_names if n.endswith("s")]
    all_n  = available_names

    want_l = want.lower()
    want_stripped = want_l.rstrip("s")

    for pool in [plural, all_n]:
        # 1. Exact
        for n in pool:
            if n == want:
                return n
        # 2. Case-insensitive exact
        for n in pool:
            if n.lower() == want_l:
                return n
        # 3. Lowercase stripped match (e.g. 'bondbrokenevents' vs 'bondBrokenEvents')
        for n in pool:
            if n.lower().rstrip("s") == want_stripped:
                return n
        # 4. want is a substring of n (lowercased, stripped)
        for n in pool:
            if want_stripped in n.lower():
                return n
        # 5. n stripped is substring of want
        for n in pool:
            if n.lower().rstrip("s") in want_l:
                return n

    return None  # will fall back to using want as-is


# ── Pagination ────────────────────────────────────────────────────────────────

def fetch_entity(endpoint, real_name, fields_str, is_ormi=False):
    """
    Fetch ALL records for one entity using skip-based pagination (1000/page).
    Returns list of dicts.
    """
    results    = []
    skip       = 0
    page_sleep = 6 if is_ormi else 0.4   # conservative inter-page delay for Ormi

    while True:
        q = (
            f"{{ {real_name}("
            f"first:1000, skip:{skip}, "
            f"orderBy:blockTimestamp, orderDirection:asc"
            f") {{ {fields_str} }} }}"
        )
        data = gql(endpoint, q, is_ormi=is_ormi)

        if data is None:
            print(f"      fetch failed at skip={skip}, stopping", flush=True)
            break

        items = data.get(real_name, [])
        if not items:
            break

        results.extend(items)
        print(f"      skip={skip:>6}: +{len(items):>4} → total {len(results)}", flush=True)

        if len(items) < 1000:
            break   # last page

        skip += 1000
        time.sleep(page_sleep)

    return results


# ── Per-subgraph orchestration ────────────────────────────────────────────────

def fetch_subgraph(name, endpoint, fields_map):
    is_ormi = "ormilabs" in endpoint
    provider = "Ormi" if is_ormi else "Goldsky"

    print(f"\n{'='*62}", flush=True)
    print(f"  SUBGRAPH: {name}  [{provider}]", flush=True)

    # Schema discovery
    print(f"  → Discovering schema…", flush=True)
    schema_names = discover_schema(endpoint, is_ormi=is_ormi)

    if schema_names:
        print(f"  → {len(schema_names)} queryable entities: {schema_names[:12]}", flush=True)
    else:
        print(f"  → Schema discovery failed — using fallback names", flush=True)
        schema_names = FALLBACK_NAMES.get(name, [])
        print(f"  → Fallback: {schema_names}", flush=True)

    # Fetch each entity
    result_data = {}
    inter_sleep = 8 if is_ormi else 0.6

    for want_name, fields_str in fields_map.items():
        real = best_match(want_name, schema_names)
        if real is None:
            print(f"  → {want_name} — NO MATCH in schema, skipping", flush=True)
            result_data[want_name] = []
            continue

        print(f"  → {want_name} → {real}", flush=True)
        items = fetch_entity(endpoint, real, fields_str, is_ormi=is_ormi)
        result_data[real] = items
        print(f"     ✓ {len(items)} records", flush=True)
        time.sleep(inter_sleep)

    return result_data


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    args    = [a for a in sys.argv[1:] if not a.startswith("--")]
    targets = args if args else list(FIELDS.keys())
    out_dir = "rize-governance-hub"
    os.makedirs(out_dir, exist_ok=True)

    ts = datetime.now(timezone.utc).isoformat()
    print(f"Governance bootstrap — {ts}", flush=True)
    print(f"Targets: {targets}", flush=True)

    for name in targets:
        if name not in FIELDS:
            print(f"Unknown subgraph: {name}", flush=True)
            continue

        data = fetch_subgraph(name, ENDPOINTS[name], FIELDS[name])

        out = {
            "subgraph":   name,
            "scraped_at": ts,
            "bootstrap":  True,
            "counts":     {e: len(v) for e, v in data.items()},
            "data":       data,
        }

        path = os.path.join(out_dir, f"{name}.json")
        with open(path, "w") as f:
            json.dump(out, f, separators=(",", ":"))

        size_kb = os.path.getsize(path) // 1024
        print(f"\n  ✓ {path} — {size_kb} KB | {out['counts']}", flush=True)

    print(f"\nDone — {datetime.now(timezone.utc).isoformat()}", flush=True)


if __name__ == "__main__":
    main()
