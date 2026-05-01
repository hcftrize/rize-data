#!/usr/bin/env python3
"""
compute_bond_states.py
======================
Source of truth generator for bond states since genesis.

Reads the 6 existing governance JSONs and produces bond-states.json —
the 7th JSON containing the exact chronological state of every bond
at every event that changed its balance, timeMarker, maturity, boost or VP.

Called by:
  - bootstrap_bond_states.py  (one-time genesis run)
  - update-bond-states.yml    (daily, AFTER update-governance.yml)

Location in repo: rize-governance-hub/compute_bond_states.py
Output:           rize-governance-hub/bond-states.json

Rules verified against T-RIZE GovernanceBonding contract:
  BondCreated:   balance += amount  | timeMarker = event.timestamp (maturity=0)
  IncreaseBond:  balance += amount  | timeMarker = snapshot.timeMarker (dilution calc done onchain)
  BreakBond:     balance -= amount  | timeMarker UNCHANGED (confirmed in contract)
  Release:       no effect on balance or timeMarker (just transfers already-broken RIZE)

  maturity  = max(0, min(1, (T - timeMarker) / fullMaturity))
  boost     = 1 + 2 * maturity        (base=100, maturedBonus=200 → simplifies to 1+2m)
  VP        = balance * boost
"""

import json
import os
import time
from datetime import datetime, timezone

# Script lives in rize-governance-hub/ — all JSONs are siblings
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Pool defaults (overridden from pool-config.json)
DEFAULT_FULL_MATURITY = 94608000   # 3 years in seconds
DEFAULT_BASE_WEIGHT   = 100
DEFAULT_MATURED_BONUS = 200


# ── Helpers ────────────────────────────────────────────────────────────────────

def load_json(filename):
    path = os.path.join(SCRIPT_DIR, filename)
    if not os.path.exists(path):
        print(f"  [WARN] {filename} not found", flush=True)
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def parse_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def ts_to_date(ts):
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")


def calc_maturity(event_ts, time_marker, full_maturity_s):
    if time_marker is None or time_marker <= 0:
        return 0.0
    return max(0.0, min(1.0, (int(event_ts) - int(time_marker)) / full_maturity_s))


def calc_boost(mat):
    return 1.0 + 2.0 * mat


# ── Main ────────────────────────────────────────────────────────────────────────

def compute_bond_states():
    print("\n" + "=" * 64, flush=True)
    print("  COMPUTE BOND STATES — 7th JSON", flush=True)
    print("=" * 64, flush=True)

    # Load source JSONs
    pc_data = load_json("pool-config.json").get("data", {})
    bc_data = load_json("bond-created.json").get("data", {})
    bb_data = load_json("bond-broken.json").get("data", {})
    tm_data = load_json("bond-timemarker.json").get("data", {})

    # Pool config
    pools = pc_data.get("pools", [])
    if pools:
        full_maturity_s = int(pools[0].get("fullMaturity", DEFAULT_FULL_MATURITY))
        base_weight     = int(pools[0].get("baseWeight", DEFAULT_BASE_WEIGHT))
        matured_bonus   = int(pools[0].get("maturedWeightBonus", DEFAULT_MATURED_BONUS))
    else:
        full_maturity_s = DEFAULT_FULL_MATURITY
        base_weight     = DEFAULT_BASE_WEIGHT
        matured_bonus   = DEFAULT_MATURED_BONUS

    print(f"  Pool: fullMaturity={full_maturity_s}s | base={base_weight} | bonus={matured_bonus}", flush=True)

    # Owner + pool map from bonds[]
    owner_map = {}
    pool_map  = {}
    for bond in bc_data.get("bonds", []):
        nid = str(bond.get("nftId") or bond.get("id", ""))
        owner_map[nid] = (bond.get("owner") or "").lower()
        pool_map[nid]  = bond.get("poolId", 2)

    # Snapshot lookup: nftId → sorted list by blockNumber
    # Each IncreaseBond produces exactly one snapshot with matching txHash + blockNumber
    snap_by_nft = {}
    for snap in tm_data.get("bondTimeMarkerSnapshots", []):
        nid = str(snap["nftId"])
        if nid not in snap_by_nft:
            snap_by_nft[nid] = []
        snap_by_nft[nid].append({
            "blockNumber": int(snap["blockNumber"]),
            "timeMarker":  int(snap["timeMarker"]),
        })
    for nid in snap_by_nft:
        snap_by_nft[nid].sort(key=lambda s: s["blockNumber"])

    def get_snapshot(nid, block_number):
        """Return snapshot for this IncreaseBond. Exact block match first, then closest before."""
        snaps = snap_by_nft.get(str(nid), [])
        bn = int(block_number)
        for s in snaps:
            if s["blockNumber"] == bn:
                return s
        best = None
        for s in snaps:
            if s["blockNumber"] <= bn:
                best = s
        return best

    # Collect raw events per nftId
    raw_events = {}

    def add_event(nid, ev):
        nid = str(nid)
        if nid not in raw_events:
            raw_events[nid] = []
        raw_events[nid].append(ev)

    # BondCreated
    for e in bc_data.get("bondCreatedEvents", []):
        nid = str(e["nftId"])
        add_event(nid, {
            "ts":    int(e["timestamp"]),
            "bn":    int(e.get("blockNumber", 0)),
            "type":  "BondCreated",
            "delta": +parse_float(e["amount"]),
            "newTM": int(e["timestamp"]),  # timeMarker = creation timestamp → maturity 0
            "txHash": e.get("txHash", ""),
        })
        if nid not in owner_map:
            owner_map[nid] = (e.get("owner") or "").lower()
        if nid not in pool_map:
            pool_map[nid] = e.get("poolId", 2)

    # IncreaseBond — timeMarker is the exact onchain result from the snapshot
    skipped = 0
    for e in bc_data.get("increaseBondEvents", []):
        nid  = str(e["nftId"])
        bn   = int(e.get("blockNumber", 0))
        snap = get_snapshot(nid, bn)
        if snap is None:
            skipped += 1
            print(f"  [WARN] No snapshot: IncreaseBond nftId={nid} block={bn}", flush=True)
            continue
        add_event(nid, {
            "ts":    int(e["timestamp"]),
            "bn":    bn,
            "type":  "IncreaseBond",
            "delta": +parse_float(e["amount"]),
            "newTM": snap["timeMarker"],  # exact post-contract timeMarker
            "txHash": e.get("txHash", ""),
        })

    # BreakBond — timeMarker never changes
    for e in bb_data.get("bondBrokenEvents", []):
        nid = str(e["nftId"])
        add_event(nid, {
            "ts":    int(e["timestamp"]),
            "bn":    int(e.get("blockNumber", 0)),
            "type":  "Break",
            "delta": -parse_float(e["amount"]),
            "newTM": None,  # contract confirmed: timeMarker unchanged on break
            "txHash": e.get("txHash", ""),
        })

    if skipped:
        print(f"  [WARN] Skipped {skipped} IncreaseBond events (missing snapshot)", flush=True)

    # Process each nftId chronologically
    now_ts      = int(time.time())
    bond_states = {}

    for nid, events in raw_events.items():
        events.sort(key=lambda x: (x["ts"], x["bn"]))

        balance     = 0.0
        time_marker = None
        state_list  = []

        for ev in events:
            balance = max(0.0, balance + ev["delta"])
            if ev["newTM"] is not None:
                time_marker = ev["newTM"]

            mat   = calc_maturity(ev["ts"], time_marker, full_maturity_s)
            boost = calc_boost(mat)
            vp    = balance * boost

            state_list.append({
                "ts":         ev["ts"],
                "date":       ts_to_date(ev["ts"]),
                "type":       ev["type"],
                "delta":      round(ev["delta"], 8),
                "balance":    round(balance, 8),
                "timeMarker": time_marker,
                "maturity":   round(mat, 8),
                "boost":      round(boost, 8),
                "vp":         round(vp, 4),
                "txHash":     ev["txHash"],
            })

        # Current state
        mat_now   = calc_maturity(now_ts, time_marker, full_maturity_s)
        boost_now = calc_boost(mat_now)
        vp_now    = balance * boost_now

        full_mat_ts   = (int(time_marker) + full_maturity_s) if time_marker else None
        full_mat_date = ts_to_date(full_mat_ts) if full_mat_ts else None

        bond_states[nid] = {
            "owner":   owner_map.get(nid, ""),
            "poolId":  pool_map.get(nid, 2),
            "events":  state_list,
            "current": {
                "balance":     round(balance, 8),
                "timeMarker":  time_marker,
                "maturity":    round(mat_now, 8),
                "boost":       round(boost_now, 8),
                "vp":          round(vp_now, 4),
                "fullMatDate": full_mat_date,
                "vpAtFullMat": round(balance * 3.0, 4),
                "isActive":    balance > 0,
            },
        }

    # Stats
    active     = [b for b in bond_states.values() if b["current"]["isActive"]]
    total_rize = sum(b["current"]["balance"] for b in active)
    total_vp   = sum(b["current"]["vp"]      for b in active)
    total_ev   = sum(len(b["events"])         for b in bond_states.values())

    print(f"  Bonds:         {len(bond_states):>7,}", flush=True)
    print(f"  Active:        {len(active):>7,}", flush=True)
    print(f"  Total RIZE:    {total_rize:>14,.2f}", flush=True)
    print(f"  Total VP:      {total_vp:>14,.2f}", flush=True)
    print(f"  Total events:  {total_ev:>7,}", flush=True)

    # Owner index: owner (lowercase) → [nftId, ...]
    owner_index = {}
    for nid, state in bond_states.items():
        owner = state["owner"]
        if not owner:
            continue
        if owner not in owner_index:
            owner_index[owner] = []
        owner_index[owner].append(nid)

    # Write output
    output = {
        "generated_at":  datetime.now(timezone.utc).isoformat(),
        "fullMaturity":  full_maturity_s,
        "baseWeight":    base_weight,
        "maturedBonus":  matured_bonus,
        "stats": {
            "totalBonds":   len(bond_states),
            "activeBonds":  len(active),
            "totalRIZE":    round(total_rize, 2),
            "totalVP":      round(total_vp, 2),
            "totalEvents":  total_ev,
        },
        "ownerIndex":   owner_index,
        "bondStates":   bond_states,
    }

    out_path = os.path.join(SCRIPT_DIR, "bond-states.json")
    tmp_path = out_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(output, f, separators=(",", ":"), ensure_ascii=False)
    os.replace(tmp_path, out_path)  # atomic: old file intact if write fails

    size_kb = os.path.getsize(out_path) // 1024
    print(f"\n  ✓ bond-states.json written atomically — {size_kb:,} KB", flush=True)
    return output


if __name__ == "__main__":
    compute_bond_states()
