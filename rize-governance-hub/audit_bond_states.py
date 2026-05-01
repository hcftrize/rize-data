#!/usr/bin/env python3
"""
audit_bond_states.py v2
=======================
Diagnoses discrepancies between bond-states.json total RIZE
and the expected total from the 6 source JSONs.

Run from the rize-governance-hub/ directory:
  python3 audit_bond_states.py
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
print("  BOND STATES AUDIT v2")
print("=" * 64)

# ── Load ──
bc  = load("bond-created.json").get("data", {})
bb  = load("bond-broken.json").get("data", {})
bs  = load("bond-states.json")
bss = bs.get("bondStates", bs) if bs else {}

created_events  = bc.get("bondCreatedEvents", [])
increase_events = bc.get("increaseBondEvents", [])
break_events    = bb.get("bondBrokenEvents", [])
bonds_list      = bc.get("bonds", [])

# ── 1. Counts ──
sep()
print("1. EVENT COUNTS")
print(f"   bondCreatedEvents : {len(created_events):>8,}")
print(f"   increaseBondEvents: {len(increase_events):>8,}")
print(f"   bondBrokenEvents  : {len(break_events):>8,}")
print(f"   bonds[]           : {len(bonds_list):>8,}")
print(f"   bondStates nftIds : {len(bss):>8,}")

# ── 2. totalDeposited sum ──
sep()
print("2. TOTAL FROM bonds[].totalDeposited (cumulative deposits, no breaks)")
total_deposited = sum(pf(b.get("totalDeposited", 0)) for b in bonds_list)
print(f"   Sum totalDeposited: {total_deposited:>16,.2f} RIZE")

# ── 3. Breaks sum ──
sep()
print("3. TOTAL BREAKS")
total_breaks = sum(pf(e.get("amount", 0)) for e in break_events)
print(f"   Sum all breaks    : {total_breaks:>16,.2f} RIZE")
print(f"   Expected balance  : {total_deposited - total_breaks:>16,.2f} RIZE  (deposited - breaks)")

# ── 4. bond-states.json total ──
sep()
print("4. BOND-STATES.JSON COMPUTED TOTAL")
bs_total  = sum(s.get("current", {}).get("balance", 0) for s in bss.values() if s.get("current", {}).get("balance", 0) > 0)
bs_active = sum(1 for s in bss.values() if s.get("current", {}).get("balance", 0) > 0)
print(f"   Active bonds      : {bs_active:>8,}")
print(f"   Total RIZE        : {bs_total:>16,.2f} RIZE")
print(f"   DIFFERENCE vs expected: {(total_deposited - total_breaks) - bs_total:>+16,.2f} RIZE")

# ── Build break totals per nftId ──
break_by_nft = {}
for e in break_events:
    nid = str(e["nftId"])
    break_by_nft[nid] = break_by_nft.get(nid, 0) + pf(e.get("amount", 0))

# ── Build bonds dict ──
bonds_by_nid = {str(b.get("nftId") or b.get("id", "")): b for b in bonds_list}

# ── 5. Orphan breaks ──
sep()
print("5. BREAKS FOR BONDS WITHOUT bondCreatedEvent")
created_nftids = {str(e["nftId"]) for e in created_events}
orphan_breaks = {}
for e in break_events:
    nid = str(e["nftId"])
    if nid not in created_nftids:
        orphan_breaks[nid] = orphan_breaks.get(nid, 0) + pf(e.get("amount", 0))
orphan_total = sum(orphan_breaks.values())
print(f"   NftIds with orphan breaks: {len(orphan_breaks):,}")
print(f"   Total orphan break RIZE  : {orphan_total:>16,.2f} RIZE")

# ── 6. Event-based recalc ──
sep()
print("6. RECALC FROM RAW EVENTS ONLY (created + increases - breaks)")
event_balance = {}
for e in created_events:
    nid = str(e["nftId"])
    event_balance[nid] = event_balance.get(nid, 0) + pf(e.get("amount", 0))
for e in increase_events:
    nid = str(e["nftId"])
    event_balance[nid] = event_balance.get(nid, 0) + pf(e.get("amount", 0))
for e in break_events:
    nid = str(e["nftId"])
    event_balance[nid] = event_balance.get(nid, 0) - pf(e.get("amount", 0))

event_total  = sum(max(0.0, v) for v in event_balance.values())
event_active = sum(1 for v in event_balance.values() if v > 0)
print(f"   Active bonds (event-based): {event_active:>8,}")
print(f"   Total RIZE (event-based)  : {event_total:>16,.2f} RIZE")
print(f"   bond-states.json total    : {bs_total:>16,.2f} RIZE")
print(f"   DELTA                     : {event_total - bs_total:>+16,.2f} RIZE")

# ── 7. KEY: Bonds where breaks > totalDeposited ──
sep()
print("7. BONDS WHERE TOTAL BREAKS > totalDeposited  ← KEY CHECK")
overbroken = []
for nid, brk in break_by_nft.items():
    b = bonds_by_nid.get(nid)
    if not b:
        continue
    td = pf(b.get("totalDeposited", 0))
    if brk > td + 0.01:
        overbroken.append((nid, td, brk, brk - td))
overbroken.sort(key=lambda x: -x[3])
total_excess = sum(x[3] for x in overbroken)
print(f"   Bonds with breaks > deposited: {len(overbroken):,}")
print(f"   Total excess breaks          : {total_excess:>16,.2f} RIZE")
if overbroken:
    print(f"   {'nftId':>8}  {'totalDeposited':>16}  {'totalBreaks':>16}  {'excess':>14}")
    for nid, td, brk, exc in overbroken[:20]:
        print(f"   {nid:>8}  {td:>16,.2f}  {brk:>16,.2f}  {exc:>+14,.2f}")
else:
    print("   None found.")

# ── 8. Stale totalDeposited ──
sep()
print("8. BONDS WHERE events gross != bonds[].totalDeposited (stale)")
mismatches = []
for nid in {str(b.get("nftId") or b.get("id", "")) for b in bonds_list}:
    created_amt  = sum(pf(e["amount"]) for e in created_events  if str(e["nftId"]) == nid)
    increase_amt = sum(pf(e["amount"]) for e in increase_events if str(e["nftId"]) == nid)
    ev_gross = created_amt + increase_amt
    td = pf(bonds_by_nid.get(nid, {}).get("totalDeposited", 0))
    diff = ev_gross - td
    if abs(diff) > 0.01:
        mismatches.append((nid, td, ev_gross, diff))
mismatches.sort(key=lambda x: -abs(x[3]))
total_mismatch = sum(x[3] for x in mismatches)
print(f"   Bonds with stale totalDeposited: {len(mismatches):,}")
print(f"   Total RIZE difference          : {total_mismatch:>+16,.2f} RIZE")
if mismatches:
    print(f"   {'nftId':>8}  {'bonds[]':>16}  {'events_gross':>16}  {'diff':>12}")
    for nid, td, ev, diff in mismatches[:10]:
        print(f"   {nid:>8}  {td:>16,.2f}  {ev:>16,.2f}  {diff:>+12,.2f}")

# ── 9. Summary ──
sep()
print("9. SUMMARY")
print(f"   bonds[].totalDeposited sum  : {total_deposited:>16,.2f} RIZE")
print(f"   All breaks sum              : {total_breaks:>16,.2f} RIZE")
print(f"   Net (deposited - breaks)    : {total_deposited - total_breaks:>16,.2f} RIZE")
print(f"   bond-states.json total      : {bs_total:>16,.2f} RIZE  (delta: {(total_deposited-total_breaks)-bs_total:+,.0f})")
print(f"   Event-based recalc total    : {event_total:>16,.2f} RIZE  (same as bond-states: {'YES' if abs(event_total-bs_total)<100 else 'NO'})")
print(f"   Orphan breaks (no creation) : {orphan_total:>16,.2f} RIZE")
print(f"   Excess breaks (brk > dep)   : {total_excess:>16,.2f} RIZE")
print(f"   Stale totalDeposited delta  : {total_mismatch:>+16,.2f} RIZE")
sep()

# ── 11. Breaks vs Releases — queue non retirée ──
sep()
print("11. BREAKS vs RELEASES — RIZE cassé mais pas encore sorti du contrat")
print("    Théorie: le RPC totalBonded inclut le RIZE en queue de release")
print("    Nous on le soustrait dès le break → on under-count de ce montant")
lc = load("bond-lifecycle.json").get("data", {})
release_events = lc.get("tokensReleasedEvents", [])
total_released = sum(pf(e.get("amount", 0)) for e in release_events)
queue_rize = total_breaks - total_released
print(f"   Sum all breaks         : {total_breaks:>16,.2f} RIZE")
print(f"   Sum all releases       : {total_released:>16,.2f} RIZE")
print(f"   En queue (non releasé) : {queue_rize:>16,.2f} RIZE  ← clé")
print(f"   Notre net balance      : {event_total:>16,.2f} RIZE")
print(f"   Notre net + queue      : {event_total + queue_rize:>16,.2f} RIZE")
print(f"   RPC live               :    ~927,000,000.00 RIZE")
print(f"   Delta net+queue vs RPC : {event_total + queue_rize - 927_000_000:>+16,.2f} RIZE")
if abs(event_total + queue_rize - 927_000_000) < 5_000_000:
    print()
    print("   ✓ THÉORIE CONFIRMÉE: le RPC compte le RIZE en queue de release")
    print("     comme encore 'bondé'. Notre calcul est correct pour le VP")
    print("     (RIZE cassé n'a plus de VP), mais le total affiché doit")
    print("     inclure la queue pour matcher le RPC.")
else:
    print()
    print("   Théorie non confirmée par les chiffres.")
sep()

# ── 10. Conclusion ──
print("10. CONCLUSION")
if total_excess > 1_000_000:
    print(f"  !! EXCESS BREAKS = {total_excess:,.2f} RIZE")
    print(f"     {len(overbroken)} bonds have more breaks than deposits.")
    print(f"     These are the source of the missing RIZE.")
    print(f"     Likely cause: subgraph counting breaks on wrong nftId,")
    print(f"     or same break event indexed twice.")
elif abs(event_total - bs_total) < 10_000:
    print(f"  bond-states.json matches raw event recalc. JSON is correct.")
    print(f"  Both methods give ~{event_total:,.0f} RIZE.")
    print(f"  The gap vs RPC 927M is in the SOURCE DATA.")
    print(f"  The subgraph bootstrap missed some bondCreatedEvents.")
    print(f"  Those missing bonds have no creation event → not counted.")
    print(f"  Solution: re-bootstrap bond-created.json from the live subgraph.")
else:
    print("  Inconclusive. Review sections 6 and 7 carefully.")
sep()
