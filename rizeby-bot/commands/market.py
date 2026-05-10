"""
Commands: /perf, /pricesim, /portfoliosim, /arbitrage, /market
Any base asset supported — RIZE by default, CC or any coin if specified first.
"""
import httpx
from utils.coingecko import (
    get_markets, get_market_chart, get_global, get_simple_price,
    resolve_coin_ids, get_coin_detail, parse_base_and_compare,
    display_name, RIZE_ID, RIZE_SUPPLY, cg_get,
)
from utils.formatters import fmt_usd, fmt_pct, fmt_price, fmt_num, parse_amount


# ── /rizeby perf [base] {compare assets} ─────────────────────────────────────

async def cmd_perf(args: list[str]) -> str:
    """
    7D, 30D and 90D price performance of selected tokens against USD.
    Base asset is first if it's a known coin (default: RIZE).
    Usage: /rizeby perf eth link mantra
           /rizeby cc perf eth link   (CC as base)
           /rizeby sol perf eth btc   (SOL as base)
    """
    base_id, compare_tokens = parse_base_and_compare(args)
    token_map = await resolve_coin_ids(compare_tokens)

    all_ids = list(set([base_id] + list(token_map.values())))
    markets_data = await get_markets(all_ids)
    if not markets_data:
        return "❌ Could not fetch performance data."

    by_id = {c["id"]: c for c in markets_data}
    base_name = display_name(base_id)

    # Fetch 90d chart for each
    perf_90d: dict[str, float] = {}
    for cid in all_ids:
        chart = await get_market_chart(cid, 90)
        if chart and chart.get("prices") and len(chart["prices"]) >= 2:
            p0 = chart["prices"][0][1]
            p1 = chart["prices"][-1][1]
            if p0:
                perf_90d[cid] = ((p1 - p0) / p0) * 100

    def make_row(cid, label):
        c = by_id.get(cid, {})
        p7  = c.get("price_change_percentage_7d_in_currency")
        p30 = c.get("price_change_percentage_30d_in_currency")
        p90 = perf_90d.get(cid)
        return (label, p7, p30, p90)

    rows = [make_row(base_id, base_name)]
    for orig, cid in token_map.items():
        if cid != base_id:
            rows.append(make_row(cid, display_name(cid, orig)))

    rows = [rows[0]] + sorted(rows[1:], key=lambda r: (r[1] or -9999), reverse=True)

    def fmt_cell(v):
        if v is None: return "  —  "
        sign = "+" if v > 0 else ""
        return f"{sign}{v:.1f}%"

    lines = [
        "📊 *Performance Comparison*",
        "_7D, 30D and 90D price performance against USD_",
        "",
        "```",
        f"{'Token':<8} {'7D':>8} {'30D':>8} {'90D':>8}",
        "─" * 36,
    ]
    for label, p7, p30, p90 in rows:
        lines.append(f"{label:<8} {fmt_cell(p7):>8} {fmt_cell(p30):>8} {fmt_cell(p90):>8}")
    lines.append("```")

    return "\n".join(lines)


# ── /rizeby pricesim [base] {compare assets} ──────────────────────────────────

async def cmd_pricesim(args: list[str]) -> str:
    """
    What would {base} be worth if it had each asset's market cap?
    Usage: /rizeby pricesim eth link cc
           /rizeby cc pricesim eth btc sol
    """
    base_id, compare_tokens = parse_base_and_compare(args)
    token_map = await resolve_coin_ids(compare_tokens)
    base_name = display_name(base_id)

    all_ids = list(set([base_id] + list(token_map.values())))
    markets_data = await get_markets(all_ids)
    if not markets_data:
        return "❌ Could not fetch market data."

    by_id = {c["id"]: c for c in markets_data}
    base  = by_id.get(base_id, {})
    base_price   = base.get("current_price", 0)
    base_supply  = base.get("circulating_supply") or (RIZE_SUPPLY if base_id == RIZE_ID else 1)
    base_mcap    = base.get("market_cap", 0)

    lines = [
        f"🎯 *{base_name} Price Simulation*",
        f"_What would {base_name} be worth if it had each asset's market cap?_",
        "",
        f"Current {base_name} price: {fmt_price(base_price)}",
        f"Supply: {fmt_num(base_supply)}",
        "",
        "```",
        f"{'Asset':<8} {'MCap':>10} {'Hyp. Price':>12} {'Chg':>8} {'% of MCap':>10}",
        "─" * 52,
    ]

    for orig, cid in token_map.items():
        if cid == base_id:
            continue
        c = by_id.get(cid, {})
        target_mcap = c.get("market_cap", 0)
        if not target_mcap:
            continue
        hyp_price   = target_mcap / base_supply
        pct_change  = ((hyp_price / base_price) - 1) * 100 if base_price else 0
        pct_of_mcap = (base_mcap / target_mcap) * 100 if target_mcap else 0
        label       = display_name(cid, orig)
        sign        = "+" if pct_change > 0 else ""

        lines.append(
            f"{label:<8} {fmt_usd(target_mcap):>10} {fmt_price(hyp_price):>12} "
            f"{sign}{pct_change:.0f}%    {pct_of_mcap:.2f}%"
        )

    lines.append("```")
    return "\n".join(lines)


# ── /rizeby portfoliosim [base] {compare assets} {amount} ────────────────────

async def cmd_portfoliosim(args: list[str]) -> str:
    """
    Estimated value of your {base} holdings at each simulated target price.
    Usage: /rizeby portfoliosim eth link mantra 1000000
           /rizeby cc portfoliosim eth btc 50000
    """
    base_id, remaining = parse_base_and_compare(args)
    base_name = display_name(base_id)

    # Extract amount and token list
    amount = None
    tokens = []
    for a in remaining:
        parsed = parse_amount(a)
        if parsed is not None and amount is None:
            amount = parsed
        elif parse_amount(a) is None:
            tokens.append(a)

    if amount is None:
        base_sym = base_name.lower()
        return (
            f"❌ Please include your {base_name} amount at the end.\n\n"
            f"Example: `/rizeby portfoliosim eth link {base_sym} 1000000`\n"
            f"Also works: `1 000 000`, `1.000.000`, `1M`"
        )

    token_map = await resolve_coin_ids(tokens)
    all_ids   = list(set([base_id] + list(token_map.values())))
    markets_data = await get_markets(all_ids)
    if not markets_data:
        return "❌ Could not fetch market data."

    by_id = {c["id"]: c for c in markets_data}
    base  = by_id.get(base_id, {})
    base_price  = base.get("current_price", 0)
    base_supply = base.get("circulating_supply") or (RIZE_SUPPLY if base_id == RIZE_ID else 1)
    current_bag = amount * base_price

    lines = [
        f"💼 *Portfolio Simulation*",
        f"_Estimated value of {fmt_num(amount)} {base_name} at each simulated target price_",
        "",
        f"Current {base_name} price: {fmt_price(base_price)}",
        f"Current bag value: {fmt_usd(current_bag)}",
        "",
        "```",
        f"{'Asset':<8} {'Hyp. Price':>12} {'Bag Value':>12} {'Gain/Loss':>10}",
        "─" * 46,
    ]

    for orig, cid in token_map.items():
        if cid == base_id:
            continue
        c = by_id.get(cid, {})
        target_mcap = c.get("market_cap", 0)
        if not target_mcap:
            continue
        hyp_price = target_mcap / base_supply
        bag_value = amount * hyp_price
        pct       = ((bag_value / current_bag) - 1) * 100 if current_bag else 0
        sign      = "+" if pct > 0 else ""
        label     = display_name(cid, orig)

        lines.append(
            f"{label:<8} {fmt_price(hyp_price):>12} {fmt_usd(bag_value):>12} {sign}{pct:.0f}%"
        )

    lines.append("```")
    return "\n".join(lines)


# ── /rizeby arbitrage [base] {compare assets} {amount} ───────────────────────

async def cmd_arbitrage(args: list[str]) -> str:
    """
    Ratio analysis — compare base asset vs others in their native units.
    Usage: /rizeby arbitrage eth cc link 1000000
           /rizeby cc arbitrage eth btc 50000
    """
    base_id, remaining = parse_base_and_compare(args)
    base_name = display_name(base_id)

    amount = None
    tokens = []
    for a in remaining:
        parsed = parse_amount(a)
        if parsed is not None and amount is None:
            amount = parsed
        elif parse_amount(a) is None:
            tokens.append(a)

    token_map = await resolve_coin_ids(tokens)
    all_ids   = list(set([base_id] + list(token_map.values())))
    prices    = await get_simple_price(all_ids)
    if not prices:
        return "❌ Could not fetch price data."

    base_price = prices.get(base_id, {}).get("usd", 0)

    lines = [
        f"⚖️ *Ratio Analysis — {base_name}*",
        "_Compare gains and losses expressed directly in compared asset units._",
        "_Monitor arbitrage opportunities between assets._",
        "",
    ]
    if amount:
        lines.append(f"Bag: {fmt_num(amount)} {base_name} = {fmt_usd(amount * base_price)}")
        lines.append("")

    lines += [
        "```",
        f"{'Asset':<8} {'1 {base_name}':>12} {'Bag In Asset':>14}",
        "─" * 38,
    ]

    for orig, cid in token_map.items():
        if cid == base_id:
            continue
        coin_price = prices.get(cid, {}).get("usd", 0)
        if not coin_price:
            continue
        ratio        = base_price / coin_price
        bag_in_asset = (amount * base_price / coin_price) if amount else None
        label        = display_name(cid, orig)
        bag_str      = fmt_num(bag_in_asset, 4) if bag_in_asset else "—"
        lines.append(f"{label:<8} {ratio:>12.6f} {bag_str:>14}")

    lines.append("```")
    return "\n".join(lines)


# ── /rizeby market ─────────────────────────────────────────────────────────

async def cmd_market(args: list[str]) -> str:
    """Broader market context — BTC.D, ETH.D, Fear&Greed, AltSzn."""
    import asyncio

    async def fetch_fng():
        try:
            async with httpx.AsyncClient(timeout=8) as c:
                r = await c.get("https://api.alternative.me/fng/?limit=1")
                return r.json()
        except Exception:
            return None

    async def fetch_altszn():
        try:
            async with httpx.AsyncClient(timeout=8) as c:
                r = await c.get("https://api.coin-stats.com/v2/markets/chart/altcoin_season_index?type=3m")
                return r.json()
        except Exception:
            return None

    global_data, fng_data, altszn_data = await asyncio.gather(
        get_global(), fetch_fng(), fetch_altszn()
    )

    lines = [
        "🌍 *Market Context*",
        "_Broader market positioning, relative performance, and valuation signal._",
        "",
    ]

    if global_data:
        gd = global_data.get("data", {})
        total_mcap = gd.get("total_market_cap", {}).get("usd", 0)
        dominance  = gd.get("market_cap_percentage", {})
        btc_d   = dominance.get("btc", 0)
        eth_d   = dominance.get("eth", 0)
        link_d  = dominance.get("link", 0)

        # RIZE dominance
        rize_data = await cg_get("/simple/price", {"ids":"rize","vs_currencies":"usd","include_market_cap":"true"})
        rize_mcap = rize_data.get("rize", {}).get("usd_market_cap", 0) if rize_data else 0
        rize_d    = (rize_mcap / total_mcap * 100) if (rize_mcap and total_mcap) else 0

        lines += [
            f"BTC.D: {btc_d:.2f}%",
            f"ETH.D: {eth_d:.2f}%",
            f"LINK.D: {link_d:.3f}%",
            f"RIZE.D: {rize_d:.6f}%",
            "",
            f"TOTAL MCap: {fmt_usd(total_mcap)}",
        ]

    if fng_data:
        fng      = fng_data.get("data", [{}])[0]
        fng_val  = fng.get("value", "—")
        fng_cls  = fng.get("value_classification", "—")
        lines.append(f"Fear & Greed: {fng_val} ({fng_cls})")

    if altszn_data:
        vals = altszn_data if isinstance(altszn_data, list) else altszn_data.get("data", [])
        if vals:
            last  = vals[-1]
            score = int(last.get("value", 0) if isinstance(last, dict) else last)
            if score >= 75:
                season = "Altcoin Season 🟢"
            elif score >= 50:
                season = "Neutral ⚪"
            else:
                season = "Bitcoin Season 🟠"
            lines.append(f"BTC/Alt Season: {season}")
            lines.append(f"ALTSZN Score: {score}/100")

    return "\n".join(lines)
