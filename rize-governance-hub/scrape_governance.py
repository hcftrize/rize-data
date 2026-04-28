#!/usr/bin/env python3
"""
Bootstrap scraper — ALL 6 RIZE governance subgraphs.
Full erasure + rewrite on each run.
Usage:
  python3 scrape_governance.py                  # all 6
  python3 scrape_governance.py bond-broken      # single
v6 — 30s entre chaque query Ormi (au lieu de 120s)
"""
import json, time, sys, os, urllib.request, urllib.error
from datetime import datetime, timezone

ORMI_API_KEY   = os.environ.get("ORMI_API_KEY", "")
ORMI_API_KEY_2 = os.environ.get("ORMI_API_KEY_2", "")

ENDPOINTS = {
    "pool-config":     "https://api.goldsky.com/api/public/project_cmocpxhlpgzgs01y06xr9dto2/subgraphs/tokerize-pool-config/1.0.0/gn",
    "bond-lifecycle":  "https://api.goldsky.com/api/public/project_cmocnm0h8gx3n01y7hpoe4kxv/subgraphs/tokerize-bond-lifecycle/1.0.0/gn",
    "bond-broken":     "https://api.goldsky.com/api/public/project_cmocqkq31mv0m010y19bu6obd/subgraphs/tokerize-bond-broken/1.0.0/gn",
    "nft-transfers":   "https://api.goldsky.com/api/public/project_cmocqwx6tnlbf010yce109jo9/subgraphs/tokerize-nft-transfers/1.0.0/gn",
    "bond-timemarker": "https://api.subgraph.ormilabs.com/api/private/ac2ecb60-44a8-4df2-83cb-08bd1bced775/subgraphs/tokerize-bond-timemarker/scraper/gn",
    "bond-created":    "https://api.subgraph.ormilabs.com/api/private/a9ede79c-2a5c-4bb8-9208-ac30662368b5/subgraphs/tokerize-bond-created/ormiunusable/gn",
}

ORMI_KEYS = {
    "bond-timemarker": ORMI_API_KEY_2,
    "bond-created":    ORMI_API_KEY,
}

ENTITIES = {
    "pool-config": {
        "pools":                     "id poolId baseWeight maturedWeightBonus fullMaturity updatedAtDate updatedAtTimestamp",
        "poolUpdatedEvents":         "id poolId baseWeight maturedWeightBonus fullMaturity date blockNumber timestamp txHash",
        "releaseWarmupUpdatedEvents":"id value date blockNumber timestamp txHash",
        "migratorAddedEvents":       "id migrator date blockNumber timestamp txHash",
        "migratorRemovedEvents":     "id migrator date blockNumber timestamp txHash",
    },
    "bond-lifecycle": {
        "tokensReleasedEvents":    "id nftId to amount date blockNumber timestamp txHash",
        "bondMigratedEvents":      "id nftId toPool migrator date blockNumber timestamp txHash",
        "vestingUpdatedEvents":    "id nftId amount cliff vesting start date blockNumber timestamp txHash",
        "vestedTokenClawedEvents": "id nftId amount to date blockNumber timestamp txHash",
    },
    "bond-broken": {
        "bondBrokenEvents": "id nftId amount date blockNumber timestamp txHash",
    },
    "nft-transfers": {
        "nftTransferEvents": "id tokenId from to isMint date blockNumber timestamp txHash",
        "bondOwners":        "id tokenId owner mintDate mintTimestamp lastTransferDate lastTransferTimestamp transferCount",
    },
    "bond-timemarker": {
        "bondTimeMarkerSnapshots": "id nftId timeMarker amount poolId blockNumber timestamp",
    },
    "bond-created": {
        "bondCreatedEvents":  "id nftId owner poolId amount date blockNumber timestamp txHash",
        "increaseBondEvents": "id nftId amount date blockNumber timestamp txHash",
        "bonds":              "id nftId owner poolId createdAtDate createdAtTimestamp createdAtBlock totalDeposited increaseCount lastDepositDate lastDepositTimestamp",
    },
}

SNAPSHOT_ENTITIES = {"pools", "bondOwners", "bondTimeMarkerSnapshots", "bonds"}

HEADERS_BASE = {
    "Content-Type": "application/json",
    "Accept":       "application/json",
    "User-Agent":   "Mozilla/5.0 (compatible; TokerizeBot/1.0; +https://tokerize.top)",
    "Origin":       "https://tokerize.top",
    "Referer":      "https://tokerize.top/",
}

# ── Délais Ormi ───────────────────────────────────────────────────────────────
ORMI_PAUSE_BEFORE_QUERY = 60   # secondes entre chaque requête Ormi
ORMI_PAUSE_429          = 60   # secondes d'attente sur 429
ORMI_PAUSE_INTER_ENTITY = 60   # secondes entre entités Ormi

def get_headers(subgraph_name=None):
    h = dict(HEADERS_BASE)
    if subgraph_name and subgraph_name in ORMI_KEYS:
        key = ORMI_KEYS[subgraph_name]
        if key:
            h["Authorization"] = f"Bearer {key}"
    return h

def gql(endpoint, query, subgraph_name=None, is_ormi=False):
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
                print(f"    429 — retry #{rate_tries}, waiting {ORMI_PAUSE_429}s…", flush=True)
                time.sleep(ORMI_PAUSE_429)
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

def ormi_discover(endpoint, subgraph_name):
    print(f"    [Ormi] pause {ORMI_PAUSE_BEFORE_QUERY}s avant introspection…", flush=True)
    time.sleep(ORMI_PAUSE_BEFORE_QUERY)
    q = "{ __schema { queryType { fields { name } } } }"
    data = gql(endpoint, q, subgraph_name=subgraph_name, is_ormi=True)
    if not data:
        print(f"    [Ormi] introspection échouée — noms hardcodés utilisés", flush=True)
        return {}
    fields = data.get("__schema", {}).get("queryType", {}).get("fields", [])
    names  = [f["name"] for f in fields if not f["name"].startswith("_")]
    print(f"    [Ormi] entités: {names}", flush=True)
    return {n.lower(): n for n in names}

def resolve_name(want, confirmed):
    if not confirmed:
        return want
    return confirmed.get(want.lower(), want)

def fetch_entity(endpoint, entity_name, fields_str, subgraph_name=None, is_ormi=False):
    is_snapshot  = entity_name in SNAPSHOT_ENTITIES
    order_by     = "id" if is_snapshot else "timestamp"
    cursor_field = "id" if is_snapshot else "timestamp"
    results = []
    cursor  = None
    page    = 0
    while True:
        where_clause = "" if cursor is None else f', where: {{{cursor_field}_gt: "{cursor}"}}'
        q = (
            f"{{ {entity_name}("
            f"first:1000"
            f"{where_clause}, "
            f"orderBy:{order_by}, orderDirection:asc"
            f") {{ {fields_str} }} }}"
        )
        if is_ormi:
            print(f"      [Ormi] pause {ORMI_PAUSE_BEFORE_QUERY}s avant page {page+1}…", flush=True)
            time.sleep(ORMI_PAUSE_BEFORE_QUERY)
        data = gql(endpoint, q, subgraph_name=subgraph_name, is_ormi=is_ormi)
        if data is None:
            print(f"      fetch failed (page {page}), stopping", flush=True)
            break
        items = data.get(entity_name, [])
        if not items:
            break
        seen_ids  = {r["id"] for r in results}
        new_items = [i for i in items if i["id"] not in seen_ids]
        results.extend(new_items)
        page += 1
        print(f"      page={page:>3}: +{len(new_items):>4} → total {len(results)}", flush=True)
        if len(items) < 1000:
            break
        cursor = items[-1][cursor_field]
        if not is_ormi:
            time.sleep(0.5)
    return results

def fetch_subgraph(name, endpoint, entities):
    is_ormi  = "ormilabs" in endpoint
    provider = "Ormi" if is_ormi else "Goldsky"
    print(f"\n{'='*62}", flush=True)
    print(f"  SUBGRAPH: {name}  [{provider}]", flush=True)
    confirmed = ormi_discover(endpoint, name) if is_ormi else {}
    result_data = {}
    for entity_name, fields_str in entities.items():
        real_name = resolve_name(entity_name, confirmed)
        label     = f"{entity_name} → {real_name}" if real_name != entity_name else entity_name
        print(f"  → {label}", flush=True)
        items = fetch_entity(endpoint, real_name, fields_str, subgraph_name=name, is_ormi=is_ormi)
        result_data[real_name] = items
        print(f"     ✓ {len(items)} records", flush=True)
        if is_ormi:
            print(f"     [Ormi] pause {ORMI_PAUSE_INTER_ENTITY}s entre entités…", flush=True)
            time.sleep(ORMI_PAUSE_INTER_ENTITY)
        else:
            time.sleep(0.8)
    return result_data

def main():
    args    = [a for a in sys.argv[1:] if not a.startswith("--")]
    targets = args if args else list(ENTITIES.keys())
    out_dir = "rize-governance-hub"
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    print(f"Governance bootstrap v6 — {ts}", flush=True)
    print(f"Targets: {targets}", flush=True)
    print(f"Ormi delays: {ORMI_PAUSE_BEFORE_QUERY}s/query, {ORMI_PAUSE_429}s/429, {ORMI_PAUSE_INTER_ENTITY}s/entity", flush=True)
    for name in targets:
        if name not in ENTITIES:
            print(f"Unknown subgraph: {name}", flush=True)
            continue
        data = fetch_subgraph(name, ENDPOINTS[name], ENTITIES[name])
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
