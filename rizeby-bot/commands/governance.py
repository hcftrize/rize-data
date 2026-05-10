"""
Commands: /govflows, /govwhalealert, /govwallet, /govbond
Exact logic from rize-governance-hub.html.
- Amounts: parseFloat (already in RIZE, not wei)
- JSON paths: rize-governance-hub/ folder on main branch
- bondBrokenEvents, bondCreatedEvents, increaseBondEvents, tokensReleasedEvents
"""
from utils.github_data import get_bond_created, get_bond_broken, get_bond_lifecycle, get_bond_states
from utils.formatters import fmt_rize, fmt_num

WHALE_MIN = 5_000_000  # default, matches hub default


def parse_amt(v) -> float:
    """Amounts are already in RIZE — parseFloat only."""
    try:
        return float(str(v).replace(",", "")) if v else 0.0
    except Exception:
        return 0.0


def ts_to_date(ts) -> str:
    from datetime import datetime, timezone
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return "—"


def short_addr(a: str) -> str:
    if not a or len(a) < 10: return a or "—"
    return f"{a[:6]}…{a[-4:]}"


# ── /govflows ─────────────────────────────────────────────────────────────────

async def cmd_govflows(args: list, page: int = 0) -> str:
    bb = await get_bond_broken()
    bc = await get_bond_created()
    if not bb:
        return "Could not load governance flow data."

    # Build monthly buckets — same logic as initCalendar() in hub
    monthly: dict = {}

    def ensure(ym):
        if ym not in monthly:
            monthly[ym] = {"breaks": 0, "breaks_rize": 0.0,
                           "created": 0, "created_rize": 0.0,
                           "increased": 0, "increased_rize": 0.0}

    for e in (bb.get("bondBrokenEvents", []) if isinstance(bb, dict) else []):
        d  = e.get("date") or ts_to_date(e.get("timestamp", 0))
        ym = d[:7]
        ensure(ym)
        monthly[ym]["breaks"] += 1
        monthly[ym]["breaks_rize"] += parse_amt(e.get("amount", 0))

    if bc:
        for e in (bc.get("bondCreatedEvents", []) if isinstance(bc, dict) else []):
            d  = e.get("date") or ts_to_date(e.get("timestamp", 0))
            ym = d[:7]
            ensure(ym)
            monthly[ym]["created"] += 1
            monthly[ym]["created_rize"] += parse_amt(e.get("amount", 0))
        for e in (bc.get("increaseBondEvents", []) if isinstance(bc, dict) else []):
            d  = e.get("date") or ts_to_date(e.get("timestamp", 0))
            ym = d[:7]
            ensure(ym)
            monthly[ym]["increased"] += 1
            monthly[ym]["increased_rize"] += parse_amt(e.get("amount", 0))

    sorted_months = sorted(monthly.keys(), reverse=True)
    per_page = 6
    start    = page * per_page
    page_months = sorted_months[start:start + per_page]

    if not page_months:
        return "No more months to display."

    lines = [
        "📊 *Governance Flows — Monthly Breakdown*",
        "",
    ]
    for ym in page_months:
        m = monthly[ym]
        net = m["created_rize"] + m["increased_rize"] - m["breaks_rize"]
        sign = "+" if net >= 0 else ""
        lines += [
            f"*{ym}*",
            f"  Breaks: {m['breaks']} · {fmt_rize(m['breaks_rize'])}",
            f"  Created: {m['created']} · {fmt_rize(m['created_rize'])}",
            f"  Increased: {m['increased']} · {fmt_rize(m['increased_rize'])}",
            f"  Net: {sign}{fmt_rize(net)}",
            "",
        ]

    if start + per_page < len(sorted_months):
        lines.append("Reply *next* to see earlier months.")

    return "\n".join(lines)


# ── /govwhalealert ────────────────────────────────────────────────────────────

async def cmd_govwhalealert(args: list, page: int = 0) -> str:
    # Parse filter — same as hub whaleDirFilter
    dir_filter = "all"
    whale_min  = WHALE_MIN
    for a in args:
        al = a.lower()
        if al in ("breaks", "break"):       dir_filter = "break"
        elif al in ("bond", "bonds"):       dir_filter = "bond"
        elif al in ("increase", "increases"): dir_filter = "increase"
        elif al in ("bond+increase", "bondincrease"): dir_filter = "bond+increase"
        elif al in ("releases", "release"): dir_filter = "release"
        # Allow custom threshold e.g. "1m" "10m"
        from utils.formatters import parse_amount
        parsed = parse_amount(al)
        if parsed and parsed >= 100_000:
            whale_min = parsed

    bb = await get_bond_broken()
    bc = await get_bond_created()
    lc = await get_bond_lifecycle()
    if not bb:
        return "Could not load whale alert data."

    all_events = []

    # Breaks
    for e in (bb.get("bondBrokenEvents", []) if isinstance(bb, dict) else []):
        rize = parse_amt(e.get("amount", 0))
        if rize >= whale_min:
            all_events.append({
                "ts": int(e.get("timestamp", 0)),
                "date": e.get("date") or ts_to_date(e.get("timestamp", 0)),
                "dir": "break", "nft": e.get("nftId", "?"),
                "rize": rize, "owner": e.get("owner", ""),
            })

    # Bonds + Increases
    if bc:
        for e in (bc.get("bondCreatedEvents", []) if isinstance(bc, dict) else []):
            rize = parse_amt(e.get("amount", 0))
            if rize >= whale_min:
                all_events.append({
                    "ts": int(e.get("timestamp", 0)),
                    "date": e.get("date") or ts_to_date(e.get("timestamp", 0)),
                    "dir": "bond", "nft": e.get("nftId", "?"),
                    "rize": rize, "owner": e.get("owner", ""),
                })
        for e in (bc.get("increaseBondEvents", []) if isinstance(bc, dict) else []):
            rize = parse_amt(e.get("amount", 0))
            if rize >= whale_min:
                all_events.append({
                    "ts": int(e.get("timestamp", 0)),
                    "date": e.get("date") or ts_to_date(e.get("timestamp", 0)),
                    "dir": "increase", "nft": e.get("nftId", "?"),
                    "rize": rize, "owner": e.get("owner", ""),
                })

    # Releases
    if lc:
        for e in (lc.get("tokensReleasedEvents", []) if isinstance(lc, dict) else []):
            rize = parse_amt(e.get("amount", 0))
            if rize >= whale_min:
                all_events.append({
                    "ts": int(e.get("timestamp", 0)),
                    "date": e.get("date") or ts_to_date(e.get("timestamp", 0)),
                    "dir": "release", "nft": e.get("nftId", "?"),
                    "rize": rize, "owner": e.get("to") or e.get("owner", ""),
                })

    # Apply direction filter
    if dir_filter == "break":
        all_events = [e for e in all_events if e["dir"] == "break"]
    elif dir_filter == "bond":
        all_events = [e for e in all_events if e["dir"] == "bond"]
    elif dir_filter == "increase":
        all_events = [e for e in all_events if e["dir"] == "increase"]
    elif dir_filter == "bond+increase":
        all_events = [e for e in all_events if e["dir"] in ("bond", "increase")]
    elif dir_filter == "release":
        all_events = [e for e in all_events if e["dir"] == "release"]

    all_events.sort(key=lambda e: e["ts"], reverse=True)

    per_page = 5
    start    = page * per_page
    page_ev  = all_events[start:start + per_page]

    if not page_ev:
        return f"No whale events found (>{fmt_rize(whale_min)})."

    total = len(all_events)
    dir_labels = {
        "break": "🔴 Break", "bond": "🟢 Bond",
        "increase": "🟡 Increase", "release": "🔵 Release",
    }
    filter_label = {"all": "All", "break": "Breaks", "bond": "Bonds",
                    "increase": "Increases", "bond+increase": "Bonds+Inc",
                    "release": "Releases"}.get(dir_filter, dir_filter)

    lines = [
        f"🐋 *Whale Alert — {filter_label}* (>{fmt_rize(whale_min)})",
        f"_{start+1}–{min(start+per_page,total)} of {total}_",
        "",
        "```",
        f"{'Date':<12} {'Type':<10} {'#':>6} {'Amount':>12}  Wallet",
        "─" * 56,
    ]
    for e in page_ev:
        label = dir_labels.get(e["dir"], e["dir"])
        lines.append(
            f"{e['date']:<12} {e['dir']:<10} #{str(e['nft']):>5} "
            f"{fmt_rize(e['rize']):>12}  {short_addr(e['owner'])}"
        )
    lines.append("```")

    if start + per_page < total:
        lines.append("Reply *next* to see more.")

    return "\n".join(lines)


# ── /govwallet / /govbond ─────────────────────────────────────────────────────

async def cmd_govwallet(args: list) -> str:
    if not args:
        return (
            "Provide a wallet address or bond number.\n\n"
            "Examples:\n"
            "`/govwallet 0x88ab...`\n"
            "`/govbond 10034`"
        )

    query = args[0].strip()
    bs    = await get_bond_states()
    if not bs:
        return "Could not load bond states data."

    # bs may be the raw dict with bond entries keyed by nftId
    # Structure: {nftId: {owner, current: {balance, maturity, vp, boost}, events: [...]}}
    bond_states = bs if isinstance(bs, dict) else {}

    # Bond number lookup
    if query.startswith("#") or query.isdigit():
        nft_id = query.lstrip("#")
        state  = bond_states.get(nft_id) or bond_states.get(int(nft_id) if nft_id.isdigit() else nft_id)
        if not state:
            return f"Bond #{nft_id} not found."
        return _format_bond(nft_id, state)

    # Wallet address lookup
    addr = query.lower()
    nft_ids = [nid for nid, s in bond_states.items()
               if isinstance(s, dict) and (s.get("owner", "") or "").lower() == addr]

    if not nft_ids:
        return f"No bonds found for `{short_addr(addr)}`."

    return _format_wallet(addr, nft_ids, bond_states)


def _format_bond(nft_id, state: dict) -> str:
    cur     = state.get("current", state)
    balance = parse_amt(cur.get("balance", 0))
    mat     = float(cur.get("maturity", 0)) * 100
    boost   = float(cur.get("boost", 1))
    vp      = parse_amt(cur.get("vp", 0))
    owner   = state.get("owner", "—")

    lines = [
        f"🔗 *Bond #{nft_id}*",
        "",
        f"Owner: `{short_addr(owner)}`",
        f"Balance: {fmt_rize(balance)}",
        f"Maturity: {mat:.2f}%",
        f"Boost: {boost:.3f}×",
        f"Voting Power: {fmt_rize(vp)}",
    ]
    events = state.get("events", [])
    if events:
        lines += ["", "*Recent Activity:*", "```"]
        for e in events[-5:]:
            delta = abs(parse_amt(e.get("delta", 0)))
            lines.append(f"{e.get('date','—')}  {e.get('type','—'):<16}  {fmt_rize(delta) if delta else ''}")
        lines.append("```")
    return "\n".join(lines)


def _format_wallet(addr: str, nft_ids: list, bond_states: dict) -> str:
    total_vp = 0.0; total_rize = 0.0; mats = []; all_events = []
    active_bonds = 0

    for nid in nft_ids:
        s   = bond_states.get(str(nid), {})
        cur = s.get("current", s)
        bal = parse_amt(cur.get("balance", 0))
        mat = float(cur.get("maturity", 0))
        vp  = parse_amt(cur.get("vp", 0))
        if bal > 0:
            active_bonds += 1
            total_rize   += bal
            total_vp     += vp
            mats.append(mat)
        for e in (s.get("events") or []):
            all_events.append({**e, "nftId": nid})

    avg_mat = (sum(mats) / len(mats) * 100) if mats else 0.0
    all_events_sorted = sorted(all_events, key=lambda e: e.get("ts", 0))
    first_bond = next((e.get("date", "—") for e in all_events_sorted
                       if "Created" in e.get("type", "")), "—")

    lines = [
        f"👛 *Wallet Profile*",
        f"`{short_addr(addr)}`",
        "",
        f"Total VP: *{fmt_rize(total_vp)}*",
        f"RIZE Bonded: {fmt_rize(total_rize)}",
        f"Active Bonds: {active_bonds}",
        f"Avg Maturity: {avg_mat:.2f}%",
        f"First Bond: {first_bond}",
    ]

    recent = sorted(all_events, key=lambda e: e.get("ts", 0), reverse=True)[:5]
    if recent:
        lines += ["", "*Recent Activity:*", "```"]
        for e in recent:
            delta = abs(parse_amt(e.get("delta", 0)))
            lines.append(
                f"{e.get('date','—')}  {e.get('type','—'):<16}  "
                f"#{e.get('nftId','?')}  {fmt_rize(delta) if delta else ''}"
            )
        lines.append("```")
        if len(all_events) > 5:
            lines.append("_Reply *next* to see more activity._")

    return "\n".join(lines)
