#!/usr/bin/env python3
"""
scrape_unbonding.py  —  Tokerize
Fetches BondBroken events from Goldsky and builds a daily rolling
7-day unbonding queue series into rize-data-hub/unbonding-queue.json.

Usage:
  python scripts/scrape_unbonding.py             # incremental (last 14 days)
  python scripts/scrape_unbonding.py --bootstrap # full history from genesis
"""

import json
import sys
import urllib.request
from datetime import datetime, timezone, timedelta, date
from pathlib import Path

# ── Config ─────────────────────────────────────────────────────────────────────
GOLDSKY_URL = "https://api.goldsky.com/api/public/project_cmoa6u5wk3kx201y4g3s52z77/subgraphs/tokerize-bond-broken/1.1.0/gn"
OUTPUT      = Path(__file__).parent.parent / "rize-data-hub" / "unbonding-queue.json"
TIMEOUT     = 30
PAGE_SIZE   = 1000


# ── Helpers ────────────────────────────────────────────────────────────────────
def graphql(query: str) -> dict:
    payload = json.dumps({"query": query}).encode()
    req = urllib.request.Request(
        GOLDSKY_URL, data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "Tokerize-Bot/1.0"}
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


def fetch_events(start_date: str, end_date: str) -> list:
    """Fetch all BondBroken events between start_date and end_date (YYYY-MM-DD)."""
    all_events = []
    skip = 0
    while True:
        q = f"""{{
          bondBrokens(
            first: {PAGE_SIZE}, skip: {skip},
            orderBy: timestamp, orderDirection: asc,
            where: {{ date_gte: "{start_date}", date_lte: "{end_date}" }}
          ) {{ id amount date }}
        }}"""
        res = graphql(q)
        items = res.get("data", {}).get("bondBrokens", [])
        all_events.extend(items)
        if len(items) < PAGE_SIZE:
            break
        skip += PAGE_SIZE
    print(f"  → {len(all_events)} events fetched ({start_date} → {end_date})")
    return all_events


def build_series(events: list, from_date: str, to_date: str) -> list:
    """
    For each day in [from_date, to_date], compute the rolling 7-day
    unbonding queue = sum of BondBroken amounts with date in [day-7, day].
    Returns [{date, value}, ...].
    """
    # Group by date
    by_date: dict[str, float] = {}
    for e in events:
        d = e["date"]
        by_date[d] = by_date.get(d, 0) + float(e["amount"] or 0)

    series = []
    cur = datetime.fromisoformat(from_date)
    end = datetime.fromisoformat(to_date)
    while cur <= end:
        day = cur.strftime("%Y-%m-%d")
        cutoff = (cur - timedelta(days=7)).strftime("%Y-%m-%d")
        total = sum(v for d, v in by_date.items() if cutoff <= d <= day)
        series.append({"date": day, "value": round(total, 4)})
        cur += timedelta(days=1)
    return series


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
    today     = date.today().isoformat()
    now_iso   = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    existing = load_existing()
    existing_series = existing.get("series", [])

    if bootstrap:
        print("=== BOOTSTRAP — full history from genesis ===")
        # Fetch everything from genesis
        start_fetch = "2024-07-31"
        end_fetch   = today
        events = fetch_events(start_fetch, end_fetch)

        # Need events from 7 days before first day too (for rolling window)
        # Genesis is 2024-07-31, window starts 7 days before first event
        series_start = "2024-07-31"
        new_series = build_series(events, series_start, today)
        print(f"  Built {len(new_series)} daily points")

    else:
        print("=== INCREMENTAL — last 14 days ===")
        if not existing_series:
            print("  No existing data — run with --bootstrap first")
            sys.exit(0)

        # Find last date in existing series
        last_date = existing_series[-1]["date"]
        print(f"  Last existing point: {last_date}")

        if last_date == today:
            print("  Already up to date — nothing to do")
            sys.exit(0)

        # Fetch events for the rolling window (14 days back to cover 7-day window correctly)
        window_start = (datetime.fromisoformat(last_date) - timedelta(days=7)).strftime("%Y-%m-%d")
        events = fetch_events(window_start, today)

        # Rebuild from day after last existing point
        rebuild_from = (datetime.fromisoformat(last_date) + timedelta(days=1)).strftime("%Y-%m-%d")

        # We need all events for the rolling window — combine with what we know
        # by rebuilding only the new days (series_start = rebuild_from)
        # but we need events from window_start for correct 7-day rolling
        new_points = build_series(events, rebuild_from, today)
        print(f"  Adding {len(new_points)} new daily points")

        # Merge: keep existing up to last_date, append new points
        new_series = existing_series + new_points

    # Write output
    payload = {
        "updatedAt": now_iso,
        "series":    new_series,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"  ✓ {len(new_series)} total points → {OUTPUT}")
    if new_series:
        last = new_series[-1]
        print(f"  Latest: {last['date']} = {last['value']:,.0f} RIZE unbonding")


if __name__ == "__main__":
    main()
