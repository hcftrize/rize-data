#!/usr/bin/env python3
"""
scrape_volume.py  —  Tokerize
Fetches RIZE daily volume from CoinGecko /history endpoint and updates
rize-data-hub/volume-history.json.

Logic:
  - Calls /coins/rize/history?date=DD-MM-YYYY for the last 7 days
  - Overwrites/fills those 7 points in the JSON with exact CoinGecko values
  - Preserves all existing history beyond 7 days
  - If cron missed 2-3 days, those days get corrected automatically

Usage:
  python scripts/scrape_volume.py             # updates last 7 days
  python scripts/scrape_volume.py --bootstrap # updates last 365 days
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
RIZE_GENESIS  = date(2025, 5, 15)
OUTPUT        = Path(__file__).parent.parent / "rize-data-hub" / "volume-history.json"
TIMEOUT       = 30
WINDOW_DAYS   = 7
SLEEP_BETWEEN = 3.0


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


def fetch_day(d: date) -> float | None:
    date_str = d.strftime("%d-%m-%Y")
    try:
        data   = cg_fetch(f"/coins/{RIZE_ID}/history", {"date": date_str})
        volume = data.get("market_data", {}).get("total_volume", {}).get("usd")
        return round(float(volume), 2) if volume else None
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

    by_date = {p["date"]: p["volume"] for p in existing_series}

    if bootstrap:
        delta = (today - RIZE_GENESIS).days + 1
        days  = list(range(delta - 1, -1, -1))
        print(f"=== BOOTSTRAP — fetching {len(days)} days from genesis ({RIZE_GENESIS}) ===")
    else:
        days = list(range(WINDOW_DAYS - 1, -1, -1))
        print(f"=== INCREMENTAL — fetching last {WINDOW_DAYS} days ===")

    updated = []
    for i in days:
        d        = today - timedelta(days=i)
        date_str = d.isoformat()
        volume   = fetch_day(d)
        if volume is not None:
            old = by_date.get(date_str)
            by_date[date_str] = volume
            if old != volume:
                print(f"  {date_str}: {f'${old:,.2f}' if old else 'new'} → ${volume:,.2f}")
                updated.append(date_str)
        time.sleep(SLEEP_BETWEEN)

    final_series = [{"date": d, "volume": v} for d, v in sorted(by_date.items())]

    payload = {
        "updatedAt": now_iso,
        "series":    final_series,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"\n  ✓ {len(final_series)} total points → {OUTPUT}")
    print(f"  Updated: {len(updated)} point(s) — {', '.join(updated) if updated else 'none'}")
    if final_series:
        last = final_series[-1]
        print(f"  Latest: {last['date']} = ${last['volume']:,.0f} volume")


if __name__ == "__main__":
    main()
