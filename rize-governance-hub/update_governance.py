#!/usr/bin/env python3
"""
Daily incremental updater — appends new records into the 6 governance JSONs.
Queries the unified Goldsky subgraph (tokerize-governance-unified).

Usage:
  python3 update_governance.py              # all 6
  python3 update_governance.py bond-broken  # single

v1-unified — migrated from 6 Ormi/Goldsky endpoints to single Goldsky endpoint.
  - snapshot entities  (pools, bonds, bondOwners): full refresh, upsert by id
  - incremental entities (all events): append where timestamp_gt last known
"""

import json, time, sys, os, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

GOLDSKY_API_KEY = os.environ.get("GOLDSKY_API_KEY", "")

# ── Endpoint ──────────────────────────────────────────────────────────────────
# Update version tag here if you redeploy the subgraph with a new version.
UNIFIED_ENDPOINT = (
    "https://api.goldsky.com/api/public/"
    "project_cmoa6u5wk3kx201y4g3s52z77/"
    "subgraphs/tokerize-governance-unified/1.0.0/gn"
)

HEADERS = {
    "Content-Type": "application/json",
    "Accept":       "application/json",
    "User-Agent":   "Mozilla/5.0 (compatible; TokerizeBot/1.0; +https://tokerize.top)",
    "Origin":       "https://tokerize.top",
    "Referer":      "https://tokerize.top/",
    "Authorization": f"Bearer {GOLDSKY_API_KEY}",
}

# ── Entity config ─────────────────────────────────────────────────────────────
# mode "incremental": append where timestamp_gt last known timestamp
# mode "snapshot":    full refresh, upsert by id (state entities)

QUERIES = {
    "pool-config": {
        "pools": {
            "mode":   "snapshot",
            "fields": "id poolId baseWeight maturedWeightBonus fullMaturity updatedAtDate updatedAtTimestamp",
        },
        "poolUpdatedEvents": {
            "mode":   "incremental",
            "fields": "id poolId baseWeight maturedWeightBonus fullMaturity date blockNumber timestamp txHash",
        },
        "releaseWarmupUpdatedEvents": {
            "mode":   "incremental",
            "fields": "id value date blockNumber timestamp txHash",
        },
        "migratorAddedEvents": {
            "mode":   "incremental",
            "fields": "id migrator date blockNumber timestamp txHash",
        },
        "migratorRemovedEvents": {
            "mode":   "incremental",
            "fields": "id migrator date blockNumber timestamp txHash",
        },
    },
    "bond-lifecycle": {
        "tokensReleasedEvents": {
            "mode":   "incremental",
            "fields": "id nftId to amount date blockNumber timestamp txHash",
        },
        "bondMigratedEvents": {
            "mode":   "incremental",
            "fields": "id nftId toPool migrator date blockNumber timestamp txHash",
        },
        "vestingUpdatedEvents": {
            "mode":   "incremental",
            "fields": "id nftId amount cliff vesting start date blockNumber timestamp txHash",
        },
        "vestedTokenClawedEvents": {
            "mode":   "incremental",
            "fields": "id nftId amount to date blockNumber timestamp txHash",
        },
    },
    "bond-broken": {
        "bondBrokenEvents": {
            "mode":   "incremental",
            "fields": "id nftId amount date blockNumber timestamp txHash",
        },
    },
    "nft-transfers": {
        "nftTransferEvents": {
            "mode":   "incremental",
            "fields": "id tokenId from to isMint date blockNumber timestamp txHash",
        },
        "bondOwners": {
            "mode":   "snapshot",
            "fields": "id tokenId owner mintDate mintTimestamp lastTransferDate lastTransferTimestamp transferCount",
        },
    },
    "bond-timemarker": {
        "bondTimeMarkerSnapshots": {
            "mode":   "incremental",
            "fields": "id nftId timeMarker amount poolId blockNumber timestamp",
        },
    },
    "bond-created": {
        "bondCreatedEvents": {
            "mode":   "incremental",
            "fields": "id nftId owner poolId amount date blockNumber timestamp txHash",
        },
        "increaseBondEvents": {
            "mode":   "incremental",
            "fields": "id nftId amount date blockNumber timestamp txHash",
        },
        "bonds": {
            "mode":   "snapshot",
            "fields": "id nftId owner poolId createdAtDate createdAtTimestamp createdAtBlock totalDeposited increaseCount lastDepositDate lastDepositTimestamp",
        },
    },
}

# ── HTTP / GQL ────────────────────────────────────────────────────────────────

def gql(query, max_429=10):
    payload = json.dumps({"query": query}).encode()
    req = urllib.request.Request(
        UNIFIED_ENDPOINT, data=payload, headers=HEADERS, method="POST"
    )
    net_tries  = 0
    rate_tries = 0
    while True:
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                data = json.loads(r.read())
            if "errors" in data:
                print(f"    GQL error: {data['errors'][0].get('message', '?')}", flush=True)
                return None
            return data.get("data", {})
        except urllib.error.HTTPError as e:
            if e.code == 429:
                rate_tries += 1
                if rate_tries > max_429:
                    print(f"    429 — max retries reached, giving up", flush=True)
                    return None
                wait = min(30 * rate_tries, 180)
                print(f"    429 — retry {rate_tries}/{max_429} in {wait}s…", flush=True)
                time.sleep(wait)
            else:
                net_tries += 1
                if net_tries > 4:
                    print(f"    HTTP {e.code} — giving up", flush=True)
                    return None
                wait = 2 ** (net_tries - 1)
                print(f"    HTTP {e.code} — retry {net_tries}/4 in {wait}s", flush=True)
                time.sleep(wait)
        except Exception as e:
            net_tries += 1
            if net_tries > 4:
                print(f"    Error — giving up ({e})", flush=True)
                return None
            wait = 2 ** (net_tries - 1)
            print(f"    Error ({e}) — retry {net_tries}/4 in {wait}s", flush=True)
            time.sleep(wait)

# ── Fetch helpers ─────────────────────────────────────────────────────────────

def fetch_incremental(entity, fields, ts_cutoff):
    """Fetch all records with timestamp > ts_cutoff, paginating."""
    results   = []
    cursor_ts = str(ts_cutoff)
    page      = 0
    while True:
        q = (
            f'{{ {entity}('
            f'first:1000, orderBy:timestamp, orderDirection:asc, '
            f'where:{{timestamp_gt:"{cursor_ts}"}}'
            f') {{ {fields} }} }}'
        )
        data = gql(q)
        if data is None:
            break
        items = data.get(entity, [])
        if not items:
            break
        results.extend(items)
        page += 1
        print(f"    [{entity}] page {page}: +{len(items)}", flush=True)
        if len(items) < 1000:
            break
        cursor_ts = items[-1]["timestamp"]
        time.sleep(0.3)
    return results


def fetch_snapshot(entity, fields):
    """Full fetch of a state entity, paginating by id."""
    results = []
    cursor  = None
    page    = 0
    while True:
        where = f', where:{{id_gt:"{cursor}"}}' if cursor else ""
        q = (
            f"{{ {entity}("
            f"first:1000{where}, orderBy:id, orderDirection:asc"
            f") {{ {fields} }} }}"
        )
        data = gql(q)
        if data is None:
            break
        items = data.get(entity, [])
        if not items:
            break
        results.extend(items)
        page += 1
        print(f"    [{entity}] snapshot page {page}: +{len(items)} → total {len(results)}", flush=True)
        if len(items) < 1000:
            break
        cursor = items[-1]["id"]
        time.sleep(0.3)
    return results

# ── Merge helpers ─────────────────────────────────────────────────────────────

def merge_append(existing, new_items):
    """Append new event records that don't already exist."""
    existing_ids = {item["id"] for item in existing}
    added = 0
    for item in new_items:
        if item["id"] not in existing_ids:
            existing.append(item)
            existing_ids.add(item["id"])
            added += 1
    return added


def merge_upsert(existing, new_items):
    """Upsert state records by id — update existing, append new."""
    existing_map = {item["id"]: item for item in existing}
    updated = added = 0
    for item in new_items:
        if item["id"] in existing_map:
            existing_map[item["id"]] = item
            updated += 1
        else:
            existing_map[item["id"]] = item
            added += 1
    return list(existing_map.values()), added, updated

# ── Per-subgraph update ───────────────────────────────────────────────────────

def get_last_timestamp(records):
    """Return the max timestamp already in the file as int, or 0."""
    if not records:
        return 0
    return max(int(r["timestamp"]) for r in records if "timestamp" in r)


def update_subgraph(name, entities_cfg, out_dir, days_back=9):
    path = os.path.join(out_dir, f"{name}.json")

    if os.path.exists(path):
        with open(path) as f:
            existing = json.load(f)
        data = existing.get("data", {})
    else:
        print(f"  [{name}] No existing JSON — run bootstrap first", flush=True)
        return 0

    # Fallback cutoff: now - days_back (safety net for empty entities)
    fallback_cutoff = int(
        (datetime.now(timezone.utc) - timedelta(days=days_back)).timestamp()
    )

    print(f"\n{'='*62}", flush=True)
    print(f"  UPDATE: {name}", flush=True)

    total_added = 0

    for entity, cfg in entities_cfg.items():
        mode   = cfg["mode"]
        fields = cfg["fields"]

        existing_records = data.get(entity, [])
        print(f"  → {entity} [{mode}] (existing: {len(existing_records)})", flush=True)

        if mode == "snapshot":
            new_items = fetch_snapshot(entity, fields)
            merged, added, updated = merge_upsert(existing_records, new_items)
            data[entity] = merged
            total_added += added
            print(f"     ✓ +{added} new, {updated} updated (total: {len(merged)})", flush=True)

        else:  # incremental
            last_ts = get_last_timestamp(existing_records)
            cutoff  = last_ts if last_ts > 0 else fallback_cutoff
            print(f"     last timestamp: {cutoff}", flush=True)
            new_items = fetch_incremental(entity, fields, cutoff)
            added     = merge_append(existing_records, new_items)
            data[entity] = existing_records
            total_added += added
            print(f"     ✓ +{added} new (total: {len(existing_records)})", flush=True)

        time.sleep(0.5)

    existing["updated_at"] = datetime.now(timezone.utc).isoformat()
    existing["counts"]     = {e: len(data.get(e, [])) for e in entities_cfg}
    existing["data"]       = data

    with open(path, "w") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)

    size_kb = os.path.getsize(path) // 1024
    print(f"\n  ✓ {path} — +{total_added} new records — {size_kb} KB", flush=True)
    return total_added

# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    args    = [a for a in sys.argv[1:] if not a.startswith("--")]
    targets = args if args else list(QUERIES.keys())
    out_dir = "rize-governance-hub"
    os.makedirs(out_dir, exist_ok=True)

    print(f"Governance updater v1-unified — {datetime.now(timezone.utc).isoformat()}", flush=True)
    print(f"Endpoint: {UNIFIED_ENDPOINT}", flush=True)
    print(f"Targets: {targets}", flush=True)

    grand_total = 0
    for name in targets:
        if name not in QUERIES:
            print(f"Unknown subgraph: {name}", flush=True)
            continue
        added = update_subgraph(name, QUERIES[name], out_dir)
        grand_total += added

    print(f"\nDone — {datetime.now(timezone.utc).isoformat()} | total new records: {grand_total}", flush=True)


if __name__ == "__main__":
    main()
