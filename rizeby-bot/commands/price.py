"""
Commands: /price, /chart, /tvl, /traderize, /trade{ticker}
Any coin supported — fully dynamic via CoinGecko search.
"""
import httpx
from utils.coingecko import (
    get_coin_detail, get_tickers, cg_get,
    parse_base_and_compare, display_name, resolve_coin_id, search_coin,
    get_tv_symbol, RIZE_ID,
)
from utils.github_data import get_mcap_history
from utils.formatters import fmt_usd, fmt_pct, fmt_price, fmt_num


async def cmd_price(args: list) -> tuple:
    if not args:
        coin_id   = RIZE_ID
        coin_name = "RIZE"
    else:
        coin_id = await resolve_coin_id(args[0])
        if not coin_id:
            return f"❌ Could not find coin `{args[0]}` on CoinGecko.", {}
        coin_name = args[0].upper()

    data = await get_coin_detail(coin_id)
    if not data:
        return f"❌ Could not fetch price for `{coin_name}`.", {}

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
    rank      = data.get("market_cap_rank")
    sym       = data.get("symbol", "").upper() or coin_name

    tvl_str = None
    if coin_id == RIZE_ID:
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
        f"*{data.get('name', coin_name)}* — ${sym}" + (f" · Rank #{rank}" if rank else ""),
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
        {"text": "🔄 Refresh", "callback_data": f"price_{coin_id}"}
    ]]}
    return "\n".join(lines), markup


async def cmd_tvl(args: list) -> str:
    import asyncio as _asyncio
    history_coro = get_mcap_history()
    cg_coro      = get_coin_detail(RIZE_ID)
    history, price_data = await _asyncio.gather(history_coro, cg_coro)

    tvl = None; date = ""
    if history:
        series = history.get("series", []) if isinstance(history, dict) else history if isinstance(history, list) else []
        if series:
            latest = series[-1]
            tvl  = latest.get("tvl") or latest.get("TVL")
            date = latest.get("date", "")

    live_price = live_mcap = live_fdv = None
    if price_data:
        md = price_data.get("market_data", {})
        live_price = md.get("current_price", {}).get("usd")
        live_mcap  = md.get("market_cap", {}).get("usd")
        live_fdv   = md.get("fully_diluted_valuation", {}).get("usd")

    mcap_tvl = (live_mcap / tvl) if (live_mcap and tvl and tvl > 0) else None
    fdv_tvl  = (live_fdv  / tvl) if (live_fdv  and tvl and tvl > 0) else None

    def valuation(ratio):
        if not ratio: return ""
        if ratio < 0.95: return "🟢 Undervalued"
        if ratio <= 1.05: return "🟡 Fair"
        if ratio < 2.0:  return "🟠 Overvalued"
        return "🔴 Highly Overvalued"

    return "\n".join([
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
    ])


async def cmd_chart(args: list) -> tuple:
    import os
    if not args:
        coin_id   = RIZE_ID
        coin_name = "RIZE"
        remaining = []
    else:
        INTERVALS = {"15m","1h","4h","1d","1w","1m","3m","5m","30m","45m","2h","3h"}
        # First arg that is NOT an interval = ticker
        ticker_arg = None
        remaining  = []
        for i, a in enumerate(args):
            if a.lower() in INTERVALS:
                remaining = args[i:]
                break
            elif ticker_arg is None:
                ticker_arg = a
            else:
                remaining.append(a)

        if ticker_arg:
            coin_id = await resolve_coin_id(ticker_arg)
            if not coin_id:
                return None, f"❌ Could not find `{ticker_arg}` on CoinGecko."
            coin_name = ticker_arg.upper()
        else:
            coin_id   = RIZE_ID
            coin_name = "RIZE"

    CHARTIMG_INTERVALS = {"15m":"15m","1h":"1h","4h":"4h","1d":"1D","1w":"1W","1m":"1M"}
    interval_key = "1d"
    for a in remaining:
        al = a.lower()
        if al in CHARTIMG_INTERVALS:
            interval_key = al
            break
    tv_interval = CHARTIMG_INTERVALS.get(interval_key, "1D")

    # Resolve TradingView symbol dynamically (tickers → TV search → fallback)
    detail = await get_coin_detail(coin_id)
    sym = detail.get("symbol", coin_name).upper() if detail else coin_name.upper()
    tv_symbol = await get_tv_symbol(coin_id, sym)

    api_key = os.environ.get("CHARTIMG_KEY", "")
    if not api_key:
        return None, "Chart API key not configured."

    try:
        from urllib.parse import urlencode
        base_params = {
            "symbol": tv_symbol, "interval": tv_interval,
            "theme": "dark", "style": "candle", "width": 800, "height": 500,
        }
        query = urlencode(list(base_params.items()) + [("studies", "BB")])
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"https://api.chart-img.com/v1/tradingview/advanced-chart?{query}",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
                return r.content, f"📊 {coin_name} — {interval_key.upper()} (TradingView)"
            try:
                err = r.json()
                msg = err.get("error") or err.get("message") or str(r.status_code)
            except Exception:
                msg = str(r.status_code)
            return None, f"Chart error: {msg}"
    except Exception as e:
        return None, f"Could not generate chart: {e}"


async def cmd_traderize(args: list) -> str:
    return await _cmd_trade(RIZE_ID, "RIZE")

async def cmd_tradecc(args: list) -> str:
    coin_id = await resolve_coin_id("canton-network")
    return await _cmd_trade(coin_id or "canton-network", "CC")

async def cmd_trade_any(ticker: str) -> str:
    coin_id = await resolve_coin_id(ticker)
    if not coin_id:
        return f"❌ Could not find trading pairs for `{ticker}`."
    match = await search_coin(ticker)
    sym = match["symbol"] if match else ticker.upper()
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
        by_exchange.setdefault(ex, []).append({"pair": f"{base}/{tgt}", "vol": vol})

    ex_ranked = sorted(by_exchange.items(), key=lambda x: sum(p["vol"] for p in x[1]), reverse=True)
    DEX_SKIP  = {"0x", "pancake", "aerodrome", "uniswap v", "curve", "balancer"}

    lines = [f"🔄 *{symbol} Trading Pairs*", ""]
    shown = 0
    for ex_name, pairs in ex_ranked:
        if shown >= 8: break
        name_lower = ex_name.lower()
        if ex_name.startswith("0x") or any(s in name_lower for s in DEX_SKIP):
            continue
        pairs_sorted = sorted(pairs, key=lambda p: p["vol"], reverse=True)
        lines.append(f"*{ex_name}*: {' · '.join(p['pair'] for p in pairs_sorted[:4])}")
        lines.append(f"  Vol: {fmt_usd(pairs_sorted[0]['vol'])}/24h")
        shown += 1

    all_pairs = sorted(
        [{"ex": ex, **p} for ex, pairs in by_exchange.items() for p in pairs],
        key=lambda x: x["vol"], reverse=True,
    )
    filtered = [p for p in all_pairs if not p["ex"].startswith("0x")
                and not any(s in p["ex"].lower() for s in DEX_SKIP)]
    if filtered:
        lines += ["", "🏆 *Top volume pairs:*"]
        for p in filtered[:2]:
            lines.append(f"  {p['ex']} — {p['pair']} · {fmt_usd(p['vol'])}/24h")

    return "\n".join(lines)
    
