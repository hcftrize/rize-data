"""CoinGecko API wrapper — fully dynamic, no hardcoded coin maps."""
import os
import httpx

CG_BASE = "https://api.coingecko.com/api/v3"
CG_KEY  = os.environ.get("COINGECKO_API_KEY", "")

HEADERS = {
    "accept": "application/json",
    "x-cg-demo-api-key": CG_KEY,
}

RIZE_ID     = "rize"
RIZE_SUPPLY = 5_000_000_000

# Small cache for search results to avoid redundant API calls within a request
_search_cache: dict = {}


async def cg_get(path: str, params: dict = None) -> dict | list | None:
    url = CG_BASE + path
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, headers=HEADERS, params=params or {})
            r.raise_for_status()
            return r.json()
    except Exception:
        return None


async def search_coin(query: str) -> dict | None:
    """Search CoinGecko and return the best match {id, symbol, name} or None."""
    q = query.lower().strip()
    if q in _search_cache:
        return _search_cache[q]

    # Special case: RIZE always resolves to "rize"
    if q == "rize":
        result = {"id": "rize", "symbol": "RIZE", "name": "RIZE"}
        _search_cache[q] = result
        return result

    data = await cg_get("/search", {"query": q})
    if not data or not data.get("coins"):
        _search_cache[q] = None
        return None

    coins = data["coins"]
    # Prefer exact symbol match first, then exact name match, then first result
    best = None
    for coin in coins:
        if coin.get("symbol", "").lower() == q:
            best = coin
            break
    if not best:
        for coin in coins:
            if coin.get("name", "").lower() == q:
                best = coin
                break
    if not best:
        best = coins[0]

    result = {
        "id":     best["id"],
        "symbol": best.get("symbol", "").upper(),
        "name":   best.get("name", best["id"]),
    }
    _search_cache[q] = result
    return result


async def resolve_coin_id(token: str) -> str | None:
    """Resolve a ticker/name string to a CoinGecko coin ID."""
    match = await search_coin(token)
    return match["id"] if match else None


async def resolve_coin_ids(tokens: list[str]) -> dict[str, str]:
    """Resolve multiple tokens to {original: coin_id}."""
    result = {}
    for t in tokens:
        coin_id = await resolve_coin_id(t)
        if coin_id:
            result[t] = coin_id
    return result


def display_name(coin_id: str, original: str = "") -> str:
    """Return display name: use original ticker uppercased, fallback to coin_id."""
    if original:
        return original.upper()
    # Use cached search result if available
    cached = _search_cache.get(coin_id.lower())
    if cached and cached.get("symbol"):
        return cached["symbol"].upper()
    return coin_id.upper()[:10]


async def parse_base_and_compare(args: list[str]) -> tuple[str, list[str]]:
    """
    Fully dynamic: resolves first arg via live CoinGecko search.
    If it resolves to a coin != RIZE, it's the base.
    Otherwise RIZE is the base.
    Returns (base_coin_id, compare_tokens).
    """
    if not args:
        return RIZE_ID, []

    first = args[0].strip()

    # Numeric = amount, not a base override
    clean = first.replace(".", "").replace(",", "").replace(" ", "").rstrip("mkb")
    if clean.isdigit():
        return RIZE_ID, args

    # Try to resolve first arg as a coin
    coin_id = await resolve_coin_id(first)
    if coin_id and coin_id != RIZE_ID:
        # Cache display name
        if first.lower() not in _search_cache:
            pass  # already cached by resolve_coin_id → search_coin
        return coin_id, args[1:]

    return RIZE_ID, args


async def get_markets(coin_ids: list[str]) -> list | None:
    return await cg_get("/coins/markets", {
        "vs_currency": "usd", "ids": ",".join(coin_ids),
        "price_change_percentage": "1h,7d,30d,90d",
        "order": "market_cap_desc", "per_page": 50, "page": 1,
    })


async def get_coin_detail(coin_id: str) -> dict | None:
    return await cg_get(f"/coins/{coin_id}", {
        "localization": "false", "tickers": "false", "market_data": "true",
        "community_data": "false", "developer_data": "false",
    })


async def get_market_chart(coin_id: str, days: int = 90) -> dict | None:
    return await cg_get(f"/coins/{coin_id}/market_chart",
                        {"vs_currency": "usd", "days": days, "interval": "daily"})


async def get_global() -> dict | None:
    return await cg_get("/global")


async def get_tickers(coin_id: str) -> list | None:
    data = await cg_get(f"/coins/{coin_id}/tickers",
                        {"include_exchange_logo": "false", "order": "volume_desc", "depth": "false"})
    return data.get("tickers") if data else None


async def get_simple_price(coin_ids: list[str]) -> dict | None:
    return await cg_get("/simple/price", {
        "ids": ",".join(coin_ids), "vs_currencies": "usd,btc,eth",
        "include_market_cap": "true", "include_24hr_vol": "true", "include_24hr_change": "true",
    })
