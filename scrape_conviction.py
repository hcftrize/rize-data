"""
scrape_conviction.py
====================
Daily script — runs at 08:00 UTC via GitHub Actions.
Appends one data point per day to conviction-history.json.

Fetches:
  - bonded         : balanceOf(governance contract)
  - cex            : sum balanceOf(all CEX addresses)
  - unbonding_queue: sum of BondBroken events in last 7 days
  - whales         : new transfers > 5M RIZE in last 24h (keeps 30d rolling window)

IMPORTANT: BondBroken topic0 is discovered at runtime from the first matching log
to avoid keccak256 vs sha3_256 confusion. Once stable, it can be hardcoded.
"""

import json, os, time, urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

RIZE_TOKEN   = '0x9818B6c09f5ECc843060927E8587c427C7C93583'
GOV_CONTRACT = '0x5a134098bDBEb05Da9eAc35439c5624547ed26eE'
DECIMALS     = 1e18
WHALE_MIN    = 5_000_000
OUTPUT_FILE  = Path('rize-data-hub/conviction-history.json')
ALCHEMY_URL  = os.environ.get(
    'ALCHEMY_RPC_URL',
    'https://base-mainnet.g.alchemy.com/v2/qS-QZnHMq-cqmoFkw-grY'
)

# BondBroken(uint256 nftId, uint256 amount) — confirmed from Basescan tx logs
# keccak256("BondBroken(uint256,uint256)") — verified against real on-chain event
BOND_BROKEN_TOPIC = '0xc23747277531c745e0e6b38cafe2803258edc500eee3dffa3f081b89d9970096'

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


def rpc(method, params):
    payload = json.dumps({
        'jsonrpc': '2.0', 'id': 1,
        'method': method, 'params': params
    }).encode()
    req = urllib.request.Request(
        ALCHEMY_URL, data=payload,
        headers={'Content-Type': 'application/json'}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f'  RPC error: {e}')
        return None


def get_balance(address):
    padded = '000000000000000000000000' + address[2:].lower()
    res = rpc('eth_call', [{'to': RIZE_TOKEN, 'data': '0x70a08231' + padded}, 'latest'])
    if not res or not res.get('result') or res['result'] == '0x':
        return 0.0
    try:
        return int(res['result'], 16) / DECIMALS
    except:
        return 0.0


def get_current_block():
    res = rpc('eth_blockNumber', [])
    if res and res.get('result'):
        return int(res['result'], 16)
    return 0


def get_unbonding_queue():
    """
    Sum all BondBroken events from last 7 days = active unbonding queue.
    BondBroken topic0 verified on-chain from Basescan tx logs.
    7 days = unbonding lock period on T-RIZE governance.
    """
    current_block = get_current_block()
    if not current_block:
        print('  [WARN] Could not get current block')
        return 0.0

    blocks_7d = 7 * 24 * 3600 * 2  # ~1,209,600 blocks (Base = ~2 blocks/sec)
    from_block = hex(max(0, current_block - blocks_7d))

    res = rpc('eth_getLogs', [{
        'fromBlock': from_block,
        'toBlock'  : 'latest',
        'address'  : GOV_CONTRACT,
        'topics'   : [BOND_BROKEN_TOPIC],
    }])

    if not res or 'result' not in res:
        print('  [WARN] eth_getLogs failed for BondBroken')
        return 0.0

    logs = res['result']
    if not logs:
        print('  No BondBroken events in last 7 days — queue is empty')
        return 0.0

    # BondBroken(uint256 nftId, uint256 amount):
    # - topics[1] = nftId (indexed)
    # - data = amount (uint256, 32 bytes)
    total = 0.0
    for log in logs:
        data = log.get('data', '0x')
        if len(data) >= 66:
            try:
                amount = int(data[2:66], 16) / DECIMALS
                total += amount
            except:
                pass

    print(f'  {len(logs)} BondBroken events in last 7d → {total:,.2f} RIZE in queue')
    return round(total, 2)


def fetch_recent_whales():
    """Fetch transfers > 5M RIZE from last 24h via alchemy_getAssetTransfers."""
    block_res = rpc('eth_blockNumber', [])
    if not block_res or not block_res.get('result'):
        return []
    current = int(block_res['result'], 16)
    yesterday_block = hex(current - 43200)  # ~24h of Base blocks

    params = {
        'fromBlock': yesterday_block,
        'toBlock'  : 'latest',
        'contractAddresses': [RIZE_TOKEN],
        'category' : ['erc20'],
        'withMetadata': True,
        'excludeZeroValue': True,
        'maxCount' : '0x3e8',
        'order'    : 'desc',
    }
    res = rpc('alchemy_getAssetTransfers', [params])
    if not res or 'result' not in res:
        return []

    txs = res['result'].get('transfers', [])

    def label(addr):
        if not addr: return 'Unknown'
        a = addr.lower()
        if a == GOV_CONTRACT.lower(): return 'Governance'
        for name, ca in CEX_ADDRESSES.items():
            if a == ca.lower(): return name
        return addr[:6] + '…' + addr[-4:]

    whales = []
    for tx in txs:
        v = float(tx.get('value') or 0)
        if v < WHALE_MIN:
            continue
        ts = tx.get('metadata', {}).get('blockTimestamp', '')
        whales.append({
            'date'       : ts[:10] if ts else date.today().isoformat(),
            'amount'     : round(v, 2),
            'from'       : tx.get('from', ''),
            'to'         : tx.get('to', ''),
            'from_label' : label(tx.get('from', '')),
            'to_label'   : label(tx.get('to', '')),
            'tx'         : tx.get('hash', ''),
        })
    return whales


def main():
    OUTPUT_FILE.parent.mkdir(exist_ok=True)
    today = date.today().isoformat()

    # Load existing
    if OUTPUT_FILE.exists():
        history = json.loads(OUTPUT_FILE.read_text(encoding='utf-8'))
        print(f'Loaded existing JSON ({len(history.get("bonded", []))} bonded points)')
    else:
        print('No JSON found — creating fresh')
        history = {'bonded': [], 'cex': [], 'unbonding': [], 'whales': [], 'metadata': {}}

    # Check if today already recorded
    existing_dates = {e['date'] for e in history.get('bonded', [])}
    if today in existing_dates:
        print(f'Today ({today}) already recorded — nothing to do')
        return

    print(f'Fetching snapshot for {today}...')

    # 1. Bonded
    bonded = get_balance(GOV_CONTRACT)
    print(f'  Bonded         : {bonded:,.0f} RIZE')

    # 2. Unbonding queue
    time.sleep(0.3)
    unbonding = get_unbonding_queue()
    print(f'  Unbonding queue: {unbonding:,.2f} RIZE')

    # 3. CEX total
    cex_total = 0.0
    for name, addr in CEX_ADDRESSES.items():
        bal = get_balance(addr)
        cex_total += bal
        time.sleep(0.15)
    print(f'  CEX total      : {cex_total:,.0f} RIZE')

    # 4. Whale movements last 24h
    print('  Fetching whale movements...')
    new_whales = fetch_recent_whales()
    print(f'  Whales         : {len(new_whales)} new movements >5M RIZE')

    # Append today's points
    history.setdefault('bonded',    []).append({'date': today, 'value': round(bonded, 2)})
    history.setdefault('cex',       []).append({'date': today, 'value': round(cex_total, 2)})
    history.setdefault('unbonding', []).append({'date': today, 'value': round(unbonding, 2)})

    # Merge whales — deduplicate by tx hash, keep last 30 days only
    cutoff = (date.today() - timedelta(days=30)).isoformat()
    existing_hashes = {w['tx'] for w in history.get('whales', [])}
    for w in new_whales:
        if w['tx'] not in existing_hashes:
            history.setdefault('whales', []).append(w)
            existing_hashes.add(w['tx'])

    # Trim whales to 30d rolling window
    history['whales'] = [w for w in history['whales'] if w.get('date', '') >= cutoff]
    history['whales'].sort(key=lambda x: x['date'], reverse=True)

    # Update metadata
    history.setdefault('metadata', {})['updated'] = datetime.now(timezone.utc).isoformat()

    OUTPUT_FILE.write_text(
        json.dumps(history, indent=2, ensure_ascii=False),
        encoding='utf-8'
    )
    print(f'\n✅ Saved — {len(history["bonded"])} bonded points, {len(history["whales"])} whale movements')


if __name__ == '__main__':
    main()
