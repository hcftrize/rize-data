#!/usr/bin/env python3
"""
Bootstrap scraper — ALL 6 RIZE governance subgraphs.
Full erasure + rewrite on each run.
Usage:
  python3 scrape_governance.py                  # all 6
  python3 scrape_governance.py bond-broken      # single

v4 — champs hardcodés d'après introspection GraphQL réelle :
  - orderBy:timestamp partout (blockTimestamp n'existe pas)
  - nftId = bond NFT ID (pas bondId), txHash (pas transactionHash)
  - owner absent des events Goldsky (présent seulement dans bondOwners)
  - pool-config : entité 'pools' ajoutée (snapshot état actuel des pools)
  - Ormi : pauses longues + backoff progressif 429 (max 180s)
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

# Champs réels vérifiés par introspection directe sur chaque subgraph Goldsky.
# Ormi : convention identique supposée (nftId, timestamp, txHash).
# Entités sans timestamp (snapshots) : orderBy:id utilisé à la place.
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
    # Ormi — noms et champs supposés d'après convention Goldsky observée.
    # Si les noms sont faux, l'erreur GQL indiquera le vrai nom.
    "bond-timemarker": {
        "bondTimeMarkerEvents": "id nftId timeMarker amount poolId date blockNumber timestamp txHash",
    },
    "bond-created": {
        "bondCreatedEvents":   "id nftId amount owner poolId date blockNumber timestamp txHash",
        "bondIncreasedEvents": "id nftId amount owner poolId date blockNumber timestamp txHash",
    },
}

# Entités snapshot (pas d'events, pas de timestamp) → orderBy:id
SNAPSHOT_ENTITIES = {"pools", "bondOwners"}

HEADERS = {
    "Content-Type": "application/json",
    "Accept":       "application/json",
    "User-Agent":   "Mozilla/5.0 (compatible; TokerizeBot/1.0; +https://tokerize.top)",
    "Origin":       "https://tokerize.top",
    "Referer":      "https://tokerize.top/",
}


# ── HTTP / GQL ────────────────────────────────────────────────────────────────

def gql(endpoint, query, is_ormi=False, max_429=10):
    payload = json.dumps({"query": query}).encode()
    req = urllib.request.Request(endpoint, data=payload, headers=HEADERS, method="POST")
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
                    print(f"    429 — max retries ({max_429}), giving up", flush=True)
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


# ── Ormi : confirmer les noms d'entités si possible ──────────────────────────

def ormi_discover(endpoint):
    """
    Tente l'introspection Ormi pour confirmer les noms d'entités.
    Retourne dict lowercase→realname, ou {} si 429 persistant.
    """
    print(f"    [Ormi] pause 15s avant introspection…", flush=True)
    time.sleep(15)
    q = "{ __schema { queryType { fields { name } } } }"
    data = gql(endpoint, q, is_ormi=True, max_429=4)
    if not data:
        print(f"    [Ormi] introspection échouée — noms hardcodés utilisés", flush=True)
        return {}
    fields = data.get("__schema", {}).get("queryType", {}).get("fields", [])
    names  = [f["name"] for f in fields if not f["name"].startswith("_")]
    print(f"    [Ormi] entités: {names}", flush=True)
    return {n.lower(): n for n in names}


def resolve_name(want, confirmed):
    """Résout le vrai nom depuis le dict confirmed (lowercase→real), ou retourne want."""
    if not confirmed:
        return want
    return confirmed.get(want.lower(), want)


# ── Pagination cursor-based (timestamp_gt / id_gt) ───────────────────────────
# The Graph hard limit: skip > 5000 boucle ou échoue.
# On utilise un curseur sur le dernier timestamp/id vu → pas de limite.

def fetch_entity(endpoint, entity_name, fields_str, is_ormi=False):
    is_snapshot = entity_name in SNAPSHOT_ENTITIES
    order_by    = "id" if is_snapshot else "timestamp"
    cursor_field = "id" if is_snapshot else "timestamp"
    page_sleep  = 8 if is_ormi else 0.5

    results = []
    cursor  = None   # None = première page, pas de filtre
    page    = 0

    while True:
        # Filtre curseur : on prend tout ce qui est > dernier vu
        if cursor is None:
            where_clause = ""
        else:
            where_clause = f', where: {{{cursor_field}_gt: "{cursor}"}}'

        q = (
            f"{{ {entity_name}("
            f"first:1000"
            f"{where_clause}, "
            f"orderBy:{order_by}, orderDirection:asc"
            f") {{ {fields_str} }} }}"
        )
        data = gql(endpoint, q, is_ormi=is_ormi)

        if data is None:
            print(f"      fetch failed (page {page}), stopping", flush=True)
            break

        items = data.get(entity_name, [])
        if not items:
            break

        # Déduplique par id au cas où le curseur chevauche
        seen_ids = {r["id"] for r in results}
        new_items = [i for i in items if i["id"] not in seen_ids]
        results.extend(new_items)
        page += 1

        print(f"      page={page:>3}: +{len(new_items):>4} → total {len(results)}", flush=True)

        if len(items) < 1000:
            break  # dernière page

        # Avance le curseur sur la valeur du dernier item
        cursor = items[-1][cursor_field]
        time.sleep(page_sleep)

    return results


# ── Orchestration ─────────────────────────────────────────────────────────────

def fetch_subgraph(name, endpoint, entities):
    is_ormi  = "ormilabs" in endpoint
    provider = "Ormi" if is_ormi else "Goldsky"

    print(f"\n{'='*62}", flush=True)
    print(f"  SUBGRAPH: {name}  [{provider}]", flush=True)

    confirmed = ormi_discover(endpoint) if is_ormi else {}

    result_data = {}
    inter_sleep = 10 if is_ormi else 0.8

    for entity_name, fields_str in entities.items():
        real_name = resolve_name(entity_name, confirmed)
        label     = f"{entity_name} → {real_name}" if real_name != entity_name else entity_name
        print(f"  → {label}", flush=True)

        items = fetch_entity(endpoint, real_name, fields_str, is_ormi=is_ormi)
        result_data[real_name] = items
        print(f"     ✓ {len(items)} records", flush=True)
        time.sleep(inter_sleep)

    return result_data


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    args    = [a for a in sys.argv[1:] if not a.startswith("--")]
    targets = args if args else list(ENTITIES.keys())
    out_dir = "rize-governance-hub"
    os.makedirs(out_dir, exist_ok=True)

    ts = datetime.now(timezone.utc).isoformat()
    print(f"Governance bootstrap v4 — {ts}", flush=True)
    print(f"Targets: {targets}", flush=True)

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
