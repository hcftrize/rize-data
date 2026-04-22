"""
bootstrap_bond_events.py
========================
Run ONCE to backfill the last 7 days of BondBroken events into conviction-history.json.
After this, scrape_conviction.py takes over scanning only 24h per day.

Usage:
    python bootstrap_bond_events.py
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
CHUNK_SIZE        = 1500
BLOCKS_PER_DAY    = 24 * 3600 * 2   # ~172,800


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


def get_current_block():
    res = rpc('eth_blockNumber', [])
    if res and res.get('result'):
        return int(res['result'], 16)
    return 0


def block_to_date(block_num, current_block):
    """Approximate date for a block based on distance from current block."""
    blocks_ago   = current_block - block_num
    seconds_ago  = blocks_ago / 2.0  # Base ~2 blocks/sec
    dt           = datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)
    return dt.date().isoformat()


def main():
    if not OUTPUT_FILE.exists():
        print('ERROR: conviction-history.json not found. Run from repo root.')
        return

    history = json.loads(OUTPUT_FILE.read_text(encoding='utf-8'))
    print(f'Loaded JSON ({len(history.get("bonded", []))} bonded points)')

    # Ensure bond_events key exists
    history.setdefault('bond_events', [])
    existing_tx = {e['tx'] for e in history['bond_events']}
    print(f'Existing bond_events: {len(history["bond_events"])}')

    current_block = get_current_block()
    if not current_block:
        print('ERROR: Could not get current block')
        return
    print(f'Current block: {current_block}')

    # Scan last 7 days
    start_block = max(0, current_block - 7 * BLOCKS_PER_DAY)
    total_chunks = (current_block - start_block) // CHUNK_SIZE + 1
    print(f'Scanning blocks {start_block} → {current_block} ({total_chunks} chunks)...')

    new_events = []
    chunks_done = 0
    block = start_block

    while block <= current_block:
        to_block = min(block + CHUNK_SIZE - 1, current_block)
        res = rpc('eth_getLogs', [{
            'fromBlock': hex(block),
            'toBlock'  : hex(to_block),
            'address'  : GOV_CONTRACT,
            'topics'   : [BOND_BROKEN_TOPIC],
        }])

        if res and 'result' in res:
            for log in res['result']:
                tx_hash = log.get('transactionHash', '')
                if tx_hash in existing_tx:
                    continue
                data = log.get('data', '0x')
                if len(data) >= 66:
                    try:
                        amount     = int(data[2:66], 16) / DECIMALS
                        block_num  = int(log.get('blockNumber', '0x0'), 16)
                        event_date = block_to_date(block_num, current_block)
                        new_events.append({
                            'date'  : event_date,
                            'amount': round(amount, 2),
                            'tx'    : tx_hash,
                        })
                        existing_tx.add(tx_hash)
                    except:
                        pass
        elif res and 'error' in res:
            print(f'  [WARN] chunk error: {res["error"]}')

        chunks_done += 1
        if chunks_done % 100 == 0:
            print(f'  {chunks_done}/{total_chunks} chunks, {len(new_events)} events so far...')

        block += CHUNK_SIZE
        time.sleep(0.05)

    print(f'\nFound {len(new_events)} new BondBroken events in last 7 days')

    # Merge into history
    history['bond_events'].extend(new_events)
    history['bond_events'].sort(key=lambda x: x['date'], reverse=True)

    # Compute unbonding queue = sum of all bond_events (all within 7 days)
    queue_total = sum(e['amount'] for e in history['bond_events'])
    print(f'Unbonding queue total: {queue_total:,.2f} RIZE')

    # Update today's unbonding value in the series if it exists
    today = date.today().isoformat()
    for entry in history.get('unbonding', []):
        if entry['date'] == today:
            entry['value'] = round(queue_total, 2)
            print(f'Updated unbonding series for {today}')
            break

    # Update metadata
    history.setdefault('metadata', {})['updated'] = datetime.now(timezone.utc).isoformat()

    OUTPUT_FILE.write_text(
        json.dumps(history, indent=2, ensure_ascii=False),
        encoding='utf-8'
    )
    print(f'\n✅ Done — {len(history["bond_events"])} bond_events in JSON')
    print(f'   Unbonding queue: {queue_total:,.2f} RIZE')
    print(f'\nNow commit & push to dev, then main.')
    print('From tomorrow, scrape_conviction.py handles daily updates automatically.')


if __name__ == '__main__':
    main()
