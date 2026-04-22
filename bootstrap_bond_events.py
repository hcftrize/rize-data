"""
bootstrap_bond_events.py
========================
Run ONCE to backfill last 7 days of BondBroken events.
Uses alchemy_getAssetTransfers + eth_getTransactionReceipt — no eth_getLogs.
"""

import json, os, time, urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

GOV_CONTRACT      = '0x5a134098bDBEb05Da9eAc35439c5624547ed26eE'
DECIMALS          = 1e18
OUTPUT_FILE       = Path('rize-data-hub/conviction-history.json')
ALCHEMY_URL       = os.environ.get(
    'ALCHEMY_RPC_URL',
    'https://base-mainnet.g.alchemy.com/v2/qS-QZnHMq-cqmoFkw-grY'
)
BOND_BROKEN_TOPIC = '0xc23747277531c745e0e6b38cafe2803258edc500eee3dffa3f081b89d9970096'
BLOCKS_PER_DAY    = 24 * 3600 * 2   # ~172,800


BASE_PUBLIC_RPCS = [
    'https://base.llamarpc.com',          # LlamaNodes — no key, no IP block
    'https://base-rpc.publicnode.com',    # PublicNode — no key
    'https://1rpc.io/base',               # 1RPC — no key
]

def rpc_public(method, params):
    """Try multiple public Base RPCs in order — no key needed."""
    for endpoint in BASE_PUBLIC_RPCS:
        payload = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}).encode()
        req = urllib.request.Request(
            endpoint, data=payload,
            headers={'Content-Type': 'application/json', 'User-Agent': 'python-urllib/3.11'}
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                result = json.loads(r.read().decode())
                if result and ('result' in result or 'error' in result):
                    return result
        except Exception as e:
            print(f'  [{endpoint}] failed: {e}')
            continue
    return None


def rpc(method, params, url=None):
    endpoint = url or ALCHEMY_URL
    payload = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}).encode()
    req = urllib.request.Request(endpoint, data=payload, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f'  RPC error ({endpoint}): {e}')
        return None


def get_current_block():
    res = rpc('eth_blockNumber', [])
    if res and res.get('result'):
        return int(res['result'], 16)
    return 0


def main():
    if not OUTPUT_FILE.exists():
        print('ERROR: conviction-history.json not found. Run from repo root.')
        return

    history = json.loads(OUTPUT_FILE.read_text(encoding='utf-8'))
    print(f'Loaded JSON ({len(history.get("bonded", []))} bonded points)')

    history.setdefault('bond_events', [])
    existing_tx = {e['tx'] for e in history['bond_events']}
    print(f'Existing bond_events: {len(history["bond_events"])}')

    current_block = get_current_block()
    if not current_block:
        print('ERROR: Could not get current block')
        return
    print(f'Current block: {current_block}')

    # Scan 7 days using Base public RPC (no block limit on eth_getLogs)
    start_block = max(0, current_block - 7 * BLOCKS_PER_DAY)
    print(f'Scanning blocks {start_block} → {current_block} via Base public RPC...')

    res = rpc_public('eth_getLogs', [{
        'fromBlock': hex(start_block),
        'toBlock'  : 'latest',
        'address'  : GOV_CONTRACT,
        'topics'   : [BOND_BROKEN_TOPIC],
    }])

    print(f'eth_getLogs response: {str(res)[:200]}')

    new_events = []
    if res and 'result' in res:
        logs = res['result']
        print(f'{len(logs)} BondBroken events found')
        for log in logs:
            tx_hash = log.get('transactionHash', '')
            if tx_hash in existing_tx:
                continue
            data = log.get('data', '0x')
            if len(data) >= 66:
                try:
                    amount     = int(data[2:66], 16) / DECIMALS
                    blk_num    = int(log.get('blockNumber', '0x0'), 16)
                    blocks_ago = current_block - blk_num
                    secs_ago   = blocks_ago / 2.0
                    event_dt   = datetime.now(timezone.utc) - timedelta(seconds=secs_ago)
                    event_date = event_dt.date().isoformat()
                    new_events.append({'date': event_date, 'amount': round(amount, 2), 'tx': tx_hash})
                    existing_tx.add(tx_hash)
                except:
                    pass
    else:
        print(f'[WARN] eth_getLogs failed or returned no result')

    print(f'\nFound {len(new_events)} new BondBroken events')

    history['bond_events'].extend(new_events)
    history['bond_events'].sort(key=lambda x: x['date'], reverse=True)

    queue_total = sum(e['amount'] for e in history['bond_events'])
    print(f'Unbonding queue: {queue_total:,.2f} RIZE')

    today = date.today().isoformat()
    for entry in history.get('unbonding', []):
        if entry['date'] == today:
            entry['value'] = round(queue_total, 2)
            break

    history.setdefault('metadata', {})['updated'] = datetime.now(timezone.utc).isoformat()
    OUTPUT_FILE.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'\n✅ Done — {len(history["bond_events"])} bond_events saved')
    print(f'   Unbonding queue: {queue_total:,.2f} RIZE')


if __name__ == '__main__':
    main()
