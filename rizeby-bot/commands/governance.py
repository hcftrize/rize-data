"""
Commands: /govflows, /govwhalealert, /govwallet, /govbond
Data: GitHub JSONs — bond-created.json, bond-broken.json, bond-lifecycle.json, bond-states.json
Identical computation to the Governance Hub modules.
"""
from utils.github_data import get_bond_created, get_bond_broken, get_bond_lifecycle, get_bond_states
from utils.formatters import fmt_rize, fmt_num, fmt_pct

DECIMALS = 10 ** 18
FULL_MAT = 94_608_000  # 3 years in seconds


def parse_amt(v) -> float:
    try:
        return int(str(v)) / DECIMALS
    except Exception:
        return 0.0


def _short_addr(addr: str) -> str:
    if not addr or len(addr) < 12:
        return addr or "—"
    return f"{addr[:6]}…{addr[-4:]}"


# ── /rizeby govflows ──────────────────────────────────────────────────────────

async def cmd_govflows(args: list[str], page: int = 0) -> str:
    """Monthly bond flow breakdown — last 6 months per page."""
    bc_data = await get_bond_created()
    bb_data = await get_bond_broken()
    if not bc_data or not bb_data:
        return "❌ Could not load governance flow data."

    created   = bc_data.get("bondCreatedEvents", [])
    increases = bc_data.get("increaseBondEvents", [])
    breaks    = bb_data.get("bondBrokenEvents", [])

    # Aggregate by month
    monthly: dict[str, dict] = {}

    def ensure(ym):
        if ym not in monthly:
            monthly[ym] = {"breaks": 0, "breaks_vol": 0.0, "created": 0, "created_vol": 0.0, "increased": 0, "increased_vol": 0.0}

    for e in breaks:
        d = (e.get("date") or "")[:7]
        if d:
            ensure(d)
            monthly[d]["breaks"] += 1
            monthly[d]["breaks_vol"] += parse_amt(e.get("amount", 0))

    for e in created:
        d = (e.get("date") or e.get("createdAtDate") or "")[:7]
        if d:
            ensure(d)
            monthly[d]["created"] += 1
            monthly[d]["created_vol"] += parse_amt(e.get("amount") or e.get("totalDeposited", 0))

    for e in increases:
        d = (e.get("date") or "")[:7]
        if d:
            ensure(d)
            monthly[d]["increased"] += 1
            monthly[d]["increased_vol"] += parse_amt(e.get("amount", 0))

    sorted_months = sorted(monthly.keys(), reverse=True)
    per_page = 6
    start    = page * per_page
    page_months = sorted_months[start:start + per_page]

    if not page_months:
        return "No more months to display."

    lines = [
        "📊 *Governance Flows — Monthly Breakdown*",
        "",
        "```",
        f"{'Month':<8} {'Breaks':>6} {'Vol':>10} {'Created':>7} {'Vol':>10} {'Inc':>4} {'Vol':>10}",
        "─" * 60,
    ]

    for ym in page_months:
        m = monthly[ym]
        lines.append(
            f"{ym:<8} "
            f"{m['breaks']:>6} "
            f"{fmt_rize(m['breaks_vol']):>10} "
            f"{m['created']:>7} "
            f"{fmt_rize(m['created_vol']):>10} "
            f"{m['increased']:>4} "
            f"{fmt_rize(m['increased_vol']):>10}"
        )

    lines.append("```")

    total = len(sorted_months)
    if start + per_page < total:
        lines += ["", "Reply *next* to see earlier months."]

    return "\n".join(lines)


# ── /rizeby govwhalealert ─────────────────────────────────────────────────────

async def cmd_govwhalealert(args: list[str], page: int = 0) -> str:
    """Last whale transactions (>5M RIZE) with filter support."""
    bc_data = await get_bond_created()
    bb_data = await get_bond_broken()
    lc_data = await get_bond_lifecycle()
    if not bb_data:
        return "❌ Could not load whale alert data."

    # Parse filter from args
    filter_mode = "all"
    for a in args:
        al = a.lower()
        if al in ("breaks", "break"):
            filter_mode = "break"
        elif al in ("bond+increase", "bond", "increase", "bonds"):
            filter_mode = "bond"
        elif al in ("releases", "release"):
            filter_mode = "release"

    WHALE_THRESHOLD = 5_000_000  # 5M RIZE

    all_events = []

    if filter_mode in ("all", "break"):
        for e in (bb_data.get("bondBrokenEvents") or []):
            amt = parse_amt(e.get("amount", 0))
            if amt >= WHALE_THRESHOLD:
                all_events.append({
                    "ts":    int(e.get("timestamp", 0)),
                    "date":  e.get("date", "—"),
                    "type":  "Break",
                    "nft":   e.get("nftId", "?"),
                    "amt":   amt,
                    "owner": e.get("owner", ""),
                })

    if filter_mode in ("all", "bond") and bc_data:
        for e in (bc_data.get("bondCreatedEvents") or []):
            amt = parse_amt(e.get("amount") or e.get("totalDeposited", 0))
            if amt >= WHALE_THRESHOLD:
                all_events.append({
                    "ts":    int(e.get("createdAtTimestamp") or e.get("timestamp", 0)),
                    "date":  e.get("createdAtDate") or e.get("date", "—"),
                    "type":  "Bond Created",
                    "nft":   e.get("nftId", "?"),
                    "amt":   amt,
                    "owner": e.get("owner", ""),
                })
        for e in (bc_data.get("increaseBondEvents") or []):
            amt = parse_amt(e.get("amount", 0))
            if amt >= WHALE_THRESHOLD:
                all_events.append({
                    "ts":    int(e.get("timestamp", 0)),
                    "date":  e.get("date", "—"),
                    "type":  "IncreaseBond",
                    "nft":   e.get("nftId", "?"),
                    "amt":   amt,
                    "owner": e.get("owner", ""),
                })

    if filter_mode in ("all", "release") and lc_data:
        for e in (lc_data.get("tokensReleasedEvents") or []):
            amt = parse_amt(e.get("amount", 0))
            if amt >= WHALE_THRESHOLD:
                all_events.append({
                    "ts":    int(e.get("timestamp", 0)),
                    "date":  e.get("date", "—"),
                    "type":  "Release",
                    "nft":   e.get("nftId", "?"),
                    "amt":   amt,
                    "owner": e.get("to") or e.get("owner", ""),
                })

    all_events.sort(key=lambda e: e["ts"], reverse=True)

    per_page = 5
    start    = page * per_page
    page_events = all_events[start:start + per_page]

    if not page_events:
        return f"No whale events found{' for this filter' if filter_mode != 'all' else ''}."

    total = len(all_events)
    filter_label = {"all": "All", "break": "Breaks", "bond": "Bonds/Increases", "release": "Releases"}[filter_mode]

    lines = [
        f"🐋 *Governance Whale Alert — {filter_label}*",
        f"_Transactions > 5M RIZE — showing {start+1}–{min(start+per_page, total)} of {total}_",
        "",
        "```",
        f"{'Date':<12} {'Type':<13} {'Bond':>6} {'Amount':>12} {'Wallet'}",
        "─" * 58,
    ]

    type_abbr = {
        "Break": "🔴 Break",
        "Bond Created": "🟢 BondCreated",
        "IncreaseBond": "🟡 Increase",
        "Release": "🔵 Release",
    }

    for e in page_events:
        lines.append(
            f"{e['date']:<12} "
            f"{type_abbr.get(e['type'], e['type']):<13} "
            f"#{str(e['nft']):>5} "
            f"{fmt_rize(e['amt']):>12} "
            f"{_short_addr(e['owner'])}"
        )

    lines.append("```")

    if start + per_page < total:
        lines += ["", "Reply *next* to see more."]

    return "\n".join(lines)


# ── /rizeby govwallet / govbond ───────────────────────────────────────────────

async def cmd_govwallet(args: list[str]) -> str:
    """Wallet or bond profile from bond-states.json — mirrors Wallet Explorer."""
    if not args:
        return (
            "❓ Provide a wallet address or bond number.\n\n"
            "Examples:\n"
            "`/rizeby govwallet 0x88ab8a...`\n"
            "`/rizeby govbond 10034`"
        )

    query = args[0].strip()
    bs    = await get_bond_states()
    if not bs:
        return "❌ Could not load bond states data."

    # Bond number lookup
    if query.startswith("#") or query.isdigit():
        nft_id = query.lstrip("#")
        state  = bs.get("bondStates", bs).get(nft_id)
        if not state:
            return f"❌ Bond #{nft_id} not found."
        return _format_bond(nft_id, state)

    # Wallet address lookup
    addr = query.lower()
    bond_states = bs.get("bondStates", bs)
    owner_index = bs.get("ownerIndex", {})

    nft_ids = owner_index.get(addr, [])
    if not nft_ids:
        # Fallback: scan all bonds
        nft_ids = [nid for nid, s in bond_states.items() if (s.get("owner") or "").lower() == addr]

    if not nft_ids:
        return f"❌ No active bonds found for `{_short_addr(addr)}`."

    return _format_wallet(addr, nft_ids, bond_states, bs)


def _format_bond(nft_id: str, state: dict) -> str:
    cur = state.get("current") or state
    balance  = cur.get("balance", 0)
    maturity = cur.get("maturity", 0)
    boost    = cur.get("boost", 1)
    vp       = cur.get("vp", 0)
    owner    = state.get("owner") or cur.get("owner", "—")

    lines = [
        f"🔗 *Bond #{nft_id}*",
        "",
        f"Owner: `{_short_addr(owner)}`",
        f"Balance: {fmt_rize(balance)}",
        f"Maturity: {maturity * 100:.2f}%",
        f"Boost: {boost:.3f}×",
        f"Voting Power: {fmt_rize(vp)}",
    ]

    events = state.get("events", [])
    if events:
        lines += ["", "*Recent Activity:*", "```"]
        for e in events[-5:]:
            lines.append(f"{e.get('date','—')}  {e.get('type','—'):<16}  {fmt_rize(abs(e.get('delta', 0)))}")
        lines.append("```")

    return "\n".join(lines)


def _format_wallet(addr: str, nft_ids: list, bond_states: dict, bs: dict) -> str:
    import time

    now = time.time()
    total_vp    = 0.0
    total_rize  = 0.0
    maturities  = []
    all_events  = []

    for nid in nft_ids:
        state = bond_states.get(str(nid), {})
        cur   = state.get("current") or state
        bal   = cur.get("balance", 0)
        mat   = cur.get("maturity", 0)
        vp    = cur.get("vp", 0)
        if bal > 0:
            total_rize += bal
            total_vp   += vp
            maturities.append(mat)
        for e in (state.get("events") or []):
            all_events.append({**e, "nftId": nid})

    avg_mat   = (sum(maturities) / len(maturities) * 100) if maturities else 0
    act_bonds = len([nid for nid in nft_ids if bond_states.get(str(nid), {}).get("current", {}).get("balance", 0) > 0])

    # Rank from leaderboard
    lb = bs.get("leaderboard", [])
    rank = next((i + 1 for i, w in enumerate(lb) if w.get("owner", "").lower() == addr.lower()), None)

    # First bond date
    all_events_sorted = sorted(all_events, key=lambda e: e.get("ts", 0))
    first_bond = next((e.get("date", "—") for e in all_events_sorted if e.get("type") == "BondCreated"), "—")

    # VP projection (6 months)
    elapsed_avg = avg_mat / 100 * FULL_MAT
    vp_6m = sum(
        bond_states.get(str(nid), {}).get("current", {}).get("balance", 0) *
        (1 + 2 * min(1, (bond_states.get(str(nid), {}).get("current", {}).get("maturity", 0) + 6 * 30 * 86400 / FULL_MAT)))
        for nid in nft_ids
    )

    lines = [
        f"👛 *Wallet Profile*",
        f"`{_short_addr(addr)}`",
        f"{'Rank #' + str(rank) if rank else ''}",
        "",
        f"Total VP: *{fmt_rize(total_vp)}*",
        f"RIZE Bonded: {fmt_rize(total_rize)}",
        f"Active Bonds: {act_bonds}",
        f"Avg Maturity: {avg_mat:.2f}%",
        f"First Bond: {first_bond}",
        f"VP in 6M: ~{fmt_rize(vp_6m)}",
    ]

    # Last 5 timeline events
    recent_events = sorted(all_events, key=lambda e: e.get("ts", 0), reverse=True)[:5]
    if recent_events:
        lines += ["", "*Full Activity Timeline:*", "```"]
        for e in recent_events:
            nft    = e.get("nftId", "?")
            etype  = e.get("type", "—")
            delta  = abs(e.get("delta", 0))
            date   = e.get("date", "—")
            lines.append(f"{date}  {etype:<16}  #{nft}  {fmt_rize(delta) if delta else ''}")
        lines.append("```")
        if len(all_events) > 5:
            lines.append("_Reply *next* to see more activity._")

    return "\n".join(lines)
