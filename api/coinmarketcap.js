export default async function handler(req, res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, OPTIONS");
  if (req.method === "OPTIONS") {
    return res.status(200).end();
  }

  const { path, ...params } = req.query;
  if (!path) {
    return res.status(400).json({ error: "Missing path parameter" });
  }

  const query = new URLSearchParams(params).toString();
  const url = `https://pro-api.coinmarketcap.com${path}${query ? "?" + query : ""}`;

  try {
    const headers = {
      "Accept": "application/json",
      "X-CMC_PRO_API_KEY": process.env.CMC_API_KEY || "",
    };
    const upstream = await fetch(url, { headers });
    const data = await upstream.json();
    return res.status(upstream.status).json(data);
  } catch (err) {
    return res.status(500).json({ error: "Proxy error", detail: err.message });
  }
}
