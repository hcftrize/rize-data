// api/basescan.js — Vercel Edge Function
// Proxies Basescan API calls server-side, keeping the API key secret.
//
// Usage (from frontend):
//   GET /api/basescan?action=tokentx&address=0x...&startblock=0&endblock=99999999&sort=asc
//   GET /api/basescan?action=tokenbalance&contractaddress=0x...&address=0x...
//   GET /api/basescan?action=eth_call&to=0x...&data=0x...
//
// All params are forwarded to Basescan; the key is injected server-side.

export default async function handler(req) {
  const url = new URL(req.url);
  const params = new URLSearchParams(url.searchParams);

  // Inject API key
  params.set("apikey", process.env.BASESCAN_API_KEY || "");

  // Default module if not specified
  if (!params.has("module")) {
    // Infer module from action
    const action = params.get("action") || "";
    if (action === "tokenbalance" || action === "tokentx") {
      params.set("module", "account");
    } else if (action === "eth_call") {
      params.set("module", "proxy");
    } else {
      params.set("module", "account");
    }
  }

  const basescanUrl = `https://api.basescan.org/api?${params.toString()}`;

  try {
    const resp = await fetch(basescanUrl, {
      headers: { "Accept": "application/json" }
    });
    const data = await resp.json();

    return new Response(JSON.stringify(data), {
      status: 200,
      headers: {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "public, s-maxage=60, stale-while-revalidate=120",
      },
    });
  } catch (err) {
    return new Response(JSON.stringify({ error: err.message }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }
}

export const config = { runtime: "edge" };
