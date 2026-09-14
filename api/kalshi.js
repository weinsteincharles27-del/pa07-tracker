// Kalshi top of book, read server-side and handed to the page with CORS.
//
// This is a Vercel serverless function. It is not used by GitHub Pages; it
// exists so that pointing Vercel at this repository makes Kalshi truly live
// (seconds, not the ten minutes the Actions schedule manages) with no change
// to the page, which already tries /api/kalshi first. Public market data on
// Kalshi needs no key, so this deploys with no secrets at all.
//
// Cache for 30 seconds at the edge: a busy page then costs Kalshi two reads a
// minute no matter how many people have it open.

const BASE = "https://api.elections.kalshi.com/trade-api/v2/markets";
const TICKERS = { D: "HOUSEPA7-26-D", R: "HOUSEPA7-26-R" };

async function book(ticker) {
  const r = await fetch(`${BASE}/${ticker}/orderbook?depth=5`, {
    headers: { Accept: "application/json", "User-Agent": "pa07-tracker (vercel)" },
  });
  if (!r.ok) throw new Error(`Kalshi ${r.status} for ${ticker}`);
  return r.json();
}

function top(raw) {
  const ob = raw.orderbook_fp || {};
  const desc = (rows) => (rows || []).map(([p, s]) => [Number(p), Number(s)]).sort((a, b) => b[0] - a[0]);
  const yes = desc(ob.yes_dollars), no = desc(ob.no_dollars);
  const bid = yes.length ? yes[0][0] : null;
  const ask = no.length ? Math.round((1 - no[0][0]) * 1e4) / 1e4 : null;
  return {
    yes_bid: bid, yes_ask: ask,
    mid: bid !== null && ask !== null ? Math.round((bid + ask) / 2 * 1e4) / 1e4 : null,
    bid_size: yes.length ? yes[0][1] : null,
    ask_size: no.length ? no[0][1] : null,
  };
}

export default async function handler(req, res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Cache-Control", "s-maxage=30, stale-while-revalidate=60");
  try {
    const [d, r] = await Promise.all([book(TICKERS.D), book(TICKERS.R)]);
    res.status(200).json({
      at: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
      source: "vercel", tickers: TICKERS, D: top(d), R: top(r),
    });
  } catch (err) {
    res.status(502).json({ error: String(err.message || err) });
  }
}
