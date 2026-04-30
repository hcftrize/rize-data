#!/usr/bin/env python3
"""
bootstrap_bond_states.py
=========================
One-time script to generate bond-states.json from the 6 existing genesis JSONs.

Run this ONCE after deploying the 6 bootstrapped JSONs to the repo.
After that, update-bond-states.yml runs daily automatically.

Usage:
  python3 rize-governance-hub/bootstrap_bond_states.py

The script:
1. Verifies all 6 source JSONs exist and are non-empty
2. Calls compute_bond_states() to generate bond-states.json
3. Prints a validation summary for manual verification

Location in repo: rize-governance-hub/bootstrap_bond_states.py
"""

import os
import sys
import json

# Add script directory to path so we can import compute_bond_states
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from compute_bond_states import compute_bond_states, load_json, calc_maturity, calc_boost

REQUIRED_JSONS = [
    "bond-created.json",
    "bond-broken.json",
    "bond-timemarker.json",
    "pool-config.json",
    "bond-lifecycle.json",
    "nft-transfers.json",
]


def verify_sources():
    """Check all 6 source JSONs exist and contain data."""
    print("\n── Verifying source JSONs ──────────────────────────────────")
    ok = True
    for filename in REQUIRED_JSONS:
        path = os.path.join(SCRIPT_DIR, filename)
        if not os.path.exists(path):
            print(f"  [MISSING] {filename}")
            ok = False
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        counts = data.get("counts", {})
        size_kb = os.path.getsize(path) // 1024
        print(f"  [OK] {filename:<28} {size_kb:>6} KB  counts={counts}")
    return ok


def validate_bond4(result):
    """
    Manual validation: bond #4 (0xe0eabf... wallet).
    Known facts from Basescan:
      - Created 2025-05-16 with 146,250,000 RIZE
      - Many breaks since genesis totaling ~100M+ RIZE
      - Current balance should be well BELOW 146.25M
    """
    print("\n── Validation: Bond #4 ─────────────────────────────────────")
    state = result.get("bondStates", {}).get("4")
    if not state:
        print("  [ERROR] Bond #4 not found in output!")
        return

    current = state["current"]
    events  = state["events"]

    print(f"  Owner:          {state['owner']}")
    print(f"  Events total:   {len(events)}")
    print(f"  Current balance:{current['balance']:>20,.4f} RIZE")
    print(f"  Current VP:     {current['vp']:>20,.4f}")
    print(f"  Maturity:       {current['maturity']*100:.4f}%")
    print(f"  Boost:          {current['boost']:.6f}x")
    print(f"  Full mat date:  {current['fullMatDate']}")
    print(f"  IsActive:       {current['isActive']}")

    print("\n  First 3 events:")
    for ev in events[:3]:
        print(f"    {ev['date']}  {ev['type']:<14} delta={ev['delta']:>15,.4f}  "
              f"balance={ev['balance']:>15,.4f}  mat={ev['maturity']*100:.2f}%  vp={ev['vp']:>15,.2f}")

    print("\n  Last 3 events:")
    for ev in events[-3:]:
        print(f"    {ev['date']}  {ev['type']:<14} delta={ev['delta']:>15,.4f}  "
              f"balance={ev['balance']:>15,.4f}  mat={ev['maturity']*100:.2f}%  vp={ev['vp']:>15,.2f}")

    # Sanity checks
    created_ev = next((e for e in events if e["type"] == "BondCreated"), None)
    if created_ev:
        assert created_ev["maturity"] == 0.0, "BondCreated must have maturity=0"
        assert created_ev["boost"] == 1.0,    "BondCreated must have boost=1x"
        assert abs(created_ev["vp"] - created_ev["balance"]) < 0.01, "VP at creation must equal balance (1x)"
        print("\n  ✓ Creation sanity: maturity=0, boost=1x, VP=balance ✓")

    if current["balance"] >= 146250000 * 0.99:
        print("\n  [WARNING] Balance still near initial deposit — breaks may not be applied!")
    else:
        reduction = 146250000 - current["balance"]
        print(f"\n  ✓ Balance correctly reduced by {reduction:,.2f} RIZE from breaks ✓")


def main():
    print("=" * 64)
    print("  BOOTSTRAP bond-states.json from genesis")
    print("=" * 64)

    # Verify sources
    if not verify_sources():
        print("\n[ABORT] Missing source JSONs. Run bootstrap for the 6 JSONs first.")
        sys.exit(1)

    # Compute
    result = compute_bond_states()

    # Validate with bond #4 as reference
    validate_bond4(result)

    print("\n" + "=" * 64)
    print("  Bootstrap complete.")
    print("  bond-states.json is ready to commit to the repo.")
    print("  Verify the bond #4 output above against Basescan before committing.")
    print("=" * 64)


if __name__ == "__main__":
    main()
