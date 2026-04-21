"""
bootstrap_conviction.py
=======================
One-time script — builds conviction-history.json from scratch via Alchemy.

Run once:
    python bootstrap_conviction.py

Builds:
  - bonded[]     : daily RIZE bonded in governance (from first block to yesterday)
  - cex[]        : daily RIZE on exchanges (from first block to yesterday)  
  - unbonding[]  : daily unbonding queue value (starts today — live only)
  - whales[]     : all transfers > 5M RIZE in last 30 days
"""

import json, os, time, urllib.request
from datetime import date, datetime, timedelta, timezone
from collections import defaultdict
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
# Block 30245406 = first governance contract tx (hex)
GENESIS_BLOCK = '0x1CE2E5E'

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
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f'  RPC error: {e}')
        return None


def fetch_transfers(from_addr=None, to_addr=None, label='', from_block=GENESIS_BLOCK):
    """Fetch all ERC20 RIZE transfers via alchemy_getAssetTransfers."""
    all_txs = []
    page_key = None
    while True:
        params = {
            'fromBlock': from_block,
            'toBlock': 'latest',
            'contractAddresses': [RIZE_TOKEN],
            'category': ['erc20'],
            'withMetadata': True,
            'excludeZeroValue': True,
            'maxCount': '0x3e8',
            'order': 'asc',
        }
        if from_addr: params['fromAddress'] = from_addr
        if to_addr:   params['toAddress']   = to_addr
        if page_key:  params['pageKey']     = page_key

        res = rpc('alchemy_getAssetTransfers', [params])
        if not res or 'result' not in res:
            break
        batch = res['result'].get('transfers', [])
        all_txs.extend(batch)
        page_key = res['result'].get('pageKey')
        if not page_key:
            break
        time.sleep(0.2)

    print(f'  {label}: {len(all_txs)} transfers')
    return all_txs


def tx_date(tx):
    ts = tx.get('metadata', {}).get('blockTimestamp', '')
    return ts[:10] if ts else None


def tx_value(tx):
    v = tx.get('value')
    return float(v) if v else 0.0


def build_daily_balance(inflows, outflows, start_date, end_date):
    """Build cumulative daily balance from in/out transfers."""
    day_delta = defaultdict(float)
    for tx in inflows:
        d = tx_date(tx)
        if d: day_delta[d] += tx_value(tx)
    for tx in outflows:
        d = tx_date(tx)
        if d: day_delta[d] -= tx_value(tx)

    result = []
    balance = 0.0
    cur = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    while cur <= end:
        k = cur.isoformat()
        balance = max(0.0, balance + day_delta.get(k, 0.0))
        result.append({'date': k, 'value': round(balance, 2)})
        cur += timedelta(days=1)
    return result


def get_live_balance(address):
    """Get current token balance via balanceOf."""
    padded = '000000000000000000000000' + address[2:].lower()
    res = rpc('eth_call', [{'to': RIZE_TOKEN, 'data': '0x70a08231' + padded}, 'latest'])
    if not res or not res.get('result') or res['result'] == '0x':
        return 0.0
    try:
        return int(res['result'], 16) / DECIMALS
    except:
        return 0.0


def get_releasable():
    """Get current unbonding queue via releasableTokens()."""
    res = rpc('eth_call', [{'to': GOV_CONTRACT, 'data': '0x1c269043'}, 'latest'])
    if not res or not res.get('result') or res['result'] == '0x':
        return 0.0
    try:
        return int(res['result'], 16) / DECIMALS
    except:
        return 0.0


def main():
    OUTPUT_FILE.parent.mkdir(exist_ok=True)
    today     = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    print('=== CONVICTION BOOTSTRAP ===\n')

    # ── 1. Governance bonded history ────────────────────────────
    print('1. Fetching governance transfers...')
    gov_in  = fetch_transfers(to_addr=GOV_CONTRACT,   label='Gov inflows')
    time.sleep(0.3)
    gov_out = fetch_transfers(from_addr=GOV_CONTRACT, label='Gov outflows')
    time.sleep(0.3)

    # Find first date
    all_gov = gov_in + gov_out
    dates_gov = [tx_date(tx) for tx in all_gov if tx_date(tx)]
    start_gov = min(dates_gov) if dates_gov else today

    bonded_hist = build_daily_balance(gov_in, gov_out, start_gov, yesterday)
    print(f'  → {len(bonded_hist)} daily bonded points built')

    # Add today's live value
    print('  Fetching live bonded...')
    live_bonded = get_live_balance(GOV_CONTRACT)
    print(f'  Live bonded: {live_bonded:,.0f} RIZE')
    bonded_hist.append({'date': today, 'value': round(live_bonded, 2)})

    # ── 2. CEX history ───────────────────────────────────────────
    print('\n2. Fetching CEX transfers...')
    cex_inflows  = []
    cex_outflows = []
    for name, addr in CEX_ADDRESSES.items():
        ins  = fetch_transfers(to_addr=addr,   label=f'{name} in')
        time.sleep(0.2)
        outs = fetch_transfers(from_addr=addr, label=f'{name} out')
        time.sleep(0.2)
        # Tag each tx with address
        for tx in ins:  tx['_addr'] = addr
        for tx in outs: tx['_addr'] = addr
        cex_inflows.extend(ins)
        cex_outflows.extend(outs)

    # Build per-address daily deltas
    day_delta_per_addr = defaultdict(lambda: defaultdict(float))
    for tx in cex_inflows:
        d = tx_date(tx)
        if d: day_delta_per_addr[tx['_addr']][d] += tx_value(tx)
    for tx in cex_outflows:
        d = tx_date(tx)
        if d: day_delta_per_addr[tx['_addr']][d] -= tx_value(tx)

    all_cex_dates = set()
    for deltas in day_delta_per_addr.values():
        all_cex_dates.update(deltas.keys())

    start_cex = min(all_cex_dates) if all_cex_dates else today
    balances  = defaultdict(float)
    cex_hist  = []
    cur = date.fromisoformat(start_cex)
    end = date.fromisoformat(yesterday)
    while cur <= end:
        k = cur.isoformat()
        for addr in day_delta_per_addr:
            balances[addr] = max(0.0, balances[addr] + day_delta_per_addr[addr].get(k, 0.0))
        total = sum(balances.values())
        cex_hist.append({'date': k, 'value': round(total, 2)})
        cur += timedelta(days=1)

    # Add today's live CEX value
    print('  Fetching live CEX balances...')
    live_cex = 0.0
    for name, addr in CEX_ADDRESSES.items():
        bal = get_live_balance(addr)
        live_cex += bal
        time.sleep(0.1)
    print(f'  Live CEX total: {live_cex:,.0f} RIZE')
    cex_hist.append({'date': today, 'value': round(live_cex, 2)})
    print(f'  → {len(cex_hist)} daily CEX points built')

    # ── 3. Unbonding queue — starts today ───────────────────────
    print('\n3. Fetching live unbonding queue...')
    live_unbonding = get_releasable()
    print(f'  Unbonding queue: {live_unbonding:,.0f} RIZE')
    unbonding_hist = [{'date': today, 'value': round(live_unbonding, 2)}]

    # ── 4. Whales — last 30 days via Alchemy ────────────────────
    print('\n4. Fetching whale movements (last 30 days, >5M RIZE)...')
    cutoff = (date.today() - timedelta(days=30)).isoformat()

    # Collect all unique transfers from gov + CEX fetches
    all_txs = gov_in + gov_out + cex_inflows + cex_outflows
    seen = set()
    unique = []
    for tx in all_txs:
        h = tx.get('hash', '')
        if h and h not in seen:
            seen.add(h)
            unique.append(tx)

    cex_set = {a.lower() for a in CEX_ADDRESSES.values()}
    gov_lower = GOV_CONTRACT.lower()

    def label(addr):
        if not addr: return 'Unknown'
        a = addr.lower()
        if a == gov_lower: return 'Governance'
        for name, ca in CEX_ADDRESSES.items():
            if a == ca.lower(): return name
        return addr[:6] + '…' + addr[-4:]

    whales = []
    for tx in unique:
        v = tx_value(tx)
        d = tx_date(tx)
        if v < WHALE_MIN or not d or d < cutoff:
            continue
        whales.append({
            'date'       : d,
            'amount'     : round(v, 2),
            'from'       : tx.get('from', ''),
            'to'         : tx.get('to', ''),
            'from_label' : label(tx.get('from', '')),
            'to_label'   : label(tx.get('to', '')),
            'tx'         : tx.get('hash', ''),
        })
    whales.sort(key=lambda x: x['date'], reverse=True)
    print(f'  → {len(whales)} whale movements found')

    # ── Save ────────────────────────────────────────────────────
    history = {
        'bonded'   : bonded_hist,
        'cex'      : cex_hist,
        'unbonding': unbonding_hist,
        'whales'   : whales,
        'metadata' : {
            'token'      : RIZE_TOKEN,
            'governance' : GOV_CONTRACT,
            'cex_addresses': list(CEX_ADDRESSES.values()),
            'updated'    : datetime.now(timezone.utc).isoformat(),
        }
    }

    OUTPUT_FILE.write_text(
        json.dumps(history, indent=2, ensure_ascii=False),
        encoding='utf-8'
    )

    print(f'\n✅ Bootstrap complete:')
    print(f'   Bonded    : {len(bonded_hist)} days (from {bonded_hist[0]["date"]})')
    print(f'   CEX       : {len(cex_hist)} days (from {cex_hist[0]["date"]})')
    print(f'   Unbonding : starts {unbonding_hist[0]["date"]}')
    print(f'   Whales    : {len(whales)} movements (last 30d)')


if __name__ == '__main__':
    main()
