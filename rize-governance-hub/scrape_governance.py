#!/usr/bin/env python3
"""
Bootstrap scraper — ALL 6 RIZE governance subgraphs.
Full erasure + rewrite on each run (bootstrap mode).
Usage:
  python3 scrape_governance.py                  # all 6
  python3 scrape_governance.py bond-broken      # single
  python3 scrape_governance.py --bootstrap      # explicit full
Output: rize-governance-hub/<name>.json
"""

import json, time, sys, os, urllib.request
from datetime import datetime, timezone

ENDPOINTS = {
    "pool-config":    "https://api.goldsky.com/api/public/project_cmocpxhlpgzgs01y06xr9dto2/subgraphs/tokerize-pool-config/1.0.0/gn",
    "bond-lifecycle": "https://api.goldsky.com/api/public/project_cmocnm0h8gx3n01y7hpoe4kxv/subgraphs/tokerize-bond-lifecycle/1.0.0/gn",
    "bond-broken":    "https://api.goldsky.com/api/public/project_cmocqkq31mv0m010y19bu6obd/subgraphs/tokerize-bond-broken/1.0.0/gn",
    "nft-transfers":  "https://api.goldsky.com/api/public/project_cmocqwx6tnlbf010yce109jo9/subgraphs/tokerize-nft-transfers/1.0.0/gn",
    "bond-timemarker":"https://api.subgraph.ormilabs.com/api/public/ac2ecb60-44a8-4df2-83cb-08bd1bced775/subgraphs/tokerize-bond-timemarker/1.0.0/gn",
    "bond-created":   "https://api.subgraph.ormilabs.com/api/public/a9ede79c-2a5c-4bb8-9208-ac30662368b5/subgraphs/tokerize-bond-created/1.0.0/gn",
}

# Each query uses cursor-based pagination via id_gt for reliability
QUERIES = {
    "pool-config": {
        "poolUpdateds": """{ poolUpdateds(first:1000,orderBy:id,orderDirection:asc,where:{id_gt:"CURSOR"}) {
            id blockNumber blockTimestamp transactionHash
            poolId maxMultiplier fullMaturityPeriod warmupPeriod distributionPeriod } }""",
        "releaseWarmupUpdateds": """{ releaseWarmupUpdateds(first:1000,orderBy:id,orderDirection:asc,where:{id_gt:"CURSOR"}) {
            id blockNumber blockTimestamp transactionHash warmupPeriod } }""",
        "migratorAddeds": """{ migratorAddeds(first:1000,orderBy:id,orderDirection:asc,where:{id_gt:"CURSOR"}) {
            id blockNumber blockTimestamp transactionHash migrator } }""",
        "migratorRemoveds": """{ migratorRemoveds(first:1000,orderBy:id,orderDirection:asc,where:{id_gt:"CURSOR"}) {
            id blockNumber blockTimestamp transactionHash migrator } }""",
    },
    "bond-lifecycle": {
        "tokensReleaseds": """{ tokensReleaseds(first:1000,orderBy:id,orderDirection:asc,where:{id_gt:"CURSOR"}) {
            id blockNumber blockTimestamp transactionHash bondId amount to } }""",
        "bondMigrateds": """{ bondMigrateds(first:1000,orderBy:id,orderDirection:asc,where:{id_gt:"CURSOR"}) {
            id blockNumber blockTimestamp transactionHash bondId fromPool toPool amount } }""",
        "vestingUpdateds": """{ vestingUpdateds(first:1000,orderBy:id,orderDirection:asc,where:{id_gt:"CURSOR"}) {
            id blockNumber blockTimestamp transactionHash bondId vestingEnd } }""",
        "vestedTokenClaweds": """{ vestedTokenClaweds(first:1000,orderBy:id,orderDirection:asc,where:{id_gt:"CURSOR"}) {
            id blockNumber blockTimestamp transactionHash bondId amount } }""",
    },
    "bond-broken": {
        "bondBrokens": """{ bondBrokens(first:1000,orderBy:id,orderDirection:asc,where:{id_gt:"CURSOR"}) {
            id blockNumber blockTimestamp transactionHash bondId amount owner date } }""",
    },
    "nft-transfers": {
        "transfers": """{ transfers(first:1000,orderBy:id,orderDirection:asc,where:{id_gt:"CURSOR"}) {
            id blockNumber blockTimestamp transactionHash from to tokenId transferCount } }""",
    },
    "bond-timemarker": {
        "bondTimeMarkers": """{ bondTimeMarkers(first:1000,orderBy:id,orderDirection:asc,where:{id_gt:"CURSOR"}) {
            id blockNumber blockTimestamp transactionHash bondId timeMarker amount poolId } }""",
    },
    "bond-created": {
        "bondCreateds": """{ bondCreateds(first:1000,orderBy:id,orderDirection:asc,where:{id_gt:"CURSOR"}) {
            id blockNumber blockTimestamp transactionHash bondId amount owner poolId } }""",
        "bondIncreaseds": """{ bondIncreaseds(first:1000,orderBy:id,orderDirection:asc,where:{id_gt:"CURSOR"}) {
            id blockNumber blockTimestamp transactionHash bondId amount owner poolId } }""",
    },
}

def gql(endpoint, query, retries=4):
    payload = json.dumps({"query": query}).encode()
    req = urllib.request.Request(
        endpoint, data=payload,
        headers={"Content-Type":"application/json","Accept":"application/json"},
        method="POST"
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                data = json.loads(r.read())
            if "errors" in data:
                print(f"    GQL error: {data['errors'][0].get('message','?')}", flush=True)
                return None
            return data.get("data", {})
        except Exception as e:
            wait = 2 ** attempt
            print(f"    Attempt {attempt+1} failed ({e}), retrying in {wait}s...", flush=True)
            if attempt < retries - 1:
                time.sleep(wait)
    return None

def fetch_entity(name, endpoint, entity, query_tpl):
    """Fetch all records for a single entity using cursor pagination."""
    results = []
    cursor = ""
    page = 0
    while True:
        q = query_tpl.replace("CURSOR", cursor)
        data = gql(endpoint, q)
        if data is None:
            print(f"    [{name}:{entity}] fetch failed at page {page}, stopping", flush=True)
            break
        items = data.get(entity, [])
        if not items:
            break
        results.extend(items)
        page += 1
        print(f"    [{name}:{entity}] page {page}: +{len(items)} → total {len(results)}", flush=True)
        if len(items) < 1000:
            break
        cursor = items[-1]["id"]
        time.sleep(0.3)
    return results

def fetch_subgraph(name, endpoint, entities_queries):
    print(f"\n{'='*60}", flush=True)
    print(f"  SUBGRAPH: {name}", flush=True)
    data = {}
    for entity, query_tpl in entities_queries.items():
        print(f"  → {entity}", flush=True)
        data[entity] = fetch_entity(name, endpoint, entity, query_tpl)
        time.sleep(0.5)
    return data

def write_json(name, data, output_dir):
    ts = datetime.now(timezone.utc).isoformat()
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
    print(f"\n  ✓ {path} — {size_kb} KB", flush=True)
    return size_kb

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    targets = args if args else list(QUERIES.keys())
    output_dir = "rize-governance-hub"
    os.makedirs(output_dir, exist_ok=True)

    print(f"Starting governance bootstrap — {datetime.now(timezone.utc).isoformat()}", flush=True)
    print(f"Targets: {targets}", flush=True)

    summary = {}
    for name in targets:
        if name not in QUERIES:
            print(f"Unknown subgraph: {name}", flush=True)
            continue
        data = fetch_subgraph(name, ENDPOINTS[name], QUERIES[name])
        size_kb = write_json(name, data, output_dir)
        summary[name] = {"counts": {e: len(v) for e, v in data.items()}, "size_kb": size_kb}

    print(f"\n{'='*60}", flush=True)
    print("BOOTSTRAP COMPLETE", flush=True)
    for name, info in summary.items():
        print(f"  {name}: {info['counts']} | {info['size_kb']} KB", flush=True)
    print(f"Done at {datetime.now(timezone.utc).isoformat()}", flush=True)

if __name__ == "__main__":
    main()
