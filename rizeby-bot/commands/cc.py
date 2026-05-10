"""
Commands: /ccprice, /ccburnmint [1d|1w], /ccallocation
CC Data Hub — exact logic from cc-data-hub.html.
CantonScan fields: data[].mintAmount, data[].burnAmount, data[].date
                  data[].superValidatorRewards, data[].validatorRewards, data[].appRewards
"""
import httpx
from utils.coingecko import get_coin_detail, get_tickers, cg_get
from utils.formatters import fmt_usd, fmt_price, fmt_pct, fmt_num

CANTONSCAN_WEEK = "https://fossil-outlook-levitate-gloomy.cantonscan.com/api/mining-rounds/timeseries?interval=week"
CANTONSCAN_DAY  = "https://fossil-outlook-levitate-gloomy.cantonscan.com/api/mining-rounds/timeseries?interval=day"
CC_ID = "canton-network"


async def _fetch_cantonscan(interval: str) -> list:
    url = CANTONSCAN_DAY if interval == "day" else CANTONSCAN_WEEK
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
            # Response shape: {data: [...]} or direct list
            if isinstance(data, dict):
                return data.get("data", [])
            return data if isinstance(data, list) else []
    except Exception as e:
        return []


async def cmd_cc_price(args: list) -> str:
    data = await get_coin_detail(CC_ID)
    if not data:
        return "Could not fetch CC price."
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

    return "\n".join([
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
    ])


async def cmd_cc_burnmint(args: list) -> str:
    interval = "day" if args and args[0].lower() in ("1d", "day", "daily") else "week"
    period_label = "Daily" if interval == "day" else "Weekly"
    period_word  = "today" if interval == "day" else "this week"

    rows = await _fetch_cantonscan(interval)
    if not rows:
        return f"Could not fetch burn/mint data from CantonScan."

    latest = rows[-1]
    mint = float(latest.get("mintAmount") or 0)
    burn = float(latest.get("burnAmount") or 0)
    ratio = burn / mint if mint else 0

    # Status matches cc-data-hub logic: >1.05 deflationary, >=0.95 neutral, else inflationary
    if ratio > 1.05:
        status = "Deflationary 🟢"
    elif ratio >= 0.95:
        status = "Neutral 🟡"
    else:
        status = "Inflationary 🔴"

    # Last 5 periods
    recent = rows[-5:]
    lines = [
        f"🔥 *CC Burn/Mint — {period_label}*",
        "",
        f"Burn/Mint Ratio {period_word}: *{ratio:.4f}*",
        f"Status: {status}",
        "",
        f"Minted {period_word}: {fmt_num(mint)} CC",
        f"Burned {period_word}: {fmt_num(burn)} CC",
        "",
        f"Recent {period_label.lower()} periods:",
    ]
    for e in reversed(recent):
        date = str(e.get("date", "—"))[:10]
        m = float(e.get("mintAmount") or 0)
        b = float(e.get("burnAmount") or 0)
        r = b / m if m else 0
        lines.append(f"  {date}: M {fmt_num(m)} · B {fmt_num(b)} · {r:.4f}")

    return "\n".join(lines)


async def cmd_cc_allocation(args: list) -> str:
    rows = await _fetch_cantonscan("week")
    if not rows:
        return "Could not fetch allocation data from CantonScan."

    # Same field names as cc-data-hub: superValidatorRewards, validatorRewards, appRewards
    total_sv  = sum(float(r.get("superValidatorRewards") or 0) for r in rows)
    total_val = sum(float(r.get("validatorRewards")      or 0) for r in rows)
    total_app = sum(float(r.get("appRewards")            or 0) for r in rows)
    total_mint = total_sv + total_val + total_app

    if not total_mint:
        return "No allocation data available."

    pct_sv  = total_sv  / total_mint * 100
    pct_val = total_val / total_mint * 100
    pct_app = total_app / total_mint * 100

    # Also get burn totals
    total_burned = sum(float(r.get("burnAmount") or 0) for r in rows)
    total_minted_raw = sum(float(r.get("mintAmount") or 0) for r in rows)
    burn_ratio = total_burned / total_minted_raw if total_minted_raw else 0

    return "\n".join([
        "📊 *CC Mint Allocation — Since Genesis*",
        "_Distribution of minted CC by role_",
        "",
        f"Super Validators: *{pct_sv:.1f}%* ({fmt_num(total_sv)} CC)",
        f"Validators:       *{pct_val:.1f}%* ({fmt_num(total_val)} CC)",
        f"Apps:             *{pct_app:.1f}%* ({fmt_num(total_app)} CC)",
        "",
        f"Total Minted: {fmt_num(total_minted_raw)} CC",
        f"Total Burned: {fmt_num(total_burned)} CC",
        f"Cumulative Burn/Mint: {burn_ratio:.4f}",
    ])
