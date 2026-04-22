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


def rpc(method, params):
    payload = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}).encode()
    req = urllib.request.Request(ALCHEMY_URL, data=payload, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f'  RPC error: {e}')
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

    # Scan 7 days: one request per day window using alchemy_getAssetTransfers
    all_hashes = set()
    for day_offset in range(7):
        day_start = current_block - (day_offset + 1) * BLOCKS_PER_DAY
        day_end   = current_block - day_offset * BLOCKS_PER_DAY
        res = rpc('alchemy_getAssetTransfers', [{
            'fromBlock'       : hex(max(0, day_start)),
            'toBlock'         : hex(day_end),
            'toAddress'       : GOV_CONTRACT,
            'category'        : ['internal', 'external'],
            'maxCount'        : '0x3e8',
            'order'           : 'desc',
            'withMetadata'    : False,
            'excludeZeroValue': False,
        }])
        if res and 'result' in res:
            day_hashes = {tx.get('hash','') for tx in res['result'].get('transfers', []) if tx.get('hash')}
            all_hashes |= day_hashes
            print(f'  Day -{day_offset+1}: {len(day_hashes)} txs found')
        time.sleep(0.2)

    print(f'\n{len(all_hashes)} total unique txs, fetching receipts...')

    new_events = []
    for i, tx_hash in enumerate(all_hashes):
        if tx_hash in existing_tx:
            continue
        receipt = rpc('eth_getTransactionReceipt', [tx_hash])
        if not receipt or not receipt.get('result'):
            continue
        for log in receipt['result'].get('logs', []):
            topics = log.get('topics', [])
            if not topics or topics[0].lower() != BOND_BROKEN_TOPIC.lower():
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
        if (i+1) % 20 == 0:
            print(f'  {i+1}/{len(all_hashes)} receipts checked, {len(new_events)} events so far...')
        time.sleep(0.1)

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
