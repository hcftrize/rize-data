#!/usr/bin/env python3
"""
scrape_mcap.py  —  Tokerize
Fetches T-RIZE historical MCap, FDV + TVL and writes mcap-history.json.

Sources:
  - MCap + FDV : defillama.com/api/charts/coingecko/rize?fullChart=true
                 (data.mcaps = [[ts_ms, value], ...])
  - TVL        : api.llama.fi/protocol/t-rize
                 (data.tvl = [{date: ts_s, totalLiquidityUSD: value}, ...])

Usage:
  python scripts/scrape_mcap.py             # incremental — last 7 days
  python scripts/scrape_mcap.py --bootstrap # full history from genesis
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
WINDOW     = 7  # days rewritten in incremental mode


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

    print("=== Fetching MCap + FDV from DefiLlama charts ===")
    charts = fetch(CHARTS_URL)
    data   = charts.get("data", charts)  # handle both {data: ...} and direct

    # MCap: [[ts_ms, value], ...]
    mcap_by_date: dict[str, float] = {}
    for point in data.get("mcaps", []):
        if point[1] and point[1] > 0:
            d = ts_ms_to_date(int(point[0]))
            mcap_by_date[d] = round(float(point[1]), 2)
    print(f"  MCap points : {len(mcap_by_date)}")

    # FDV: not in this endpoint — derive from coinData if present
    # coinData.market_data.fully_diluted_valuation.usd = current FDV
    # We store FDV ratio: fdv = mcap / market_cap_fdv_ratio if available
    # For historical FDV we use: fdv = mcap / market_cap_fdv_ratio (constant approx)
    # Better: just store mcap for now, FDV can be calculated client-side
    # Actually coinData has market_cap_fdv_ratio — use it for today only
    fdv_ratio = None
    coin_data = data.get("coinData", {})
    md = coin_data.get("market_data", {})
    if md.get("market_cap_fdv_ratio"):
        fdv_ratio = float(md["market_cap_fdv_ratio"])

    fdv_by_date: dict[str, float] = {}
    if fdv_ratio and fdv_ratio > 0:
        for d, mcap in mcap_by_date.items():
            fdv_by_date[d] = round(mcap / fdv_ratio, 2)
    print(f"  FDV points  : {len(fdv_by_date)} (derived from ratio {fdv_ratio})")

    print("=== Fetching TVL from DefiLlama protocol ===")
    tvl_data = fetch(TVL_URL)
    tvl_by_date: dict[str, float] = {}
    for point in tvl_data.get("tvl", []):
        if isinstance(point, dict) and point.get("totalLiquidityUSD"):
            d = ts_s_to_date(int(point["date"]))
            tvl_by_date[d] = round(float(point["totalLiquidityUSD"]), 2)
    print(f"  TVL points  : {len(tvl_by_date)}")

    # ── Build fresh dataset ────────────────────────────────────────────────────
    all_dates = sorted(set(
        list(mcap_by_date.keys()) +
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

    # ── Merge with existing JSON ───────────────────────────────────────────────
    existing = load_existing()
    by_date  = {p["date"]: p for p in existing.get("series", [])}

    if bootstrap:
        by_date = fresh
        print(f"  Bootstrap: wrote {len(fresh)} points")
    else:
        cutoff  = (datetime.now(timezone.utc) - timedelta(days=WINDOW)).strftime("%Y-%m-%d")
        updated = sum(1 for d, p in fresh.items() if d >= cutoff and (by_date.update({d: p}) or True))
        print(f"  Incremental: updated last {WINDOW} days")

    final_series = [v for _, v in sorted(by_date.items())]

    payload = {
        "updatedAt": now_iso,
        "source":    "DefiLlama (MCap/FDV: charts API, TVL: protocol API)",
        "series":    final_series,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"\n  ✓ {len(final_series)} total points → {OUTPUT}")
    if final_series:
        last = final_series[-1]
        print(f"  Latest : {last['date']}")
        print(f"    MCap   : ${last.get('mcap', 0):,.0f}")
        print(f"    FDV    : ${last.get('fdv', 0):,.0f}")
        print(f"    TVL    : ${last.get('tvl', 0):,.0f}")
        print(f"    M/TVL  : {last.get('mcap_tvl', '—')}")

    ath = max((p.get("mcap", 0) or 0 for p in final_series), default=0)
    ath_date = next((p["date"] for p in final_series if (p.get("mcap") or 0) == ath), "—")
    print(f"  ATH MCap: ${ath:,.0f} on {ath_date}")


if __name__ == "__main__":
    main()
