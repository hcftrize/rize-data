"""
Commands: /ccprice, /ccburnmint [1d|1w], /ccallocation
CC Data Hub — CantonScan API.
"""
import httpx
from utils.coingecko import get_coin_detail, get_tickers, cg_get
from utils.formatters import fmt_usd, fmt_price, fmt_pct, fmt_num

CANTONSCAN_BASE = "https://fossil-outlook-levitate-gloomy.cantonscan.com/api"
CC_ID = "canton-network"


async def cmd_cc_price(args: list) -> str:
    data = await get_coin_detail(CC_ID)
    if not data:
        return "❌ Could not fetch CC price."
    md = data.get("market_data", {})
    price_usd = md.get("current_price", {}).get("usd", 0)
    price_btc = md.get("current_price", {}).get("btc", 0)
    price_eth = md.get("current_price", {}).get("eth", 0)
    high_24h  = md.get("high_24h", {}).get("usd", 0)
    low_24h   = md.get("low_24h", {}).get("usd", 0)
    ch_1h     = md.get("price_change_percentage_1h_in_currency", {}).get("usd")
    ch_24h    = md.get("price_change_percentage_24h", 0)
    ch_7d     = md.get("price_change_percentage_7d", 0)
    ch_30d    = md.get("price_change_percentage_30d", 0)
    ath       = md.get("ath", {}).get("usd", 0)
    ath_pct   = md.get("ath_change_percentage", {}).get("usd", 0)
    vol_24h   = md.get("total_volume", {}).get("usd", 0)
    mcap      = md.get("market_cap", {}).get("usd", 0)

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
        "",
        f"1h: {arrow(ch_1h)}",
        f"24h: {arrow(ch_24h)}",
        f"7d: {arrow(ch_7d)}",
        f"30d: {arrow(ch_30d)}",
        "",
        f"ATH: {fmt_price(ath)} ({fmt_pct(ath_pct)})",
        f"% to ATH: {fmt_pct(pct_to_ath) if pct_to_ath else '—'}",
        f"24h Vol: {fmt_usd(vol_24h)}",
        f"MCap: {fmt_usd(mcap)}",
    ]
    return "\n".join(lines)


async def cmd_cc_burnmint(args: list) -> str:
    interval = "week" if args and args[0].lower() in ("1w", "week", "weekly") else "day"
    period_label = "Weekly" if interval == "week" else "Daily"

    url = f"{CANTONSCAN_BASE}/mining-rounds/timeseries?interval={interval}"
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            r = await client.get(url)
            data = r.json()
    except Exception:
        return "❌ Could not fetch burn/mint data from CantonScan."

    if not data or not isinstance(data, list):
        return "❌ No burn/mint data available."

    latest = data[-1]
    total_minted = float(latest.get("totalMinted") or latest.get("minted") or 0)
    total_burned = float(latest.get("totalBurned") or latest.get("burned") or 0)
    ratio = total_burned / total_minted if total_minted else 0

    status = "🔥 Deflationary" if ratio >= 1 else "⚖️ Near Neutral" if ratio >= 0.8 else "📈 Inflationary"
    period_word = "this week" if interval == "week" else "today"

    # Last 5 periods
    recent = data[-5:]
    period_name = "Week" if interval == "week" else "Day"

    lines = [
        f"🔥 *CC Burn/Mint — {period_label}*",
        "",
        f"Burn/Mint Ratio {period_word}: *{ratio:.3f}*",
        f"Tokenomics Status: {status}",
        "",
        f"Minted {period_word}: {fmt_num(total_minted)} CC",
        f"Burned {period_word}: {fmt_num(total_burned)} CC",
        "",
        f"Last 5 {period_name.lower()}s:",
    ]

    for entry in reversed(recent):
        date = str(entry.get("date") or entry.get("week") or "—")[:10]
        m = float(entry.get("totalMinted") or entry.get("minted") or 0)
        b = float(entry.get("totalBurned") or entry.get("burned") or 0)
        r_val = b / m if m else 0
        lines.append(f"  {date}: Minted {fmt_num(m)} · Burned {fmt_num(b)} · Ratio {r_val:.3f}")

    return "\n".join(lines)


async def cmd_cc_allocation(args: list) -> str:
    url_day = f"{CANTONSCAN_BASE}/mining-rounds/timeseries?interval=day"
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            r = await client.get(url_day)
            data = r.json()
    except Exception:
        return "❌ Could not fetch allocation data."

    if not data or not isinstance(data, list):
        return "❌ No allocation data available."

    # Try different field names
    def get_field(entry, *names):
        for n in names:
            if entry.get(n) is not None:
                return float(entry.get(n) or 0)
        return 0.0

    total_sv   = sum(get_field(e, "superValidatorRewards", "sv_rewards", "superValidator") for e in data)
    total_val  = sum(get_field(e, "validatorRewards", "validator_rewards", "validator") for e in data)
    total_app  = sum(get_field(e, "appRewards", "app_rewards", "apps") for e in data)
    total_burn = sum(get_field(e, "totalBurned", "burned") for e in data)
    total_mint = sum(get_field(e, "totalMinted", "minted") for e in data)

    grand = total_sv + total_val + total_app
    if grand == 0:
        return "❌ No allocation data to display."

    burn_ratio = total_burn / total_mint if total_mint else 0

    lines = [
        "📊 *CC Mint Allocation — Since Genesis*",
        "_Distribution of minted CC by role_",
        "",
        f"Super Validators: *{total_sv/grand*100:.1f}%* ({fmt_num(total_sv)} CC)",
        f"Validators:       *{total_val/grand*100:.1f}%* ({fmt_num(total_val)} CC)",
        f"Apps:             *{total_app/grand*100:.1f}%* ({fmt_num(total_app)} CC)",
        "",
        f"Total Minted: {fmt_num(total_mint)} CC",
        f"Total Burned: {fmt_num(total_burn)} CC",
        f"Cumulative Burn/Mint Ratio: {burn_ratio:.3f}",
    ]
    return "\n".join(lines)
