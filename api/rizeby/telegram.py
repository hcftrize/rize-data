"""
RizeBy Telegram Bot — Vercel Serverless Webhook Handler
File location in repo: api/rizeby/telegram.py
"""
import json, os, asyncio, sys, httpx, time
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'rizeby-bot'))

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TG_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# ── Pagination state ──────────────────────────────────────────────────────────
_pagination: dict = {}
PAGE_TTL = 600  # 10 min


def _set_page(chat_id: int, cmd: str, page: int, args: list):
    _pagination[chat_id] = {"cmd": cmd, "page": page, "args": args, "ts": time.time()}


def _get_page(chat_id: int):
    state = _pagination.get(chat_id)
    if state and (time.time() - state["ts"]) < PAGE_TTL:
        return state
    return None


def _next_page(chat_id: int):
    state = _get_page(chat_id)
    if state:
        state["page"] += 1
        state["ts"] = time.time()
        return state
    return None


async def route_command(cmd: str, args: list, chat_id: int, message_id: int = 0, thread_id: int = None) -> None:
    cmd_lower = cmd.lower().strip()

    # ── "next" reply ──────────────────────────────────────────────────────
    if cmd_lower in ("next",):
        state = _next_page(chat_id)
        if not state:
            await send_message(chat_id, "No active list to navigate. Run a command first.", thread_id=thread_id)
            return
        await route_command(state["cmd"], state["args"], chat_id, message_id, thread_id)
        return

    # ── "see wallet" reply after /govbond ────────────────────────────────
    if cmd_lower in ("see wallet", "seewallet") or " ".join([cmd_lower] + args).lower() == "see wallet":
        state = _get_page(chat_id)
        if state and state["cmd"] == "govbond_owner" and state["args"]:
            nft_id = state["args"][0].lstrip("#").strip()
            try:
                from utils.github_data import get_bond_states
                from commands.governance import _load_bs_parts, cmd_govwallet
                bs_raw = await get_bond_states()
                bond_states, _, _ = _load_bs_parts(bs_raw)
                state_data = (bond_states or {}).get(str(nft_id), {})
                owner = state_data.get("owner", "")
                if owner:
                    await send_message(chat_id, await cmd_govwallet([owner]), thread_id=thread_id)
                else:
                    await send_message(chat_id, f"Owner not found for bond #{nft_id}. Try `/govwallet 0x...`", thread_id=thread_id)
            except Exception:
                await send_message(chat_id, "Could not load wallet. Try `/govwallet 0x...` directly.", thread_id=thread_id)
        else:
            await send_message(chat_id, "Reply *see wallet* right after a `/govbond` result.", thread_id=thread_id)
        return

    # ── "page N" reply ────────────────────────────────────────────────────
    if cmd_lower.startswith("page") and args and args[0].isdigit():
        target = int(args[0]) - 1  # 0-indexed
        state = _get_page(chat_id)
        if state:
            state["page"] = target
            state["ts"] = time.time()
            await route_command(state["cmd"], state["args"], chat_id, message_id)
        else:
            await send_message(chat_id, "No active list to navigate.", thread_id=thread_id)
        return

    # ── CC sub-commands ───────────────────────────────────────────────────
    if cmd_lower in ("cc", "ccprice"):
        from commands.cc import cmd_cc_price
        await send_message(chat_id, await cmd_cc_price(args), thread_id=thread_id)
        return
    if cmd_lower in ("ccburnmint", "ccburn", "ccmint"):
        from commands.cc import cmd_cc_burnmint
        await send_message(chat_id, await cmd_cc_burnmint(args), thread_id=thread_id)
        return
    if cmd_lower in ("ccallocation", "ccalloc"):
        from commands.cc import cmd_cc_allocation
        await send_message(chat_id, await cmd_cc_allocation(args), thread_id=thread_id)
        return

    # ── Price & market ────────────────────────────────────────────────────
    if cmd_lower in ("price", "p"):
        from commands.price import cmd_price
        text, markup = await cmd_price(args)
        await send_message(chat_id, text, markup, thread_id=thread_id)

    elif cmd_lower in ("chart", "c"):
        from commands.price import cmd_chart
        img, caption = await cmd_chart(args)
        if img: await send_photo(chat_id, img, caption, thread_id=thread_id)
        else:   await send_message(chat_id, caption, thread_id=thread_id)

    elif cmd_lower == "tvl":
        from commands.price import cmd_tvl
        await send_message(chat_id, await cmd_tvl(args), thread_id=thread_id)

    elif cmd_lower in ("perf", "performance"):
        from commands.market import cmd_perf
        await send_message(chat_id, await cmd_perf(args), thread_id=thread_id)

    elif cmd_lower in ("pricesim", "ps"):
        from commands.market import cmd_pricesim
        await send_message(chat_id, await cmd_pricesim(args), thread_id=thread_id)

    elif cmd_lower in ("portfoliosim", "portfolio", "bag"):
        from commands.market import cmd_portfoliosim
        await send_message(chat_id, await cmd_portfoliosim(args), thread_id=thread_id)

    elif cmd_lower in ("arbitrage", "ratio", "arb"):
        from commands.market import cmd_arbitrage
        await send_message(chat_id, await cmd_arbitrage(args), thread_id=thread_id)

    elif cmd_lower in ("market", "mkt"):
        from commands.market import cmd_market
        await send_message(chat_id, await cmd_market(args), thread_id=thread_id)

    elif cmd_lower in ("unbond", "queue"):
        from commands.rize import cmd_unbond
        page = _get_page(chat_id)
        p = page["page"] if page and page["cmd"] == "unbond" else 0
        _set_page(chat_id, "unbond", p, args)
        await send_message(chat_id, await cmd_unbond(args, page=p), thread_id=thread_id)

    elif cmd_lower in ("totalbonded", "bonded"):
        from commands.rize import cmd_totalbonded
        await send_message(chat_id, await cmd_totalbonded(args), thread_id=thread_id)

    elif cmd_lower in ("traderize",):
        from commands.price import cmd_traderize
        await send_message(chat_id, await cmd_traderize(args), thread_id=thread_id)

    elif cmd_lower in ("tradecc",):
        from commands.price import cmd_tradecc
        await send_message(chat_id, await cmd_tradecc(args), thread_id=thread_id)

    elif cmd_lower.startswith("trade") and len(cmd_lower) > 5:
        from commands.price import cmd_trade_any
        await send_message(chat_id, await cmd_trade_any(cmd_lower[5:]), thread_id=thread_id)

    # ── Ecosystem ─────────────────────────────────────────────────────────
    elif cmd_lower == "rwa":
        from commands.ecosystem import cmd_rwa
        await send_message(chat_id, await cmd_rwa(args), thread_id=thread_id)

    elif cmd_lower in ("vision87", "v87"):
        from commands.ecosystem import cmd_vision87
        await send_message(chat_id, await cmd_vision87(args), thread_id=thread_id)

    elif cmd_lower in ("vision60", "v60"):
        from commands.ecosystem import cmd_vision60
        await send_message(chat_id, await cmd_vision60(args), thread_id=thread_id)

    elif cmd_lower == "kairos":
        from commands.ecosystem import cmd_kairos
        await send_message(chat_id, await cmd_kairos(args), thread_id=thread_id)

    elif cmd_lower == "cantonboard":
        from commands.ecosystem import cmd_cantonboard
        await send_message(chat_id, await cmd_cantonboard(args), thread_id=thread_id)

    elif cmd_lower == "cantonlist":
        page = _get_page(chat_id)
        p = page["page"] if page and page["cmd"] == "cantonlist" else 0
        _set_page(chat_id, "cantonlist", p, args)
        await _cmd_cantonlist(chat_id, p, thread_id=thread_id)

    elif cmd_lower.startswith("ecosystem"):
        from commands.ecosystem import cmd_ecosystem
        parts = cmd_lower[len("ecosystem"):].strip().split() + args
        entity_args = [a for a in parts if a]
        if not entity_args:
            # List view - set pagination context so replies work
            _set_page(chat_id, "ecosystem", 0, [])
        await send_message(chat_id, await cmd_ecosystem(entity_args), thread_id=thread_id)

    elif cmd_lower.startswith("canton") and cmd_lower not in ("cantongov", "cantonboard", "cantonlist"):
        from commands.ecosystem import cmd_canton
        parts = cmd_lower[len("canton"):].strip().split() + args
        await send_message(chat_id, await cmd_canton([a for a in parts if a]), thread_id=thread_id)

    # ── Canton governance ─────────────────────────────────────────────────
    elif cmd_lower.startswith("cip"):
        from commands.canton_gov import cmd_cip
        cip_args = cmd_lower[3:].strip().split() + args
        cip_args = [a for a in cip_args if a]
        if not cip_args:
            page = _get_page(chat_id)
            p = page["page"] if page and page["cmd"] == "cip" else 0
            _set_page(chat_id, "cip", p, [])
            await send_message(chat_id, await cmd_cip([], page=p), thread_id=thread_id)
        else:
            await send_message(chat_id, await cmd_cip(cip_args), thread_id=thread_id)

    elif cmd_lower in ("cantongov", "cgov"):
        from commands.canton_gov import cmd_cantongov
        page = _get_page(chat_id)
        p = page["page"] if page and page["cmd"] == "cantongov" else 0
        _set_page(chat_id, "cantongov", p, args)
        await send_message(chat_id, await cmd_cantongov(args, page=p), thread_id=thread_id)

    # ── Governance hub ────────────────────────────────────────────────────
    elif cmd_lower in ("govflows", "flows"):
        from commands.governance import cmd_govflows
        page = _get_page(chat_id)
        p = page["page"] if page and page["cmd"] == "govflows" else 0
        _set_page(chat_id, "govflows", p, args)
        await send_message(chat_id, await cmd_govflows(args, page=p), thread_id=thread_id)

    elif cmd_lower in ("govwhalealert", "whales", "whale"):
        from commands.governance import cmd_govwhalealert
        page = _get_page(chat_id)
        p = page["page"] if page and page["cmd"] == "govwhalealert" else 0
        _set_page(chat_id, "govwhalealert", p, args)
        await send_message(chat_id, await cmd_govwhalealert(args, page=p), thread_id=thread_id)

    elif cmd_lower.startswith("govbond"):
        from commands.governance import cmd_govbond
        query = cmd_lower.replace("govbond", "").strip()
        combined = ([query] if query else []) + args
        # Store nft_id so "see wallet" can look up the owner
        if combined:
            _set_page(chat_id, "govbond_owner", 0, combined)
        result = await cmd_govbond(combined)
        await send_message(chat_id, result, thread_id=thread_id)

    elif cmd_lower.startswith("govwallet"):
        from commands.governance import cmd_govwallet
        query = cmd_lower.replace("govwallet", "").strip()
        combined = ([query] if query else []) + args
        page = _get_page(chat_id)
        p = page["page"] if page and page["cmd"] == "govwallet_timeline" else 0
        _set_page(chat_id, "govwallet_timeline", p, combined)
        await send_message(chat_id, await cmd_govwallet(combined), thread_id=thread_id)

    # ── Fun ───────────────────────────────────────────────────────────────
    elif cmd_lower in ("sayhello", "hello", "hi", "start"):
        from commands.fun import cmd_sayhello
        await send_message(chat_id, await cmd_sayhello(args), thread_id=thread_id)

    elif cmd_lower in ("insult", "roast"):
        from commands.fun import cmd_insult
        await send_message(chat_id, await cmd_insult(args), thread_id=thread_id)

    elif cmd_lower in ("help", "commands", ""):
        await send_message(chat_id, HELP_TEXT, thread_id=thread_id)

    else:
        # Bonus hidden: try lookup by name/entity
        from commands.ecosystem import lookup_any
        result = await lookup_any(cmd_lower + (" " + " ".join(args) if args else ""))
        if result:
            await send_message(chat_id, result, thread_id=thread_id)
        # If nothing found — silently ignore (no error in groups)


async def _cmd_cantonlist(chat_id: int, page: int, thread_id: int = None):
    from utils.github_data import get_entities
    entities = await get_entities()
    if not entities:
        await send_message(chat_id, "Could not load Canton entities.", thread_id=thread_id)
        return
    per_page = 20
    start = page * per_page
    page_ents = entities[start:start + per_page]
    total = len(entities)
    total_pages = (total - 1) // per_page + 1

    lines = [f"🏛 *Canton Network — All Entities*",
             f"_Page {page+1}/{total_pages} · {total} entities_", ""]

    for e in page_ents:
        name = e.get("name", "?")
        raw_tags = e.get("tags", [])
        clean = [t for t in raw_tags if isinstance(t, str) and len(t) < 40
                 and "\n" not in t and "Roles" not in t and "Network" not in t
                 and "items found" not in t]
        tag_str = clean[0] if clean else ""
        lines.append(f"• *{name}*" + (f" — {tag_str}" if tag_str else ""))

    lines += [
        "",
        "_Reply with a name to learn more, or type `/canton {name}`_",
        "_Reply *next* for more · Reply *page N* to jump to page N_",
    ]
    await send_message(chat_id, "\n".join(lines), thread_id=thread_id)
    _set_page(chat_id, "cantonlist", page, [])


# ── Callback query handler (Refresh button) ───────────────────────────────────

async def handle_callback(callback: dict) -> None:
    data    = callback.get("data", "")
    chat_id = callback["message"]["chat"]["id"]
    msg_id  = callback["message"]["message_id"]
    if data.startswith("price_"):
        coin_id = data[6:]
        from commands.price import cmd_price
        from utils.coingecko import DISPLAY_MAP
        token = next((k for k, v in DISPLAY_MAP.items() if k == coin_id), coin_id)
        text, markup = await cmd_price([token])
        await edit_message(chat_id, msg_id, text, markup)
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(f"{TG_API}/answerCallbackQuery",
                             json={"callback_query_id": callback["id"]})
    except Exception:
        pass


HELP_TEXT = """
🤖 *RizeBy — Tokerize Intelligence Bot*

*Prices & Charts*
`/price` or `/p` — RIZE price · `/p cc` `/p eth` for any coin
`/chart [15m|1h|4h|1d|1w|1M]` — OHLC chart (any coin first)
`/tvl` — TVL & MCap/TVL · FDV/TVL ratios
`/market` — BTC.D, Fear & Greed, Altcoin Season

*Analysis* — put any coin first to use it as base asset
`/perf {assets}` — Performance 7D/30D/90D vs USD
`/pricesim {assets}` — Price sim vs other mcaps
`/portfoliosim {amount} {coin} to {assets}` — Bag simulation
`/arbitrage {amount} {coin} to {assets}` — Ratio analysis

*On-Chain RIZE*
`/unbond` — Live unbonding queue
`/totalbonded` — Live total RIZE bonded

*Trading Pairs*
`/traderize` · `/tradecc` · `/trade{ticker}` (any coin)

*Canton Coin (CC)*
`/ccprice` · `/ccburnmint [1d|1w]` · `/ccallocation`

*T-RIZE Ecosystem*
`/ecosystem` · `/ecosystem {name}` — T-RIZE partners
`/canton {entity}` — Search 290+ Canton entities
`/cantonlist` — Browse all Canton entities
`/cantonboard` · `/cantonboard {name}` — Board members
`/rwa` · `/vision87` · `/vision60` · `/kairos`

*Canton Governance*
`/cip` · `/cip {number}` — CIP list & detail
`/cantongov` — Active governance proposals

*Governance Hub*
`/govflows` — Monthly bond flows
`/govwhalealert [breaks|bond+increase|releases]`
`/govwallet {0x}` · `/govbond {#}` — Wallet & bond profile

*Fun*
`/sayhello` · `/insult`

*Navigation*
Reply *next* after any paginated list to see more
Reply *page 7* to jump to any page
""".strip()


# ── Telegram API helpers ──────────────────────────────────────────────────────

async def send_message(chat_id: int, text: str, reply_markup: dict = None, thread_id: int = None) -> None:
    payload = {"chat_id": chat_id, "text": text,
               "parse_mode": "Markdown", "disable_web_page_preview": True}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    if thread_id:
        payload["message_thread_id"] = thread_id
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


async def send_photo(chat_id: int, photo_bytes: bytes, caption: str = "", thread_id: int = None) -> None:
    try:
        data = {"chat_id": chat_id, "caption": caption, "parse_mode": "Markdown"}
        if thread_id:
            data["message_thread_id"] = str(thread_id)
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                f"{TG_API}/sendPhoto",
                data=data,
                files={"photo": ("chart.png", photo_bytes, "image/png")},
            )
    except Exception:
        pass


async def register_commands() -> None:
    """Register bot commands for the Telegram command list dropdown."""
    commands = [
        {"command": "help",         "description": "All commands & how to use RizeBy"},
        {"command": "price",        "description": "RIZE price — /price or /price cc /price eth"},
        {"command": "chart",        "description": "OHLC chart — /chart 1h /chart 1d etc"},
        {"command": "tvl",          "description": "TVL, MCap/TVL, FDV/TVL"},
        {"command": "perf",         "description": "Performance 7D/30D/90D — /perf eth link"},
        {"command": "pricesim",     "description": "Price simulation — /pricesim eth btc"},
        {"command": "portfoliosim", "description": "Portfolio sim — /portfoliosim 1M rize to eth"},
        {"command": "arbitrage",    "description": "Ratio analysis — /arbitrage 1M rize to eth"},
        {"command": "market",       "description": "BTC.D, Fear & Greed, Altcoin Season"},
        {"command": "unbond",       "description": "Live unbonding queue"},
        {"command": "totalbonded",  "description": "Total RIZE bonded live"},
        {"command": "traderize",    "description": "RIZE trading pairs"},
        {"command": "tradecc",      "description": "CC trading pairs"},
        {"command": "ccprice",      "description": "Canton Coin price"},
        {"command": "ccburnmint",   "description": "CC burn/mint ratio — /ccburnmint 1d or 1w"},
        {"command": "ccallocation", "description": "CC mint allocation by role"},
        {"command": "canton",       "description": "Canton entity — /canton franklin templeton"},
        {"command": "cantonlist",   "description": "Browse all 290+ Canton entities"},
        {"command": "cantonboard",  "description": "Canton Foundation board members"},
        {"command": "ecosystem",    "description": "T-RIZE ecosystem partners"},
        {"command": "rwa",          "description": "T-RIZE RWA deals overview"},
        {"command": "vision87",     "description": "Vision 87 by Champfleury deal"},
        {"command": "vision60",     "description": "Vision 60 by Ste-Rose deal"},
        {"command": "kairos",       "description": "Kairos Digital Loan Notes"},
        {"command": "cip",          "description": "Canton CIPs — /cip or /cip 0116"},
        {"command": "cantongov",    "description": "Active Canton governance proposals"},
        {"command": "govflows",     "description": "Monthly governance bond flows"},
        {"command": "govwhalealert","description": "Whale alerts — /govwhalealert breaks"},
        {"command": "govwallet",    "description": "Wallet profile — /govwallet 0x..."},
        {"command": "govbond",      "description": "Bond profile — /govbond 10034"},
        {"command": "sayhello",     "description": "GM from RizeBy"},
        {"command": "insult",       "description": "Get roasted"},
    ]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(f"{TG_API}/setMyCommands", json={"commands": commands})
    except Exception:
        pass


def parse_update(body: dict):
    if body.get("callback_query"):
        return "callback", body["callback_query"]

    msg = body.get("message") or body.get("edited_message")
    if not msg:
        return None, None

    # CRITICAL: use the message's own chat id, not the update-level id
    # message_thread_id handles forum sub-channels (FR chat, EN chat etc)
    chat_id   = msg["chat"]["id"]
    msg_id    = msg.get("message_id", 0)
    thread_id = msg.get("message_thread_id")  # None for main channel
    text    = (msg.get("text") or "").strip()
    if not text:
        return None, None

    # Strip bot @mention
    if "@" in text:
        text = text.split("@")[0].strip()

    parts = text.split()
    if not parts:
        return None, None

    first = parts[0].lstrip("/").lower()

    # Only process if it's a command (starts with /) or known keywords
    is_command = parts[0].startswith("/")
    known_keywords = {"next", "page"}
    # Multi-word keywords
    full_text_lower = text.lower().strip()
    if full_text_lower in ("see wallet", "seewallet"):
        return "cmd", (chat_id, "see wallet", [], msg_id, thread_id)

    if not is_command and first not in known_keywords:
        # Check if user is replying to a paginated context (cantonlist, ecosystem, cantonboard)
        active_state = _pagination.get(chat_id)
        if active_state and (time.time() - active_state.get("ts", 0)) < PAGE_TTL:
            active_cmd = active_state.get("cmd", "")
            if active_cmd == "cantonlist":
                # Plain text reply to cantonlist = canton entity lookup
                return "cmd", (chat_id, "canton", parts, msg_id, thread_id)
            if active_cmd == "ecosystem":
                # Plain text reply to ecosystem = ecosystem entity lookup
                return "cmd", (chat_id, "ecosystem", parts, msg_id, thread_id)
            if active_cmd == "cantonboard":
                return "cmd", (chat_id, "cantonboard", parts, msg_id, thread_id)
        # In groups: ignore plain text — don't spam error messages
        return None, None

    # "next" as standalone
    if first == "next":
        return "cmd", (chat_id, "next", [], msg_id, thread_id)

    # "page N"
    if first == "page" and len(parts) > 1 and parts[1].isdigit():
        return "cmd", (chat_id, "page", [parts[1]], msg_id, thread_id)

    if first == "rizeby":
        cmd  = parts[1].lower() if len(parts) > 1 else "help"
        args = parts[2:]
    else:
        cmd  = first
        args = parts[1:]

    return "cmd", (chat_id, cmd, list(args), msg_id, thread_id)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body   = json.loads(self.rfile.read(length))
            kind, payload = parse_update(body)
            if kind == "callback":
                asyncio.run(handle_callback(payload))
            elif kind == "cmd":
                chat_id, cmd, args, msg_id, thread_id = payload
                asyncio.run(route_command(cmd, args, chat_id, msg_id, thread_id))
            # else: plain text in group — silently ignore
        except Exception:
            pass
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        # Register commands on GET (called once when checking webhook)
        asyncio.run(register_commands())
        self.wfile.write(b"RizeBy bot is running.")

    def log_message(self, format, *args):
        pass
