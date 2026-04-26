#!/usr/bin/env python3
"""
scrape_mcap.py  —  Tokerize
Fetches T-RIZE historical MCap, FDV, TVL from DefiLlama.

Sources:
  - prices + mcaps : defillama.com/api/charts/coingecko/rize?fullChart=true
  - total_supply   : coinData.market_data.total_supply (from same call)
  - FDV            : price × total_supply (matches DefiLlama exactly)
  - TVL            : api.llama.fi/protocol/t-rize

Usage:
  python scripts/scrape_mcap.py             # incremental — last 7 days
  python scripts/scrape_mcap.py --bootstrap # full history — overwrites all
"""

import json
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Config ─────────────────────────────────────────────────────────────────────
CHARTS_URL = "https://defillama.com/api/charts/coingecko/rize?fullChart=true"
TVL_URL    = "https://api.llama.fi/protocol/t-rize"
OUTPUT     = Path(__file__).parent.parent / "rize-data-hub" / "mcap-history.json"
TIMEOUT    = 30
WINDOW     = 7


# ── Helpers ────────────────────────────────────────────────────────────────────
def fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Tokerize-Bot/1.0",
        "Accept":     "application/json",
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


def ts_ms_to_date(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def ts_s_to_date(ts_s: int) -> str:
    return datetime.fromtimestamp(ts_s, tz=timezone.utc).strftime("%Y-%m-%d")


def load_existing() -> dict:
    if OUTPUT.exists():
        try:
            with open(OUTPUT) as f:
                return json.load(f)
        except Exception:
            pass
    return {"updatedAt": "", "series": []}


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    bootstrap = "--bootstrap" in sys.argv
    now_iso   = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ── Fetch charts (MCap + Price) ────────────────────────────────────────────
    print("=== Fetching MCap + Price from DefiLlama charts ===")
    charts     = fetch(CHARTS_URL)
    data       = charts.get("data", charts)
    coin_data  = data.get("coinData", {})
    md         = coin_data.get("market_data", {})

    # Total supply — used to compute FDV = price × total_supply
    total_supply = float(md.get("total_supply") or 0)
    print(f"  Total supply : {total_supply:,.0f}")

    # Build price lookup: date → price
    price_by_date: dict[str, float] = {}
    for ts_ms, price in data.get("prices", []):
        if price and price > 0:
            d = ts_ms_to_date(int(ts_ms))
            price_by_date[d] = float(price)

    # Build mcap lookup: date → mcap
    mcap_by_date: dict[str, float] = {}
    for ts_ms, mcap in data.get("mcaps", []):
        if mcap and mcap > 0:
            d = ts_ms_to_date(int(ts_ms))
            mcap_by_date[d] = round(float(mcap), 2)

    # FDV = price × total_supply (matches DefiLlama exactly)
    fdv_by_date: dict[str, float] = {}
    if total_supply > 0:
        for d, price in price_by_date.items():
            fdv_by_date[d] = round(price * total_supply, 2)

    print(f"  MCap points  : {len(mcap_by_date)}")
    print(f"  FDV points   : {len(fdv_by_date)}")

    # ── Fetch TVL ──────────────────────────────────────────────────────────────
    print("=== Fetching TVL from DefiLlama protocol ===")
    tvl_data = fetch(TVL_URL)
    tvl_by_date: dict[str, float] = {}
    for point in tvl_data.get("tvl", []):
        if isinstance(point, dict) and point.get("totalLiquidityUSD"):
            d = ts_s_to_date(int(point["date"]))
            tvl_by_date[d] = round(float(point["totalLiquidityUSD"]), 2)
    print(f"  TVL points   : {len(tvl_by_date)}")

    # ── Build fresh dataset ────────────────────────────────────────────────────
    all_dates = sorted(set(
        list(mcap_by_date.keys()) +
        list(fdv_by_date.keys())  +
        list(tvl_by_date.keys())
    ))

    fresh: dict[str, dict] = {}
    for d in all_dates:
        mcap = mcap_by_date.get(d)
        fdv  = fdv_by_date.get(d)
        tvl  = tvl_by_date.get(d)
        point = {"date": d}
        if mcap:  point["mcap"] = mcap
        if fdv:   point["fdv"]  = fdv
        if tvl:   point["tvl"]  = tvl
        if mcap and tvl and tvl > 0:
            point["mcap_tvl"] = round(mcap / tvl, 4)
        if fdv and tvl and tvl > 0:
            point["fdv_tvl"]  = round(fdv  / tvl, 4)
        fresh[d] = point

    # ── Merge with existing ────────────────────────────────────────────────────
    existing = load_existing()
    by_date  = {p["date"]: p for p in existing.get("series", [])}

    if bootstrap:
        by_date = fresh
        print(f"\n  Bootstrap: {len(fresh)} points written")
    else:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=WINDOW)).strftime("%Y-%m-%d")
        for d, p in fresh.items():
            if d >= cutoff:
                by_date[d] = p
        print(f"\n  Incremental: last {WINDOW} days updated")

    final_series = [v for _, v in sorted(by_date.items())]

    payload = {
        "updatedAt": now_iso,
        "source":    "DefiLlama — FDV = price × totalSupply",
        "series":    final_series,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"  ✓ {len(final_series)} total points → {OUTPUT}")
    if final_series:
        last = final_series[-1]
        print(f"  Latest : {last['date']}")
        print(f"    MCap  : ${last.get('mcap', 0):,.0f}")
        print(f"    FDV   : ${last.get('fdv', 0):,.0f}")
        print(f"    TVL   : ${last.get('tvl', 0):,.0f}")

    # ATH check
    ath = max((p.get("mcap", 0) or 0 for p in final_series), default=0)
    ath_date = next((p["date"] for p in final_series if (p.get("mcap") or 0) == ath), "—")
    print(f"  ATH MCap : ${ath:,.0f} on {ath_date}")

    # Verify july 25
    july25 = by_date.get("2025-07-22") or by_date.get("2025-07-21")
    if july25:
        print(f"\n  Vérif juillet 2025 : MCap=${july25.get('mcap',0):,.0f} FDV=${july25.get('fdv',0):,.0f}")


if __name__ == "__main__":
    main()
