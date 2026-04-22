"""
scrape_conviction.py
====================
Daily script — runs at 08:00 UTC via GitHub Actions.
Appends one data point per day to conviction-history.json.

Fetches:
  - bonded         : balanceOf(governance contract)
  - cex            : sum balanceOf(all CEX addresses)
  - unbonding_queue: rolling 7-day window of BondBroken events
  - whales         : new transfers > 5M RIZE in last 24h (keeps 30d rolling window)

Unbonding strategy:
  - Scans only the last ~24h of blocks (~172,800 blocks, ~115 chunks of 1500)
  - New BondBroken events are stored individually in JSON with their date
  - Events older than 7 days are purged on each run
  - The sum of remaining events = active unbonding queue
  This avoids scanning 7 days of blocks (800+ chunks) every day.
"""

import json, os, time, urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

RIZE_TOKEN        = '0x9818B6c09f5ECc843060927E8587c427C7C93583'
GOV_CONTRACT      = '0x5a134098bDBEb05Da9eAc35439c5624547ed26eE'
DECIMALS          = 1e18
WHALE_MIN         = 5_000_000
OUTPUT_FILE       = Path('rize-data-hub/conviction-history.json')
ALCHEMY_URL       = os.environ.get(
    'ALCHEMY_RPC_URL',
    'https://base-mainnet.g.alchemy.com/v2/qS-QZnHMq-cqmoFkw-grY'
)

# BondBroken(uint256 nftId, uint256 amount) — verified on-chain from Basescan
BOND_BROKEN_TOPIC  = '0xc23747277531c745e0e6b38cafe2803258edc500eee3dffa3f081b89d9970096'
BASE_PUBLIC_RPC    = 'https://rpc.ankr.com/base'

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

BLOCKS_PER_DAY  = 24 * 3600 * 2   # ~172,800  (Base ~2 blocks/sec)


def rpc(method, params, url=None):
    endpoint = url or ALCHEMY_URL
    payload = json.dumps({
        'jsonrpc': '2.0', 'id': 1,
        'method': method, 'params': params
    }).encode()
    req = urllib.request.Request(
        endpoint, data=payload,
        headers={'Content-Type': 'application/json'}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f'  RPC error ({endpoint}): {e}')
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


def fetch_bond_broken_events_24h(current_block):
    """
    Fetch BondBroken events from last 24h using Base public RPC.
    Single eth_getLogs call — no block range restriction on mainnet.base.org.
    """
    from_block = hex(max(0, current_block - BLOCKS_PER_DAY))

    res = rpc('eth_getLogs', [{
        'fromBlock': from_block,
        'toBlock'  : 'latest',
        'address'  : GOV_CONTRACT,
        'topics'   : [BOND_BROKEN_TOPIC],
    }], url=BASE_PUBLIC_RPC)

    if not res or 'result' not in res:
        print(f'  [WARN] eth_getLogs failed: {res}')
        return []

    logs = res['result']
    events = []
    for log in logs:
        data = log.get('data', '0x')
        if len(data) >= 66:
            try:
                amount     = int(data[2:66], 16) / DECIMALS
                blk_num    = int(log.get('blockNumber', '0x0'), 16)
                blocks_ago = current_block - blk_num
                secs_ago   = blocks_ago / 2.0
                event_dt   = datetime.now(timezone.utc) - timedelta(seconds=secs_ago)
                event_date = event_dt.date().isoformat()
                events.append({
                    'date'  : event_date,
                    'amount': round(amount, 2),
                    'tx'    : log.get('transactionHash', ''),
                })
            except:
                pass

    print(f'  {len(events)} BondBroken events in last 24h')
    return events


def compute_unbonding_queue(bond_events):
    """Sum all BondBroken events — already filtered to last 7 days."""
    return round(sum(e['amount'] for e in bond_events), 2)


def fetch_recent_whales():
    """Fetch transfers > 5M RIZE from last 24h via alchemy_getAssetTransfers."""
    block_res = rpc('eth_blockNumber', [])
    if not block_res or not block_res.get('result'):
        return []
    current  = int(block_res['result'], 16)
    from_blk = hex(current - 43200)  # ~12h Base blocks

    params = {
        'fromBlock'       : from_blk,
        'toBlock'         : 'latest',
        'contractAddresses': [RIZE_TOKEN],
        'category'        : ['erc20'],
        'withMetadata'    : True,
        'excludeZeroValue': True,
        'maxCount'        : '0x3e8',
        'order'           : 'desc',
    }
    res = rpc('alchemy_getAssetTransfers', [params])
    if not res or 'result' not in res:
        return []

    def label(addr):
        if not addr: return 'Unknown'
        a = addr.lower()
        if a == GOV_CONTRACT.lower(): return 'Governance'
        for name, ca in CEX_ADDRESSES.items():
            if a == ca.lower(): return name
        return addr[:6] + '…' + addr[-4:]

    whales = []
    for tx in res['result'].get('transfers', []):
        v = float(tx.get('value') or 0)
        if v < WHALE_MIN:
            continue
        ts = tx.get('metadata', {}).get('blockTimestamp', '')
        whales.append({
            'date'      : ts[:10] if ts else date.today().isoformat(),
            'amount'    : round(v, 2),
            'from'      : tx.get('from', ''),
            'to'        : tx.get('to', ''),
            'from_label': label(tx.get('from', '')),
            'to_label'  : label(tx.get('to', '')),
            'tx'        : tx.get('hash', ''),
        })
    return whales


def main():
    OUTPUT_FILE.parent.mkdir(exist_ok=True)
    today    = date.today().isoformat()
    cutoff7d = (date.today() - timedelta(days=7)).isoformat()
    cutoff30d= (date.today() - timedelta(days=30)).isoformat()

    # Load existing JSON
    if OUTPUT_FILE.exists():
        history = json.loads(OUTPUT_FILE.read_text(encoding='utf-8'))
        print(f'Loaded existing JSON ({len(history.get("bonded", []))} bonded points)')
    else:
        print('No JSON found — creating fresh')
        history = {'bonded': [], 'cex': [], 'unbonding': [], 'bond_events': [], 'whales': [], 'metadata': {}}

    # Ensure bond_events key exists (may be absent in older JSON)
    history.setdefault('bond_events', [])

    # Check if today already recorded
    existing_dates = {e['date'] for e in history.get('bonded', [])}
    if today in existing_dates:
        print(f'Today ({today}) already recorded — nothing to do')
        return

    print(f'Fetching snapshot for {today}...')

    current_block = get_current_block()

    # 1. Bonded
    bonded = get_balance(GOV_CONTRACT)
    print(f'  Bonded         : {bonded:,.0f} RIZE')

    # 2. BondBroken events (last 24h only)
    print('  Scanning last 24h for BondBroken events...')
    new_events = fetch_bond_broken_events_24h(current_block)

    # Merge new events (deduplicate by tx hash)
    existing_tx = {e['tx'] for e in history['bond_events']}
    for ev in new_events:
        if ev['tx'] not in existing_tx:
            history['bond_events'].append(ev)
            existing_tx.add(ev['tx'])

    # Purge events older than 7 days — they are past the unbonding lock period
    history['bond_events'] = [e for e in history['bond_events'] if e.get('date', '') >= cutoff7d]

    # Unbonding queue = sum of remaining events
    unbonding = compute_unbonding_queue(history['bond_events'])
    print(f'  Unbonding queue: {unbonding:,.2f} RIZE ({len(history["bond_events"])} active events)')

    # 3. CEX total
    cex_total = 0.0
    for name, addr in CEX_ADDRESSES.items():
        bal = get_balance(addr)
        cex_total += bal
        time.sleep(0.15)
    print(f'  CEX total      : {cex_total:,.0f} RIZE')

    # 4. Whale movements (last 24h)
    print('  Fetching whale movements...')
    new_whales = fetch_recent_whales()
    print(f'  Whales         : {len(new_whales)} new movements >5M RIZE')

    # Append daily series points
    history.setdefault('bonded',    []).append({'date': today, 'value': round(bonded, 2)})
    history.setdefault('cex',       []).append({'date': today, 'value': round(cex_total, 2)})
    history.setdefault('unbonding', []).append({'date': today, 'value': unbonding})

    # Merge whales — deduplicate, keep 30d rolling window
    existing_hashes = {w['tx'] for w in history.get('whales', [])}
    for w in new_whales:
        if w['tx'] not in existing_hashes:
            history.setdefault('whales', []).append(w)
            existing_hashes.add(w['tx'])
    history['whales'] = [w for w in history['whales'] if w.get('date', '') >= cutoff30d]
    history['whales'].sort(key=lambda x: x['date'], reverse=True)

    # Update metadata
    history.setdefault('metadata', {})['updated'] = datetime.now(timezone.utc).isoformat()

    OUTPUT_FILE.write_text(
        json.dumps(history, indent=2, ensure_ascii=False),
        encoding='utf-8'
    )
    print(f'\n✅ Saved — {len(history["bonded"])} bonded points, '
          f'{len(history["bond_events"])} active bond events, '
          f'{len(history["whales"])} whale movements')


if __name__ == '__main__':
    main()
