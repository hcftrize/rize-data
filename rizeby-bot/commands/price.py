"""
Commands: /price, /chart, /tvl, /traderize, /tradecc
Any coin supported for /price and /chart — RIZE by default.
"""
import httpx
from utils.coingecko import (
    get_coin_detail, get_tickers, cg_get, get_kraken_pair,
    parse_base_and_compare, display_name, RIZE_ID, RIZE_SUPPLY
)
from utils.github_data import get_mcap_history
from utils.formatters import fmt_usd, fmt_pct, fmt_num, fmt_price


# ── /rizeby price [coin] ──────────────────────────────────────────────────────

async def cmd_price(args: list[str]) -> tuple[str, dict]:
    """
    Price for any coin — default RIZE.
    /rizeby price → RIZE
    /rizeby cc price → CC
    /rizeby eth price → ETH
    """
    base_id, _ = parse_base_and_compare(args)
    coin_name   = display_name(base_id)

    data = await get_coin_detail(base_id)
    if not data:
        return f"❌ Could not fetch {coin_name} price.", {}

    md        = data.get("market_data", {})
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

    # TVL only for RIZE
    tvl_str = None
    if base_id == RIZE_ID:
        history = await get_mcap_history()
        if history:
            series = history.get("series", [])
            if series:
                tvl = series[-1].get("tvl")
                if tvl:
                    tvl_str = fmt_usd(tvl)

    pct_to_ath = ((ath / price_usd) - 1) * 100 if price_usd and ath else None

    def arrow(v):
        if v is None: return "—"
        return f"{'📈' if v > 0 else '📉'} {fmt_pct(v)}"

    sym = data.get("symbol", "").upper() or coin_name
    lines = [
        f"*{coin_name}* — ${sym}",
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
    if tvl_str:
        lines.append(f"TVL: {tvl_str}")

    markup = {"inline_keyboard": [[{"text": "🔄 Refresh", "callback_data": f"refresh_price_{base_id}"}]]}
    return "\n".join(lines), markup


# ── /rizeby tvl ───────────────────────────────────────────────────────────────

async def cmd_tvl(args: list[str]) -> str:
    history = await get_mcap_history()
    if not history:
        return "❌ Could not fetch TVL data."
    series = history.get("series", [])
    if not series:
        return "❌ No TVL data available."

    latest   = series[-1]
    mcap     = latest.get("mcap")
    fdv      = latest.get("fdv")
    tvl      = latest.get("tvl")
    mcap_tvl = latest.get("mcap_tvl")
    fdv_tvl  = latest.get("fdv_tvl")
    date     = latest.get("date", "")

    price_data = await get_coin_detail(RIZE_ID)
    live_mcap = live_price = None
    if price_data:
        md = price_data.get("market_data", {})
        live_mcap  = md.get("market_cap", {}).get("usd")
        live_price = md.get("current_price", {}).get("usd")

    def valuation(ratio):
        if ratio is None: return "—"
        if ratio < 0.5:   return "🟢 Undervalued"
        if ratio < 1.0:   return "🟡 Fair"
        if ratio < 2.0:   return "🟠 Overvalued"
        return "🔴 Highly Overvalued"

    lines = [
        "📊 *RIZE MCap & TVL*",
        f"_Data as of {date}_",
        "",
        f"💰 Live Price: {fmt_price(live_price) if live_price else '—'}",
        f"📈 Live MCap: {fmt_usd(live_mcap) if live_mcap else '—'}",
        "",
        f"TVL: {fmt_usd(tvl)}",
        f"MCap: {fmt_usd(mcap)}",
        f"FDV: {fmt_usd(fdv)}",
        "",
        f"MCap/TVL: {f'{mcap_tvl:.2f}×' if mcap_tvl else '—'} {valuation(mcap_tvl)}",
        f"FDV/TVL: {f'{fdv_tvl:.2f}×' if fdv_tvl else '—'} {valuation(fdv_tvl)}",
    ]
    return "\n".join(lines)


# ── /rizeby chart [coin] [interval] ──────────────────────────────────────────

KRAKEN_INTERVALS = {
    "15m":60*15//60 or 15,"1h":60,"4h":240,"1d":1440,"1w":10080,"1M":43200,
}

async def cmd_chart(args: list[str]) -> tuple[bytes | None, str]:
    """
    OHLC chart for any coin on Kraken.
    /rizeby chart        → RIZE daily
    /rizeby chart 1h     → RIZE 1h
    /rizeby cc chart 4h  → CC 4h
    /rizeby eth chart 1w → ETH weekly
    """
    base_id, remaining = parse_base_and_compare(args)
    coin_name = display_name(base_id)

    # Interval from remaining args
    interval_key = "1d"
    for a in remaining:
        al = a.lower()
        if al in KRAKEN_INTERVALS or al in ("daily","weekly","monthly","15m","1h","4h","1d","1w","1M"):
            interval_key = al
            break
    if interval_key == "monthly": interval_key = "1M"
    if interval_key == "daily":   interval_key = "1d"
    if interval_key == "weekly":  interval_key = "1w"

    interval_min = KRAKEN_INTERVALS.get(interval_key, 1440)

    # Get Kraken pair
    pair = get_kraken_pair(base_id)
    if not pair:
        return None, f"❌ No Kraken pair found for {coin_name}. Try RIZE, ETH, BTC, LINK, SOL…"

    url = f"https://api.kraken.com/0/public/OHLC?pair={pair}&interval={interval_min}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url)
            data = r.json()
    except Exception:
        return None, "❌ Could not fetch chart data from Kraken."

    if data.get("error"):
        return None, f"❌ Kraken error: {data['error']}"

    result   = data.get("result", {})
    ohlc_key = next((k for k in result if k != "last"), None)
    if not ohlc_key:
        return None, "❌ No OHLC data returned."

    candles = result[ohlc_key][-60:]
    closes  = [float(c[4]) for c in candles]

    chart_cfg = {
        "type": "line",
        "data": {
            "labels": [str(c[0]) for c in candles],
            "datasets": [{
                "label": f"{coin_name}/USD {interval_key}",
                "data": closes,
                "borderColor": "#7ee0ff",
                "backgroundColor": "rgba(126,224,255,0.08)",
                "borderWidth": 2,
                "pointRadius": 0,
                "fill": True,
                "tension": 0.3,
            }]
        },
        "options": {
            "plugins": {
                "legend": {"labels": {"color": "#ffffff"}},
                "title": {
                    "display": True,
                    "text": f"{coin_name}/USD — {interval_key} (Kraken)",
                    "color": "#ffffff",
                    "font": {"size": 16},
                }
            },
            "scales": {
                "x": {"display": False},
                "y": {"ticks": {"color": "#b6c1d8"}, "grid": {"color": "rgba(255,255,255,0.06)"}},
            },
        },
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                "https://quickchart.io/chart",
                json={"c": chart_cfg, "backgroundColor": "#060818", "width": 800, "height": 400},
            )
            if r.status_code == 200:
                caption = f"📊 {coin_name}/USD — {interval_key} (Kraken)\nLast: {fmt_price(closes[-1]) if closes else '—'}"
                return r.content, caption
    except Exception:
        pass

    return None, "❌ Could not generate chart image."


# ── /rizeby traderize / tradecc ───────────────────────────────────────────────

async def cmd_traderize(args: list[str]) -> str:
    return await _cmd_trade(RIZE_ID, "RIZE")

async def cmd_tradecc(args: list[str]) -> str:
    return await _cmd_trade("canton-network", "CC")

async def _cmd_trade(coin_id: str, symbol: str) -> str:
    tickers = await get_tickers(coin_id)
    if not tickers:
        return f"❌ Could not fetch trading pairs for {symbol}."

    by_exchange: dict[str, list] = {}
    for t in tickers:
        ex  = t.get("market", {}).get("name", "Unknown")
        vol = t.get("converted_volume", {}).get("usd", 0) or 0
        pair = f"{t.get('base','')}/{t.get('target','')}"
        by_exchange.setdefault(ex, []).append({"pair": pair, "vol": vol})

    ex_ranked = sorted(by_exchange.items(), key=lambda x: sum(p["vol"] for p in x[1]), reverse=True)

    lines = [f"🔄 *{symbol} Trading Pairs*", ""]
    for ex_name, pairs in ex_ranked[:8]:
        pairs_sorted = sorted(pairs, key=lambda p: p["vol"], reverse=True)
        pairs_str    = " · ".join(p["pair"] for p in pairs_sorted[:4])
        top_vol      = fmt_usd(pairs_sorted[0]["vol"])
        lines.append(f"*{ex_name}*: {pairs_str}")
        lines.append(f"  Vol: {top_vol}/24h")

    all_pairs = sorted(
        [{"ex": ex, **p} for ex, pairs in by_exchange.items() for p in pairs],
        key=lambda x: x["vol"], reverse=True,
    )
    if all_pairs:
        lines += ["", "🏆 *Top volume pairs:*"]
        for p in all_pairs[:2]:
            lines.append(f"  {p['ex']} — {p['pair']} · {fmt_usd(p['vol'])}/24h")

    return "\n".join(lines)
