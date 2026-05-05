#!/usr/bin/env python3
"""
audit_bond_states.py v4
=======================
Full audit including wei/RIZE conversion precision check.

Update RPC_LIVE to exact value shown on dashboard when running.
Run from rize-governance-hub/ directory.
"""

import json, os
from decimal import Decimal, getcontext
getcontext().prec = 50

# ── Update to exact RPC value at time of running ──────────────────
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

def pd(v):
    try: return Decimal(str(v))
    except: return Decimal("0")

def sep():
    print("─" * 64)

print("=" * 64)
print("  BOND STATES AUDIT v4")
print("=" * 64)

# ── Load ──────────────────────────────────────────────────────────
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

# ── 1. Counts ─────────────────────────────────────────────────────
sep()
print("1. EVENT COUNTS")
print(f"   bondCreatedEvents   : {len(created_events):>8,}")
print(f"   increaseBondEvents  : {len(increase_events):>8,}")
print(f"   bondBrokenEvents    : {len(break_events):>8,}")
print(f"   tokensReleasedEvents: {len(release_events):>8,}")
print(f"   bonds[]             : {len(bonds_list):>8,}")
print(f"   bondStates nftIds   : {len(bss):>8,}")

# ── 2. Duplicate check ────────────────────────────────────────────
sep()
print("2. DUPLICATE CHECK")
for name, events in [
    ("bondBrokenEvents",     break_events),
    ("bondCreatedEvents",    created_events),
    ("increaseBondEvents",   increase_events),
    ("tokensReleasedEvents", release_events),
]:
    ids = [e["id"] for e in events]
    dupes = len(ids) - len(set(ids))
    print(f"   {name:<26}: {dupes:>4} duplicates")

# ── 3. Amount format analysis ─────────────────────────────────────
sep()
print("3. AMOUNT FORMAT — wei vs RIZE detection")
print("   Checking if amounts are already in RIZE or still in wei...")

# Sample max amount from each array
def max_amount(events, field="amount"):
    vals = [pf(e.get(field, 0)) for e in events if e.get(field)]
    return max(vals) if vals else 0

max_created  = max_amount(created_events)
max_broken   = max_amount(break_events)
max_released = max_amount(release_events)
max_increase = max_amount(increase_events)

print(f"   Max bondCreatedEvent amount : {max_created:>20,.6f}")
print(f"   Max bondBrokenEvent amount  : {max_broken:>20,.6f}")
print(f"   Max tokensReleased amount   : {max_released:>20,.6f}")
print(f"   Max increaseBond amount     : {max_increase:>20,.6f}")

# If amounts > 1e15 they're likely in wei
wei_threshold = 1e15
if max_created > wei_threshold:
    print(f"\n   !! Amounts appear to be in WEI (values > 1e15)")
    print(f"      Must divide by 1e18 to get RIZE")
    WEI_MODE = True
else:
    print(f"\n   ✓ Amounts appear to be in RIZE (human-readable)")
    WEI_MODE = False

# ── 4. Precision check on individual amounts ──────────────────────
sep()
print("4. DECIMAL PRECISION — checking for truncation/rounding in amounts")

# Check if amounts have exactly 18 decimal places (wei) or are already divided
def check_decimals(events, name, sample=20):
    counts = {"integer": 0, "few_dec": 0, "many_dec": 0, "very_many": 0}
    for e in events[:sample]:
        v = str(e.get("amount", "0"))
        if "." in v:
            dec_places = len(v.split(".")[1])
            if dec_places <= 2: counts["few_dec"] += 1
            elif dec_places <= 8: counts["many_dec"] += 1
            else: counts["very_many"] += 1
        else:
            counts["integer"] += 1
    print(f"   {name} (sample {sample}): integer={counts['integer']} "
          f"≤2dec={counts['few_dec']} ≤8dec={counts['many_dec']} >8dec={counts['very_many']}")

check_decimals(break_events, "bondBrokenEvents")
check_decimals(release_events, "tokensReleasedEvents")
check_decimals(created_events, "bondCreatedEvents")

# ── 5. Totals (float and Decimal) ─────────────────────────────────
sep()
print("5. TOTALS — float vs Decimal")

total_created_f  = sum(pf(e.get("amount",0)) for e in created_events)
total_increase_f = sum(pf(e.get("amount",0)) for e in increase_events)
total_broken_f   = sum(pf(e.get("amount",0)) for e in break_events)
total_released_f = sum(pf(e.get("amount",0)) for e in release_events)

total_created_d  = sum(pd(e.get("amount",0)) for e in created_events)
total_increase_d = sum(pd(e.get("amount",0)) for e in increase_events)
total_broken_d   = sum(pd(e.get("amount",0)) for e in break_events)
total_released_d = sum(pd(e.get("amount",0)) for e in release_events)

print(f"   {'':30} {'Float':>20}  {'Decimal':>20}  {'Delta':>12}")
print(f"   {'bondCreatedEvents':30} {total_created_f:>20,.4f}  {float(total_created_d):>20,.4f}  {total_created_f-float(total_created_d):>+12.6f}")
print(f"   {'increaseBondEvents':30} {total_increase_f:>20,.4f}  {float(total_increase_d):>20,.4f}  {total_increase_f-float(total_increase_d):>+12.6f}")
print(f"   {'bondBrokenEvents':30} {total_broken_f:>20,.4f}  {float(total_broken_d):>20,.4f}  {total_broken_f-float(total_broken_d):>+12.6f}")
print(f"   {'tokensReleasedEvents':30} {total_released_f:>20,.4f}  {float(total_released_d):>20,.4f}  {total_released_f-float(total_released_d):>+12.6f}")

# ── 6. Net balance ────────────────────────────────────────────────
sep()
print("6. NET BALANCE COMPUTATION")

# Event-based (Decimal)
ev_bal_d = {}
for e in created_events:
    nid = str(e["nftId"])
    ev_bal_d[nid] = ev_bal_d.get(nid, Decimal("0")) + pd(e.get("amount","0"))
for e in increase_events:
    nid = str(e["nftId"])
    ev_bal_d[nid] = ev_bal_d.get(nid, Decimal("0")) + pd(e.get("amount","0"))
for e in break_events:
    nid = str(e["nftId"])
    ev_bal_d[nid] = ev_bal_d.get(nid, Decimal("0")) - pd(e.get("amount","0"))

net_d    = sum(max(Decimal("0"), v) for v in ev_bal_d.values())
queue_d  = total_broken_d - total_released_d
total_d  = net_d + queue_d

net_f    = sum(max(0.0, float(v)) for v in ev_bal_d.values())
queue_f  = total_broken_f - total_released_f
total_f  = net_f + queue_f

print(f"   Net balance (Decimal)  : {float(net_d):>20,.6f} RIZE")
print(f"   Net balance (float)    : {net_f:>20,.6f} RIZE")
print(f"   Queue (Decimal)        : {float(queue_d):>20,.6f} RIZE")
print(f"   Total in contract (Dec): {float(total_d):>20,.6f} RIZE")
print(f"   RPC live               : {float(RPC_LIVE):>20,.6f} RIZE")
print(f"   DELTA (Dec vs RPC)     : {float(total_d)-float(RPC_LIVE):>+20,.6f} RIZE")

# ── 7. Truncation analysis ────────────────────────────────────────
sep()
print("7. TRUNCATION ANALYSIS — potential rounding in subgraph")
print("   If subgraph stores amounts truncated to N decimals,")
print("   cumulative error = N * num_events")
print()

# Check: if each amount was truncated to 6 decimal places, what's the max error?
# 97,237 break events * max 0.0000005 truncation each = ~0.049 RIZE
# That's tiny. But if truncated to 0 decimals (integer RIZE)...

# Check actual decimal precision in break events
dec_places_list = []
for e in break_events:
    v = str(e.get("amount","0"))
    if "." in v:
        dec_places_list.append(len(v.split(".")[1].rstrip("0")))
    else:
        dec_places_list.append(0)

if dec_places_list:
    avg_dec = sum(dec_places_list) / len(dec_places_list)
    max_dec = max(dec_places_list)
    min_dec = min(dec_places_list)
    print(f"   breakBond amounts decimal places:")
    print(f"     min={min_dec}, max={max_dec}, avg={avg_dec:.2f}")
    # Max truncation error per event if stored at avg precision
    max_trunc_per_event = 10 ** (-min_dec) if min_dec > 0 else 1.0
    total_trunc_error = max_trunc_per_event * len(break_events)
    print(f"     Max truncation error/event: {max_trunc_per_event:.10f} RIZE")
    print(f"     Max cumulative trunc error: {total_trunc_error:,.6f} RIZE")

# Same for releases
dec_places_rel = []
for e in release_events:
    v = str(e.get("amount","0"))
    if "." in v:
        dec_places_rel.append(len(v.split(".")[1].rstrip("0")))
    else:
        dec_places_rel.append(0)

if dec_places_rel:
    avg_dec_r = sum(dec_places_rel) / len(dec_places_rel)
    max_dec_r = max(dec_places_rel)
    min_dec_r = min(dec_places_rel)
    print(f"\n   tokensReleased amounts decimal places:")
    print(f"     min={min_dec_r}, max={max_dec_r}, avg={avg_dec_r:.2f}")

# ── 8. Subgraph amount format — are they divided by 1e18? ─────────
sep()
print("8. SUBGRAPH AMOUNT FORMAT VERIFICATION")
print("   Checking known bond #4: should be 146,250,000 RIZE exactly")

bond4_created = [e for e in created_events if str(e.get("nftId","")) == "4"]
if bond4_created:
    amt = bond4_created[0].get("amount","?")
    print(f"   bondCreatedEvent #4 amount: {amt}")
    amt_f = pf(amt)
    if abs(amt_f - 146250000) < 1:
        print(f"   ✓ Confirmed: amounts are in RIZE (not wei)")
    elif abs(amt_f / 1e18 - 146250000) < 1:
        print(f"   !! Amounts are in WEI — need /1e18 conversion")
    else:
        print(f"   ?? Unexpected value: {amt_f}")

# Check a release — bond #4 first release
bond4_rel = [e for e in release_events if str(e.get("nftId","")) == "4"]
if bond4_rel:
    print(f"\n   First release #4 amount: {bond4_rel[0].get('amount','?')}")
    print(f"   This should match a BondBroken amount for #4")
    bond4_brk = [e for e in break_events if str(e.get("nftId","")) == "4"]
    if bond4_brk:
        print(f"   First break #4 amount  : {bond4_brk[0].get('amount','?')}")

# ── 9. RPC reconciliation ─────────────────────────────────────────
sep()
print("9. RPC RECONCILIATION")
print(f"   Net balance (Decimal)  : {float(net_d):>18,.6f} RIZE")
print(f"   Queue (breaks-releases): {float(queue_d):>18,.6f} RIZE")
print(f"   Total in contract      : {float(total_d):>18,.6f} RIZE")
print(f"   RPC live               : {float(RPC_LIVE):>18,.6f} RIZE")
delta = float(total_d) - float(RPC_LIVE)
print(f"   DELTA                  : {delta:>+18,.6f} RIZE ({delta/float(RPC_LIVE)*100:+.4f}%)")
print()
if delta > 0:
    print(f"   ON COMPTE {delta:,.2f} RIZE DE PLUS que le RPC.")
    print(f"   Causes possibles (par ordre de probabilité):")
    print(f"   1. tokensReleasedEvents incomplets dans le subgraph")
    print(f"      → des releases onchain non indexées → queue sur-estimée")
    print(f"   2. Arrondi/troncature dans les montants du subgraph")
    print(f"      → voir section 7 pour l'amplitude possible")
    print(f"   3. Releases failed sur Basescan comptées à tort")
elif delta < 0:
    print(f"   ON COMPTE {abs(delta):,.2f} RIZE DE MOINS que le RPC.")
    print(f"   Causes possibles:")
    print(f"   1. bondCreatedEvents ou increaseBondEvents incomplets")
    print(f"   2. Breaks sur-comptés (doublons)")
else:
    print(f"   ✓ PARFAIT — zéro écart avec le RPC.")

# ── 10. Bond-states check ─────────────────────────────────────────
sep()
print("10. BOND-STATES.JSON CONSISTENCY")
bs_total  = sum(s.get("current",{}).get("balance",0) for s in bss.values() if s.get("current",{}).get("balance",0)>0)
bs_active = sum(1 for s in bss.values() if s.get("current",{}).get("balance",0)>0)
print(f"    Active bonds    : {bs_active:>8,}")
print(f"    Total RIZE      : {bs_total:>18,.6f} RIZE")
print(f"    Event-based net : {float(net_d):>18,.6f} RIZE")
print(f"    DELTA           : {bs_total - float(net_d):>+18,.6f} RIZE")
if abs(bs_total - float(net_d)) < 1:
    print(f"    ✓ bond-states.json is consistent with raw events")
else:
    print(f"    !! bond-states.json differs from raw event recalc")

sep()
