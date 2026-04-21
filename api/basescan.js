// api/basescan.js — Vercel Serverless Function
// Proxies Basescan API calls server-side, keeping BASESCAN_API_KEY secret.
//
// Frontend usage:
//   GET /api/basescan?action=tokentx&address=0x...
//   GET /api/basescan?action=tokenbalance&contractaddress=0x...&address=0x...

export default async function handler(req, res) {
  const params = new URLSearchParams(req.query);

  // Inject API key server-side
  params.set('apikey', process.env.BASESCAN_API_KEY || '');

  // Infer module from action if not set
  if (!params.has('module')) {
    const action = params.get('action') || '';
    if (['tokenbalance', 'tokentx'].includes(action)) {
      params.set('module', 'account');
    } else if (action === 'eth_call') {
      params.set('module', 'proxy');
    } else {
      params.set('module', 'account');
    }
  }

  const basescanUrl = `https://api.basescan.org/api?${params.toString()}`;

  try {
    const resp = await fetch(basescanUrl, {
      headers: { 'Accept': 'application/json' }
    });
    const data = await resp.json();

    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Cache-Control', 'public, s-maxage=60, stale-while-revalidate=120');
    res.status(200).json(data);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
}
