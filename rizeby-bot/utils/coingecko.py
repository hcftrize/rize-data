"""CoinGecko API wrapper — supports any base asset, not just RIZE."""
import os
import httpx

CG_BASE = "https://api.coingecko.com/api/v3"
CG_KEY  = os.environ.get("COINGECKO_API_KEY", "")

HEADERS = {
    "accept": "application/json",
    "x-cg-demo-api-key": CG_KEY,
}

COIN_MAP = {
    "rize":"rize","btc":"bitcoin","bitcoin":"bitcoin","eth":"ethereum",
    "ethereum":"ethereum","link":"chainlink","chainlink":"chainlink",
    "mantra":"mantra-dao","om":"mantra-dao","ondo":"ondo-finance",
    "cc":"canton-network","canton":"canton-network","sol":"solana",
    "solana":"solana","avax":"avalanche-2","avalanche":"avalanche-2",
    "matic":"matic-network","pol":"matic-network","dot":"polkadot",
    "ada":"cardano","cardano":"cardano","atom":"cosmos","near":"near",
    "apt":"aptos","sui":"sui","arb":"arbitrum","op":"optimism",
    "inj":"injective-protocol","sei":"sei-network","uni":"uniswap",
    "aave":"aave","mkr":"maker","snx":"havven","comp":"compound-governance-token",
    "ldo":"lido-dao","crv":"curve-dao-token","pendle":"pendle",
    "eigen":"eigenlayer","trx":"tron","ton":"the-open-network",
    "doge":"dogecoin","shib":"shiba-inu","pepe":"pepe","ltc":"litecoin",
    "xrp":"ripple","bnb":"binancecoin","xlm":"stellar",
}

DISPLAY_MAP = {
    "rize":"RIZE","canton-network":"CC","mantra-dao":"MANTRA",
    "avalanche-2":"AVAX","matic-network":"POL","injective-protocol":"INJ",
    "sei-network":"SEI","compound-governance-token":"COMP","lido-dao":"LDO",
    "curve-dao-token":"CRV","the-open-network":"TON","binancecoin":"BNB",
    "bitcoin":"BTC","ethereum":"ETH","chainlink":"LINK","ondo-finance":"ONDO",
    "solana":"SOL","polkadot":"DOT","cardano":"ADA","cosmos":"ATOM",
    "near":"NEAR","aptos":"APT","sui":"SUI","arbitrum":"ARB",
    "optimism":"OP","uniswap":"UNI","aave":"AAVE","maker":"MKR",
    "havven":"SNX","pendle":"PENDLE","eigenlayer":"EIGEN","tron":"TRX",
    "dogecoin":"DOGE","shiba-inu":"SHIB","pepe":"PEPE","litecoin":"LTC",
    "ripple":"XRP","stellar":"XLM","ondo-finance":"ONDO",
}

KRAKEN_PAIRS = {
    "rize":"RIZEUSD","bitcoin":"XBTUSD","ethereum":"ETHUSD",
    "chainlink":"LINKUSD","solana":"SOLUSD","avalanche-2":"AVAXUSD",
    "polkadot":"DOTUSD","cardano":"ADAUSD","cosmos":"ATOMUSD",
    "litecoin":"LTCUSD","ripple":"XRPUSD","dogecoin":"XDGUSD",
    "uniswap":"UNIUSD","aave":"AAVEUSD","canton-network":"CCUSD",
}

RIZE_ID = "rize"
RIZE_SUPPLY = 5_000_000_000


async def cg_get(path: str, params: dict = None) -> dict | list | None:
    url = CG_BASE + path
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, headers=HEADERS, params=params or {})
            r.raise_for_status()
            return r.json()
    except Exception:
        return None


async def resolve_coin_ids(tokens: list[str]) -> dict[str, str]:
    result = {}
    unknown = []
    for t in tokens:
        tl = t.lower().strip()
        if tl in COIN_MAP:
            result[tl] = COIN_MAP[tl]
        else:
            unknown.append(tl)
    for t in unknown:
        data = await cg_get("/search", {"query": t})
        if data and data.get("coins"):
            result[t] = data["coins"][0]["id"]
    return result


def display_name(coin_id: str, original: str = "") -> str:
    return DISPLAY_MAP.get(coin_id, original.upper() if original else coin_id.upper()[:8])


def parse_base_and_compare(args: list[str]) -> tuple[str, list[str]]:
    """
    If first token is a known coin != RIZE, use it as base asset.
    Otherwise RIZE is the base.
    Returns (base_coin_id, compare_tokens).
    """
    if not args:
        return RIZE_ID, []
    first = args[0].lower().strip()
    # Numeric = not a base override
    clean = first.replace(".","").replace(",","").replace(" ","").rstrip("mkb")
    if clean.isdigit():
        return RIZE_ID, args
    if first in COIN_MAP and COIN_MAP[first] != RIZE_ID:
        return COIN_MAP[first], args[1:]
    return RIZE_ID, args


async def get_markets(coin_ids: list[str]) -> list | None:
    return await cg_get("/coins/markets", {
        "vs_currency":"usd","ids":",".join(coin_ids),
        "price_change_percentage":"1h,7d,30d,90d",
        "order":"market_cap_desc","per_page":50,"page":1,
    })


async def get_coin_detail(coin_id: str) -> dict | None:
    return await cg_get(f"/coins/{coin_id}", {
        "localization":"false","tickers":"false","market_data":"true",
        "community_data":"false","developer_data":"false",
    })


async def get_market_chart(coin_id: str, days: int = 90) -> dict | None:
    return await cg_get(f"/coins/{coin_id}/market_chart",
        {"vs_currency":"usd","days":days,"interval":"daily"})


async def get_global() -> dict | None:
    return await cg_get("/global")


async def get_tickers(coin_id: str) -> list | None:
    data = await cg_get(f"/coins/{coin_id}/tickers",
        {"include_exchange_logo":"false","order":"volume_desc","depth":"false"})
    return data.get("tickers") if data else None


async def get_simple_price(coin_ids: list[str]) -> dict | None:
    return await cg_get("/simple/price", {
        "ids":",".join(coin_ids),"vs_currencies":"usd,btc,eth",
        "include_market_cap":"true","include_24hr_vol":"true","include_24hr_change":"true",
    })


def get_kraken_pair(coin_id: str) -> str | None:
    return KRAKEN_PAIRS.get(coin_id)
