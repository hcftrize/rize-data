# RizeBy — Tokerize Telegram Bot

Telegram bot for the RIZE / Canton ecosystem. Deployed as a Vercel serverless function inside the TOKERIZE repo.

## Architecture

```
rizeby-bot/
├── api/telegram.py        ← Vercel webhook endpoint (POST /api/rizeby/telegram)
├── commands/
│   ├── price.py           ← /price, /chart, /tvl, /traderize, /tradecc
│   ├── market.py          ← /perf, /pricesim, /portfoliosim, /arbitrage, /market
│   ├── rize.py            ← /unbond, /totalbonded
│   ├── cc.py              ← /cc price, /cc burnmint, /cc allocation
│   ├── ecosystem.py       ← /canton, /ecosystem, /vision87, /vision60, /kairos, /cantonboard
│   ├── canton_gov.py      ← /cip, /cantongov
│   ├── governance.py      ← /govflows, /govwhalealert, /govwallet, /govbond
│   └── fun.py             ← /sayhello, /insult
├── utils/
│   ├── coingecko.py       ← CoinGecko API wrapper + COIN_MAP + parse_base_and_compare()
│   ├── github_data.py     ← GitHub JSON loader
│   ├── formatters.py      ← Text formatting helpers
│   └── fuzzy.py           ← Fuzzy matching for /canton
├── setup_webhook.py       ← One-time webhook registration
└── requirements.txt
```

## Environment Variables (Vercel)

| Variable | Description |
|---|---|
| `TELEGRAM_TOKEN` | Bot token from @BotFather |
| `COINGECKO_API_KEY` | CoinGecko Demo API key (already in Vercel) |
| `ALCHEMY_KEY` | Optional — defaults to existing key |

## Vercel Route

Add to your root `vercel.json`:
```json
{
  "functions": {
    "rizeby-bot/api/telegram.py": { "runtime": "python3.12", "maxDuration": 30 }
  },
  "routes": [
    { "src": "/api/rizeby/telegram", "dest": "/rizeby-bot/api/telegram.py" }
  ]
}
```

## One-time Setup

After deploying, register the webhook:
```bash
TELEGRAM_TOKEN=your_token python rizeby-bot/setup_webhook.py https://tokerize.top/api/rizeby/telegram
```

---

## Commands

All commands work with or without the `/rizeby` prefix:
- `/rizeby price` = `/price` = `/rizeby rize price`

### Base asset logic
The financial commands (/perf, /pricesim, /portfoliosim, /arbitrage, /price, /chart)
use **RIZE as the default base asset**. If you put a different coin first, it becomes the base:

```
/rizeby perf eth link mantra       → RIZE vs ETH, LINK, MANTRA
/rizeby cc perf eth link           → CC vs ETH, LINK
/rizeby sol perf eth btc           → SOL vs ETH, BTC
/rizeby pricesim eth btc cc        → RIZE price sim vs ETH, BTC, CC mcaps
/rizeby cc pricesim eth btc        → CC price sim vs ETH, BTC mcaps
/rizeby portfoliosim eth link 1000000    → RIZE bag of 1M
/rizeby cc portfoliosim eth 50000        → CC bag of 50K
/rizeby arbitrage eth cc link 1000000    → RIZE ratio vs ETH, CC, LINK
/rizeby cc arbitrage eth btc 50000       → CC ratio vs ETH, BTC
```

### RIZE Data Hub
- `/rizeby price [{coin}]` — Price, MCap, ATH, Vol. Default: RIZE
- `/rizeby chart [{coin}] [15m|1h|4h|1d|1w|1M]` — OHLC chart. Default: RIZE daily
- `/rizeby tvl` — RIZE TVL, MCap/TVL, FDV/TVL ratios
- `/rizeby perf {compare assets}` — Performance 7D/30D/90D
- `/rizeby pricesim {compare assets}` — Price simulation vs other mcaps
- `/rizeby portfoliosim {compare assets} {amount}` — Portfolio simulation
- `/rizeby arbitrage {compare assets} [{amount}]` — Ratio analysis
- `/rizeby market` — Market context (BTC.D, Fear&Greed, AltSzn)
- `/rizeby unbond` — Live unbonding queue (Goldsky)
- `/rizeby totalbonded` — Live total RIZE bonded (Alchemy RPC)
- `/rizeby traderize` — RIZE trading pairs
- `/rizeby tradecc` — CC trading pairs

### CC Data Hub
- `/rizeby cc price` — Canton Coin price (= `/rizeby price cc`)
- `/rizeby cc burnmint [1d|1w]` — Burn/mint ratio from CantonScan
- `/rizeby cc allocation` — Mint allocation by role (SVs, Validators, Apps)

### Ecosystem
- `/rizeby canton {entity name}` — Any of 290+ Canton Network entities (fuzzy match)
- `/rizeby vision87` / `/rizeby vision60` / `/rizeby kairos` — T-RIZE RWA deals
- `/rizeby cantonboard` — Canton Foundation board members
- `/rizeby ecosystem [{entity}]` — T-RIZE ecosystem entities

### Canton Governance
- `/rizeby cip` — Latest 5 CIPs, reply *next* for more
- `/rizeby cip 0116` — Specific CIP detail
- `/rizeby cantongov` — Active governance proposals, reply *next* for more

### Governance Hub
- `/rizeby govflows` — Monthly bond flows (breaks/created/increased) — reply *next* for older months
- `/rizeby govwhalealert [breaks|bond+increase|releases]` — Whale alerts >5M RIZE
- `/rizeby govwallet {0x...}` — Wallet governance profile (VP, loyalty, bonds, timeline)
- `/rizeby govbond {#}` — Bond profile

### Fun
- `/rizeby sayhello` — GM
- `/rizeby insult` — Get roasted 🔥
