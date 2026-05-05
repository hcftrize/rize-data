#!/usr/bin/env python3
"""
audit_bond_states.py v3
=======================
Diagnoses discrepancies between bond-states.json total RIZE
and the expected total from the 6 source JSONs.

Run from the rize-governance-hub/ directory:
  python3 audit_bond_states.py

Update RPC_LIVE below to the exact value shown on your dashboard
at the moment you run this script.
"""

import json, os
from decimal import Decimal, getcontext
getcontext().prec = 50

# ── Update this to exact RPC value at time of running ──
RPC_LIVE = Decimal("927701491")

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
print("  BOND STATES AUDIT v3")
print("=" * 64)

# ── Load ──
bc  = load("bond-created.json").get("data", {})
bb  = load("bond-broken.json").get("data", {})
lc  = load("bond-lifecycle.json").get("data", {})
bs  = load("bond-states.json")
bss = bs.get("bondStates", bs) if bs else {}

created_events  = bc.get("bondCreatedEvents", [])
increase_events = bc.get("increaseBondEvents", [])
break_events    = bb.get("bondBrokenEvents", [])
release_events  = lc.get("tokensReleasedEvents", [])
bonds_list      = bc.get("bonds", [])

# ── 1. Counts ──
sep()
print("1. EVENT COUNTS")
print(f"   bondCreatedEvents  : {len(created_events):>8,}")
print(f"   increaseBondEvents : {len(increase_events):>8,}")
print(f"   bondBrokenEvents   : {len(break_events):>8,}")
print(f"   tokensReleasedEvents:{len(release_events):>8,}")
print(f"   bonds[]            : {len(bonds_list):>8,}")
print(f"   bondStates nftIds  : {len(bss):>8,}")

# ── 2. Duplicate check — KEY ──
sep()
print("2. DUPLICATE CHECK — doublons dans chaque event array")
break_ids    = [e["id"] for e in break_events]
created_ids  = [e["id"] for e in created_events]
increase_ids = [e["id"] for e in increase_events]
release_ids  = [e["id"] for e in release_events]

dupes_break    = len(break_ids)    - len(set(break_ids))
dupes_created  = len(created_ids)  - len(set(created_ids))
dupes_increase = len(increase_ids) - len(set(increase_ids))
dupes_release  = len(release_ids)  - len(set(release_ids))

print(f"   bondBrokenEvents doublons   : {dupes_break:>6,}")
print(f"   bondCreatedEvents doublons  : {dupes_created:>6,}")
print(f"   increaseBondEvents doublons : {dupes_increase:>6,}")
print(f"   tokensReleasedEvents doublons:{dupes_release:>6,}")

# Show duplicate break amounts
if dupes_break > 0:
    from collections import Counter
    id_counts = Counter(break_ids)
    dupe_ids = {bid: cnt for bid, cnt in id_counts.items() if cnt > 1}
    dupe_events = [e for e in break_events if e["id"] in dupe_ids]
    dupe_rize = sum(pf(e.get("amount",0)) * (dupe_ids[e["id"]]-1) for e in dupe_events) / 2
    print(f"\n   !! {dupes_break} BREAK DOUBLONS TROUVÉS")
    print(f"      RIZE sur-compté (breaks en double): {dupe_rize:>14,.2f} RIZE")
    print(f"      Top 10 IDs en doublon:")
    for bid, cnt in sorted(dupe_ids.items(), key=lambda x:-x[1])[:10]:
        ev = next(e for e in break_events if e["id"]==bid)
        print(f"        nftId={ev['nftId']:>6}  amount={pf(ev.get('amount',0)):>14,.4f}  count={cnt}")

# ── 3. totalDeposited sum ──
sep()
print("3. TOTAL FROM bonds[].totalDeposited (cumulative, no breaks)")
total_deposited = sum(pf(b.get("totalDeposited", 0)) for b in bonds_list)
print(f"   Sum totalDeposited : {total_deposited:>16,.2f} RIZE")

# ── 4. Breaks and releases sums ──
sep()
print("4. BREAKS AND RELEASES")
total_breaks   = sum(pf(e.get("amount", 0)) for e in break_events)
total_released = sum(pf(e.get("amount", 0)) for e in release_events)
queue_rize     = total_breaks - total_released
print(f"   Sum all breaks     : {total_breaks:>16,.2f} RIZE")
print(f"   Sum all releases   : {total_released:>16,.2f} RIZE")
print(f"   Queue (brk-rel)    : {queue_rize:>16,.2f} RIZE")
print(f"   Net (dep-breaks)   : {total_deposited - total_breaks:>16,.2f} RIZE")

# ── 5. bond-states.json total ──
sep()
print("5. BOND-STATES.JSON COMPUTED TOTAL")
bs_total  = sum(s.get("current",{}).get("balance",0) for s in bss.values() if s.get("current",{}).get("balance",0)>0)
bs_active = sum(1 for s in bss.values() if s.get("current",{}).get("balance",0)>0)
print(f"   Active bonds       : {bs_active:>8,}")
print(f"   Total RIZE         : {bs_total:>16,.2f} RIZE")

# ── 6. Event-based recalc ──
sep()
print("6. RECALC FROM RAW EVENTS (created + increases - breaks)")
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
print(f"   Active bonds       : {event_active:>8,}")
print(f"   Total RIZE         : {event_total:>16,.2f} RIZE")
print(f"   bond-states total  : {bs_total:>16,.2f} RIZE")
print(f"   DELTA              : {event_total - bs_total:>+16,.2f} RIZE")

# ── 7. Orphan breaks ──
sep()
print("7. ORPHAN BREAKS (nftId sans bondCreatedEvent)")
created_nftids = {str(e["nftId"]) for e in created_events}
orphan_breaks = {}
for e in break_events:
    nid = str(e["nftId"])
    if nid not in created_nftids:
        orphan_breaks[nid] = orphan_breaks.get(nid, 0) + pf(e.get("amount", 0))
orphan_total = sum(orphan_breaks.values())
print(f"   NftIds orphelins   : {len(orphan_breaks):,}")
print(f"   Total RIZE orphelin: {orphan_total:>16,.2f} RIZE")

# ── 8. Bonds where breaks > totalDeposited ──
sep()
print("8. BONDS WHERE TOTAL BREAKS > totalDeposited")
bonds_by_nid = {str(b.get("nftId") or b.get("id","")): b for b in bonds_list}
break_by_nft = {}
for e in break_events:
    nid = str(e["nftId"])
    break_by_nft[nid] = break_by_nft.get(nid, 0) + pf(e.get("amount", 0))

overbroken = []
for nid, brk in break_by_nft.items():
    b = bonds_by_nid.get(nid)
    if not b: continue
    td = pf(b.get("totalDeposited", 0))
    if brk > td + 0.01:
        overbroken.append((nid, td, brk, brk - td))
overbroken.sort(key=lambda x: -x[3])
total_excess = sum(x[3] for x in overbroken)
print(f"   Bonds overbroken   : {len(overbroken):,}")
print(f"   Total excess       : {total_excess:>16,.2f} RIZE")
if overbroken:
    print(f"   {'nftId':>8}  {'totalDeposited':>16}  {'totalBreaks':>16}  {'excess':>14}")
    for nid, td, brk, exc in overbroken[:10]:
        print(f"   {nid:>8}  {td:>16,.2f}  {brk:>16,.2f}  {exc:>+14,.2f}")
else:
    print("   None found.")

# ── 9. Stale totalDeposited ──
sep()
print("9. STALE totalDeposited (events gross != bonds[])")
mismatches = []
for nid in {str(b.get("nftId") or b.get("id","")) for b in bonds_list}:
    ca = sum(pf(e["amount"]) for e in created_events  if str(e["nftId"])==nid)
    ia = sum(pf(e["amount"]) for e in increase_events if str(e["nftId"])==nid)
    ev_gross = ca + ia
    td = pf(bonds_by_nid.get(nid,{}).get("totalDeposited",0))
    diff = ev_gross - td
    if abs(diff) > 0.01:
        mismatches.append((nid, td, ev_gross, diff))
mismatches.sort(key=lambda x: -abs(x[3]))
total_mismatch = sum(x[3] for x in mismatches)
print(f"   Stale bonds        : {len(mismatches):,}")
print(f"   Total delta        : {total_mismatch:>+16,.2f} RIZE")
if mismatches:
    print(f"   {'nftId':>8}  {'bonds[]':>16}  {'events_gross':>16}  {'diff':>12}")
    for nid, td, ev, diff in mismatches[:10]:
        print(f"   {nid:>8}  {td:>16,.2f}  {ev:>16,.2f}  {diff:>+12,.2f}")

# ── 10. RPC reconciliation ──
sep()
print("10. RPC RECONCILIATION")
net_plus_queue = event_total + queue_rize
delta_vs_rpc   = net_plus_queue - float(RPC_LIVE)
print(f"   Event net balance  : {event_total:>16,.2f} RIZE")
print(f"   + Queue (brk-rel)  : {queue_rize:>16,.2f} RIZE")
print(f"   = Total in contract: {net_plus_queue:>16,.2f} RIZE")
print(f"   RPC live           : {float(RPC_LIVE):>16,.2f} RIZE")
print(f"   DELTA vs RPC       : {delta_vs_rpc:>+16,.2f} RIZE")
if delta_vs_rpc > 1000:
    print(f"\n   !! On compte {delta_vs_rpc:,.0f} RIZE DE PLUS que le RPC.")
    print(f"      Cause probable: doublons dans les events (voir section 2).")
elif delta_vs_rpc < -1000:
    print(f"\n   !! On compte {abs(delta_vs_rpc):,.0f} RIZE DE MOINS que le RPC.")
    print(f"      Cause probable: events manquants dans les JSONs source.")
else:
    print(f"\n   ✓ Delta < 1000 RIZE — données cohérentes avec le RPC.")

# ── 11. Decimal precision ──
sep()
print("11. PRÉCISION FLOATING POINT")
event_bal_dec = {}
for e in created_events:
    nid = str(e["nftId"])
    event_bal_dec[nid] = event_bal_dec.get(nid, Decimal("0")) + Decimal(str(e.get("amount","0")))
for e in increase_events:
    nid = str(e["nftId"])
    event_bal_dec[nid] = event_bal_dec.get(nid, Decimal("0")) + Decimal(str(e.get("amount","0")))
for e in break_events:
    nid = str(e["nftId"])
    event_bal_dec[nid] = event_bal_dec.get(nid, Decimal("0")) - Decimal(str(e.get("amount","0")))

net_dec   = sum(max(Decimal("0"), v) for v in event_bal_dec.values())
queue_dec = sum(Decimal(str(e.get("amount","0"))) for e in break_events) - \
            sum(Decimal(str(e.get("amount","0"))) for e in release_events)
total_dec = net_dec + queue_dec

delta_fp_net   = float(net_dec)   - event_total
delta_fp_queue = float(queue_dec) - queue_rize
delta_dec_rpc  = float(total_dec) - float(RPC_LIVE)

print(f"   Float net          : {event_total:>20,.6f} RIZE")
print(f"   Decimal net        : {float(net_dec):>20,.6f} RIZE")
print(f"   Delta FP net       : {delta_fp_net:>+20,.8f} RIZE")
print(f"   Delta FP queue     : {delta_fp_queue:>+20,.8f} RIZE")
print(f"   Decimal total      : {float(total_dec):>20,.6f} RIZE")
print(f"   Delta Decimal/RPC  : {delta_dec_rpc:>+20,.6f} RIZE")
if abs(delta_fp_net) < 1.0:
    print("   ✓ Floating point < 1 RIZE — négligeable.")
else:
    print(f"   !! FP impact = {delta_fp_net:+,.4f} RIZE — passer en Decimal.")

# ── 12. Summary ──
sep()
print("12. SUMMARY")
print(f"   bondCreatedEvents         : {len(created_events):>8,}")
print(f"   bondBrokenEvents          : {len(break_events):>8,}  (doublons: {dupes_break})")
print(f"   tokensReleasedEvents      : {len(release_events):>8,}  (doublons: {dupes_release})")
print(f"   Sum totalDeposited        : {total_deposited:>16,.2f} RIZE")
print(f"   Sum breaks                : {total_breaks:>16,.2f} RIZE")
print(f"   Sum releases              : {total_released:>16,.2f} RIZE")
print(f"   Queue (breaks-releases)   : {queue_rize:>16,.2f} RIZE")
print(f"   Event net balance         : {event_total:>16,.2f} RIZE")
print(f"   bond-states total         : {bs_total:>16,.2f} RIZE")
print(f"   Event net + queue         : {net_plus_queue:>16,.2f} RIZE")
print(f"   RPC live                  : {float(RPC_LIVE):>16,.2f} RIZE")
print(f"   Delta vs RPC              : {delta_vs_rpc:>+16,.2f} RIZE  ({delta_vs_rpc/float(RPC_LIVE)*100:+.4f}%)")
sep()
