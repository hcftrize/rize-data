"""
Commands: /cip [number], /cantongov
Data: cips.json (GitHub) + Lighthouse API.
"""
import httpx
from utils.github_data import get_cips

LIGHTHOUSE_BASE = "https://lighthouse.cantonloop.com/api"
CIP_GITHUB_URL  = "https://github.com/canton-foundation/cips"


# ── /rizeby cip [number] ──────────────────────────────────────────────────────

async def cmd_cip(args: list[str]) -> str:
    cips = await get_cips()
    if not cips:
        return "❌ Could not load CIPs data."

    # Sort descending by number
    cips_sorted = sorted(cips, key=lambda c: c.get("number", 0), reverse=True)

    # If a specific CIP number is requested
    if args:
        query = args[0].lstrip("0") if args[0].startswith("0") else args[0]
        # Handle "CIP-0116" or "116" or "0116"
        query = query.lstrip("CIP-").lstrip("0") or "0"

        match = next(
            (c for c in cips_sorted if str(c.get("number", "")).lstrip("0") == query or
             c.get("id", "").lstrip("CIP-0") == query),
            None,
        )

        if not match:
            return f"❌ CIP #{args[0]} not found.\n\nType `/rizeby cip` to see the latest CIPs."

        cip_id      = match.get("id", f"CIP-{match.get('number', '?')}")
        title       = match.get("title", "—")
        status      = match.get("status", "—")
        category    = match.get("type", "—")
        created     = match.get("created", "—")
        description = match.get("description", "No description available.")

        # Trim description to 800 chars
        if len(description) > 800:
            description = description[:800] + "…"

        lines = [
            f"📋 *{cip_id} — {title}*",
            f"Status: {status} | Category: {category}",
            f"Created: {created}",
            "",
            description,
            "",
            f"🔗 Read more: {CIP_GITHUB_URL}",
        ]
        return "\n".join(lines)

    # List latest 5
    latest = cips_sorted[:5]
    lines  = [
        "📋 *Latest Canton CIPs*",
        "",
    ]

    for c in latest:
        cip_id   = c.get("id", f"CIP-{c.get('number', '?')}")
        title    = c.get("title", "—")
        status   = c.get("status", "—")
        category = c.get("type", "—")
        status_emoji = "✅" if status == "Approved" else "🟡" if status == "Proposed" else "❌"

        lines += [
            f"{status_emoji} *{cip_id}*",
            f"  {title}",
            f"  {status} · {category}",
            "",
        ]

    lines += [
        "─────────────────────",
        "📖 Type `/rizeby cip {number}` to read a specific CIP",
        "   e.g. `/rizeby cip 0116`",
        "",
        f"🔗 {CIP_GITHUB_URL}",
    ]

    return "\n".join(lines)


# ── /rizeby cantongov ─────────────────────────────────────────────────────────

async def cmd_cantongov(args: list[str], page: int = 0) -> str:
    """
    Active Canton governance proposals from Lighthouse API.
    Shows 5 per page.
    """
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            r = await client.get(f"{LIGHTHOUSE_BASE}/proposals", params={"limit": 50})
            data = r.json()
    except Exception:
        return "❌ Could not fetch Canton governance proposals."

    proposals = data if isinstance(data, list) else data.get("proposals", data.get("data", []))
    if not proposals:
        return "❌ No proposals found."

    # Sort by most recent first
    proposals = sorted(proposals, key=lambda p: p.get("createdAt", p.get("created_at", "")), reverse=True)

    per_page = 5
    start    = page * per_page
    page_proposals = proposals[start:start + per_page]

    if not page_proposals:
        return "No more proposals to display."

    total = len(proposals)
    lines = [
        f"🏛 *Canton Network Governance* — Page {page + 1}",
        f"_Showing {start + 1}–{min(start + per_page, total)} of {total}_",
        "",
    ]

    for p in page_proposals:
        title   = p.get("title", p.get("name", "Untitled"))[:60]
        status  = p.get("status", "—")
        created = (p.get("createdAt") or p.get("created_at") or "")[:10]

        # Vote counts
        yes_pct = no_pct = None
        votes = p.get("votes") or p.get("voteCount") or {}
        if isinstance(votes, dict):
            yes = float(votes.get("yes", votes.get("accept", votes.get("for", 0))) or 0)
            no  = float(votes.get("no", votes.get("reject", votes.get("against", 0))) or 0)
            total_v = yes + no
            if total_v > 0:
                yes_pct = yes / total_v * 100
                no_pct  = no  / total_v * 100

        status_emoji = {
            "inprogress": "🟡", "active": "🟡",
            "executed": "✅", "passed": "✅", "approved": "✅",
            "rejected": "❌", "failed": "❌",
        }.get(status.lower(), "⚪")

        vote_str = ""
        if yes_pct is not None:
            vote_str = f" | ✅ {yes_pct:.0f}% / ❌ {no_pct:.0f}%"

        lines += [
            f"{status_emoji} *{title}*",
            f"  {status} · {created}{vote_str}",
            "",
        ]

    if start + per_page < total:
        lines += [
            "─────────────────────",
            "Reply *next* to see more proposals.",
        ]

    return "\n".join(lines)
