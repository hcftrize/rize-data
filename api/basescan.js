// api/basescan.js — Vercel Serverless Function
// Proxies Basescan API calls server-side, keeping BASESCAN_API_KEY secret.

export default async function handler(req, res) {
  // Build params from query string
  const params = new URLSearchParams();
  
  for (const [key, val] of Object.entries(req.query || {})) {
    params.set(key, val);
  }

  // Inject API key
  params.set('apikey', process.env.BASESCAN_API_KEY || '');

  // Infer module from action if not provided
  if (!params.has('module')) {
    const action = params.get('action') || '';
    if (['tokenbalance', 'tokentx', 'balance'].includes(action)) {
      params.set('module', 'account');
    } else if (action === 'eth_call') {
      params.set('module', 'proxy');
    } else {
      params.set('module', 'account');
    }
  }

  // Use Basescan Base mainnet API endpoint
  const basescanUrl = `https://api.basescan.org/api?${params.toString()}`;

  try {
    const resp = await fetch(basescanUrl, {
      headers: { 'Accept': 'application/json', 'User-Agent': 'Mozilla/5.0' }
    });

    if (!resp.ok) {
      return res.status(resp.status).json({ error: `Basescan HTTP ${resp.status}` });
    }

    const data = await resp.json();

    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Cache-Control', 'public, s-maxage=30, stale-while-revalidate=60');
    return res.status(200).json(data);

  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
}
