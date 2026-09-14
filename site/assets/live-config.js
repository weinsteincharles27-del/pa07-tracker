/* Where the page reads live prices from. Hand-maintained page config: the
   object below is strict JSON (tests parse it), so keep comments out here.

   Polymarket sends CORS headers and is read straight from the browser. Match
   its markets by slug, never by label: the outcomes were renamed from
   "Democratic Party" to "Bob Brooks (D)" on 10 Sep 2026 while the slugs held.

   Kalshi returns 403 to any browser request, so a server reads it and the
   page tries these endpoints in order: api/kalshi is the Vercel function in
   api/kalshi.js and only answers if the repository is deployed there; the
   raw file is rewritten every ten minutes by
   .github/workflows/kalshi-live.yml on the live-data branch. */
window.PA07_LIVE = {
  "polymarket": {
    "winner_event": "https://gamma-api.polymarket.com/events/106187",
    "margin_event": "https://gamma-api.polymarket.com/events/834502",
    "slugs": {
      "D": "will-the-democratic-party-win-the-pa-07-house-seat",
      "R": "will-the-republican-party-win-the-pa-07-house-seat"
    },
    "poll_seconds": 60
  },
  "kalshi": {
    "endpoints": [
      "api/kalshi",
      "https://raw.githubusercontent.com/weinsteincharles27-del/pa07-tracker/live-data/kalshi-live.json"
    ]
  }
};
