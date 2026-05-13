#!/usr/bin/env python3
"""
scrape_mcap.py  —  Tokerize
Fetches T-RIZE historical MCap, FDV, TVL.

Sources (primary):
  - prices + mcaps : defillama.com/api/charts/coingecko/rize?fullChart=true
  - total_supply   : coinData.market_data.total_supply (from same call)
  - FDV            : price × total_supply
  - TVL            : api.llama.fi/protocol/t-rize

Fallback (when DefiLlama returns 0 for mcap or price on a given date):
  - mcap + price   : CoinGecko /coins/rize/market_chart?days=max&interval=daily
  - total_supply   : CoinGecko /coins/rize market_data.total_supply

Usage:
  python scripts/scrape_mcap.py             # incremental — last 7 days
  python scripts/scrape_mcap.py --bootstrap # full history — overwrites all
"""

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Config ─────────────────────────────────────────────────────────────────────
CHARTS_URL   = "https://defillama.com/api/charts/coingecko/rize?fullChart=true"
TVL_URL      = "https://api.llama.fi/protocol/t-rize"
CG_BASE      = "https://api.coingecko.com/api/v3"
CG_CHART_URL = f"{CG_BASE}/coins/rize/market_chart?vs_currency=usd&days=max&interval=daily"
CG_COIN_URL  = f"{CG_BASE}/coins/rize?localization=false&tickers=false&market_data=true&community_data=false&developer_data=false"
CG_KEY       = os.environ.get("COINGECKO_API_KEY", "")

OUTPUT  = Path(__file__).parent.parent / "rize-data-hub" / "mcap-history.json"
TIMEOUT = 30
WINDOW  = 7   # days for incremental update


# ── Helpers ────────────────────────────────────────────────────────────────────
def fetch(url: str, is_cg: bool = False) -> dict:
    headers = {
        "User-Agent": "Tokerize-Bot/1.0",
        "Accept":     "application/json",
    }
    if is_cg and CG_KEY:
        headers["x-cg-demo-api-key"] = CG_KEY
    req = urllib.request.Request(url, headers=headers)
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


# ── CoinGecko fallback ─────────────────────────────────────────────────────────
def fetch_cg_fallback() -> tuple[dict, dict, float]:
    """
    Returns (price_by_date, mcap_by_date, total_supply) from CoinGecko.
    Called only when DefiLlama has gaps (0 values).
    """
    print("  -> Fetching CoinGecko fallback (market_chart + coin detail)...")
    cg_price: dict[str, float] = {}
    cg_mcap:  dict[str, float] = {}
    cg_supply = 0.0

    try:
        time.sleep(2)
        chart = fetch(CG_CHART_URL, is_cg=True)
        for ts_ms, price in chart.get("prices", []):
            if price and price > 0:
                d = ts_ms_to_date(int(ts_ms))
                cg_price[d] = float(price)
        for ts_ms, mcap in chart.get("market_caps", []):
            if mcap and mcap > 0:
                d = ts_ms_to_date(int(ts_ms))
                cg_mcap[d] = round(float(mcap), 2)
        print(f"    CG price points : {len(cg_price)}")
        print(f"    CG mcap points  : {len(cg_mcap)}")
    except Exception as e:
        print(f"    Warning: CoinGecko market_chart failed ({e})")

    try:
        time.sleep(2)
        coin = fetch(CG_COIN_URL, is_cg=True)
        cg_supply = float(coin.get("market_data", {}).get("total_supply") or 0)
        print(f"    CG total supply : {cg_supply:,.0f}")
    except Exception as e:
        print(f"    Warning: CoinGecko coin detail failed ({e})")

    return cg_price, cg_mcap, cg_supply


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    bootstrap = "--bootstrap" in sys.argv
    now_iso   = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ── Fetch charts (MCap + Price) from DefiLlama ────────────────────────────
    print("=== Fetching MCap + Price from DefiLlama charts ===")
    dl_price: dict[str, float] = {}
    dl_mcap:  dict[str, float] = {}
    total_supply = 0.0

    try:
        charts    = fetch(CHARTS_URL)
        data      = charts.get("data", charts)
        coin_data = data.get("coinData", {})
        md        = coin_data.get("market_data", {})
        total_supply = float(md.get("total_supply") or 0)
        print(f"  Total supply : {total_supply:,.0f}")

        for ts_ms, price in data.get("prices", []):
            if price and price > 0:
                d = ts_ms_to_date(int(ts_ms))
                dl_price[d] = float(price)

        for ts_ms, mcap in data.get("mcaps", []):
            if mcap and mcap > 0:
                d = ts_ms_to_date(int(ts_ms))
                dl_mcap[d] = round(float(mcap), 2)

        print(f"  DL mcap points  : {len(dl_mcap)}")
        print(f"  DL price points : {len(dl_price)}")
    except Exception as e:
        print(f"  Warning: DefiLlama charts failed ({e})")

    # ── Fetch TVL from DefiLlama ───────────────────────────────────────────────
    print("=== Fetching TVL from DefiLlama protocol ===")
    tvl_by_date: dict[str, float] = {}
    try:
        tvl_data = fetch(TVL_URL)
        for point in tvl_data.get("tvl", []):
            if isinstance(point, dict) and point.get("totalLiquidityUSD"):
                d = ts_s_to_date(int(point["date"]))
                tvl_by_date[d] = round(float(point["totalLiquidityUSD"]), 2)
        print(f"  TVL points      : {len(tvl_by_date)}")
    except Exception as e:
        print(f"  Warning: DefiLlama TVL failed ({e})")

    # ── Detect gaps — dates where DefiLlama gave 0 ────────────────────────────
    # A gap = date present in TVL (date exists) but missing from mcap or price.
    all_dl_dates = sorted(set(
        list(dl_mcap.keys()) + list(dl_price.keys()) + list(tvl_by_date.keys())
    ))
    gaps = [d for d in all_dl_dates if d not in dl_mcap or d not in dl_price]

    # ── CoinGecko fallback if needed ──────────────────────────────────────────
    cg_price: dict[str, float] = {}
    cg_mcap:  dict[str, float] = {}
    cg_supply = 0.0

    if gaps:
        print(f"\n  WARNING: {len(gaps)} date(s) missing mcap/price from DefiLlama: {gaps[:10]}")
        print("=== CoinGecko fallback ===")
        cg_price, cg_mcap, cg_supply = fetch_cg_fallback()
        filled = [d for d in gaps if d in cg_mcap]
        print(f"  Fallback filled {len(filled)}/{len(gaps)} gaps")
    else:
        print("\n  OK: No gaps — DefiLlama data complete, CoinGecko fallback not needed")

    # ── Merge: DefiLlama primary, CoinGecko fills the gaps ───────────────────
    if total_supply <= 0 and cg_supply > 0:
        total_supply = cg_supply
        print(f"  Using CoinGecko total supply as fallback: {total_supply:,.0f}")

    # DL wins on conflict (put DL last so it overwrites CG on same dates)
    price_by_date: dict[str, float] = {**cg_price, **dl_price}
    mcap_by_date:  dict[str, float] = {**cg_mcap,  **dl_mcap}

    # FDV = price x total_supply
    fdv_by_date: dict[str, float] = {}
    if total_supply > 0:
        for d, price in price_by_date.items():
            fdv_by_date[d] = round(price * total_supply, 2)

    print(f"\n  Final mcap points : {len(mcap_by_date)}")
    print(f"  Final FDV points  : {len(fdv_by_date)}")

    # ── Build fresh dataset ────────────────────────────────────────────────────
    all_dates = sorted(set(
        list(mcap_by_date.keys()) +
        list(fdv_by_date.keys())  +
        list(tvl_by_date.keys())
    ))

    fresh: dict[str, dict] = {}
    for d in all_dates:
        mcap  = mcap_by_date.get(d)
        fdv   = fdv_by_date.get(d)
        tvl   = tvl_by_date.get(d)
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
        "source":    "DefiLlama (primary) + CoinGecko (fallback) — FDV = price x totalSupply",
        "series":    final_series,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"\n  OK {len(final_series)} total points -> {OUTPUT}")
    if final_series:
        last = final_series[-1]
        print(f"  Latest : {last['date']}")
        print(f"    MCap  : ${last.get('mcap', 0):,.0f}")
        print(f"    FDV   : ${last.get('fdv', 0):,.0f}")
        print(f"    TVL   : ${last.get('tvl', 0):,.0f}")

    ath = max((p.get("mcap", 0) or 0 for p in final_series), default=0)
    ath_date = next((p["date"] for p in final_series if (p.get("mcap") or 0) == ath), "—")
    print(f"  ATH MCap : ${ath:,.0f} on {ath_date}")

    july25 = by_date.get("2025-07-22") or by_date.get("2025-07-21")
    if july25:
        print(f"\n  Verif juillet 2025 : MCap=${july25.get('mcap',0):,.0f} FDV=${july25.get('fdv',0):,.0f}")


if __name__ == "__main__":
    main()
