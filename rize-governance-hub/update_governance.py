#!/usr/bin/env python3
"""
Daily incremental updater — merges new events (last 8 days) into existing JSONs.
Runs after bootstrap is complete. Safe to run on partial/empty JSONs.
Usage:
  python3 update_governance.py              # all 6
  python3 update_governance.py bond-broken  # single
"""

import json, time, sys, os, urllib.request
from datetime import datetime, timezone, timedelta

# Same endpoints as bootstrap
ENDPOINTS = {
    "pool-config":    "https://api.goldsky.com/api/public/project_cmocpxhlpgzgs01y06xr9dto2/subgraphs/tokerize-pool-config/1.0.0/gn",
    "bond-lifecycle": "https://api.goldsky.com/api/public/project_cmocnm0h8gx3n01y7hpoe4kxv/subgraphs/tokerize-bond-lifecycle/1.0.0/gn",
    "bond-broken":    "https://api.goldsky.com/api/public/project_cmocqkq31mv0m010y19bu6obd/subgraphs/tokerize-bond-broken/1.0.0/gn",
    "nft-transfers":  "https://api.goldsky.com/api/public/project_cmocqwx6tnlbf010yce109jo9/subgraphs/tokerize-nft-transfers/1.0.0/gn",
    "bond-timemarker":"https://api.subgraph.ormilabs.com/api/public/ac2ecb60-44a8-4df2-83cb-08bd1bced775/subgraphs/tokerize-bond-timemarker/1.0.0/gn",
    "bond-created":   "https://api.subgraph.ormilabs.com/api/public/a9ede79c-2a5c-4bb8-9208-ac30662368b5/subgraphs/tokerize-bond-created/1.0.0/gn",
}

# Incremental queries — fetch by blockTimestamp_gt (last 8 days)
QUERIES_INCR = {
    "pool-config": {
        "poolUpdateds": """{ poolUpdateds(first:1000,orderBy:blockTimestamp,orderDirection:asc,where:{blockTimestamp_gt:"TS"}) {
            id blockNumber blockTimestamp transactionHash poolId maxMultiplier fullMaturityPeriod warmupPeriod distributionPeriod } }""",
        "releaseWarmupUpdateds": """{ releaseWarmupUpdateds(first:1000,orderBy:blockTimestamp,orderDirection:asc,where:{blockTimestamp_gt:"TS"}) {
            id blockNumber blockTimestamp transactionHash warmupPeriod } }""",
        "migratorAddeds": """{ migratorAddeds(first:1000,orderBy:blockTimestamp,orderDirection:asc,where:{blockTimestamp_gt:"TS"}) {
            id blockNumber blockTimestamp transactionHash migrator } }""",
        "migratorRemoveds": """{ migratorRemoveds(first:1000,orderBy:blockTimestamp,orderDirection:asc,where:{blockTimestamp_gt:"TS"}) {
            id blockNumber blockTimestamp transactionHash migrator } }""",
    },
    "bond-lifecycle": {
        "tokensReleaseds": """{ tokensReleaseds(first:1000,orderBy:blockTimestamp,orderDirection:asc,where:{blockTimestamp_gt:"TS"}) {
            id blockNumber blockTimestamp transactionHash bondId amount to } }""",
        "bondMigrateds": """{ bondMigrateds(first:1000,orderBy:blockTimestamp,orderDirection:asc,where:{blockTimestamp_gt:"TS"}) {
            id blockNumber blockTimestamp transactionHash bondId fromPool toPool amount } }""",
        "vestingUpdateds": """{ vestingUpdateds(first:1000,orderBy:blockTimestamp,orderDirection:asc,where:{blockTimestamp_gt:"TS"}) {
            id blockNumber blockTimestamp transactionHash bondId vestingEnd } }""",
        "vestedTokenClaweds": """{ vestedTokenClaweds(first:1000,orderBy:blockTimestamp,orderDirection:asc,where:{blockTimestamp_gt:"TS"}) {
            id blockNumber blockTimestamp transactionHash bondId amount } }""",
    },
    "bond-broken": {
        "bondBrokens": """{ bondBrokens(first:1000,orderBy:blockTimestamp,orderDirection:asc,where:{blockTimestamp_gt:"TS"}) {
            id blockNumber blockTimestamp transactionHash bondId amount owner date } }""",
    },
    "nft-transfers": {
        "transfers": """{ transfers(first:1000,orderBy:blockTimestamp,orderDirection:asc,where:{blockTimestamp_gt:"TS"}) {
            id blockNumber blockTimestamp transactionHash from to tokenId transferCount } }""",
    },
    "bond-timemarker": {
        "bondTimeMarkers": """{ bondTimeMarkers(first:1000,orderBy:blockTimestamp,orderDirection:asc,where:{blockTimestamp_gt:"TS"}) {
            id blockNumber blockTimestamp transactionHash bondId timeMarker amount poolId } }""",
    },
    "bond-created": {
        "bondCreateds": """{ bondCreateds(first:1000,orderBy:blockTimestamp,orderDirection:asc,where:{blockTimestamp_gt:"TS"}) {
            id blockNumber blockTimestamp transactionHash bondId amount owner poolId } }""",
        "bondIncreaseds": """{ bondIncreaseds(first:1000,orderBy:blockTimestamp,orderDirection:asc,where:{blockTimestamp_gt:"TS"}) {
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
            print(f"    Attempt {attempt+1} failed ({e}), retry in {wait}s", flush=True)
            if attempt < retries - 1:
                time.sleep(wait)
    return None

def fetch_new(name, endpoint, entity, query_tpl, ts_cutoff):
    results = []
    cursor_ts = ts_cutoff
    page = 0
    while True:
        q = query_tpl.replace("TS", str(cursor_ts))
        data = gql(endpoint, q)
        if data is None:
            break
        items = data.get(entity, [])
        if not items:
            break
        results.extend(items)
        page += 1
        print(f"    [{name}:{entity}] page {page}: +{len(items)}", flush=True)
        if len(items) < 1000:
            break
        cursor_ts = items[-1]["blockTimestamp"]
        time.sleep(0.3)
    return results

def merge(existing, new_items):
    """Merge new items into existing list, dedup by id."""
    existing_ids = {item["id"] for item in existing}
    added = 0
    for item in new_items:
        if item["id"] not in existing_ids:
            existing.append(item)
            existing_ids.add(item["id"])
            added += 1
    return added

def update_subgraph(name, endpoint, entities_queries, output_dir, days_back=8):
    path = os.path.join(output_dir, f"{name}.json")
    ts_cutoff = int((datetime.now(timezone.utc) - timedelta(days=days_back)).timestamp())

    # Load existing
    if os.path.exists(path):
        with open(path) as f:
            existing = json.load(f)
        data = existing.get("data", {})
    else:
        print(f"  [{name}] No existing JSON, treating as fresh (run bootstrap first)", flush=True)
        data = {}

    total_added = 0
    for entity, query_tpl in entities_queries.items():
        if entity not in data:
            data[entity] = []
        print(f"  → {entity} (existing: {len(data[entity])})", flush=True)
        new_items = fetch_new(name, endpoint, entity, query_tpl, ts_cutoff)
        added = merge(data[entity], new_items)
        total_added += added
        print(f"    +{added} new (total: {len(data[entity])})", flush=True)
        time.sleep(0.3)

    ts = datetime.now(timezone.utc).isoformat()
    out = {
        "subgraph": name,
        "scraped_at": ts,
        "bootstrap": False,
        "counts": {e: len(v) for e, v in data.items()},
        "data": data,
    }
    with open(path, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    size_kb = os.path.getsize(path) // 1024
    print(f"  ✓ {path} updated — +{total_added} total new events — {size_kb} KB", flush=True)

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    targets = args if args else list(QUERIES_INCR.keys())
    output_dir = "rize-governance-hub"
    os.makedirs(output_dir, exist_ok=True)

    print(f"Governance incremental update — {datetime.now(timezone.utc).isoformat()}", flush=True)
    for name in targets:
        if name not in QUERIES_INCR:
            print(f"Unknown: {name}", flush=True)
            continue
        print(f"\n{'='*50}", flush=True)
        print(f"UPDATE: {name}", flush=True)
        update_subgraph(name, ENDPOINTS[name], QUERIES_INCR[name], output_dir)

    print(f"\nDone at {datetime.now(timezone.utc).isoformat()}", flush=True)

if __name__ == "__main__":
    main()
