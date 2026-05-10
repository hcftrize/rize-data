"""
Commands: /cc price, /cc burnmint [1d|1w], /cc allocation
CC Data Hub — identical to the web module.
"""
import httpx
from utils.coingecko import get_rize_price, get_tickers, cg_get
from utils.formatters import fmt_usd, fmt_price, fmt_pct, fmt_num

CANTONSCAN_BASE = "https://fossil-outlook-levitate-gloomy.cantonscan.com/api"
CC_ID = "canton-network"


# ── /rizeby cc price ──────────────────────────────────────────────────────────

async def cmd_cc_price(args: list[str]) -> str:
    data = await cg_get(
        "/coins/canton-network",
        {
            "localization": "false",
            "tickers": "false",
            "market_data": "true",
            "community_data": "false",
            "developer_data": "false",
        },
    )
    if not data:
        return "❌ Could not fetch CC price."

    md = data.get("market_data", {})
    price_usd  = md.get("current_price", {}).get("usd", 0)
    price_btc  = md.get("current_price", {}).get("btc", 0)
    price_eth  = md.get("current_price", {}).get("eth", 0)
    high_24h   = md.get("high_24h", {}).get("usd", 0)
    low_24h    = md.get("low_24h", {}).get("usd", 0)
    ch_1h      = md.get("price_change_percentage_1h_in_currency", {}).get("usd")
    ch_24h     = md.get("price_change_percentage_24h", 0)
    ch_7d      = md.get("price_change_percentage_7d", 0)
    ch_30d     = md.get("price_change_percentage_30d", 0)
    ath        = md.get("ath", {}).get("usd", 0)
    ath_pct    = md.get("ath_change_percentage", {}).get("usd", 0)
    vol_24h    = md.get("total_volume", {}).get("usd", 0)
    mcap       = md.get("market_cap", {}).get("usd", 0)

    def arrow(v):
        if v is None: return "—"
        return f"{'📈' if v > 0 else '📉'} {fmt_pct(v)}"

    pct_to_ath = ((ath / price_usd) - 1) * 100 if price_usd and ath else None

    lines = [
        "*CC* — Canton Coin",
        "",
        f"💰 Price: {fmt_price(price_usd)}",
        f"⤷ ₿ {price_btc:.10f} | Ξ {price_eth:.8f}",
        f"⚖ H/L: {fmt_price(high_24h)} | {fmt_price(low_24h)}",
        f"1h: {arrow(ch_1h)}",
        f"24h: {arrow(ch_24h)}",
        f"7d: {arrow(ch_7d)}",
        f"30d: {arrow(ch_30d)}",
        f"ATH: {fmt_price(ath)} ({fmt_pct(ath_pct)})",
        f"% to ATH: {fmt_pct(pct_to_ath) if pct_to_ath else '—'}",
        f"24h Vol: {fmt_usd(vol_24h)}",
        f"MCap: {fmt_usd(mcap)}",
    ]
    return "\n".join(lines)


# ── /rizeby cc burnmint ───────────────────────────────────────────────────────

async def cmd_cc_burnmint(args: list[str]) -> str:
    """
    Burn/Mint ratio from CantonScan.
    Default: daily. /cc burnmint 1w → weekly.
    """
    interval = "day"
    if args and args[0].lower() in ("1w", "week", "weekly"):
        interval = "week"
    elif args and args[0].lower() in ("1d", "day", "daily"):
        interval = "day"

    url = f"{CANTONSCAN_BASE}/mining-rounds/timeseries?interval={interval}"

    try:
        async with httpx.AsyncClient(timeout=12) as client:
            r = await client.get(url)
            data = r.json()
    except Exception:
        return "❌ Could not fetch burn/mint data from CantonScan."

    if not data or not isinstance(data, list):
        return "❌ No burn/mint data available."

    # Get last period
    latest = data[-1] if data else {}
    period_label = "this week" if interval == "week" else "today"

    total_minted = float(latest.get("totalMinted", 0) or 0)
    total_burned = float(latest.get("totalBurned", 0) or 0)
    ratio = total_burned / total_minted if total_minted else 0

    # Tokenomics status
    if ratio >= 1:
        status = "🔥 Deflationary"
    elif ratio >= 0.8:
        status = "⚖️ Near Neutral"
    else:
        status = "📈 Inflationary"

    # Last 5 periods
    recent = data[-5:]

    period_name = "Week" if interval == "week" else "Day"

    lines = [
        f"🔥 *CC Burn/Mint — {period_name}ly*",
        "",
        f"Burn/Mint Ratio {period_label}: *{ratio:.3f}*",
        f"Tokenomics Status: {status}",
        "",
        f"Minted {period_label}: {fmt_num(total_minted)} CC",
        f"Burned {period_label}: {fmt_num(total_burned)} CC",
        "",
        f"Last 5 {period_name.lower()}s:",
        "```",
        f"{'Date':<12} {'Minted':>12} {'Burned':>12} {'Ratio':>7}",
        "─" * 47,
    ]

    for entry in reversed(recent):
        date = entry.get("date", entry.get("week", "—"))[:10]
        m = float(entry.get("totalMinted", 0) or 0)
        b = float(entry.get("totalBurned", 0) or 0)
        r = b / m if m else 0
        lines.append(f"{date:<12} {fmt_num(m):>12} {fmt_num(b):>12} {r:>7.3f}")

    lines.append("```")
    return "\n".join(lines)


# ── /rizeby cc allocation ─────────────────────────────────────────────────────

async def cmd_cc_allocation(args: list[str]) -> str:
    """
    Mint allocation per role since genesis — SuperValidators, Validators, Apps.
    """
    # Try to get data from CantonScan timeseries, aggregate by role
    url_day = f"{CANTONSCAN_BASE}/mining-rounds/timeseries?interval=day"

    try:
        async with httpx.AsyncClient(timeout=12) as client:
            r = await client.get(url_day)
            data = r.json()
    except Exception:
        return "❌ Could not fetch allocation data."

    if not data or not isinstance(data, list):
        return "❌ No allocation data available."

    # Aggregate totals
    total_sv   = sum(float(e.get("superValidatorRewards", 0) or 0) for e in data)
    total_val  = sum(float(e.get("validatorRewards", 0)      or 0) for e in data)
    total_app  = sum(float(e.get("appRewards", 0)             or 0) for e in data)
    total_burn = sum(float(e.get("totalBurned", 0)            or 0) for e in data)
    total_mint = sum(float(e.get("totalMinted", 0)            or 0) for e in data)

    grand = total_sv + total_val + total_app
    if grand == 0:
        return "❌ No allocation data to display."

    sv_pct  = total_sv  / grand * 100
    val_pct = total_val / grand * 100
    app_pct = total_app / grand * 100

    burn_ratio = total_burn / total_mint if total_mint else 0

    lines = [
        "📊 *CC Mint Allocation — Since Genesis*",
        "_Distribution of minted CC by role_",
        "",
        f"Super Validators: *{sv_pct:.1f}%* ({fmt_num(total_sv)} CC)",
        f"Validators:       *{val_pct:.1f}%* ({fmt_num(total_val)} CC)",
        f"Apps:             *{app_pct:.1f}%* ({fmt_num(total_app)} CC)",
        "",
        f"Total Minted: {fmt_num(total_mint)} CC",
        f"Total Burned: {fmt_num(total_burn)} CC",
        f"Cumulative Burn/Mint Ratio: {burn_ratio:.3f}",
    ]

    return "\n".join(lines)
