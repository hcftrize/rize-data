# RizeBy — Tokerize Telegram Bot

Telegram bot for the RIZE / Canton ecosystem. Lives inside the TOKERIZE repo, deployed as a Vercel serverless function.

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
│   ├── coingecko.py       ← CoinGecko API wrapper
│   ├── github_data.py     ← GitHub JSON loader
│   ├── formatters.py      ← Text formatting helpers
│   └── fuzzy.py           ← Fuzzy matching for /canton
├── setup_webhook.py       ← One-time webhook registration script
└── requirements.txt
```

## Environment Variables (Vercel)

| Variable | Description |
|---|---|
| `TELEGRAM_TOKEN` | Bot token from @BotFather |
| `COINGECKO_API_KEY` | CoinGecko Demo API key |
| `ALCHEMY_KEY` | Alchemy Base mainnet key (optional, defaults to existing key) |

## Vercel Route

Add to your root `vercel.json`:
```json
{
  "functions": {
    "rizeby-bot/api/telegram.py": {
      "runtime": "python3.12",
      "maxDuration": 30
    }
  },
  "routes": [
    { "src": "/api/rizeby/telegram", "dest": "/rizeby-bot/api/telegram.py" }
  ]
}
```

## One-time Setup

After deploying, register the webhook with Telegram:

```bash
TELEGRAM_TOKEN=your_token python rizeby-bot/setup_webhook.py https://tokerize.top/api/rizeby/telegram
```

## Commands

All commands work with or without the `/rizeby` prefix:
- `/rizeby price` = `/price` = `/rizeby rize price`

### RIZE Data Hub
- `/rizeby price` — Price, MCap, ATH, Vol, TVL
- `/rizeby chart [15m|1h|4h|1d|1w|1M]` — RIZE/USD chart from Kraken
- `/rizeby tvl` — TVL, MCap/TVL, FDV/TVL ratios
- `/rizeby perf eth link mantra` — Performance comparison 7D/30D/90D
- `/rizeby pricesim eth link cc` — Price simulation vs other asset mcaps
- `/rizeby portfoliosim eth link 1000000` — Portfolio simulation
- `/rizeby arbitrage eth cc 1000000` — Ratio analysis
- `/rizeby market` — Market context (BTC.D, Fear&Greed, AltSzn)
- `/rizeby unbond` — Live unbonding queue
- `/rizeby totalbonded` — Live total RIZE bonded
- `/rizeby traderize` — RIZE trading pairs
- `/rizeby tradecc` — CC trading pairs

### CC Data Hub
- `/rizeby cc price` — Canton Coin price
- `/rizeby cc burnmint [1d|1w]` — Burn/mint ratio
- `/rizeby cc allocation` — Mint allocation by role

### Ecosystem
- `/rizeby canton {entity}` — Canton Network entity (290+ entities, fuzzy match)
- `/rizeby vision87` / `/rizeby vision60` / `/rizeby kairos` — T-RIZE RWA deals
- `/rizeby cantonboard` — Canton Foundation board members
- `/rizeby ecosystem [{entity}]` — T-RIZE ecosystem entities

### Canton Governance
- `/rizeby cip` — Latest 5 CIPs
- `/rizeby cip 0116` — Specific CIP detail
- `/rizeby cantongov` — Active governance proposals

### Governance Hub
- `/rizeby govflows` — Monthly bond flow breakdown
- `/rizeby govwhalealert [breaks|bond+increase|releases]` — Whale alerts
- `/rizeby govwallet {0x...}` — Wallet governance profile
- `/rizeby govbond {#}` — Bond profile

### Fun
- `/rizeby sayhello` — GM
- `/rizeby insult` — Get roasted
