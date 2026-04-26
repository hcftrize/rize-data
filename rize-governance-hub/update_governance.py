#!/usr/bin/env python3
"""
Daily incremental updater — merges new events (last 8 days) into existing JSONs.
Runs after bootstrap is complete. Safe to run on partial/empty JSONs.
Usage:
  python3 update_governance.py              # all 6
  python3 update_governance.py bond-broken  # single

Fixes vs previous version:
  - Entity names updated to match real Goldsky/Ormi schema (xxxEvents pattern)
  - gql() handles 429 with progressive backoff (same as bootstrap)
  - merge() uses 'id' dedup (unchanged, was correct)
"""

import json, time, sys, os, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

ENDPOINTS = {
    "pool-config":     "https://api.goldsky.com/api/public/project_cmocpxhlpgzgs01y06xr9dto2/subgraphs/tokerize-pool-config/1.0.0/gn",
    "bond-lifecycle":  "https://api.goldsky.com/api/public/project_cmocnm0h8gx3n01y7hpoe4kxv/subgraphs/tokerize-bond-lifecycle/1.0.0/gn",
    "bond-broken":     "https://api.goldsky.com/api/public/project_cmocqkq31mv0m010y19bu6obd/subgraphs/tokerize-bond-broken/1.0.0/gn",
    "nft-transfers":   "https://api.goldsky.com/api/public/project_cmocqwx6tnlbf010yce109jo9/subgraphs/tokerize-nft-transfers/1.0.0/gn",
    "bond-timemarker": "https://api.subgraph.ormilabs.com/api/public/ac2ecb60-44a8-4df2-83cb-08bd1bced775/subgraphs/tokerize-bond-timemarker/1.0.0/gn",
    "bond-created":    "https://api.subgraph.ormilabs.com/api/public/a9ede79c-2a5c-4bb8-9208-ac30662368b5/subgraphs/tokerize-bond-created/1.0.0/gn",
}

HEADERS = {
    "Content-Type": "application/json",
    "Accept":       "application/json",
    "User-Agent":   "Mozilla/5.0 (compatible; TokerizeBot/1.0; +https://tokerize.top)",
    "Origin":       "https://tokerize.top",
    "Referer":      "https://tokerize.top/",
}

# Entity names corrected to match actual GraphQL schema (xxxEvents pattern).
# TS is replaced at runtime with the unix timestamp cutoff string.
QUERIES_INCR = {
    "pool-config": {
        "poolUpdatedEvents": """{ poolUpdatedEvents(first:1000,orderBy:blockTimestamp,orderDirection:asc,where:{blockTimestamp_gt:"TS"}) {
            id blockNumber blockTimestamp transactionHash poolId maxMultiplier fullMaturityPeriod warmupPeriod distributionPeriod } }""",
        "releaseWarmupUpdatedEvents": """{ releaseWarmupUpdatedEvents(first:1000,orderBy:blockTimestamp,orderDirection:asc,where:{blockTimestamp_gt:"TS"}) {
            id blockNumber blockTimestamp transactionHash warmupPeriod } }""",
        "migratorAddedEvents": """{ migratorAddedEvents(first:1000,orderBy:blockTimestamp,orderDirection:asc,where:{blockTimestamp_gt:"TS"}) {
            id blockNumber blockTimestamp transactionHash migrator } }""",
        "migratorRemovedEvents": """{ migratorRemovedEvents(first:1000,orderBy:blockTimestamp,orderDirection:asc,where:{blockTimestamp_gt:"TS"}) {
            id blockNumber blockTimestamp transactionHash migrator } }""",
    },
    "bond-lifecycle": {
        "tokensReleasedEvents": """{ tokensReleasedEvents(first:1000,orderBy:blockTimestamp,orderDirection:asc,where:{blockTimestamp_gt:"TS"}) {
            id blockNumber blockTimestamp transactionHash bondId amount to } }""",
        "bondMigratedEvents": """{ bondMigratedEvents(first:1000,orderBy:blockTimestamp,orderDirection:asc,where:{blockTimestamp_gt:"TS"}) {
            id blockNumber blockTimestamp transactionHash bondId fromPool toPool amount } }""",
        "vestingUpdatedEvents": """{ vestingUpdatedEvents(first:1000,orderBy:blockTimestamp,orderDirection:asc,where:{blockTimestamp_gt:"TS"}) {
            id blockNumber blockTimestamp transactionHash bondId vestingEnd } }""",
        "vestedTokenClawedEvents": """{ vestedTokenClawedEvents(first:1000,orderBy:blockTimestamp,orderDirection:asc,where:{blockTimestamp_gt:"TS"}) {
            id blockNumber blockTimestamp transactionHash bondId amount } }""",
    },
    "bond-broken": {
        "bondBrokenEvents": """{ bondBrokenEvents(first:1000,orderBy:blockTimestamp,orderDirection:asc,where:{blockTimestamp_gt:"TS"}) {
            id blockNumber blockTimestamp transactionHash bondId amount owner date } }""",
    },
    "nft-transfers": {
        "nftTransferEvents": """{ nftTransferEvents(first:1000,orderBy:blockTimestamp,orderDirection:asc,where:{blockTimestamp_gt:"TS"}) {
            id blockNumber blockTimestamp transactionHash from to tokenId transferCount } }""",
    },
    "bond-timemarker": {
        "bondTimeMarkerEvents": """{ bondTimeMarkerEvents(first:1000,orderBy:blockTimestamp,orderDirection:asc,where:{blockTimestamp_gt:"TS"}) {
            id blockNumber blockTimestamp transactionHash bondId timeMarker amount poolId } }""",
    },
    "bond-created": {
        "bondCreatedEvents": """{ bondCreatedEvents(first:1000,orderBy:blockTimestamp,orderDirection:asc,where:{blockTimestamp_gt:"TS"}) {
            id blockNumber blockTimestamp transactionHash bondId amount owner poolId } }""",
        "bondIncreasedEvents": """{ bondIncreasedEvents(first:1000,orderBy:blockTimestamp,orderDirection:asc,where:{blockTimestamp_gt:"TS"}) {
            id blockNumber blockTimestamp transactionHash bondId amount owner poolId } }""",
    },
}


def gql(endpoint, query, is_ormi=False, max_429_retries=8):
    """
    Execute a GraphQL query with robust retry logic.
    - 429: progressive backoff (30s → 60s → 90s … max 120s), up to max_429_retries.
    - Other failures: exponential backoff, 4 retries.
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
                print(f"    GQL error: {data['errors'][0].get('message','?')}", flush=True)
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
                    return None
                wait = 2 ** (network_retries - 1)
                print(f"    HTTP {e.code} — retry {network_retries}/4 in {wait}s", flush=True)
                time.sleep(wait)

        except Exception as e:
            network_retries += 1
            if network_retries > 4:
                print(f"    Network error — giving up ({e})", flush=True)
                return None
            wait = 2 ** (network_retries - 1)
            print(f"    Error ({e}) — retry {network_retries}/4 in {wait}s", flush=True)
            time.sleep(wait)


def fetch_new(subgraph_name, endpoint, entity, query_tpl, ts_cutoff, is_ormi=False):
    """
    Fetch all new records since ts_cutoff for one entity.
    Uses blockTimestamp_gt cursor pagination to avoid skip > 5000 limits.
    """
    results   = []
    cursor_ts = ts_cutoff
    page      = 0
    page_sleep = 6 if is_ormi else 0.4

    while True:
        q = query_tpl.replace("TS", str(cursor_ts))
        data = gql(endpoint, q, is_ormi=is_ormi)
        if data is None:
            break

        items = data.get(entity, [])
        if not items:
            break

        results.extend(items)
        page += 1
        print(f"    [{subgraph_name}:{entity}] page {page}: +{len(items)}", flush=True)

        if len(items) < 1000:
            break

        # Advance cursor to last item's timestamp to avoid skip > 5000
        cursor_ts = items[-1]["blockTimestamp"]
        time.sleep(page_sleep)

    return results


def merge(existing, new_items):
    """Merge new items into existing list, dedup by id. Returns count added."""
    existing_ids = {item["id"] for item in existing}
    added = 0
    for item in new_items:
        if item["id"] not in existing_ids:
            existing.append(item)
            existing_ids.add(item["id"])
            added += 1
    return added


def update_subgraph(name, endpoint, entities_queries, output_dir, days_back=8):
    path       = os.path.join(output_dir, f"{name}.json")
    is_ormi    = "ormilabs" in endpoint
    ts_cutoff  = int((datetime.now(timezone.utc) - timedelta(days=days_back)).timestamp())

    # Ormi: pause before hitting API
    if is_ormi:
        print(f"  [Ormi] pausing 10s before update to reduce 429 risk…", flush=True)
        time.sleep(10)

    # Load existing JSON
    if os.path.exists(path):
        with open(path) as f:
            existing = json.load(f)
        data = existing.get("data", {})
    else:
        print(f"  [{name}] No existing JSON — run bootstrap first", flush=True)
        data = {}

    total_added  = 0
    inter_sleep  = 8 if is_ormi else 0.5

    for entity, query_tpl in entities_queries.items():
        if entity not in data:
            data[entity] = []
        print(f"  → {entity} (existing: {len(data[entity])})", flush=True)

        new_items = fetch_new(name, endpoint, entity, query_tpl, ts_cutoff, is_ormi=is_ormi)
        added     = merge(data[entity], new_items)
        total_added += added
        print(f"    +{added} new (total: {len(data[entity])})", flush=True)
        time.sleep(inter_sleep)

    ts = datetime.now(timezone.utc).isoformat()
    out = {
        "subgraph":   name,
        "scraped_at": ts,
        "bootstrap":  False,
        "counts":     {e: len(v) for e, v in data.items()},
        "data":       data,
    }
    with open(path, "w") as f:
        json.dump(out, f, separators=(",", ":"))

    size_kb = os.path.getsize(path) // 1024
    print(f"  ✓ {path} updated — +{total_added} new events — {size_kb} KB", flush=True)


def main():
    args    = [a for a in sys.argv[1:] if not a.startswith("--")]
    targets = args if args else list(QUERIES_INCR.keys())
    out_dir = "rize-governance-hub"
    os.makedirs(out_dir, exist_ok=True)

    print(f"Governance incremental update — {datetime.now(timezone.utc).isoformat()}", flush=True)

    for name in targets:
        if name not in QUERIES_INCR:
            print(f"Unknown: {name}", flush=True)
            continue
        print(f"\n{'='*52}", flush=True)
        print(f"UPDATE: {name}", flush=True)
        update_subgraph(name, ENDPOINTS[name], QUERIES_INCR[name], out_dir)

    print(f"\nDone at {datetime.now(timezone.utc).isoformat()}", flush=True)


if __name__ == "__main__":
    main()
