// api/basescan.js — Vercel Serverless Function
// Uses Basescan API (native Base chain API) — free tier

export default async function handler(req, res) {
  const params = new URLSearchParams();

  for (const [key, val] of Object.entries(req.query || {})) {
    params.set(key, val);
  }

  params.set('apikey', process.env.BASESCAN_API_KEY || '');

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

  const apiUrl = `https://api.basescan.org/api?${params.toString()}`;

  try {
    const resp = await fetch(apiUrl, {
      headers: { 'Accept': 'application/json', 'User-Agent': 'Mozilla/5.0' }
    });
    if (!resp.ok) {
      return res.status(resp.status).json({ error: `API HTTP ${resp.status}` });
    }
    const data = await resp.json();
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Cache-Control', 'public, s-maxage=30, stale-while-revalidate=60');
    return res.status(200).json(data);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
}
