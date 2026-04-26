#!/usr/bin/env python3
"""
Bootstrap scraper — ALL 6 RIZE governance subgraphs.
Full erasure + rewrite on each run.
Usage:
  python3 scrape_governance.py                  # all 6
  python3 scrape_governance.py bond-broken      # single
"""

import json, time, sys, os, urllib.request, urllib.error
from datetime import datetime, timezone

ENDPOINTS = {
    "pool-config":    "https://api.goldsky.com/api/public/project_cmocpxhlpgzgs01y06xr9dto2/subgraphs/tokerize-pool-config/1.0.0/gn",
    "bond-lifecycle": "https://api.goldsky.com/api/public/project_cmocnm0h8gx3n01y7hpoe4kxv/subgraphs/tokerize-bond-lifecycle/1.0.0/gn",
    "bond-broken":    "https://api.goldsky.com/api/public/project_cmocqkq31mv0m010y19bu6obd/subgraphs/tokerize-bond-broken/1.0.0/gn",
    "nft-transfers":  "https://api.goldsky.com/api/public/project_cmocqwx6tnlbf010yce109jo9/subgraphs/tokerize-nft-transfers/1.0.0/gn",
    "bond-timemarker":"https://api.subgraph.ormilabs.com/api/public/ac2ecb60-44a8-4df2-83cb-08bd1bced775/subgraphs/tokerize-bond-timemarker/1.0.0/gn",
    "bond-created":   "https://api.subgraph.ormilabs.com/api/public/a9ede79c-2a5c-4bb8-9208-ac30662368b5/subgraphs/tokerize-bond-created/1.0.0/gn",
}

# Field templates — ENTITY and SKIP replaced at runtime after schema discovery
# We store the fields we want per subgraph; entity name discovered via introspection
FIELDS = {
    "pool-config": {
        "poolupdateds":           "id blockNumber blockTimestamp transactionHash poolId maxMultiplier fullMaturityPeriod warmupPeriod distributionPeriod",
        "releasewarmupupdateds":  "id blockNumber blockTimestamp transactionHash warmupPeriod",
        "migratoraddeds":         "id blockNumber blockTimestamp transactionHash migrator",
        "migratorremoveds":       "id blockNumber blockTimestamp transactionHash migrator",
    },
    "bond-lifecycle": {
        "tokensreleaseds":        "id blockNumber blockTimestamp transactionHash bondId amount to",
        "bondmigrateds":          "id blockNumber blockTimestamp transactionHash bondId fromPool toPool amount",
        "vestingupdateds":        "id blockNumber blockTimestamp transactionHash bondId vestingEnd",
        "vestedtokenclaweds":     "id blockNumber blockTimestamp transactionHash bondId amount",
    },
    "bond-broken": {
        "bondBrokens":            "id blockNumber blockTimestamp transactionHash bondId amount owner date",
    },
    "nft-transfers": {
        "transfers":              "id blockNumber blockTimestamp transactionHash from to tokenId transferCount",
    },
    "bond-timemarker": {
        "bondtimemarkers":        "id blockNumber blockTimestamp transactionHash bondId timeMarker amount poolId",
    },
    "bond-created": {
        "bondcreateds":           "id blockNumber blockTimestamp transactionHash bondId amount owner poolId",
        "bondincreaseds":         "id blockNumber blockTimestamp transactionHash bondId amount owner poolId",
    },
}

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (compatible; TokerizeBot/1.0; +https://tokerize.top)",
    "Origin": "https://tokerize.top",
    "Referer": "https://tokerize.top/",
}

def gql(endpoint, query, retries=4, base_sleep=1):
    payload = json.dumps({"query": query}).encode()
    req = urllib.request.Request(endpoint, data=payload, headers=HEADERS, method="POST")
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read())
            if "errors" in data:
                msg = data["errors"][0].get("message", "?")
                print(f"    GQL error: {msg}", flush=True)
                return None
            return data.get("data", {})
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 30
                print(f"    Rate limited (429), waiting {wait}s...", flush=True)
            else:
                wait = base_sleep * (2 ** attempt)
                print(f"    Attempt {attempt+1} HTTP {e.code}, retry in {wait}s", flush=True)
            if attempt < retries - 1:
                time.sleep(wait)
        except Exception as e:
            wait = base_sleep * (2 ** attempt)
            print(f"    Attempt {attempt+1} failed ({e}), retry in {wait}s", flush=True)
            if attempt < retries - 1:
                time.sleep(wait)
    return None

def discover_schema(endpoint, is_ormi=False):
    """Return dict of lowercase_name -> real_name for all queryable fields."""
    q = "{ __schema { queryType { fields { name } } } }"
    base = 3 if is_ormi else 1
    data = gql(endpoint, q, base_sleep=base)
    if not data:
        return {}
    fields = data.get("__schema", {}).get("queryType", {}).get("fields", [])
    return {f["name"].lower(): f["name"] for f in fields if not f["name"].startswith("_")}

def fetch_entity(endpoint, real_name, fields_str, is_ormi=False):
    """Fetch all pages for one entity. Returns list of items."""
    results = []
    skip = 0
    page_sleep = 4 if is_ormi else 0.4
    base_sleep = 3 if is_ormi else 1
    while True:
        q = f"""{{ {real_name}(first:1000, skip:{skip}, orderBy:blockTimestamp, orderDirection:asc) {{
            {fields_str}
        }} }}"""
        data = gql(endpoint, q, base_sleep=base_sleep)
        if data is None:
            print(f"      fetch failed at skip={skip}, stopping", flush=True)
            break
        items = data.get(real_name, [])
        if not items:
            break
        results.extend(items)
        print(f"      skip={skip}: +{len(items)} → total {len(results)}", flush=True)
        if len(items) < 1000:
            break
        skip += 1000
        time.sleep(page_sleep)
    return results

def fetch_subgraph(name, endpoint, fields_map):
    is_ormi = "ormilabs" in endpoint
    print(f"\n{'='*60}", flush=True)
    print(f"  SUBGRAPH: {name} ({'Ormi' if is_ormi else 'Goldsky'})", flush=True)

    print(f"  → Discovering schema...", flush=True)
    schema = discover_schema(endpoint, is_ormi=is_ormi)
    if schema:
        print(f"  → Found {len(schema)} entities: {list(schema.values())[:10]}", flush=True)
    else:
        print(f"  → Schema discovery failed, using field names as-is", flush=True)

    data = {}
    for key_lower, fields_str in fields_map.items():
        # Match our lowercase key to real entity name from schema
        real = schema.get(key_lower, key_lower)
        print(f"  → {key_lower} → {real}", flush=True)
        items = fetch_entity(endpoint, real, fields_str, is_ormi=is_ormi)
        data[real] = items
        print(f"     Total: {len(items)}", flush=True)
        time.sleep(2 if is_ormi else 0.5)

    return data

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    targets = args if args else list(FIELDS.keys())
    output_dir = "rize-governance-hub"
    os.makedirs(output_dir, exist_ok=True)

    ts = datetime.now(timezone.utc).isoformat()
    print(f"Governance bootstrap — {ts}", flush=True)
    print(f"Targets: {targets}", flush=True)

    for name in targets:
        if name not in FIELDS:
            print(f"Unknown: {name}", flush=True)
            continue
        data = fetch_subgraph(name, ENDPOINTS[name], FIELDS[name])
        out = {
            "subgraph": name,
            "scraped_at": ts,
            "bootstrap": True,
            "counts": {e: len(v) for e, v in data.items()},
            "data": data,
        }
        path = os.path.join(output_dir, f"{name}.json")
        with open(path, "w") as f:
            json.dump(out, f, separators=(",", ":"))
        size_kb = os.path.getsize(path) // 1024
        print(f"\n  ✓ {path} — {size_kb} KB | {out['counts']}", flush=True)

    print(f"\nDone — {datetime.now(timezone.utc).isoformat()}", flush=True)

if __name__ == "__main__":
    main()
