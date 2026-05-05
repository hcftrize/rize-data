#!/usr/bin/env python3
"""
Bootstrap scraper — ALL 6 RIZE governance subgraphs.
Full erasure + rewrite on each run.
Usage:
  python3 scrape_governance.py                  # all 6
  python3 scrape_governance.py bond-lifecycle   # single

v8 — CRITICAL FIX: cursor sur id (pas timestamp) pour tous les event entities.
     Avec cursor=timestamp, les events partageant le même timestamp (même bloc)
     étaient perdus silencieusement lors de la pagination.
     Fix: orderBy=id, cursor=id pour tous les entities sans exception.
     Autres fixes: dedup O(1) avec set persistent, écriture atomique.
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
    "bond-timemarker": "https://api.subgraph.ormilabs.com/api/public/ac2ecb60-44a8-4df2-83cb-08bd1bced775/subgraphs/tokerize-bond-timemarker/v2/gn",
    "bond-created":    "https://api.subgraph.ormilabs.com/api/private/a9ede79c-2a5c-4bb8-9208-ac30662368b5/subgraphs/tokerize-bond-created/ormiunusable/gn",
}

ORMI_KEYS = {
    "bond-created": ORMI_API_KEY,
}

ENTITIES = {
    "pool-config": {
        "pools":                      "id poolId baseWeight maturedWeightBonus fullMaturity updatedAtDate updatedAtTimestamp",
        "poolUpdatedEvents":          "id poolId baseWeight maturedWeightBonus fullMaturity date blockNumber timestamp txHash",
        "releaseWarmupUpdatedEvents": "id value date blockNumber timestamp txHash",
        "migratorAddedEvents":        "id migrator date blockNumber timestamp txHash",
        "migratorRemovedEvents":      "id migrator date blockNumber timestamp txHash",
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

# ── Délais Ormi ───────────────────────────────────────────────────────────────
ORMI_PAUSE_BEFORE_QUERY = 60
ORMI_PAUSE_429          = 60
ORMI_PAUSE_INTER_ENTITY = 60

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

def gql(endpoint, query, subgraph_name=None, is_ormi=False):
    payload = json.dumps({"query": query}).encode()
    req = urllib.request.Request(
        endpoint, data=payload, headers=get_headers(subgraph_name), method="POST"
    )
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
        except Exception as exc:
            net_tries += 1
            if net_tries > 4:
                print(f"    Error — giving up ({exc})", flush=True)
                return None
            wait = 2 ** (net_tries - 1)
            print(f"    Error ({exc}) — retry {net_tries}/4 in {wait}s", flush=True)
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
    # ── v8 CRITICAL FIX ───────────────────────────────────────────────────────
    # cursor=id pour TOUS les entities (event et snapshot confondus).
    #
    # Avant (v7): cursor=timestamp pour les events.
    # Problème: si N events partagent le même timestamp (même bloc),
    # la page suivante commence à timestamp_gt: T, excluant les N-1
    # autres events avec ce même timestamp. Perte silencieuse garantie.
    #
    # Fix: orderBy=id, cursor=id.
    # L'id GraphQL est toujours unique (txHash-logIndex ou similar).
    # Pagination 100% déterministe, zéro perte possible.
    # ─────────────────────────────────────────────────────────────────────────
    order_by     = "id"
    cursor_field = "id"

    results  = []
    seen_ids = set()  # set persistent O(1) — pas de rebuild à chaque page
    cursor   = None
    page     = 0

    while True:
        where_clause = (
            "" if cursor is None
            else f', where: {{{cursor_field}_gt: "{cursor}"}}'
        )
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

        # Dedup O(1) avec set persistent
        new_items = [i for i in items if i["id"] not in seen_ids]
        for item in new_items:
            seen_ids.add(item["id"])
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
    confirmed   = ormi_discover(endpoint, name) if is_ormi else {}
    result_data = {}
    for entity_name, fields_str in entities.items():
        real_name = resolve_name(entity_name, confirmed)
        label     = f"{entity_name} → {real_name}" if real_name != entity_name else entity_name
        print(f"  → {label}", flush=True)
        items = fetch_entity(
            endpoint, real_name, fields_str,
            subgraph_name=name, is_ormi=is_ormi
        )
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

    print(f"Governance bootstrap v8 — {ts}", flush=True)
    print(f"Targets:  {targets}", flush=True)
    print(f"Cursor:   id (v8 fix — no timestamp cursor, zero silent loss)", flush=True)
    print(f"Ormi delays: {ORMI_PAUSE_BEFORE_QUERY}s/query, {ORMI_PAUSE_429}s/429, {ORMI_PAUSE_INTER_ENTITY}s/entity", flush=True)

    for name in targets:
        if name not in ENTITIES:
            print(f"Unknown subgraph: {name}", flush=True)
            continue

        data = fetch_subgraph(name, ENDPOINTS[name], ENTITIES[name])
        out  = {
            "subgraph":   name,
            "scraped_at": ts,
            "bootstrap":  True,
            "counts":     {e: len(v) for e, v in data.items()},
            "data":       data,
        }

        path     = os.path.join(out_dir, f"{name}.json")
        tmp_path = path + ".tmp"

        # Écriture atomique: le fichier existant reste intact si crash en cours d'écriture
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)

        size_kb = os.path.getsize(path) // 1024
        print(f"\n  ✓ {path} — {size_kb} KB | {out['counts']}", flush=True)

    print(f"\nDone — {datetime.now(timezone.utc).isoformat()}", flush=True)

if __name__ == "__main__":
    main()
