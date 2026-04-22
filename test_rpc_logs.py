"""
test_rpc_logs.py
================
Tests which public Base RPCs accept eth_getLogs over a 24h block range.
Run locally or via GitHub Actions workflow_dispatch.

Usage: python test_rpc_logs.py
"""

import json, urllib.request, sys
from datetime import datetime, timezone

GOV_CONTRACT      = '0x5a134098bDBEb05Da9eAc35439c5624547ed26eE'
BOND_BROKEN_TOPIC = '0xc23747277531c745e0e6b38cafe2803258edc500eee3dffa3f081b89d9970096'
DECIMALS          = 1e18
BLOCKS_PER_DAY    = 172_800

RPCS = [
    'https://base.llamarpc.com',
    'https://base-rpc.publicnode.com',
    'https://1rpc.io/base',
    'https://base.drpc.org',
    'https://base.meowrpc.com',
    'https://mainnet.base.org',          # Coinbase official — usually generous
]


def call(endpoint, method, params, timeout=20):
    payload = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}).encode()
    req = urllib.request.Request(
        endpoint, data=payload,
        headers={'Content-Type': 'application/json', 'User-Agent': 'Tokerize-Test/1.0'}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {'_error': str(e)}


def get_current_block(endpoint):
    res = call(endpoint, 'eth_blockNumber', [])
    if res and 'result' in res:
        return int(res['result'], 16)
    return None


def decode_events(logs, current_block):
    from datetime import timedelta
    events = []
    for log in logs:
        data = log.get('data', '0x')
        try:
            amount   = int(data[2:66], 16) / DECIMALS
            blk_num  = int(log.get('blockNumber', '0x0'), 16)
            secs_ago = (current_block - blk_num) / 2.0
            event_dt = datetime.now(timezone.utc) - timedelta(seconds=secs_ago)
            events.append({
                'date':   event_dt.date().isoformat(),
                'amount': round(amount, 4),
                'tx':     log.get('transactionHash', '')[:20] + '…',
            })
        except:
            pass
    return events


print(f'Testing {len(RPCS)} public Base RPCs for eth_getLogs support')
print(f'Contract : {GOV_CONTRACT}')
print(f'Topic    : {BOND_BROKEN_TOPIC}')
print(f'Range    : ~{BLOCKS_PER_DAY:,} blocks (24h)\n')
print('=' * 70)

for rpc_url in RPCS:
    print(f'\n{rpc_url}')

    # Step 1: get current block
    current_block = get_current_block(rpc_url)
    if not current_block:
        print('  ✗ eth_blockNumber failed — skipping')
        continue
    print(f'  ✓ eth_blockNumber: {current_block:,}')

    from_block = max(0, current_block - BLOCKS_PER_DAY)

    # Step 2: eth_getLogs over 24h
    res = call(rpc_url, 'eth_getLogs', [{
        'fromBlock': hex(from_block),
        'toBlock':   'latest',
        'address':   GOV_CONTRACT,
        'topics':    [BOND_BROKEN_TOPIC],
    }])

    if '_error' in res:
        print(f'  ✗ eth_getLogs error: {res["_error"]}')
        continue

    if 'error' in res:
        code = res['error'].get('code', '?')
        msg  = res['error'].get('message', '')[:120]
        print(f'  ✗ eth_getLogs RPC error {code}: {msg}')
        continue

    logs = res.get('result', [])
    if logs is None:
        print('  ✗ eth_getLogs returned null')
        continue

    print(f'  ✓ eth_getLogs: {len(logs)} BondBroken events found')

    if logs:
        events = decode_events(logs, current_block)
        print(f'  Sample events (up to 3):')
        for e in events[:3]:
            print(f'    {e["date"]}  {e["amount"]:>12.2f} RIZE  {e["tx"]}')
    else:
        print('  (no events in last 24h — try --days 2 range if suspicious)')

print('\n' + '=' * 70)
print('Done.')
