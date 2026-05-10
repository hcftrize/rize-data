"""
RizeBy Telegram Bot — Vercel Serverless Webhook Handler
File location in repo: api/rizeby/telegram.py
"""
import json
import os
import asyncio
import sys
import httpx
from http.server import BaseHTTPRequestHandler

# Add rizeby-bot to path so imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'rizeby-bot'))

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TG_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


async def route_command(cmd: str, args: list, chat_id: int) -> None:
    cmd_lower = cmd.lower().strip()

    # CC sub-commands
    if cmd_lower == "cc" or cmd_lower.startswith("cc "):
        sub = args[0].lower() if args else "price"
        sub_args = args[1:] if args else []
        if sub in ("burnmint", "burn", "mint"):
            from commands.cc import cmd_cc_burnmint
            text = await cmd_cc_burnmint(sub_args)
        elif sub in ("allocation", "alloc"):
            from commands.cc import cmd_cc_allocation
            text = await cmd_cc_allocation(sub_args)
        else:
            from commands.cc import cmd_cc_price
            text = await cmd_cc_price(sub_args)
        await send_message(chat_id, text)
        return

    if cmd_lower in ("price", "p"):
        from commands.price import cmd_price
        text, markup = await cmd_price(args)
        await send_message(chat_id, text, markup)

    elif cmd_lower in ("chart", "c"):
        from commands.price import cmd_chart
        img_bytes, caption = await cmd_chart(args)
        if img_bytes:
            await send_photo(chat_id, img_bytes, caption)
        else:
            await send_message(chat_id, caption)

    elif cmd_lower == "tvl":
        from commands.price import cmd_tvl
        text = await cmd_tvl(args)
        await send_message(chat_id, text)

    elif cmd_lower in ("perf", "performance"):
        from commands.market import cmd_perf
        text = await cmd_perf(args)
        await send_message(chat_id, text)

    elif cmd_lower in ("pricesim", "ps"):
        from commands.market import cmd_pricesim
        text = await cmd_pricesim(args)
        await send_message(chat_id, text)

    elif cmd_lower in ("portfoliosim", "portfolio", "bag"):
        from commands.market import cmd_portfoliosim
        text = await cmd_portfoliosim(args)
        await send_message(chat_id, text)

    elif cmd_lower in ("arbitrage", "ratio", "arb"):
        from commands.market import cmd_arbitrage
        text = await cmd_arbitrage(args)
        await send_message(chat_id, text)

    elif cmd_lower in ("market", "mkt"):
        from commands.market import cmd_market
        text = await cmd_market(args)
        await send_message(chat_id, text)

    elif cmd_lower in ("unbond", "queue"):
        from commands.rize import cmd_unbond
        text = await cmd_unbond(args)
        await send_message(chat_id, text)

    elif cmd_lower in ("totalbonded", "bonded"):
        from commands.rize import cmd_totalbonded
        text = await cmd_totalbonded(args)
        await send_message(chat_id, text)

    elif cmd_lower in ("traderize", "trade"):
        from commands.price import cmd_traderize
        text = await cmd_traderize(args)
        await send_message(chat_id, text)

    elif cmd_lower in ("tradecc", "ccexchanges"):
        from commands.price import cmd_tradecc
        text = await cmd_tradecc(args)
        await send_message(chat_id, text)

    elif cmd_lower.startswith("canton") and cmd_lower not in ("cantongov", "cantonboard"):
        from commands.ecosystem import cmd_canton
        entity_parts = cmd_lower[len("canton"):].strip().split() + args
        text = await cmd_canton([a for a in entity_parts if a])
        await send_message(chat_id, text)

    elif cmd_lower == "cantonboard":
        from commands.ecosystem import cmd_cantonboard
        text = await cmd_cantonboard(args)
        await send_message(chat_id, text)

    elif cmd_lower.startswith("ecosystem"):
        from commands.ecosystem import cmd_ecosystem
        entity_parts = cmd_lower[len("ecosystem"):].strip().split() + args
        text = await cmd_ecosystem([a for a in entity_parts if a])
        await send_message(chat_id, text)

    elif cmd_lower in ("vision87", "v87"):
        from commands.ecosystem import cmd_vision87
        text = await cmd_vision87(args)
        await send_message(chat_id, text)

    elif cmd_lower in ("vision60", "v60"):
        from commands.ecosystem import cmd_vision60
        text = await cmd_vision60(args)
        await send_message(chat_id, text)

    elif cmd_lower == "kairos":
        from commands.ecosystem import cmd_kairos
        text = await cmd_kairos(args)
        await send_message(chat_id, text)

    elif cmd_lower.startswith("cip"):
        from commands.canton_gov import cmd_cip
        cip_args = cmd_lower[3:].strip().split() + args
        text = await cmd_cip([a for a in cip_args if a])
        await send_message(chat_id, text)

    elif cmd_lower in ("cantongov", "cgov"):
        from commands.canton_gov import cmd_cantongov
        text = await cmd_cantongov(args)
        await send_message(chat_id, text)

    elif cmd_lower in ("govflows", "flows"):
        from commands.governance import cmd_govflows
        text = await cmd_govflows(args)
        await send_message(chat_id, text)

    elif cmd_lower in ("govwhalealert", "whales", "whale"):
        from commands.governance import cmd_govwhalealert
        text = await cmd_govwhalealert(args)
        await send_message(chat_id, text)

    elif cmd_lower.startswith("govbond") or cmd_lower.startswith("govwallet"):
        from commands.governance import cmd_govwallet
        text = await cmd_govwallet(args)
        await send_message(chat_id, text)

    elif cmd_lower in ("sayhello", "hello", "hi", "start"):
        from commands.fun import cmd_sayhello
        text = await cmd_sayhello(args)
        await send_message(chat_id, text)

    elif cmd_lower in ("insult", "roast"):
        from commands.fun import cmd_insult
        text = await cmd_insult(args)
        await send_message(chat_id, text)

    elif cmd_lower in ("help", "commands", ""):
        await send_message(chat_id, HELP_TEXT)

    else:
        await send_message(chat_id, f"❓ Unknown command: `{cmd}`\n\nType `/rizeby help` to see all commands.")


HELP_TEXT = """
🤖 *RizeBy — Tokerize Bot*

*RIZE Data Hub*
`/rizeby price` — Price, MCap, ATH, Vol
`/rizeby chart [15m|1h|4h|1d|1w|1M]` — Chart
`/rizeby tvl` — TVL & MCap ratios
`/rizeby perf {assets}` — Performance 7D/30D/90D
`/rizeby pricesim {assets}` — Price simulation
`/rizeby portfoliosim {assets} {amount}` — Portfolio sim
`/rizeby arbitrage {assets} [{amount}]` — Ratio analysis
`/rizeby market` — BTC.D, Fear&Greed, AltSzn
`/rizeby unbond` — Live unbonding queue
`/rizeby totalbonded` — Live total bonded
`/rizeby traderize` / `/rizeby tradecc` — Trading pairs

*Any base asset:* put coin first → `/rizeby cc perf eth link`

*CC Data Hub*
`/rizeby cc price` · `/rizeby cc burnmint [1d|1w]` · `/rizeby cc allocation`

*Ecosystem*
`/rizeby canton {entity}` · `/rizeby vision87` · `/rizeby cantonboard` · `/rizeby ecosystem`

*Canton Governance*
`/rizeby cip` · `/rizeby cip 0116` · `/rizeby cantongov`

*Governance Hub*
`/rizeby govflows` · `/rizeby govwhalealert` · `/rizeby govwallet {0x}` · `/rizeby govbond {#}`

*Fun*
`/rizeby sayhello` · `/rizeby insult`
""".strip()


async def send_message(chat_id: int, text: str, reply_markup: dict = None) -> None:
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(f"{TG_API}/sendMessage", json=payload)


async def send_photo(chat_id: int, photo_bytes: bytes, caption: str = "") -> None:
    async with httpx.AsyncClient(timeout=15) as client:
        await client.post(
            f"{TG_API}/sendPhoto",
            data={"chat_id": chat_id, "caption": caption, "parse_mode": "Markdown"},
            files={"photo": ("chart.png", photo_bytes, "image/png")},
        )


def parse_update(body: dict):
    msg = body.get("message") or body.get("edited_message")
    if not msg:
        return None
    chat_id = msg["chat"]["id"]
    text    = (msg.get("text") or "").strip()
    if not text:
        return None
    text  = text.split("@")[0] if "@" in text else text
    parts = text.split()
    if not parts:
        return None
    first = parts[0].lstrip("/").lower()
    if first == "rizeby":
        cmd  = parts[1].lower() if len(parts) > 1 else "help"
        args = parts[2:]
    else:
        cmd  = first
        args = parts[1:]
    # compound: cc burnmint etc
    if cmd == "cc" and args:
        sub = args[0].lower()
        cmd = f"cc {sub}"
        args = args[1:]
    return chat_id, cmd, list(args)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = json.loads(self.rfile.read(length))
        parsed = parse_update(body)
        if parsed:
            chat_id, cmd, args = parsed
            asyncio.run(route_command(cmd, args, chat_id))
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
