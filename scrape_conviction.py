"""
scrape_conviction.py
====================
Builds/updates conviction-history.json with daily on-chain data:
- RIZE bonded in governance contract (per day)
- RIZE on exchanges (per day, sum of all CEX wallets)

Run daily via GitHub Actions. Appends today's snapshot — never
re-fetches historical data already in the JSON.

Output: rize-data-hub/conviction-history.json
"""

import json, os, time, urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

# ── Config ─────────────────────────────────────────────────────
RIZE_TOKEN    = '0x9818B6c09f5ECc843060927E8587c427C7C93583'
GOV_CONTRACT  = '0x5a134098bDBEb05Da9eAc35439c5624547ed26eE'
DECIMALS      = 10 ** 18
OUTPUT_FILE   = Path('rize-data-hub/conviction-history.json')
BASESCAN_KEY  = os.environ.get('BASESCAN_API_KEY', '')
BASESCAN_URL  = 'https://api.etherscan.io/v2/api'

CEX_ADDRESSES = {
    'Kraken Hot 1'  : '0x02Ac4617Fe004cf8Cd9c988Ff9C905b2Ec676C2d',
    'Kraken Cold 1' : '0x7DAFbA1d69F6C01AE7567Ffd7b046Ca03B706f83',
    'Kraken Cold 2' : '0xd2DD7b597Fd2435b6dB61ddf48544fd931e6869F',
    'Kraken Hot 2'  : '0xcC282E2004428939ee5149A9e7872F0B4d5d5ec7',
    'Revolut'       : '0x9b0c45d46D386cEdD98873168C36efd0DcBa8d46',
    'MEXC'          : '0x4e3ae00E8323558fA5Cac04b152238924AA31B60',
    'Bitpanda Cold' : '0x0529ea5885702715e83923c59746ae8734c553B7',
    'Bitpanda Hot'  : '0xB7C5F84455c86f9972A80e82939f7CE40b481664',
    'Ourbit'        : '0x4D59BEC2b09052c60C6149c623fb3a461fB1Fe74',
    'Gate'          : '0x0D0707963952f2fBA59dD06f2b425ace40b492Fe',
}


def basescan(params: dict):
    p = {**params, 'apikey': BASESCAN_KEY, 'chainid': '8453'}
    url = BASESCAN_URL + '?' + urllib.parse.urlencode(p)
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f'  Basescan error: {e}')
        return None


def get_token_balance(address: str) -> float:
    """Get current RIZE balance for an address."""
    res = basescan({
        'module': 'account',
        'action': 'tokenbalance',
        'contractaddress': RIZE_TOKEN,
        'address': address,
        'tag': 'latest',
    })
    time.sleep(0.25)
    if not res:
        print(f'    [WARN] No response for {address[:10]}...')
        return 0.0
    # Log API status for debugging
    status = res.get('status', '?')
    message = res.get('message', '?')
    result = res.get('result', '0')
    if status != '1':
        print(f'    [WARN] Basescan status={status} message={message} result={result!r} for {address[:10]}...')
        return 0.0
    if not result or not result.isdigit():
        print(f'    [WARN] Non-numeric result: {result!r} for {address[:10]}...')
        return 0.0
    return int(result) / DECIMALS


def main():
    import urllib.parse  # local import for the helper above

    OUTPUT_FILE.parent.mkdir(exist_ok=True)

    # Load existing history
    if OUTPUT_FILE.exists():
        history = json.loads(OUTPUT_FILE.read_text(encoding='utf-8'))
        print(f'Loaded {len(history["bonded"])} existing data points')
    else:
        history = {
            'bonded': [],   # [{date, value}]
            'cex': [],      # [{date, value}]
            'metadata': {
                'token': RIZE_TOKEN,
                'governance': GOV_CONTRACT,
                'cex_addresses': list(CEX_ADDRESSES.values()),
                'updated': '',
            }
        }
        print('Starting fresh history')

    today = date.today().isoformat()

    # Check if today's entry already exists
    existing_dates = {e['date'] for e in history['bonded']}
    if today in existing_dates:
        print(f'Today ({today}) already recorded — nothing to do')
        return

    print(f'Fetching today\'s snapshot: {today}')

    # 1. Governance bonded balance
    print('  Fetching governance bonded...')
    bonded = get_token_balance(GOV_CONTRACT)
    print(f'  Bonded: {bonded:,.0f} RIZE')

    # 2. CEX total balance
    print('  Fetching CEX balances...')
    cex_total = 0.0
    for name, addr in CEX_ADDRESSES.items():
        bal = get_token_balance(addr)
        cex_total += bal
        print(f'    {name}: {bal:,.0f}')
    print(f'  CEX total: {cex_total:,.0f} RIZE')

    # 3. Append today's entry
    history['bonded'].append({'date': today, 'value': round(bonded, 2)})
    history['cex'].append({'date': today, 'value': round(cex_total, 2)})
    history['metadata']['updated'] = datetime.now(timezone.utc).isoformat()

    # Sort by date
    history['bonded'].sort(key=lambda x: x['date'])
    history['cex'].sort(key=lambda x: x['date'])

    OUTPUT_FILE.write_text(
        json.dumps(history, indent=2, ensure_ascii=False),
        encoding='utf-8'
    )
    print(f'\n✅ Saved {len(history["bonded"])} data points to {OUTPUT_FILE}')


# Fix: urllib.parse needs to be imported at module level for basescan()
import urllib.parse

if __name__ == '__main__':
    main()
