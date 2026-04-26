#!/usr/bin/env python3
"""
scrape_mcap.py  —  Tokerize
Fetches T-RIZE historical MCap, FDV, TVL from DefiLlama in a single API call
and writes rize-data-hub/mcap-history.json.

Usage:
  python scripts/scrape_mcap.py   # full history — always fetches everything (1 call)
"""

import json
import urllib.request
from datetime import datetime, timezone, date
from pathlib import Path

# ── Config ─────────────────────────────────────────────────────────────────────
LLAMA_URL  = "https://api.llama.fi/protocol/t-rize"
OUTPUT     = Path(__file__).parent.parent / "rize-data-hub" / "mcap-history.json"
TIMEOUT    = 30


# ── Helpers ────────────────────────────────────────────────────────────────────
def llama_fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Tokerize-Bot/1.0",
        "Accept":     "application/json",
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


def ts_to_date(ts: int) -> str:
    return datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    today   = date.today().isoformat()

    print("=== FETCHING T-RIZE data from DefiLlama (1 call) ===")
    data = llama_fetch(LLAMA_URL)

    # ── TVL ────────────────────────────────────────────────────────────────────
    tvl_by_date: dict[str, float] = {}
    for point in data.get("tvl", []):
        d = ts_to_date(point["date"])
        tvl_by_date[d] = round(float(point["totalLiquidityUSD"]), 2)
    print(f"  TVL points       : {len(tvl_by_date)}")

    # ── MCap ───────────────────────────────────────────────────────────────────
    mcap_by_date: dict[str, float] = {}
    for point in data.get("mcap", []):
        d = ts_to_date(point["date"])
        mcap_by_date[d] = round(float(point["mcap"]), 2)
    print(f"  MCap points      : {len(mcap_by_date)}")

    # ── FDV ────────────────────────────────────────────────────────────────────
    # DefiLlama sometimes returns fdv separately, sometimes inside mcap array
    fdv_by_date: dict[str, float] = {}
    for point in data.get("fdv", []):
        d = ts_to_date(point["date"])
        fdv_by_date[d] = round(float(point.get("fdv", 0) or 0), 2)
    # Fallback: try inside mcap array
    if not fdv_by_date:
        for point in data.get("mcap", []):
            if "fdv" in point and point["fdv"]:
                d = ts_to_date(point["date"])
                fdv_by_date[d] = round(float(point["fdv"]), 2)
    print(f"  FDV points       : {len(fdv_by_date)}")

    # ── Also extract any extra available fields ─────────────────────────────────
    # Staking TVL, borrowed, etc. if present
    staking_by_date: dict[str, float] = {}
    for point in data.get("staking", []):
        d = ts_to_date(point["date"])
        staking_by_date[d] = round(float(point.get("totalLiquidityUSD", 0) or 0), 2)
    if staking_by_date:
        print(f"  Staking points   : {len(staking_by_date)}")

    borrowed_by_date: dict[str, float] = {}
    for point in data.get("borrowed", []):
        d = ts_to_date(point["date"])
        borrowed_by_date[d] = round(float(point.get("totalLiquidityUSD", 0) or 0), 2)
    if borrowed_by_date:
        print(f"  Borrowed points  : {len(borrowed_by_date)}")

    # ── Build unified series ───────────────────────────────────────────────────
    all_dates = sorted(set(
        list(tvl_by_date.keys()) +
        list(mcap_by_date.keys()) +
        list(fdv_by_date.keys())
    ))

    series = []
    for d in all_dates:
        tvl  = tvl_by_date.get(d)
        mcap = mcap_by_date.get(d)
        fdv  = fdv_by_date.get(d) or None

        point = {"date": d}
        if mcap:  point["mcap"]  = mcap
        if fdv:   point["fdv"]   = fdv
        if tvl:   point["tvl"]   = tvl
        if mcap and tvl and tvl > 0:
            point["mcap_tvl"] = round(mcap / tvl, 4)
        if fdv and tvl and tvl > 0:
            point["fdv_tvl"]  = round(fdv  / tvl, 4)
        if staking_by_date.get(d):
            point["staking"]  = staking_by_date[d]
        if borrowed_by_date.get(d):
            point["borrowed"] = borrowed_by_date[d]

        series.append(point)

    payload = {
        "updatedAt": now_iso,
        "source":    "DefiLlama — api.llama.fi/protocol/t-rize",
        "series":    series,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"\n  ✓ {len(series)} daily points → {OUTPUT}")
    if series:
        last = series[-1]
        print(f"  Latest: {last['date']}")
        print(f"    MCap    : ${last.get('mcap', 0):,.0f}")
        print(f"    FDV     : ${last.get('fdv', 0):,.0f}")
        print(f"    TVL     : ${last.get('tvl', 0):,.0f}")
        print(f"    M/TVL   : {last.get('mcap_tvl', '—')}")

    # ATH stats
    ath_mcap = max((p.get("mcap", 0) or 0 for p in series), default=0)
    ath_date = next((p["date"] for p in series if (p.get("mcap") or 0) == ath_mcap), "—")
    print(f"  ATH MCap: ${ath_mcap:,.0f} on {ath_date}")


if __name__ == "__main__":
    main()
