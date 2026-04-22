"""
bootstrap_bond_events.py
========================
Test : fetch BondBroken events for TODAY only via Alchemy eth_getLogs.
One single eth_getLogs call — minimal quota usage.

If this works, run again with --days 2, --days 3 ... up to --days 7
to backfill the full 7-day unbonding window.
"""

import json, os, sys, urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

GOV_CONTRACT      = '0x5a134098bDBEb05Da9eAc35439c5624547ed26eE'
DECIMALS          = 1e18
OUTPUT_FILE       = Path('rize-data-hub/conviction-history.json')
ALCHEMY_URL       = os.environ.get('ALCHEMY_RPC_URL', '')
BOND_BROKEN_TOPIC = '0xc23747277531c745e0e6b38cafe2803258edc500eee3dffa3f081b89d9970096'
BLOCKS_PER_DAY    = 172_800  # Base ~2 blocks/sec


def rpc(method, params):
    if not ALCHEMY_URL:
        print('ERROR: ALCHEMY_RPC_URL not set', file=sys.stderr)
        sys.exit(1)
    payload = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}).encode()
    req = urllib.request.Request(
        ALCHEMY_URL, data=payload,
        headers={'Content-Type': 'application/json', 'User-Agent': 'Tokerize-Bot/1.0'}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f'  RPC error: {e}', file=sys.stderr)
        return None


def get_current_block():
    res = rpc('eth_blockNumber', [])
    if res and res.get('result'):
        return int(res['result'], 16)
    print('ERROR: could not get current block', file=sys.stderr)
    sys.exit(1)


def fetch_bond_broken(from_block, to_block):
    """Single eth_getLogs call for BondBroken events in block range."""
    print(f'  eth_getLogs blocks {from_block} → {to_block} ({to_block - from_block:,} blocks) …')
    res = rpc('eth_getLogs', [{
        'fromBlock': hex(from_block),
        'toBlock':   hex(to_block),
        'address':   GOV_CONTRACT,
        'topics':    [BOND_BROKEN_TOPIC],
    }])
    if not res:
        print('  ERROR: no response from Alchemy')
        return []
    if 'error' in res:
        print(f'  ERROR from Alchemy: {res["error"]}')
        return []
    logs = res.get('result', [])
    print(f'  → {len(logs)} BondBroken events found')

    events = []
    for log in logs:
        # nftId is topics[1] (indexed), amount is data (non-indexed, 32 bytes)
        data = log.get('data', '0x')
        try:
            amount     = int(data[2:66], 16) / DECIMALS
            blk_num    = int(log.get('blockNumber', '0x0'), 16)
            blocks_ago = to_block - blk_num
            secs_ago   = blocks_ago / 2.0
            event_dt   = datetime.now(timezone.utc) - timedelta(seconds=secs_ago)
            event_date = event_dt.date().isoformat()
            events.append({
                'date':   event_date,
                'amount': round(amount, 4),
                'tx':     log.get('transactionHash', ''),
            })
        except Exception as e:
            print(f'  [WARN] could not decode log: {e}')
    return events


def main():
    # Parse --days argument (default 1 = today only)
    days = 1
    for arg in sys.argv[1:]:
        if arg.startswith('--days='):
            days = int(arg.split('=')[1])
        elif arg == '--days' and sys.argv.index(arg) + 1 < len(sys.argv):
            days = int(sys.argv[sys.argv.index(arg) + 1])
    days = max(1, min(days, 7))

    print(f'=== Bootstrap BondBroken — last {days} day(s) ===')

    if not OUTPUT_FILE.exists():
        print(f'ERROR: {OUTPUT_FILE} not found. Run from repo root.', file=sys.stderr)
        sys.exit(1)

    history = json.loads(OUTPUT_FILE.read_text(encoding='utf-8'))
    history.setdefault('bond_events', [])
    existing_tx = {e['tx'] for e in history['bond_events']}
    print(f'Existing bond_events in JSON: {len(history["bond_events"])}')

    current_block = get_current_block()
    print(f'Current block: {current_block:,}')

    # Fetch one day at a time — 1 eth_getLogs call per day
    all_new = []
    for day_offset in range(days):
        to_block   = current_block - day_offset * BLOCKS_PER_DAY
        from_block = max(0, to_block - BLOCKS_PER_DAY)
        target_date = (date.today() - timedelta(days=day_offset)).isoformat()
        print(f'\nDay {day_offset + 1}/{days} — {target_date}')
        events = fetch_bond_broken(from_block, to_block)
        new = [e for e in events if e['tx'] not in existing_tx]
        print(f'  → {len(new)} new (not already in JSON)')
        for e in new:
            existing_tx.add(e['tx'])
            all_new.append(e)

    print(f'\nTotal new BondBroken events: {len(all_new)}')

    if not all_new:
        print('Nothing new to save.')
        return

    history['bond_events'].extend(all_new)
    history['bond_events'].sort(key=lambda x: x['date'], reverse=True)

    # Recompute unbonding queue (events from last 7 days)
    cutoff7d    = (date.today() - timedelta(days=7)).isoformat()
    active      = [e for e in history['bond_events'] if e['date'] >= cutoff7d]
    queue_total = round(sum(e['amount'] for e in active), 4)
    print(f'Unbonding queue (7d): {queue_total:,.2f} RIZE from {len(active)} events')

    # Update today's unbonding entry if it exists, otherwise append
    today = date.today().isoformat()
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
