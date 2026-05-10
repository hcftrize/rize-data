"""
RizeBy Telegram Bot — Vercel Serverless Webhook Handler
File location in repo: api/rizeby/telegram.py
"""
import json, os, asyncio, sys, httpx, time
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'rizeby-bot'))

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TG_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# ── Pagination state (in-memory, per cold start) ──────────────────────────────
# Maps chat_id → {cmd, page, args, ts}
_pagination: dict = {}
PAGE_TTL = 300  # 5 min


def _set_page(chat_id: int, cmd: str, page: int, args: list):
    _pagination[chat_id] = {"cmd": cmd, "page": page, "args": args, "ts": time.time()}


def _get_page(chat_id: int):
    state = _pagination.get(chat_id)
    if state and (time.time() - state["ts"]) < PAGE_TTL:
        return state
    return None


async def route_command(cmd: str, args: list, chat_id: int, message_id: int = 0) -> None:
    cmd_lower = cmd.lower().strip()

    # ── "next" reply — advance pagination ─────────────────────────────────
    if cmd_lower in ("next", "/next"):
        state = _get_page(chat_id)
        if not state:
            await send_message(chat_id, "No active list to paginate. Run a command first.")
            return
        next_page = state["page"] + 1
        _set_page(chat_id, state["cmd"], next_page, state["args"])
        await route_command(state["cmd"], state["args"], chat_id, message_id)
        return

    # ── CC sub-commands ────────────────────────────────────────────────────
    if cmd_lower in ("cc", "ccprice"):
        from commands.cc import cmd_cc_price
        await send_message(chat_id, await cmd_cc_price(args))
        return
    if cmd_lower in ("ccburnmint", "ccburn", "ccmint"):
        from commands.cc import cmd_cc_burnmint
        await send_message(chat_id, await cmd_cc_burnmint(args))
        return
    if cmd_lower in ("ccallocation", "ccalloc"):
        from commands.cc import cmd_cc_allocation
        await send_message(chat_id, await cmd_cc_allocation(args))
        return

    # ── Price & market ─────────────────────────────────────────────────────
    if cmd_lower in ("price", "p"):
        from commands.price import cmd_price
        text, markup = await cmd_price(args)
        await send_message(chat_id, text, markup)

    elif cmd_lower in ("chart", "c"):
        from commands.price import cmd_chart
        img, caption = await cmd_chart(args)
        if img:
            await send_photo(chat_id, img, caption)
        else:
            await send_message(chat_id, caption)

    elif cmd_lower == "tvl":
        from commands.price import cmd_tvl
        await send_message(chat_id, await cmd_tvl(args))

    elif cmd_lower in ("perf", "performance"):
        from commands.market import cmd_perf
        await send_message(chat_id, await cmd_perf(args))

    elif cmd_lower in ("pricesim", "ps"):
        from commands.market import cmd_pricesim
        await send_message(chat_id, await cmd_pricesim(args))

    elif cmd_lower in ("portfoliosim", "portfolio", "bag"):
        from commands.market import cmd_portfoliosim
        await send_message(chat_id, await cmd_portfoliosim(args))

    elif cmd_lower in ("arbitrage", "ratio", "arb"):
        from commands.market import cmd_arbitrage
        await send_message(chat_id, await cmd_arbitrage(args))

    elif cmd_lower in ("market", "mkt"):
        from commands.market import cmd_market
        await send_message(chat_id, await cmd_market(args))

    elif cmd_lower in ("unbond", "queue"):
        from commands.rize import cmd_unbond
        await send_message(chat_id, await cmd_unbond(args))

    elif cmd_lower in ("totalbonded", "bonded"):
        from commands.rize import cmd_totalbonded
        await send_message(chat_id, await cmd_totalbonded(args))

    elif cmd_lower in ("traderize", "trade"):
        from commands.price import cmd_traderize
        await send_message(chat_id, await cmd_traderize(args))

    elif cmd_lower in ("tradecc",):
        from commands.price import cmd_tradecc
        await send_message(chat_id, await cmd_tradecc(args))

    elif cmd_lower.startswith("trade") and len(cmd_lower) > 5:
        from commands.price import cmd_trade_any
        await send_message(chat_id, await cmd_trade_any(cmd_lower[5:]))

    # ── Ecosystem ──────────────────────────────────────────────────────────
    elif cmd_lower == "rwa":
        from commands.ecosystem import cmd_rwa
        await send_message(chat_id, await cmd_rwa(args))

    elif cmd_lower in ("vision87", "v87"):
        from commands.ecosystem import cmd_vision87
        await send_message(chat_id, await cmd_vision87(args))

    elif cmd_lower in ("vision60", "v60"):
        from commands.ecosystem import cmd_vision60
        await send_message(chat_id, await cmd_vision60(args))

    elif cmd_lower == "kairos":
        from commands.ecosystem import cmd_kairos
        await send_message(chat_id, await cmd_kairos(args))

    elif cmd_lower == "cantonboard":
        from commands.ecosystem import cmd_cantonboard
        await send_message(chat_id, await cmd_cantonboard(args))

    elif cmd_lower == "cantonlist":
        page = _get_page(chat_id)
        p = (page["page"] if page and page["cmd"] == "cantonlist" else 0)
        _set_page(chat_id, "cantonlist", p, args)
        await _cmd_cantonlist(chat_id, p)

    elif cmd_lower.startswith("ecosystem"):
        from commands.ecosystem import cmd_ecosystem
        parts = cmd_lower[len("ecosystem"):].strip().split() + args
        await send_message(chat_id, await cmd_ecosystem([a for a in parts if a]))

    elif cmd_lower.startswith("canton") and cmd_lower not in ("cantongov", "cantonboard", "cantonlist"):
        from commands.ecosystem import cmd_canton
        parts = cmd_lower[len("canton"):].strip().split() + args
        await send_message(chat_id, await cmd_canton([a for a in parts if a]))

    # ── Canton governance ──────────────────────────────────────────────────
    elif cmd_lower.startswith("cip"):
        from commands.canton_gov import cmd_cip
        cip_args = cmd_lower[3:].strip().split() + args
        cip_args = [a for a in cip_args if a]
        if not cip_args:
            # Paginated list
            page = _get_page(chat_id)
            p = (page["page"] if page and page["cmd"] == "cip" else 0)
            _set_page(chat_id, "cip", p, [])
            await send_message(chat_id, await cmd_cip([], page=p))
        else:
            await send_message(chat_id, await cmd_cip(cip_args))

    elif cmd_lower in ("cantongov", "cgov"):
        from commands.canton_gov import cmd_cantongov
        page = _get_page(chat_id)
        p = (page["page"] if page and page["cmd"] == "cantongov" else 0)
        _set_page(chat_id, "cantongov", p, args)
        await send_message(chat_id, await cmd_cantongov(args, page=p))

    # ── Governance hub ─────────────────────────────────────────────────────
    elif cmd_lower in ("govflows", "flows"):
        from commands.governance import cmd_govflows
        page = _get_page(chat_id)
        p = (page["page"] if page and page["cmd"] == "govflows" else 0)
        _set_page(chat_id, "govflows", p, args)
        await send_message(chat_id, await cmd_govflows(args, page=p))

    elif cmd_lower in ("govwhalealert", "whales", "whale"):
        from commands.governance import cmd_govwhalealert
        page = _get_page(chat_id)
        p = (page["page"] if page and page["cmd"] == "govwhalealert" else 0)
        _set_page(chat_id, "govwhalealert", p, args)
        await send_message(chat_id, await cmd_govwhalealert(args, page=p))

    elif cmd_lower.startswith("govbond") or cmd_lower.startswith("govwallet"):
        from commands.governance import cmd_govwallet
        query = cmd_lower.replace("govbond","").replace("govwallet","").strip()
        combined = ([query] if query else []) + args
        await send_message(chat_id, await cmd_govwallet(combined))

    # ── Fun ────────────────────────────────────────────────────────────────
    elif cmd_lower in ("sayhello", "hello", "hi", "start"):
        from commands.fun import cmd_sayhello
        await send_message(chat_id, await cmd_sayhello(args))

    elif cmd_lower in ("insult", "roast"):
        from commands.fun import cmd_insult
        await send_message(chat_id, await cmd_insult(args))

    elif cmd_lower in ("help", "commands", ""):
        await send_message(chat_id, HELP_TEXT)

    else:
        # Bonus hidden: /name or /entity lookups
        from commands.ecosystem import lookup_any
        result = await lookup_any(cmd_lower + (" " + " ".join(args) if args else ""))
        if result:
            await send_message(chat_id, result)
        else:
            await send_message(chat_id, f"Unknown command: `{cmd}`\n\nType `/help` to see all commands.")


async def _cmd_cantonlist(chat_id: int, page: int):
    """Paginated list of all Canton entities."""
    from utils.github_data import get_entities
    entities = await get_entities()
    if not entities:
        await send_message(chat_id, "Could not load Canton entities.")
        return
    per_page = 20
    start = page * per_page
    page_ents = entities[start:start + per_page]
    total = len(entities)
    total_pages = (total - 1) // per_page + 1

    lines = [
        f"🏛 *Canton Network — All Entities*",
        f"_Page {page+1}/{total_pages} · {total} entities_",
        "",
    ]
    for e in page_ents:
        name = e.get("name", "?")
        tags = e.get("tags", [])
        clean = [t for t in tags if isinstance(t, str) and len(t) < 40 and "\n" not in t and "Roles" not in t and "Network" not in t]
        tag_str = clean[0] if clean else ""
        lines.append(f"• *{name}*" + (f" — {tag_str}" if tag_str else ""))

    if start + per_page < total:
        lines += ["", "_Reply *next* to see more._"]

    await send_message(chat_id, "\n".join(lines))
    _set_page(chat_id, "cantonlist", page, [])


# ── Callback query handler (refresh button) ───────────────────────────────────

async def handle_callback(callback: dict) -> None:
    data    = callback.get("data", "")
    chat_id = callback["message"]["chat"]["id"]
    msg_id  = callback["message"]["message_id"]

    if data.startswith("price_"):
        coin_id = data[6:]
        from commands.price import cmd_price
        from utils.coingecko import COIN_MAP
        # Find the token key for this coin_id
        token = next((k for k, v in COIN_MAP.items() if v == coin_id), coin_id)
        text, markup = await cmd_price([token])
        await edit_message(chat_id, msg_id, text, markup)

    # Answer callback to remove loading state
    async with httpx.AsyncClient(timeout=5) as client:
        await client.post(f"{TG_API}/answerCallbackQuery",
                         json={"callback_query_id": callback["id"]})


HELP_TEXT = """
🤖 *RizeBy — Tokerize Intelligence Bot*

*Prices & Charts*
`/price` — RIZE price · `/price cc` `/price eth` — any coin
`/chart [15m|1h|4h|1d|1w|1M]` — OHLC chart
`/tvl` — TVL & MCap/TVL ratios
`/market` — BTC.D, Fear&Greed, Altcoin Season

*Analysis* — put coin first to change base asset
`/perf {assets}` — Performance 7D/30D/90D vs USD
`/pricesim {assets}` — If RIZE had each asset's mcap
`/portfoliosim {amount} {coin} to {assets}` — Bag sim
`/arbitrage {amount} {coin} to {assets}` — Ratio analysis

*On-Chain RIZE*
`/unbond` — Live unbonding queue (last 7 days)
`/totalbonded` — Live total RIZE bonded

*Trading Pairs*
`/traderize` · `/tradecc` · `/tradebtc` `/tradeeth` etc

*Canton Coin (CC)*
`/ccprice` · `/ccburnmint [1d|1w]` · `/ccallocation`

*T-RIZE Ecosystem*
`/ecosystem` — 21 T-RIZE partners
`/ecosystem {name}` — Partner deep-dive
`/canton {entity}` — Any of 290+ Canton entities
`/cantonlist` — Browse all 290+ Canton entities
`/cantonboard` — Canton Foundation board (17 members)
`/rwa` — T-RIZE RWA deals
`/vision87` · `/vision60` · `/kairos` — Deal details

*Canton Governance*
`/cip` — Latest CIPs (reply *next* for more)
`/cip {number}` — CIP detail (e.g. `/cip 0116`)
`/cantongov` — Active governance proposals

*Governance Hub*
`/govflows` — Monthly bond flows
`/govwhalealert [breaks|bond+increase|releases]`
`/govwallet {0x...}` — Wallet governance profile
`/govbond {#}` — Bond profile

*Fun*
`/sayhello` · `/insult`

_Reply *next* after any paginated list to see more._
""".strip()


# ── Telegram API helpers ──────────────────────────────────────────────────────

async def send_message(chat_id: int, text: str, reply_markup: dict = None) -> None:
    payload = {"chat_id": chat_id, "text": text,
               "parse_mode": "Markdown", "disable_web_page_preview": True}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(f"{TG_API}/sendMessage", json=payload)
    except Exception:
        pass


async def edit_message(chat_id: int, msg_id: int, text: str, reply_markup: dict = None) -> None:
    payload = {"chat_id": chat_id, "message_id": msg_id, "text": text,
               "parse_mode": "Markdown", "disable_web_page_preview": True}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(f"{TG_API}/editMessageText", json=payload)
    except Exception:
        pass


async def send_photo(chat_id: int, photo_bytes: bytes, caption: str = "") -> None:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                f"{TG_API}/sendPhoto",
                data={"chat_id": chat_id, "caption": caption, "parse_mode": "Markdown"},
                files={"photo": ("chart.png", photo_bytes, "image/png")},
            )
    except Exception:
        pass


def parse_update(body: dict):
    # Handle callback queries (button presses)
    if body.get("callback_query"):
        return "callback", body["callback_query"]

    msg = body.get("message") or body.get("edited_message")
    if not msg:
        return None, None
    chat_id = msg["chat"]["id"]
    msg_id  = msg.get("message_id", 0)
    text    = (msg.get("text") or "").strip()
    if not text:
        return None, None
    text  = text.split("@")[0] if "@" in text else text
    parts = text.split()
    if not parts:
        return None, None
    first = parts[0].lstrip("/").lower()

    # "next" as standalone reply
    if first == "next":
        return "cmd", (msg["chat"]["id"], "next", [], msg_id)

    if first == "rizeby":
        cmd  = parts[1].lower() if len(parts) > 1 else "help"
        args = parts[2:]
    else:
        cmd  = first
        args = parts[1:]

    return "cmd", (chat_id, cmd, list(args), msg_id)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body   = json.loads(self.rfile.read(length))
            kind, payload = parse_update(body)
            if kind == "callback":
                asyncio.run(handle_callback(payload))
            elif kind == "cmd":
                chat_id, cmd, args, msg_id = payload
                asyncio.run(route_command(cmd, args, chat_id, msg_id))
        except Exception:
            pass
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"RizeBy bot is running.")

    def log_message(self, format, *args):
        pass
