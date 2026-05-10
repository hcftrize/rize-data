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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'rizeby-bot'))

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TG_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


async def route_command(cmd: str, args: list, chat_id: int) -> None:
    cmd_lower = cmd.lower().strip()

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

    # ── Market & financial ─────────────────────────────────────────────────
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
        # /tradesol /tradebtc /tradeeth etc
        ticker = cmd_lower[5:]
        from commands.price import cmd_trade_any
        await send_message(chat_id, await cmd_trade_any(ticker))

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

    elif cmd_lower.startswith("ecosystem"):
        from commands.ecosystem import cmd_ecosystem
        parts = cmd_lower[len("ecosystem"):].strip().split() + args
        await send_message(chat_id, await cmd_ecosystem([a for a in parts if a]))

    elif cmd_lower.startswith("canton") and cmd_lower != "cantongov":
        from commands.ecosystem import cmd_canton
        parts = cmd_lower[len("canton"):].strip().split() + args
        await send_message(chat_id, await cmd_canton([a for a in parts if a]))

    # ── Canton governance ──────────────────────────────────────────────────
    elif cmd_lower.startswith("cip"):
        from commands.canton_gov import cmd_cip
        cip_args = cmd_lower[3:].strip().split() + args
        await send_message(chat_id, await cmd_cip([a for a in cip_args if a]))

    elif cmd_lower in ("cantongov", "cgov"):
        from commands.canton_gov import cmd_cantongov
        await send_message(chat_id, await cmd_cantongov(args))

    # ── Governance hub ─────────────────────────────────────────────────────
    elif cmd_lower in ("govflows", "flows"):
        from commands.governance import cmd_govflows
        await send_message(chat_id, await cmd_govflows(args))

    elif cmd_lower in ("govwhalealert", "whales", "whale"):
        from commands.governance import cmd_govwhalealert
        await send_message(chat_id, await cmd_govwhalealert(args))

    elif cmd_lower.startswith("govbond") or cmd_lower.startswith("govwallet"):
        from commands.governance import cmd_govwallet
        await send_message(chat_id, await cmd_govwallet(args))

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
        # Bonus: try /name or /entity as a hidden lookup command
        from commands.ecosystem import lookup_any
        result = await lookup_any(cmd_lower + (" " + " ".join(args) if args else ""))
        if result:
            await send_message(chat_id, result)
        else:
            await send_message(chat_id, f"Unknown command: `{cmd}`\n\nType `/help` to see all commands.")


HELP_TEXT = """
🤖 *RizeBy — Tokerize Intelligence Bot*

*Prices & Market*
`/price` — RIZE price, MCap, ATH, Vol
`/price cc` or `/price eth` — Any asset price
`/chart [15m|1h|4h|1d|1w|1M]` — OHLC chart (any coin)
`/tvl` — RIZE TVL & MCap/TVL ratios
`/market` — BTC.D, Fear&Greed, AltSzn

*Performance & Simulation*
All commands below work for any base asset — put coin first:
`/perf {assets}` — Performance 7D/30D/90D
`/pricesim {assets}` — Price simulation vs other mcaps
`/portfoliosim {amount} {coin} to {assets}` — Portfolio sim
`/arbitrage {amount} {coin} to {assets}` — Ratio analysis

*On-Chain RIZE*
`/unbond` — Live unbonding queue
`/totalbonded` — Live total RIZE bonded

*Trading Pairs*
`/traderize` — RIZE trading pairs
`/tradecc` — CC trading pairs
`/trade{ticker}` — Any coin pairs (e.g. `/tradebtc`)

*CC (Canton Coin)*
`/ccprice` — CC price
`/ccburnmint [1d|1w]` — Burn/Mint ratio
`/ccallocation` — Mint allocation by role

*T-RIZE Ecosystem*
`/ecosystem` — All T-RIZE partners (21 entities)
`/ecosystem {name}` — Partner deep-dive
`/canton {entity}` — Canton Network entity (290+)
`/cantonboard` — Canton Foundation board (17 members)
`/rwa` — T-RIZE RWA deals overview
`/vision87` · `/vision60` · `/kairos` — Deal details

*Canton Governance*
`/cip` — Latest CIPs · `/cip {number}` — CIP detail
`/cantongov` — Active governance proposals

*Governance Hub*
`/govflows` — Monthly bond flow breakdown
`/govwhalealert [breaks|bond+increase|releases]` — Whale alerts
`/govwallet {0x}` — Wallet governance profile
`/govbond {#}` — Bond profile

*Fun*
`/sayhello` · `/insult`

_Tip: most commands work without `/rizeby` prefix._
""".strip()


# ── Telegram API helpers ───────────────────────────────────────────────────

async def send_message(chat_id: int, text: str, reply_markup: dict = None) -> None:
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(f"{TG_API}/sendMessage", json=payload)
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
    return chat_id, cmd, list(args)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body   = json.loads(self.rfile.read(length))
            parsed = parse_update(body)
            if parsed:
                chat_id, cmd, args = parsed
                asyncio.run(route_command(cmd, args, chat_id))
        except Exception as e:
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
        
