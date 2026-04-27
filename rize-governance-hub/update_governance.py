#!/usr/bin/env python3
"""
Daily incremental updater — merges new events (last 8 days) into existing JSONs.
Usage:
  python3 update_governance.py              # all 6
  python3 update_governance.py bond-broken  # single

v5 — endpoints Ormi privés avec Authorization: Bearer
  - bond-created    → ORMI_API_KEY
  - bond-timemarker → ORMI_API_KEY_2
  - orderBy:timestamp, filtre where:{timestamp_gt:"TS"}
  - nftId, txHash, timestamp (pas blockTimestamp/transactionHash/bondId)
"""

import json, time, sys, os, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

ORMI_API_KEY   = os.environ.get("ORMI_API_KEY", "")    # bond-created
ORMI_API_KEY_2 = os.environ.get("ORMI_API_KEY_2", "")  # bond-timemarker

ENDPOINTS = {
    "pool-config":     "https://api.goldsky.com/api/public/project_cmocpxhlpgzgs01y06xr9dto2/subgraphs/tokerize-pool-config/1.0.0/gn",
    "bond-lifecycle":  "https://api.goldsky.com/api/public/project_cmocnm0h8gx3n01y7hpoe4kxv/subgraphs/tokerize-bond-lifecycle/1.0.0/gn",
    "bond-broken":     "https://api.goldsky.com/api/public/project_cmocqkq31mv0m010y19bu6obd/subgraphs/tokerize-bond-broken/1.0.0/gn",
    "nft-transfers":   "https://api.goldsky.com/api/public/project_cmocqwx6tnlbf010yce109jo9/subgraphs/tokerize-nft-transfers/1.0.0/gn",
    "bond-timemarker": "https://api.subgraph.ormilabs.com/api/private/ac2ecb60-44a8-4df2-83cb-08bd1bced775/subgraphs/tokerize-bond-timemarker/scraper/gn",
    "bond-created":    "https://api.subgraph.ormilabs.com/api/private/a9ede79c-2a5c-4bb8-9208-ac30662368b5/subgraphs/tokerize-bond-created/v3/gn",
}

ORMI_KEYS = {
    "bond-timemarker": ORMI_API_KEY_2,
    "bond-created":    ORMI_API_KEY,
}

HEADERS_BASE = {
    "Content-Type": "application/json",
    "Accept":       "application/json",
    "User-Agent":   "Mozilla/5.0 (compatible; TokerizeBot/1.0; +https://tokerize.top)",
    "Origin":       "https://tokerize.top",
    "Referer":      "https://tokerize.top/",
}

def get_headers(subgraph_name=None):
    h = dict(HEADERS_BASE)
    if subgraph_name and subgraph_name in ORMI_KEYS:
        key = ORMI_KEYS[subgraph_name]
        if key:
            h["Authorization"] = f"Bearer {key}"
    return h

QUERIES_INCR = {
    "pool-config": {
        "pools": {
            "mode": "snapshot",
            "query": "{ pools(first:1000, orderBy:id, orderDirection:asc) { id poolId baseWeight maturedWeightBonus fullMaturity updatedAtDate updatedAtTimestamp } }",
        },
        "poolUpdatedEvents": {
            "mode": "incremental",
            "query": '{ poolUpdatedEvents(first:1000,orderBy:timestamp,orderDirection:asc,where:{timestamp_gt:"TS"}) { id poolId baseWeight maturedWeightBonus fullMaturity date blockNumber timestamp txHash } }',
        },
        "releaseWarmupUpdatedEvents": {
            "mode": "incremental",
            "query": '{ releaseWarmupUpdatedEvents(first:1000,orderBy:timestamp,orderDirection:asc,where:{timestamp_gt:"TS"}) { id value date blockNumber timestamp txHash } }',
        },
        "migratorAddedEvents": {
            "mode": "incremental",
            "query": '{ migratorAddedEvents(first:1000,orderBy:timestamp,orderDirection:asc,where:{timestamp_gt:"TS"}) { id migrator date blockNumber timestamp txHash } }',
        },
        "migratorRemovedEvents": {
            "mode": "incremental",
            "query": '{ migratorRemovedEvents(first:1000,orderBy:timestamp,orderDirection:asc,where:{timestamp_gt:"TS"}) { id migrator date blockNumber timestamp txHash } }',
        },
    },
    "bond-lifecycle": {
        "tokensReleasedEvents": {
            "mode": "incremental",
            "query": '{ tokensReleasedEvents(first:1000,orderBy:timestamp,orderDirection:asc,where:{timestamp_gt:"TS"}) { id nftId to amount date blockNumber timestamp txHash } }',
        },
        "bondMigratedEvents": {
            "mode": "incremental",
            "query": '{ bondMigratedEvents(first:1000,orderBy:timestamp,orderDirection:asc,where:{timestamp_gt:"TS"}) { id nftId toPool migrator date blockNumber timestamp txHash } }',
        },
        "vestingUpdatedEvents": {
            "mode": "incremental",
            "query": '{ vestingUpdatedEvents(first:1000,orderBy:timestamp,orderDirection:asc,where:{timestamp_gt:"TS"}) { id nftId amount cliff vesting start date blockNumber timestamp txHash } }',
        },
        "vestedTokenClawedEvents": {
            "mode": "incremental",
            "query": '{ vestedTokenClawedEvents(first:1000,orderBy:timestamp,orderDirection:asc,where:{timestamp_gt:"TS"}) { id nftId amount to date blockNumber timestamp txHash } }',
        },
    },
    "bond-broken": {
        "bondBrokenEvents": {
            "mode": "incremental",
            "query": '{ bondBrokenEvents(first:1000,orderBy:timestamp,orderDirection:asc,where:{timestamp_gt:"TS"}) { id nftId amount date blockNumber timestamp txHash } }',
        },
    },
    "nft-transfers": {
        "nftTransferEvents": {
            "mode": "incremental",
            "query": '{ nftTransferEvents(first:1000,orderBy:timestamp,orderDirection:asc,where:{timestamp_gt:"TS"}) { id tokenId from to isMint date blockNumber timestamp txHash } }',
        },
        "bondOwners": {
            "mode": "snapshot",
            "query": "{ bondOwners(first:1000, orderBy:id, orderDirection:asc) { id tokenId owner mintDate mintTimestamp lastTransferDate lastTransferTimestamp transferCount } }",
        },
    },
    "bond-timemarker": {
        "bondTimeMarkerSnapshots": {
            "mode": "snapshot",
            "query": "{ bondTimeMarkerSnapshots(first:1000, orderBy:id, orderDirection:asc) { id nftId timeMarker amount poolId blockNumber timestamp } }",
        },
    },
    "bond-created": {
        "bondCreatedEvents": {
            "mode": "incremental",
            "query": '{ bondCreatedEvents(first:1000,orderBy:timestamp,orderDirection:asc,where:{timestamp_gt:"TS"}) { id nftId owner poolId amount date blockNumber timestamp txHash } }',
        },
        "increaseBondEvents": {
            "mode": "incremental",
            "query": '{ increaseBondEvents(first:1000,orderBy:timestamp,orderDirection:asc,where:{timestamp_gt:"TS"}) { id nftId amount date blockNumber timestamp txHash } }',
        },
        "bonds": {
            "mode": "snapshot",
            "query": "{ bonds(first:1000, orderBy:id, orderDirection:asc) { id nftId owner poolId createdAtDate createdAtTimestamp createdAtBlock totalDeposited increaseCount lastDepositDate lastDepositTimestamp } }",
        },
    },
}


# ── HTTP / GQL ────────────────────────────────────────────────────────────────

def gql(endpoint, query, subgraph_name=None, is_ormi=False, max_429=10):
    payload = json.dumps({"query": query}).encode()
    req = urllib.request.Request(endpoint, data=payload, headers=get_headers(subgraph_name), method="POST")
    net_tries  = 0
    rate_tries = 0

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
                rate_tries += 1
                if rate_tries > max_429:
                    print(f"    429 — max retries, giving up", flush=True)
                    return None
                wait = min(30 * rate_tries, 180)
                print(f"    429 — retry {rate_tries}/{max_429} in {wait}s…", flush=True)
                time.sleep(wait)
            else:
                net_tries += 1
                if net_tries > 4:
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

def fetch_incremental(entity, query_tpl, ts_cutoff, endpoint, subgraph_name=None, is_ormi=False):
    results   = []
    cursor_ts = ts_cutoff
    page      = 0

    while True:
        q = query_tpl.replace("TS", str(cursor_ts))
        if is_ormi and page > 0:
            time.sleep(10)
        data = gql(endpoint, q, subgraph_name=subgraph_name, is_ormi=is_ormi)
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
        if not is_ormi:
            time.sleep(0.5)

    return results


def fetch_snapshot(entity, endpoint, fields_str, subgraph_name=None, is_ormi=False):
    results = []
    cursor  = None
    page    = 0

    while True:
        where = f', where: {{id_gt: "{cursor}"}}' if cursor else ""
        q = f"{{ {entity}(first:1000{where}, orderBy:id, orderDirection:asc) {{ {fields_str} }} }}"
        if is_ormi and page > 0:
            time.sleep(10)
        data = gql(endpoint, q, subgraph_name=subgraph_name, is_ormi=is_ormi)
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
        if not is_ormi:
            time.sleep(0.5)

    return results


def merge(existing, new_items):
    existing_ids = {item["id"] for item in existing}
    added = 0
    for item in new_items:
        if item["id"] not in existing_ids:
            existing.append(item)
            existing_ids.add(item["id"])
            added += 1
    return added


# ── Per-subgraph update ───────────────────────────────────────────────────────

def update_subgraph(name, endpoint, entities_cfg, out_dir, days_back=8):
    path      = os.path.join(out_dir, f"{name}.json")
    is_ormi   = "ormilabs" in endpoint
    ts_cutoff = int((datetime.now(timezone.utc) - timedelta(days=days_back)).timestamp())

    if is_ormi:
        print(f"  [Ormi] pause 2s avant update…", flush=True)
        time.sleep(2)

    if os.path.exists(path):
        with open(path) as f:
            existing = json.load(f)
        data = existing.get("data", {})
    else:
        print(f"  [{name}] Pas de JSON existant — lance le bootstrap d'abord", flush=True)
        data = {}

    total_added = 0
    inter_sleep = 1.2 if is_ormi else 0.8

    for entity, cfg in entities_cfg.items():
        mode  = cfg["mode"]
        query = cfg["query"]

        if entity not in data:
            data[entity] = []

        print(f"  → {entity} [{mode}] (existant: {len(data[entity])})", flush=True)

        if mode == "snapshot":
            import re
            m = re.search(r'\{[^{]*\{([^}]+)\}', query)
            fields_str = m.group(1).strip() if m else "id"
            new_items    = fetch_snapshot(entity, endpoint, fields_str, subgraph_name=name, is_ormi=is_ormi)
            data[entity] = new_items
            print(f"    snapshot refreshed: {len(new_items)} records", flush=True)
        else:
            new_items = fetch_incremental(entity, query, ts_cutoff, endpoint, subgraph_name=name, is_ormi=is_ormi)
            added     = merge(data[entity], new_items)
            total_added += added
            print(f"    +{added} nouveaux (total: {len(data[entity])})", flush=True)

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
    print(f"  ✓ {path} — +{total_added} nouveaux events — {size_kb} KB", flush=True)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    args    = [a for a in sys.argv[1:] if not a.startswith("--")]
    targets = args if args else list(QUERIES_INCR.keys())
    out_dir = "rize-governance-hub"
    os.makedirs(out_dir, exist_ok=True)

    print(f"Governance incremental update v5 — {datetime.now(timezone.utc).isoformat()}", flush=True)

    for name in targets:
        if name not in QUERIES_INCR:
            print(f"Unknown: {name}", flush=True)
            continue
        print(f"\n{'='*52}", flush=True)
        print(f"UPDATE: {name}", flush=True)
        update_subgraph(name, ENDPOINTS[name], QUERIES_INCR[name], out_dir)

    print(f"\nDone — {datetime.now(timezone.utc).isoformat()}", flush=True)


if __name__ == "__main__":
    main()
