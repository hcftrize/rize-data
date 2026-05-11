"""
Commands: /unbond, /totalbonded
- /unbond uses unbonding-queue.json + bond-broken.json (last 7 days)
  Amounts are already in RIZE (parseFloat, not wei division)
- /totalbonded uses Alchemy RPC eth_call
"""
import os
import httpx
from utils.github_data import get_bond_broken, get_unbonding_queue
from utils.formatters import fmt_rize, fmt_usd, fmt_price

ALCHEMY_URL = f"https://base-mainnet.g.alchemy.com/v2/{os.environ.get('ALCHEMY_KEY', 'qS-QZnHMq-cqmoFkw-grY')}"
GOV_CONTRACT = "0x5a134098bDBEb05Da9eAc35439c5624547ed26eE"
RIZE_TOKEN   = "0x9818B6c09f5ECc843060927E8587c427C7C93583"
DECIMALS     = 10 ** 18


def parse_amt(v) -> float:
    """Amounts in governance JSONs are already in RIZE — just parseFloat."""
    try:
        return float(str(v).replace(",", "")) if v else 0.0
    except Exception:
        return 0.0


async def cmd_unbond(args: list, page: int = 0) -> str:
    """
    Unbonding queue from bond-broken.json — last 7 days.
    Identical to convFetchUnbondingQueue in governance hub.
    Amounts are in RIZE already (parseAmt = parseFloat).
    """
    import time
    cutoff_ts = time.time() - 7 * 86400

    bb = await get_bond_broken()
    if not bb:
        return "Could not fetch unbonding queue data."

    events = bb.get("bondBrokenEvents", []) if isinstance(bb, dict) else bb
    # Filter last 7 days
    recent = [e for e in events if int(e.get("timestamp", 0)) > cutoff_ts]

    if not recent:
        return "No breaks in the last 7 days. Queue is empty."

    total_rize = sum(parse_amt(e.get("amount", 0)) for e in recent)
    count = len(recent)

    # Sort newest first
    recent_sorted = sorted(recent, key=lambda e: int(e.get("timestamp", 0)), reverse=True)

    lines = [
        "🔓 *Unbonding Queue — Live*",
        "_Bonds broken in the last 7 days (warmup period, not yet released)_",
        "",
        f"Queue total: *{fmt_rize(total_rize)}*",
        f"Active breaks: {count}",
        "",
    ]

    per_page = 5
    start = page * per_page
    page_events = recent_sorted[start:start + per_page]
    total_pages = (count - 1) // per_page + 1

    lines.append(f"_Page {page+1}/{total_pages}_")
    lines.append("")

    for e in page_events:
        nft_id = e.get("nftId", "?")
        amount = parse_amt(e.get("amount", 0))
        date   = e.get("date") or str(e.get("timestamp", "—"))[:10]
        lines += [
            f"🔴 Bond #{nft_id} — {fmt_rize(amount)}",
            f"  {date}",
            "",
        ]

    if start + per_page < count:
        lines.append(f"_Reply *next* to see more._")

    return "\n".join(lines)


async def cmd_totalbonded(args: list) -> str:
    """Live total RIZE bonded via Alchemy RPC eth_call."""
    padded = "000000000000000000000000" + GOV_CONTRACT[2:].lower()
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "eth_call",
        "params": [{"to": RIZE_TOKEN, "data": "0x70a08231" + padded}, "latest"],
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(ALCHEMY_URL, json=payload)
            result = r.json().get("result", "0x0")
    except Exception:
        return "Could not fetch total bonded (RPC error)."

    if not result or result == "0x":
        return "Empty RPC response."

    total_rize = int(result, 16) / DECIMALS
    pct_supply = (total_rize / 5_000_000_000) * 100

    from utils.coingecko import cg_get
    price_data = await cg_get("/simple/price", {"ids": "rize", "vs_currencies": "usd"})
    rize_price = price_data.get("rize", {}).get("usd", 0) if price_data else 0
    usd_value  = total_rize * rize_price

    # Circ supply from CoinGecko
    circ_supply = 5_000_000_000  # fallback
    try:
        from utils.coingecko import cg_get as _cg
        circ_data = await _cg("/coins/rize", {"localization":"false","tickers":"false","market_data":"true","community_data":"false","developer_data":"false"})
        if circ_data:
            cs = circ_data.get("market_data",{}).get("circulating_supply")
            if cs: circ_supply = float(cs)
    except Exception:
        pass
    pct_circ = (total_rize / circ_supply * 100) if circ_supply else 0

    return "\n".join([
        "🏦 *Total RIZE Bonded*",
        "",
        f"Total bonded: *{fmt_rize(total_rize)}*",
        f"% of max supply (5B): {pct_supply:.2f}%",
        f"% of circ supply: {pct_circ:.2f}%",
        f"USD value: {fmt_usd(usd_value)}",
        f"RIZE price: {fmt_price(rize_price)}",
        "",
        "_Live data_",
    ])
