#!/usr/bin/env python3
"""
scrape_volume.py  —  Tokerize
Fetches RIZE daily market data from CoinGecko /history endpoint and updates
rize-data-hub/volume-history.json.

Each point contains: volume, mcap, fdv, tvl

Usage:
  python scripts/scrape_volume.py             # updates last 7 days
  python scripts/scrape_volume.py --bootstrap # full history from genesis
"""

import json
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta, date
from pathlib import Path

# ── Config ─────────────────────────────────────────────────────────────────────
COINGECKO_API = "https://api.coingecko.com/api/v3"
RIZE_ID       = "rize"
RIZE_GENESIS  = date(2025, 5, 15)   # first trading day
OUTPUT        = Path(__file__).parent.parent / "rize-data-hub" / "volume-history.json"
TIMEOUT       = 30
WINDOW_DAYS   = 7
SLEEP_BETWEEN = 3.0  # seconds between API calls


# ── Helpers ────────────────────────────────────────────────────────────────────
def cg_fetch(path: str, params: dict = {}) -> dict:
    qs  = urllib.parse.urlencode(params) if params else ""
    url = f"{COINGECKO_API}{path}?{qs}" if qs else f"{COINGECKO_API}{path}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Tokerize-Bot/1.0",
        "Accept":     "application/json",
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


def fetch_day(d: date) -> dict | None:
    """Fetch market data for a specific date from CoinGecko /history endpoint."""
    date_str = d.strftime("%d-%m-%Y")
    try:
        data = cg_fetch(f"/coins/{RIZE_ID}/history", {"date": date_str})
        md   = data.get("market_data", {})

        volume = md.get("total_volume",          {}).get("usd")
        mcap   = md.get("market_cap",            {}).get("usd")
        fdv    = md.get("fully_diluted_valuation",{}).get("usd")
        tvl    = md.get("total_value_locked",    {}).get("usd")

        if volume is None and mcap is None:
            print(f"  WARNING: no market data for {date_str}")
            return None

        return {
            "date":   d.isoformat(),
            "volume": round(float(volume), 2) if volume else None,
            "mcap":   round(float(mcap),   2) if mcap   else None,
            "fdv":    round(float(fdv),    2) if fdv    else None,
            "tvl":    round(float(tvl),    2) if tvl    else None,
        }
    except Exception as e:
        print(f"  WARNING: could not fetch {date_str}: {e}")
        return None


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
    today     = date.today()

    existing        = load_existing()
    existing_series = existing.get("series", [])

    # Build lookup from existing JSON — preserve all existing fields
    by_date = {p["date"]: p for p in existing_series}

    if bootstrap:
        # Full history from genesis to today
        delta  = (today - RIZE_GENESIS).days + 1
        days   = list(range(delta - 1, -1, -1))
        print(f"=== BOOTSTRAP — fetching {len(days)} days from genesis ({RIZE_GENESIS}) ===")
    else:
        days = list(range(WINDOW_DAYS - 1, -1, -1))
        print(f"=== INCREMENTAL — fetching last {WINDOW_DAYS} days ===")

    updated = []
    for i in days:
        d        = today - timedelta(days=i)
        date_str = d.isoformat()

        point = fetch_day(d)
        if point is not None:
            old = by_date.get(date_str, {})
            # Merge — new values overwrite, existing fields preserved
            merged = {**old, **{k: v for k, v in point.items() if v is not None}}
            if merged != old:
                updated.append(date_str)
                print(f"  {date_str}: volume=${point.get('volume') or 0:,.0f} mcap=${point.get('mcap') or 0:,.0f} fdv=${point.get('fdv') or 0:,.0f} tvl=${point.get('tvl') or 0:,.0f}")
            by_date[date_str] = merged

        time.sleep(SLEEP_BETWEEN)

    # Rebuild series sorted by date
    final_series = [v for _, v in sorted(by_date.items())]

    payload = {
        "updatedAt": now_iso,
        "series":    final_series,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"\n  ✓ {len(final_series)} total points → {OUTPUT}")
    print(f"  Updated: {len(updated)} point(s)")
    if final_series:
        last = final_series[-1]
        print(f"  Latest: {last['date']} — volume=${last.get('volume') or 0:,.0f} mcap=${last.get('mcap') or 0:,.0f}")


if __name__ == "__main__":
    main()
