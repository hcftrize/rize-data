#!/usr/bin/env python3
"""
audit_bond_states.py
====================
Diagnoses discrepancies between bond-states.json total RIZE
and the expected total from the 6 source JSONs.

Run from the rize-governance-hub/ directory:
  python3 audit_bond_states.py

Or from repo root:
  python3 rize-governance-hub/audit_bond_states.py
"""

import json, os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def load(filename):
    path = os.path.join(SCRIPT_DIR, filename)
    if not os.path.exists(path):
        print(f"  [MISSING] {filename}")
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def pf(v): 
    try: return float(v)
    except: return 0.0

def sep():
    print("─" * 64)

print("=" * 64)
print("  BOND STATES AUDIT")
print("=" * 64)

# ── Load all sources ──
bc  = load("bond-created.json").get("data", {})
bb  = load("bond-broken.json").get("data", {})
bs  = load("bond-states.json")
bss = bs.get("bondStates", bs) if bs else {}

# ── 1. Count events ──
sep()
print("1. EVENT COUNTS")
created_events = bc.get("bondCreatedEvents", [])
increase_events = bc.get("increaseBondEvents", [])
break_events    = bb.get("bondBrokenEvents", [])
bonds_list      = bc.get("bonds", [])
print(f"   bondCreatedEvents : {len(created_events):>8,}")
print(f"   increaseBondEvents: {len(increase_events):>8,}")
print(f"   bondBrokenEvents  : {len(break_events):>8,}")
print(f"   bonds[]           : {len(bonds_list):>8,}")
print(f"   bondStates nftIds : {len(bss):>8,}")

# ── 2. Sum totalDeposited from bonds[] ──
sep()
print("2. TOTAL FROM bonds[].totalDeposited (raw, no break subtraction)")
total_deposited = sum(pf(b.get("totalDeposited", 0)) for b in bonds_list)
print(f"   Sum totalDeposited: {total_deposited:>16,.2f} RIZE")

# ── 3. Sum all breaks ──
sep()
print("3. TOTAL BREAKS")
total_breaks = sum(pf(e.get("amount", 0)) for e in break_events)
print(f"   Sum all breaks    : {total_breaks:>16,.2f} RIZE")
print(f"   Expected balance  : {total_deposited - total_breaks:>16,.2f} RIZE  (deposited - breaks)")

# ── 4. What bond-states.json computed ──
sep()
print("4. BOND-STATES.JSON COMPUTED TOTAL")
bs_total = sum(
    s.get("current", {}).get("balance", 0)
    for s in bss.values()
    if s.get("current", {}).get("balance", 0) > 0
)
bs_active = sum(1 for s in bss.values() if s.get("current", {}).get("balance", 0) > 0)
print(f"   Active bonds      : {bs_active:>8,}")
print(f"   Total RIZE        : {bs_total:>16,.2f} RIZE")
print(f"   DIFFERENCE vs expected: {(total_deposited - total_breaks) - bs_total:>+16,.2f} RIZE")

# ── 5. Find nftIds in breaks but NOT in bondCreatedEvents ──
sep()
print("5. BREAKS FOR BONDS WITHOUT bondCreatedEvent (orphan breaks)")
created_nftids = {str(e["nftId"]) for e in created_events}
orphan_breaks = {}
for e in break_events:
    nid = str(e["nftId"])
    if nid not in created_nftids:
        orphan_breaks[nid] = orphan_breaks.get(nid, 0) + pf(e.get("amount", 0))

orphan_total = sum(orphan_breaks.values())
print(f"   NftIds broken but no BondCreatedEvent: {len(orphan_breaks):,}")
print(f"   Total RIZE in these orphan breaks    : {orphan_total:>16,.2f} RIZE")
if orphan_breaks:
    top10 = sorted(orphan_breaks.items(), key=lambda x: -x[1])[:10]
    print("   Top 10 orphan nftIds by break amount:")
    for nid, amt in top10:
        print(f"     nftId={nid:>6}  breaks={amt:>14,.2f} RIZE")

# ── 6. Find nftIds in bonds[] but NOT in bondCreatedEvents ──
sep()
print("6. BONDS[] WITHOUT bondCreatedEvent")
bonds_without_event = []
for b in bonds_list:
    nid = str(b.get("nftId") or b.get("id", ""))
    if nid not in created_nftids:
        bonds_without_event.append((nid, pf(b.get("totalDeposited", 0))))

total_missing = sum(amt for _, amt in bonds_without_event)
print(f"   bonds[] without BondCreatedEvent: {len(bonds_without_event):,}")
print(f"   Total deposited for these bonds : {total_missing:>16,.2f} RIZE")
if bonds_without_event:
    top10b = sorted(bonds_without_event, key=lambda x: -x[1])[:10]
    print("   Top 10 by totalDeposited:")
    for nid, amt in top10b:
        print(f"     nftId={nid:>6}  totalDeposited={amt:>14,.2f} RIZE")

# ── 7. Compute correct total using bonds[] + breaks ──
sep()
print("7. CORRECT TOTAL (bonds[].totalDeposited - breaks by nftId)")
break_by_nft = {}
for e in break_events:
    nid = str(e["nftId"])
    break_by_nft[nid] = break_by_nft.get(nid, 0) + pf(e.get("amount", 0))

correct_total = 0.0
active_count  = 0
for b in bonds_list:
    nid = str(b.get("nftId") or b.get("id", ""))
    dep = pf(b.get("totalDeposited", 0))
    brk = break_by_nft.get(nid, 0)
    bal = max(0.0, dep - brk)
    if bal > 0:
        correct_total += bal
        active_count  += 1

print(f"   Active bonds (balance > 0)  : {active_count:>8,}")
print(f"   Correct total RIZE          : {correct_total:>16,.2f} RIZE")
print(f"   bond-states.json total      : {bs_total:>16,.2f} RIZE")
print(f"   DELTA                       : {correct_total - bs_total:>+16,.2f} RIZE")

# ── 8. Summary ──
sep()
print("8. SUMMARY")
print(f"   bonds[].totalDeposited sum  : {total_deposited:>16,.2f}")
print(f"   All breaks sum              : {total_breaks:>16,.2f}")
print(f"   Correct net balance         : {correct_total:>16,.2f}")
print(f"   bond-states computed        : {bs_total:>16,.2f}")
print(f"   Missing from bond-states    : {correct_total - bs_total:>+16,.2f}")
print(f"   Orphan breaks (no creation) : {orphan_total:>16,.2f}")
print(f"   Bonds without event         : {total_missing:>16,.2f} (totalDeposited)")
sep()

if __name__ == "__main__":
    pass
