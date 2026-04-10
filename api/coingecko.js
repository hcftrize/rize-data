export default async function handler(req, res) {
  // Allow requests from your frontend
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, OPTIONS");

  if (req.method === "OPTIONS") {
    return res.status(200).end();
  }

  // Rebuild the CoinGecko URL from the path + query params
  // e.g. /api/coingecko?path=/coins/markets&vs_currency=usd&ids=bitcoin
  const { path, ...params } = req.query;

  if (!path) {
    return res.status(400).json({ error: "Missing path parameter" });
  }

  const query = new URLSearchParams(params).toString();
  const url = `https://api.coingecko.com/api/v3${path}${query ? "?" + query : ""}`;

  try {
    const headers = { "Accept": "application/json" };

    // Clé API CoinGecko Demo — injectée via variable d'environnement Vercel
    if (process.env.COINGECKO_API_KEY) {
      headers["x-cg-demo-api-key"] = process.env.COINGECKO_API_KEY;
    }

    const upstream = await fetch(url, { headers });

    // Forward the status code and body as-is
    const data = await upstream.json();
    return res.status(upstream.status).json(data);

  } catch (err) {
    return res.status(500).json({ error: "Proxy error", detail: err.message });
  }
}
