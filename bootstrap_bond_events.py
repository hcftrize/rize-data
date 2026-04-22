"""
bootstrap_bond_events.py
========================
Backfills BondBroken events into conviction-history.json.
Uses chunked eth_getLogs via publicnode (49k blocks/chunk).

Usage:
  python bootstrap_bond_events.py --days=1   # today only (test)
  python bootstrap_bond_events.py --days=7   # full 7-day backfill
"""

import json, os, sys, urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

GOV_CONTRACT      = '0x5a134098bDBEb05Da9eAc35439c5624547ed26eE'
DECIMALS          = 1e18
OUTPUT_FILE       = Path('rize-data-hub/conviction-history.json')
BOND_BROKEN_TOPIC = '0xc23747277531c745e0e6b38cafe2803258edc500eee3dffa3f081b89d9970096'
BLOCKS_PER_DAY    = 172_800
CHUNK_SIZE        = 49_000   # safely under publicnode's 50k limit

BASE_PUBLIC_RPCS = [
    'https://base-rpc.publicnode.com',   # 50,000 block range — primary
    'https://1rpc.io/base',               # 10,000 block range — fallback
]


def call(endpoint, method, params, timeout=30):
    payload = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}).encode()
    req = urllib.request.Request(
        endpoint, data=payload,
        headers={'Content-Type': 'application/json', 'User-Agent': 'Tokerize-Bot/1.0'}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f'  [{endpoint}] error: {e}')
        return None


def get_current_block():
    for endpoint in BASE_PUBLIC_RPCS:
        res = call(endpoint, 'eth_blockNumber', [])
        if res and 'result' in res:
            return int(res['result'], 16)
    print('ERROR: could not get current block', file=sys.stderr)
    sys.exit(1)


def fetch_logs_chunked(from_block, to_block):
    """Fetch eth_getLogs in chunks, trying each RPC in order per chunk."""
    all_logs = []
    total_chunks = (to_block - from_block) // CHUNK_SIZE + 1
    cursor = from_block
    chunk_num = 0
    while cursor <= to_block:
        chunk_to = min(cursor + CHUNK_SIZE, to_block)
        chunk_num += 1
        print(f'    chunk {chunk_num}/{total_chunks}: blocks {cursor:,} → {chunk_to:,}')
        fetched = False
        for endpoint in BASE_PUBLIC_RPCS:
            res = call(endpoint, 'eth_getLogs', [{
                'fromBlock': hex(cursor),
                'toBlock':   hex(chunk_to),
                'address':   GOV_CONTRACT,
                'topics':    [BOND_BROKEN_TOPIC],
            }])
            if res and 'result' in res and res['result'] is not None:
                all_logs.extend(res['result'])
                print(f'      → {len(res["result"])} logs via {endpoint.split("/")[2]}')
                fetched = True
                break
            elif res and 'error' in res:
                print(f'      [WARN] {endpoint.split("/")[2]}: {res["error"].get("message","")[:80]}')
        if not fetched:
            print(f'      [ERROR] all RPCs failed for this chunk — skipping')
        cursor = chunk_to + 1
    return all_logs


def decode_events(logs, current_block):
    events = []
    for log in logs:
        data = log.get('data', '0x')
        try:
            amount     = int(data[2:66], 16) / DECIMALS
            blk_num    = int(log.get('blockNumber', '0x0'), 16)
            secs_ago   = (current_block - blk_num) / 2.0
            event_dt   = datetime.now(timezone.utc) - timedelta(seconds=secs_ago)
            events.append({
                'date':   event_dt.date().isoformat(),
                'amount': round(amount, 2),
                'tx':     log.get('transactionHash', ''),
            })
        except Exception as e:
            print(f'  [WARN] could not decode log: {e}')
    return events


def main():
    # Parse --days argument (default 1)
    days = 1
    for i, arg in enumerate(sys.argv[1:]):
        if arg.startswith('--days='):
            days = int(arg.split('=')[1])
        elif arg == '--days' and i + 1 < len(sys.argv[1:]):
            days = int(sys.argv[i + 2])
    days = max(1, min(days, 7))

    print(f'=== Bootstrap BondBroken — last {days} day(s) ===')
    print(f'Chunk size: {CHUNK_SIZE:,} blocks (~{CHUNK_SIZE // BLOCKS_PER_DAY * 24:.0f}h per chunk)')

    if not OUTPUT_FILE.exists():
        print(f'ERROR: {OUTPUT_FILE} not found. Run from repo root.', file=sys.stderr)
        sys.exit(1)

    history = json.loads(OUTPUT_FILE.read_text(encoding='utf-8'))
    history.setdefault('bond_events', [])
    existing_tx = {e['tx'] for e in history['bond_events']}
    print(f'Existing bond_events in JSON: {len(history["bond_events"])}')

    current_block = get_current_block()
    print(f'Current block: {current_block:,}\n')

    all_new = []
    for day_offset in range(days):
        to_block   = current_block - day_offset * BLOCKS_PER_DAY
        from_block = max(0, to_block - BLOCKS_PER_DAY)
        target_date = (date.today() - timedelta(days=day_offset)).isoformat()
        print(f'Day {day_offset + 1}/{days} — {target_date} (blocks {from_block:,} → {to_block:,})')

        logs   = fetch_logs_chunked(from_block, to_block)
        events = decode_events(logs, current_block)
        new    = [e for e in events if e['tx'] not in existing_tx]
        print(f'  → {len(events)} events found, {len(new)} new\n')

        for e in new:
            existing_tx.add(e['tx'])
            all_new.append(e)

    print(f'Total new BondBroken events: {len(all_new)}')

    if not all_new:
        print('Nothing new to save.')
        return

    history['bond_events'].extend(all_new)
    history['bond_events'].sort(key=lambda x: x['date'], reverse=True)

    # Recompute unbonding queue (last 7 days)
    cutoff7d    = (date.today() - timedelta(days=7)).isoformat()
    active      = [e for e in history['bond_events'] if e['date'] >= cutoff7d]
    queue_total = round(sum(e['amount'] for e in active), 2)
    print(f'Unbonding queue (7d active): {queue_total:,.2f} RIZE from {len(active)} events')

    # Update or append today's unbonding entry
    today   = date.today().isoformat()
    updated = False
    for entry in history.get('unbonding', []):
        if entry['date'] == today:
            entry['value'] = queue_total
            updated = True
            break
    if not updated:
        history.setdefault('unbonding', []).append({'date': today, 'value': queue_total})

    history.setdefault('metadata', {})['updated'] = datetime.now(timezone.utc).isoformat()
    OUTPUT_FILE.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'\n✅ Saved — {len(history["bond_events"])} total bond_events in JSON')


if __name__ == '__main__':
    main()
