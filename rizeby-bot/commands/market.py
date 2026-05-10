"""
Commands: /perf, /pricesim, /portfoliosim, /arbitrage, /market
Mobile-friendly text format (no ASCII tables).
"""
import httpx
from utils.coingecko import (
    get_markets, get_market_chart, get_global, get_simple_price,
    resolve_coin_ids, get_coin_detail, parse_base_and_compare,
    display_name, RIZE_ID, RIZE_SUPPLY, cg_get,
)
from utils.formatters import fmt_usd, fmt_pct, fmt_price, fmt_num, parse_amount

# Simple in-memory cache for API responses (TTL not enforced, resets per cold start)
_cache: dict = {}

async def _cached(key: str, coro):
    if key in _cache:
        return _cache[key]
    result = await coro
    if result:
        _cache[key] = result
    return result


async def cmd_perf(args: list) -> str:
    base_id, compare_tokens = parse_base_and_compare(args)
    token_map = await resolve_coin_ids(compare_tokens)
    all_ids   = list(set([base_id] + list(token_map.values())))
    base_name = display_name(base_id)

    markets_data = await _cached(f"markets_{','.join(sorted(all_ids))}", get_markets(all_ids))
    if not markets_data:
        return "❌ Could not fetch performance data."
    by_id = {c["id"]: c for c in markets_data}

    # Fetch 90d charts
    perf_90d = {}
    for cid in all_ids:
        chart = await _cached(f"chart90_{cid}", get_market_chart(cid, 90))
        if chart and chart.get("prices") and len(chart["prices"]) >= 2:
            p0 = chart["prices"][0][1]
            p1 = chart["prices"][-1][1]
            if p0:
                perf_90d[cid] = ((p1 - p0) / p0) * 100

    def make_row(cid, label):
        c = by_id.get(cid, {})
        return {
            "label": label,
            "p7":  c.get("price_change_percentage_7d_in_currency"),
            "p30": c.get("price_change_percentage_30d_in_currency"),
            "p90": perf_90d.get(cid),
        }

    rows = [make_row(base_id, base_name)]
    for orig, cid in token_map.items():
        if cid != base_id:
            rows.append(make_row(cid, display_name(cid, orig)))
    rows = [rows[0]] + sorted(rows[1:], key=lambda r: (r["p7"] or -9999), reverse=True)

    def fc(v):
        if v is None: return "—"
        sign = "+" if v > 0 else ""
        return f"{sign}{v:.1f}%"

    # Mobile-friendly: 2 per line per period
    def period_block(period_key, period_label):
        lines = [f"*{period_label}*"]
        row_pairs = [rows[i:i+2] for i in range(0, len(rows), 2)]
        for pair in row_pairs:
            parts = [f"{r['label']}: {fc(r[period_key])}" for r in pair]
            lines.append("  ".join(parts))
        return "\n".join(lines)

    text = [
        "📊 *Performance Comparison*",
        "_7D, 30D and 90D price performance against USD_",
        "",
        period_block("p7", "7 Days"),
        "",
        period_block("p30", "30 Days"),
        "",
        period_block("p90", "90 Days"),
    ]
    return "\n".join(text)


async def cmd_pricesim(args: list) -> str:
    base_id, compare_tokens = parse_base_and_compare(args)
    token_map = await resolve_coin_ids(compare_tokens)
    base_name = display_name(base_id)

    all_ids      = list(set([base_id] + list(token_map.values())))
    markets_data = await _cached(f"markets_{','.join(sorted(all_ids))}", get_markets(all_ids))
    if not markets_data:
        return "❌ Could not fetch market data."

    by_id       = {c["id"]: c for c in markets_data}
    base        = by_id.get(base_id, {})
    base_price  = base.get("current_price", 0)
    base_supply = base.get("circulating_supply") or (RIZE_SUPPLY if base_id == RIZE_ID else 1)
    base_mcap   = base.get("market_cap", 0)

    lines = [
        f"🎯 *{base_name} Price Simulation*",
        f"_What would {base_name} be worth if it had each asset's market cap?_",
        "",
        f"Current: {fmt_price(base_price)} · Supply: {fmt_num(base_supply)}",
        "",
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

        lines.append(f"*{label}* MCap: {fmt_usd(target_mcap)}")
        lines.append(f"  → {base_name} price: {fmt_price(hyp_price)} ({sign}{pct_change:.0f}%)")
        lines.append(f"  → {base_name} is {pct_of_mcap:.3f}% of {label} MCap")
        lines.append("")

    return "\n".join(lines)


async def cmd_portfoliosim(args: list) -> str:
    """
    /portfoliosim {amount} {base} to {compare assets}
    or /portfoliosim {base} {compare assets} {amount}
    """
    # Parse "X base to compare1 compare2"
    tokens = list(args)
    amount = None
    base_id = RIZE_ID
    compare_tokens = []

    # Check for "to" separator
    if "to" in [t.lower() for t in tokens]:
        to_idx = [t.lower() for t in tokens].index("to")
        left   = tokens[:to_idx]
        right  = tokens[to_idx+1:]

        # Left: amount + base
        for t in left:
            parsed = parse_amount(t)
            if parsed is not None:
                amount = parsed
            else:
                from utils.coingecko import COIN_MAP
                tl = t.lower()
                if tl in COIN_MAP:
                    base_id = COIN_MAP[tl]
        compare_tokens = right
    else:
        base_id, remaining = parse_base_and_compare(tokens)
        for t in remaining:
            parsed = parse_amount(t)
            if parsed is not None:
                amount = parsed
            else:
                compare_tokens.append(t)

    base_name = display_name(base_id)

    if amount is None:
        return (
            f"❌ Please include your {base_name} amount.\n\n"
            f"Format: `/portfoliosim {{amount}} {{coin}} to {{compare assets}}`\n"
            f"Example: `/portfoliosim 1000000 rize to eth link mantra`"
        )

    token_map    = await resolve_coin_ids(compare_tokens)
    all_ids      = list(set([base_id] + list(token_map.values())))
    markets_data = await _cached(f"markets_{','.join(sorted(all_ids))}", get_markets(all_ids))
    if not markets_data:
        return "❌ Could not fetch market data."

    by_id       = {c["id"]: c for c in markets_data}
    base        = by_id.get(base_id, {})
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

        lines.append(f"*{label}* MCap → {base_name} @ {fmt_price(hyp_price)}")
        lines.append(f"  Bag value: {fmt_usd(bag_value)} ({sign}{pct:.0f}%)")
        lines.append("")

    return "\n".join(lines)


async def cmd_arbitrage(args: list) -> str:
    """
    Ratio Analysis — identical to RIZE Data Hub.
    Shows for 7d, 30d, 90d: how much of compared asset you'd gain/lose
    by swapping base into it compared to X days ago.
    /arbitrage {amount} {base} to {compare}
    """
    tokens = list(args)
    amount = None
    base_id = RIZE_ID
    compare_tokens = []

    if "to" in [t.lower() for t in tokens]:
        to_idx = [t.lower() for t in tokens].index("to")
        left   = tokens[:to_idx]
        right  = tokens[to_idx+1:]
        for t in left:
            parsed = parse_amount(t)
            if parsed is not None:
                amount = parsed
            else:
                from utils.coingecko import COIN_MAP
                tl = t.lower()
                if tl in COIN_MAP:
                    base_id = COIN_MAP[tl]
        compare_tokens = right
    else:
        base_id, remaining = parse_base_and_compare(tokens)
        for t in remaining:
            parsed = parse_amount(t)
            if parsed is not None:
                amount = parsed
            else:
                compare_tokens.append(t)

    base_name  = display_name(base_id)
    token_map  = await resolve_coin_ids(compare_tokens)
    all_ids    = list(set([base_id] + list(token_map.values())))

    # Need price history for 7d, 30d, 90d
    # Fetch 90d chart for each coin
    charts = {}
    for cid in all_ids:
        chart = await _cached(f"chart90_{cid}", get_market_chart(cid, 90))
        if chart and chart.get("prices"):
            prices = chart["prices"]
            # prices is list of [timestamp_ms, price]
            def get_price_at(days_ago):
                target_idx = max(0, len(prices) - 1 - days_ago)
                return prices[target_idx][1] if prices else None

            charts[cid] = {
                "now":  prices[-1][1] if prices else None,
                "7d":   get_price_at(7),
                "30d":  get_price_at(30),
                "90d":  get_price_at(90),
            }

    lines = [
        f"⚖️ *Ratio Analysis — {base_name}*",
        "_Compare gains/losses expressed in compared asset units._",
        "_+1.5 ETH means you'd have gained 1.5 ETH by swapping {base_name} to ETH X days ago._",
        "",
    ]

    if amount:
        base_now = charts.get(base_id, {}).get("now", 0)
        lines.append(f"Bag: {fmt_num(amount)} {base_name} = {fmt_usd(amount * (base_now or 0))}")
        lines.append("")

    for orig, cid in token_map.items():
        if cid == base_id:
            continue
        label    = display_name(cid, orig)
        bc       = charts.get(base_id, {})
        cc       = charts.get(cid, {})

        if not bc.get("now") or not cc.get("now"):
            lines.append(f"*{label}*: data unavailable")
            lines.append("")
            continue

        lines.append(f"*{base_name} → {label}*")

        for period in ["7d", "30d", "90d"]:
            b_now  = bc.get("now", 0)
            b_past = bc.get(period, 0)
            c_now  = cc.get("now", 0)
            c_past = cc.get(period, 0)

            if not all([b_now, b_past, c_now, c_past]):
                lines.append(f"  {period.upper()}: —")
                continue

            # How many of compared asset you'd get now vs X days ago
            ratio_now  = b_now  / c_now   # 1 base = X compared now
            ratio_past = b_past / c_past  # 1 base = X compared X days ago
            delta      = ratio_now - ratio_past  # gain/loss in compared units per 1 base

            if amount:
                total_delta = delta * amount
                sign = "+" if total_delta >= 0 else ""
                pct  = ((ratio_now / ratio_past) - 1) * 100 if ratio_past else 0
                psign = "+" if pct >= 0 else ""
                lines.append(f"  {period.upper()}: {sign}{fmt_num(total_delta, 4)} {label} ({psign}{pct:.1f}%)")
            else:
                sign = "+" if delta >= 0 else ""
                pct  = ((ratio_now / ratio_past) - 1) * 100 if ratio_past else 0
                psign = "+" if pct >= 0 else ""
                lines.append(f"  {period.upper()}: {sign}{delta:.6f} {label}/unit ({psign}{pct:.1f}%)")

        lines.append("")

    return "\n".join(lines)


async def cmd_market(args: list) -> str:
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

    lines = ["🌍 *Market Context*", ""]

    if global_data:
        gd = global_data.get("data", {})
        total_mcap = gd.get("total_market_cap", {}).get("usd", 0)
        dominance  = gd.get("market_cap_percentage", {})
        btc_d   = dominance.get("btc", 0)
        eth_d   = dominance.get("eth", 0)
        # LINK not in market_cap_percentage — compute from chainlink mcap like the hub
        link_d  = 0.0  # computed below after fetching chainlink
        rize_data = await cg_get("/simple/price", {"ids": "rize", "vs_currencies": "usd", "include_market_cap": "true"})
        rize_mcap = rize_data.get("rize", {}).get("usd_market_cap", 0) if rize_data else 0
        rize_d    = (rize_mcap / total_mcap * 100) if (rize_mcap and total_mcap) else 0

        # Fetch LINK mcap for dominance (not in CG global API)
        link_data = await cg_get("/simple/price", {"ids": "chainlink", "vs_currencies": "usd", "include_market_cap": "true"})
        link_mcap = link_data.get("chainlink", {}).get("usd_market_cap", 0) if link_data else 0
        link_d = (link_mcap / total_mcap * 100) if (link_mcap and total_mcap) else 0

        lines += [
            f"BTC.D: {btc_d:.2f}%",
            f"ETH.D: {eth_d:.2f}%",
            f"LINK.D: {link_d:.3f}%",
            f"RIZE.D: {rize_d:.6f}%",
            "",
            f"TOTAL MCap: {fmt_usd(total_mcap)}",
        ]

    if fng_data:
        fng     = fng_data.get("data", [{}])[0]
        fng_val = fng.get("value", "—")
        fng_cls = fng.get("value_classification", "—")
        lines.append(f"Fear & Greed: {fng_val} ({fng_cls})")

    if altszn_data:
        vals = altszn_data if isinstance(altszn_data, list) else altszn_data.get("data", [])
        if vals:
            last  = vals[-1]
            score = int(last.get("value", 0) if isinstance(last, dict) else last)
            season = "Altcoin Season 🟢" if score >= 75 else "Neutral ⚪" if score >= 50 else "Bitcoin Season 🟠"
            lines.append(f"BTC/Alt Season: {season}")
            lines.append(f"ALTSZN Score: {score}/100")

    return "\n".join(lines)
