#!/usr/bin/env python3
"""
scrape_volume.py  —  Tokerize
Fetches RIZE daily volume from CoinGecko and builds
rize-data-hub/volume-history.json.

Usage:
  python scripts/scrape_volume.py             # incremental (last 365 days, true daily granularity)
  python scripts/scrape_volume.py --bootstrap # same — 365 days is already the full CoinGecko free tier
"""

import json
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta, date
from pathlib import Path

# ── Config ─────────────────────────────────────────────────────────────────────
COINGECKO_API = "https://api.coingecko.com/api/v3"
RIZE_ID       = "rize"
OUTPUT        = Path(__file__).parent.parent / "rize-data-hub" / "volume-history.json"
TIMEOUT       = 30


# ── Helpers ────────────────────────────────────────────────────────────────────
def cg_fetch(path: str, params: dict) -> dict:
    qs  = urllib.parse.urlencode(params)
    url = f"{COINGECKO_API}{path}?{qs}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Tokerize-Bot/1.0",
        "Accept":     "application/json",
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


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
    today     = date.today().isoformat()

    existing        = load_existing()
    existing_series = existing.get("series", [])

    # Always fetch 365 days — above 90 days CoinGecko returns true daily granularity (00:00 UTC)
    # This overwrites the last 365 points in the JSON, older history is preserved
    days = 365

    print(f"=== {'BOOTSTRAP' if bootstrap else 'INCREMENTAL'} — fetching {days} days ===")
    print(f"  Calling CoinGecko market_chart for {RIZE_ID}…")

    data = cg_fetch(f"/coins/{RIZE_ID}/market_chart", {
        "vs_currency": "usd",
        "days":        str(days),
    })

    raw_vols = data.get("total_volumes", [])
    if not raw_vols:
        print("  WARNING: no volume data returned — output unchanged.", file=sys.stderr)
        sys.exit(0)

    print(f"  → {len(raw_vols)} data points received")

    # Convert to [{date, volume}] — CoinGecko returns [timestamp_ms, value]
    # Group by date (take last value per day to avoid duplicates at day boundaries)
    by_date: dict[str, float] = {}
    for ts, v in raw_vols:
        d = datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m-%d")
        by_date[d] = v  # last value wins

    # Exclude today — the hourly points for today are incomplete
    # Tomorrow's run at 00:15 UTC will write today's definitive value
    by_date.pop(today, None)

    new_series = [{"date": d, "volume": round(v, 2)}
                  for d, v in sorted(by_date.items())]

    # Merge with existing — existing points outside the fetch window are kept
    if existing_series and not bootstrap:
        # Keep existing points strictly before the fetch window
        fetch_start = new_series[0]["date"] if new_series else today
        kept = [p for p in existing_series if p["date"] < fetch_start]
        merged = kept + new_series
    else:
        merged = new_series

    # Deduplicate by date (last wins)
    seen = {}
    for p in merged:
        seen[p["date"]] = p
    final_series = [seen[d] for d in sorted(seen.keys())]

    payload = {
        "updatedAt": now_iso,
        "series":    final_series,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"  ✓ {len(final_series)} total points → {OUTPUT}")
    if final_series:
        last = final_series[-1]
        print(f"  Latest: {last['date']} = ${last['volume']:,.0f} volume")


if __name__ == "__main__":
    main()
