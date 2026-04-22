#!/usr/bin/env python3
"""
scrape_canton.py  —  Tokerize
Fetches T-RIZE canton revenue from lighthouse.fivenorth.io (server-side,
no CORS issue) and writes rize-data-hub/canton-revenue.json.

Usage:
  python scrape_canton.py            # daily incremental (last 14 days)
  python scrape_canton.py --bootstrap  # one-shot full history from genesis
"""

import json
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Config ─────────────────────────────────────────────────────────────────────
API_BASE     = "https://lighthouse.fivenorth.io/api/parties"
RZ_GENESIS   = "2024-07-31T00:00:00.000Z"
VALIDATOR_ID = "TRIZEGroup-cantonMainnetValidator-1::12206ab3bf15b14410220357d6a6375eb1015f2e7fade1deb449463c2f2a25304889"
RIZESCORE_ID = "TRIZEGroup-RIZEScore::12206ab3bf15b14410220357d6a6375eb1015f2e7fade1deb449463c2f2a25304889"
OUTPUT      = Path(__file__).parent / "rize-data-hub" / "canton-revenue.json"
TIMEOUT     = 30

# In daily mode: refetch last N days to catch any late-arriving entries
INCREMENTAL_WINDOW_DAYS = 14

# ── Helpers ────────────────────────────────────────────────────────────────────
def fetch_json(url: str) -> list:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Tokerize-DataBot/1.0 (+https://tokerize.com)",
        "Accept":     "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            if r.status != 200:
                print(f"  WARNING HTTP {r.status}: {url}", file=sys.stderr)
                return []
            return json.loads(r.read())
    except Exception as e:
        print(f"  ERROR fetching {url}: {e}", file=sys.stderr)
        return []


def build_url(party_id: str, endpoint: str, start: str, end: str) -> str:
    params = urllib.parse.urlencode({"start_time": start, "end_time": end})
    pid    = urllib.parse.quote(party_id, safe="")
    return f"{API_BASE}/{pid}/stats/{endpoint}?{params}"


def week_key(ts: str) -> str:
    """ISO date of the Monday of the week containing ts."""
    if not ts:
        return ""
    d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    monday = d - timedelta(days=d.weekday())          # weekday(): Mon=0
    return monday.strftime("%Y-%m-%d")


def week_label(iso: str) -> str:
    """'Jul 31, 24' style label — matches rzWeekLabel() in the HTML."""
    d = datetime.fromisoformat(iso + "T12:00:00+00:00")
    return d.strftime("%b %-d, %y")                   # Linux; use %#d on Windows


def load_existing() -> dict:
    if OUTPUT.exists():
        try:
            with open(OUTPUT) as f:
                return json.load(f)
        except Exception:
            pass
    return {"weeks": [], "labels": [],
            "valW": [], "appW": [], "scoreW": [], "burnW": [], "netW": [],
            "cumNetArr": [], "cumValArr": [], "cumAppArr": [], "cumScoreArr": [],
            "rev1w": 0, "rev1m": 0, "rev1y": 0, "rev2y": 0,
            "totalNet": 0, "totalVal": 0, "totalApp": 0,
            "totalScore": 0, "totalBurn": 0,
            "updatedAt": ""}


# ── Core logic ─────────────────────────────────────────────────────────────────
def fetch_all(start: str, end: str) -> dict:
    """Fetch the 4 endpoints and return a weekMap {week_key: {val,app,score,burn}}."""
    print(f"  Fetching validator rewards  ({start[:10]} → {end[:10]}) …")
    val_rew   = fetch_json(build_url(VALIDATOR_ID, "rewards", start, end))
    print(f"    → {len(val_rew)} entries")

    print(f"  Fetching RIZEScore rewards …")
    score_rew = fetch_json(build_url(RIZESCORE_ID, "rewards", start, end))
    print(f"    → {len(score_rew)} entries")

    print(f"  Fetching validator burns …")
    val_burn  = fetch_json(build_url(VALIDATOR_ID, "burns",   start, end))
    print(f"    → {len(val_burn)} entries")

    print(f"  Fetching RIZEScore burns …")
    score_burn= fetch_json(build_url(RIZESCORE_ID, "burns",   start, end))
    print(f"    → {len(score_burn)} entries")

    week_map: dict[str, dict] = {}

    def ensure(wk):
        if wk and wk not in week_map:
            week_map[wk] = {"val": 0.0, "app": 0.0, "score": 0.0, "burn": 0.0}

    for r in val_rew:
        wk = week_key(r.get("time", ""))
        ensure(wk)
        if wk:
            week_map[wk]["val"]  += float(r.get("validator_rewards", 0) or 0)
            week_map[wk]["app"]  += float(r.get("app_rewards",       0) or 0)

    for r in score_rew:
        wk = week_key(r.get("time", ""))
        ensure(wk)
        if wk:
            week_map[wk]["score"] += float(r.get("app_rewards", 0) or 0)

    for r in (*val_burn, *score_burn):
        wk = week_key(r.get("time", ""))
        ensure(wk)
        if wk:
            week_map[wk]["burn"] += float(r.get("total_burned", 0) or 0)

    return week_map


def build_payload(merged_map: dict) -> dict:
    """
    Build the exact JSON structure the HTML rzLoad() expects:
    weeks, labels, valW, appW, scoreW, burnW, netW,
    cumNetArr, cumValArr, cumAppArr, cumScoreArr,
    rev1w, rev1m, rev1y, rev2y,
    totalNet, totalVal, totalApp, totalScore, totalBurn.
    """
    weeks = sorted(merged_map.keys())

    valW   = [round(merged_map[w]["val"],   6) for w in weeks]
    appW   = [round(merged_map[w]["app"],   6) for w in weeks]
    scoreW = [round(merged_map[w]["score"], 6) for w in weeks]
    burnW  = [round(merged_map[w]["burn"],  6) for w in weeks]
    netW   = [round(valW[i]+appW[i]+scoreW[i]-burnW[i], 6) for i in range(len(weeks))]

    labels = [week_label(w) for w in weeks]

    # Cumulative arrays — exact same accumulation as the HTML
    cumNetArr = []; cumValArr = []; cumAppArr = []; cumScoreArr = []
    cv = ca = cs = cn = 0.0
    for i in range(len(weeks)):
        cv += valW[i]; ca += appW[i]; cs += scoreW[i]; cn += netW[i]
        cumValArr.append(round(cv, 6))
        cumAppArr.append(round(ca, 6))
        cumScoreArr.append(round(cs, 6))
        cumNetArr.append(round(cn, 6))

    # Period KPIs — same sumNetLast() logic as HTML
    now = datetime.now(timezone.utc)
    def sum_net_last(days: int) -> float:
        cutoff = now - timedelta(days=days)
        total = 0.0
        for i, w in enumerate(weeks):
            wk_dt = datetime.fromisoformat(w + "T00:00:00+00:00")
            if wk_dt >= cutoff:
                total += netW[i]
        return round(total, 6)

    totalVal   = cumValArr[-1]   if cumValArr   else 0.0
    totalApp   = cumAppArr[-1]   if cumAppArr   else 0.0
    totalScore = cumScoreArr[-1] if cumScoreArr else 0.0
    totalBurn  = round(sum(burnW), 6)
    totalNet   = cumNetArr[-1]   if cumNetArr   else 0.0

    return {
        # ── Arrays consumed directly by rzLoad() ──────────────────────
        "weeks":       weeks,      # ISO Monday dates — used for period KPI calc
        "labels":      labels,     # formatted — Chart x-axis
        "valW":        valW,       # weekly validator revenue
        "appW":        appW,       # weekly T-RIZE platform app revenue
        "scoreW":      scoreW,     # weekly RIZEScore app revenue
        "burnW":        burnW,     # weekly burns
        "netW":        netW,       # weekly net (val+app+score-burn)
        "cumNetArr":   cumNetArr,  # cumulative net  — chart 1 data
        "cumValArr":   cumValArr,  # cumulative val  — chart 2 dataset 0
        "cumAppArr":   cumAppArr,  # cumulative app  — chart 2 dataset 1
        "cumScoreArr": cumScoreArr,# cumulative score— chart 2 dataset 2
        # ── KPI scalars ───────────────────────────────────────────────
        "totalVal":    totalVal,
        "totalApp":    totalApp,
        "totalScore":  totalScore,
        "totalBurn":   totalBurn,
        "totalNet":    totalNet,
        "rev1w":       sum_net_last(7),
        "rev1m":       sum_net_last(30),
        "rev1y":       sum_net_last(365),
        "rev2y":       sum_net_last(730),
        # ── Meta ──────────────────────────────────────────────────────
        "updatedAt":   now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    bootstrap = "--bootstrap" in sys.argv
    now_iso   = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    if bootstrap:
        print("=== BOOTSTRAP MODE — full history from genesis ===")
        start = RZ_GENESIS
        new_map = fetch_all(start, now_iso)
        merged_map = new_map
    else:
        print("=== INCREMENTAL MODE — last 14 days window ===")
        window_start = (datetime.now(timezone.utc) - timedelta(days=INCREMENTAL_WINDOW_DAYS))
        start = window_start.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        # Load existing weeks outside the window
        existing = load_existing()
        existing_weeks = existing.get("weeks", [])
        cutoff_iso = window_start.strftime("%Y-%m-%d")

        # Rebuild merged_map from existing data for weeks BEFORE the window
        merged_map: dict[str, dict] = {}
        for i, w in enumerate(existing_weeks):
            if w < cutoff_iso:
                merged_map[w] = {
                    "val":   existing["valW"][i],
                    "app":   existing["appW"][i],
                    "score": existing["scoreW"][i],
                    "burn":  existing["burnW"][i],
                }

        # Fetch the window and merge (overwrite) those weeks
        new_map = fetch_all(start, now_iso)
        merged_map.update(new_map)

    if not merged_map:
        print("WARNING: no data fetched — output unchanged.", file=sys.stderr)
        sys.exit(0)

    payload = build_payload(merged_map)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w") as f:
        json.dump(payload, f, indent=2)

    n = len(payload["weeks"])
    print(f"  ✓ {n} weeks written → {OUTPUT}")
    print(f"  Net={payload['totalNet']:,.2f} CC  |  Val={payload['totalVal']:,.2f}  |  App={payload['totalApp']:,.2f}  |  Score={payload['totalScore']:,.2f}  |  Burn={payload['totalBurn']:,.2f}")
    print(f"  1W={payload['rev1w']:,.2f}  1M={payload['rev1m']:,.2f}  1Y={payload['rev1y']:,.2f}  2Y={payload['rev2y']:,.2f}")


if __name__ == "__main__":
    main()
