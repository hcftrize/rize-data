"""
Commands: /unbond, /totalbonded
Live on-chain data — Goldsky subgraph + Alchemy RPC.
Identical to Rize Holders Conviction live KPIs.
"""
import os
import httpx
from utils.formatters import fmt_rize, fmt_usd, fmt_price

GOLDSKY_URL = "https://api.goldsky.com/api/public/project_cmoa6u5wk3kx201y4g3s52z77/subgraphs/tokerize-bond-broken/1.0.0/gn"
ALCHEMY_URL = f"https://base-mainnet.g.alchemy.com/v2/{os.environ.get('ALCHEMY_KEY', 'qS-QZnHMq-cqmoFkw-grY')}"

GOV_CONTRACT = "0x5a134098bDBEb05Da9eAc35439c5624547ed26eE"
RIZE_TOKEN   = "0x9818B6c09f5ECc843060927E8587c427C7C93583"
DECIMALS     = 10 ** 18


# ── /rizeby unbond ────────────────────────────────────────────────────────────

async def cmd_unbond(args: list[str]) -> str:
    """
    Unbonding queue — breaks in last 7 days not yet released.
    Same logic as convFetchUnbondingQueue in the Data Hub.
    """
    from datetime import datetime, timedelta, timezone

    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")

    query = """
    {
      bondBrokens(
        first: 1000,
        orderBy: date,
        orderDirection: desc,
        where: { date_gte: "%s" }
      ) {
        nftId
        amount
        date
        timestamp
      }
    }
    """ % cutoff_date

    try:
        async with httpx.AsyncClient(timeout=12) as client:
            r = await client.post(GOLDSKY_URL, json={"query": query})
            data = r.json()
    except Exception:
        return "❌ Could not fetch unbonding queue (Goldsky timeout)."

    events = data.get("data", {}).get("bondBrokens", [])
    if not events:
        return "📭 *Unbonding Queue*\n\nNo breaks in the last 7 days. Queue is empty."

    total_rize = sum(float(str(e.get("amount", 0)).replace(",","")) / DECIMALS for e in events)
    count = len(events)

    lines = [
        "🔓 *Unbonding Queue — Live*",
        "_Bonds broken in the last 7 days (warmup period, not yet released)_",
        "",
        f"Queue total: *{fmt_rize(total_rize)}*",
        f"Active breaks: {count}",
        "",
        "Last 5 breaks:",
        "```",
        f"{'Date':<12} {'Bond #':>8} {'Amount':>12}",
        "─" * 34,
    ]

    for e in events[:5]:
        nft_id = e.get("nftId", "?")
        amount = float(str(e.get("amount", 0)).replace(",","")) / DECIMALS
        date   = e.get("date", "—")
        lines.append(f"{date:<12} #{nft_id:>6} {fmt_rize(amount):>12}")

    lines.append("```")
    if count > 5:
        lines.append(f"_...and {count - 5} more_")

    return "\n".join(lines)


# ── /rizeby totalbonded ───────────────────────────────────────────────────────

async def cmd_totalbonded(args: list[str]) -> str:
    """
    Total RIZE bonded — live eth_call to RIZE token contract.
    Same as the hero KPI in the Data Hub.
    """
    # balanceOf(GOV_CONTRACT) on RIZE token
    padded = "000000000000000000000000" + GOV_CONTRACT[2:].lower()
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_call",
        "params": [
            {"to": RIZE_TOKEN, "data": "0x70a08231" + padded},
            "latest",
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(ALCHEMY_URL, json=payload)
            result = r.json().get("result", "0x0")
    except Exception:
        return "❌ Could not fetch total bonded (RPC error)."

    if not result or result == "0x":
        return "❌ Empty RPC response."

    total_rize = int(result, 16) / DECIMALS
    total_supply = 5_000_000_000
    pct_of_supply = (total_rize / total_supply) * 100

    # Get RIZE price for USD value
    from utils.coingecko import cg_get
    price_data = await cg_get("/simple/price", {"ids": "rize", "vs_currencies": "usd"})
    rize_price = price_data.get("rize", {}).get("usd", 0) if price_data else 0
    usd_value  = total_rize * rize_price

    lines = [
        "🏦 *Total RIZE Bonded — Live*",
        "",
        f"Total bonded: *{fmt_rize(total_rize)}*",
        f"% of 5B supply: {pct_of_supply:.2f}%",
        f"USD value: {fmt_usd(usd_value)}",
        f"RIZE price: {fmt_price(rize_price)}",
        "",
        "_Live data via Alchemy RPC_",
    ]

    return "\n".join(lines)
