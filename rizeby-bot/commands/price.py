"""
Commands: /price, /chart, /tvl, /traderize, /trade{ticker}
Any coin supported.
"""
import httpx
from utils.coingecko import (
    get_coin_detail, get_tickers, cg_get, get_kraken_pair,
    parse_base_and_compare, display_name, RIZE_ID, COIN_MAP
)
from utils.github_data import get_mcap_history
from utils.formatters import fmt_usd, fmt_pct, fmt_price, fmt_num


async def cmd_price(args: list) -> tuple:
    base_id, _ = parse_base_and_compare(args)
    coin_name = display_name(base_id)
    data = await get_coin_detail(base_id)
    if not data:
        return f"❌ Could not fetch {coin_name} price.", {}
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
    sym = data.get("symbol", "").upper() or coin_name

    tvl_str = None
    if base_id == RIZE_ID:
        history = await get_mcap_history()
        if history and isinstance(history, dict):
            series = history.get("series", [])
            if series:
                tvl = series[-1].get("tvl")
                if tvl:
                    tvl_str = fmt_usd(tvl)

    pct_to_ath = ((ath / price_usd) - 1) * 100 if price_usd and ath else None

    def arrow(v):
        if v is None: return "—"
        return f"{'📈' if v > 0 else '📉'} {fmt_pct(v)}"

    lines = [
        f"*{coin_name}* — ${sym}",
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
    if tvl_str:
        lines.append(f"TVL: {tvl_str}")

    markup = {"inline_keyboard": [[
        {"text": "🔄 Refresh", "callback_data": f"price_{base_id}"}
    ]]}
    return "\n".join(lines), markup


async def cmd_tvl(args: list) -> str:
    import asyncio as _asyncio
    # Parallel fetch: mcap-history for TVL + CoinGecko for live price/mcap/fdv
    history_coro = get_mcap_history()
    cg_coro      = get_coin_detail(RIZE_ID)
    history, price_data = await _asyncio.gather(history_coro, cg_coro)

    # TVL from mcap-history.json
    tvl  = None
    date = ""
    if history:
        if isinstance(history, dict):
            series = history.get("series", [])
        elif isinstance(history, list):
            series = history
        else:
            series = []
        if series:
            latest = series[-1]
            tvl  = latest.get("tvl") or latest.get("TVL")
            date = latest.get("date", "")

    # Live price, mcap, fdv from CoinGecko
    live_price = live_mcap = live_fdv = None
    if price_data:
        md = price_data.get("market_data", {})
        live_price = md.get("current_price", {}).get("usd")
        live_mcap  = md.get("market_cap", {}).get("usd")
        live_fdv   = md.get("fully_diluted_valuation", {}).get("usd")

    # Compute ratios locally
    mcap_tvl = (live_mcap / tvl) if (live_mcap and tvl and tvl > 0) else None
    fdv_tvl  = (live_fdv  / tvl) if (live_fdv  and tvl and tvl > 0) else None

    def valuation(ratio):
        if not ratio: return ""
        if ratio < 0.5:  return "🟢 Undervalued"
        if ratio < 1.0:  return "🟡 Fair"
        if ratio < 2.0:  return "🟠 Overvalued"
        return "🔴 Highly Overvalued"

    lines = [
        "📊 *RIZE MCap & TVL*",
        f"_TVL as of {date}_" if date else "_TVL data_",
        "",
        f"💰 Price:    {fmt_price(live_price) if live_price else '—'}",
        f"MCap:        {fmt_usd(live_mcap) if live_mcap else '—'}",
        f"FDV:         {fmt_usd(live_fdv) if live_fdv else '—'}",
        f"TVL:         {fmt_usd(tvl) if tvl else '—'}",
        "",
        f"MCap/TVL:    {f'{mcap_tvl:.2f}x' if mcap_tvl else '—'} {valuation(mcap_tvl)}",
        f"FDV/TVL:     {f'{fdv_tvl:.2f}x' if fdv_tvl else '—'} {valuation(fdv_tvl)}",
    ]
    return "\n".join(lines)


async def cmd_chart(args: list) -> tuple:
    base_id, remaining = parse_base_and_compare(args)
    coin_name = display_name(base_id)

    interval_key = "1d"
    for a in remaining:
        al = a.lower()
        if al in KRAKEN_INTERVALS:
            interval_key = al
            break
    interval_min = KRAKEN_INTERVALS.get(interval_key, 1440)

    pair = get_kraken_pair(base_id)
    if not pair:
        return None, f"❌ No Kraken chart available for {coin_name}."

    url = f"https://api.kraken.com/0/public/OHLC?pair={pair}&interval={interval_min}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url)
            data = r.json()
    except Exception:
        return None, "❌ Could not fetch chart data from Kraken."

    if data.get("error") and data["error"]:
        return None, f"❌ Kraken: {data['error']}"

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
                "borderWidth": 2, "pointRadius": 0, "fill": True, "tension": 0.3,
            }]
        },
        "options": {
            "plugins": {
                "legend": {"labels": {"color": "#ffffff"}},
                "title": {"display": True, "text": f"{coin_name}/USD — {interval_key} (Kraken)", "color": "#ffffff", "font": {"size": 16}}
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
    return None, "❌ Could not generate chart."


async def cmd_traderize(args: list) -> str:
    return await _cmd_trade(RIZE_ID, "RIZE")

async def cmd_tradecc(args: list) -> str:
    return await _cmd_trade("canton-network", "CC")

async def cmd_trade_any(ticker: str) -> str:
    """Generic /trade{ticker} for any coin."""
    ticker_lower = ticker.lower().strip()
    from utils.coingecko import COIN_MAP, display_name as dn
    coin_id = COIN_MAP.get(ticker_lower)
    if not coin_id:
        # Try search
        data = await cg_get("/search", {"query": ticker_lower})
        if data and data.get("coins"):
            coin_id = data["coins"][0]["id"]
        else:
            return f"❌ Could not find trading pairs for `{ticker}`."
    sym = dn(coin_id, ticker)
    return await _cmd_trade(coin_id, sym)

async def _cmd_trade(coin_id: str, symbol: str) -> str:
    tickers = await get_tickers(coin_id)
    if not tickers:
        return f"❌ Could not fetch trading pairs for {symbol}."

    by_exchange: dict = {}
    for t in tickers:
        ex   = t.get("market", {}).get("name", "Unknown")
        vol  = t.get("converted_volume", {}).get("usd", 0) or 0
        base = t.get("base", "")
        tgt  = t.get("target", "")
        pair = f"{base}/{tgt}"
        by_exchange.setdefault(ex, []).append({"pair": pair, "vol": vol})

    ex_ranked = sorted(by_exchange.items(), key=lambda x: sum(p["vol"] for p in x[1]), reverse=True)

    # Filter out DEX contract addresses (0x...) from exchange names
    DEX_SKIP = {"0x", "pancake", "aerodrome", "uniswap v", "curve", "balancer"}

    lines = [f"🔄 *{symbol} Trading Pairs*", ""]
    shown = 0
    for ex_name, pairs in ex_ranked:
        if shown >= 8: break
        # Skip DEX exchanges with contract-style names
        name_lower = ex_name.lower()
        if ex_name.startswith("0x") or any(s in name_lower for s in DEX_SKIP):
            continue
        pairs_sorted = sorted(pairs, key=lambda p: p["vol"], reverse=True)
        pairs_str    = " · ".join(p["pair"] for p in pairs_sorted[:4])
        top_vol      = fmt_usd(pairs_sorted[0]["vol"])
        lines.append(f"*{ex_name}*: {pairs_str}")
        lines.append(f"  Vol: {top_vol}/24h")
        shown += 1

    all_pairs = sorted(
        [{"ex": ex, **p} for ex, pairs in by_exchange.items() for p in pairs],
        key=lambda x: x["vol"], reverse=True,
    )
    if all_pairs:
        # Filter top 2 from non-DEX exchanges
        filtered_top = [p for p in all_pairs if not p["ex"].startswith("0x") and
                        not any(s in p["ex"].lower() for s in DEX_SKIP)]
        if filtered_top:
            lines += ["", "🏆 *Top volume pairs:*"]
            for p in filtered_top[:2]:
                lines.append(f"  {p['ex']} — {p['pair']} · {fmt_usd(p['vol'])}/24h")

    return "\n".join(lines)
