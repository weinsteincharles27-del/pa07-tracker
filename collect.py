import json, time, datetime, requests, kalshi

OUT = {}
PROBLEMS = []          # machine-readable; refresh.py turns these into loud alerts
PM_D = "37713776886536763857380242322222367371582682723176215910322979366716585040762"
PM_R = "56412855186822728853119072474894085602768054645914780515455268260878947887549"

def d(ts): return datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")

def problem(kind, what, detail):
    """Record a data problem rather than dying on it.

    These markets settle 3 Nov 2026 and resolved markets get renamed and re-keyed,
    so a hard KeyError here would kill the collector at exactly the moment the
    tracker is most worth reading. Degrade, but never quietly: everything recorded
    here comes back out of refresh.py as an alert.
    """
    PROBLEMS.append({"kind": kind, "what": what, "detail": detail})
    print("PROBLEM %s [%s] %s" % (kind, what, detail))

# Shapes kept whole when a side goes missing, so the builders still render a row
# of blanks instead of crashing. The date-ish fields are "" because build.py
# slices them.
PM_BLANK = {"question": None, "slug": None, "condition_id": None, "token_id": None,
            "best_bid": None, "best_ask": None, "bid_size": None, "ask_size": None,
            "last_trade": None, "volume": None, "liquidity": None,
            "one_day_change": None, "start": "", "missing": True}
K_BLANK = {"ticker": None, "event": None, "title": None, "candidate": None,
           "status": "missing", "open_time": "", "close_time": "",
           "yes_bid": None, "yes_bid_size": None, "no_bid": None, "no_bid_size": None,
           "yes_ask": None, "yes_book": [], "no_book": [], "candles": 0, "missing": True}

# ---------- Polymarket ----------
ev = kalshi.fetch("https://gamma-api.polymarket.com/events/106187").json()
def pick(markets, slug_part, label_pats):
    """Find a market by SLUG first, then by label pattern.

    groupItemTitle is a display label and Polymarket changes it: on 10 Sep 2026
    "Democratic Party" and "Republican Party" became "Bob Brooks (D)" and
    "Ryan Mackenzie (R)" mid-cycle, which broke an exact-label lookup and left
    the collector with no market at all. The slug
    (will-the-democratic-party-win-the-pa-07-house-seat) did NOT change, so it is
    the stable key; the label patterns are a second chance in case a future
    relabelling reaches the slug too.
    """
    for m in markets:
        if slug_part in (m.get("slug") or ""):
            return m, "slug"
    for m in markets:
        title = (m.get("groupItemTitle") or "")
        if any(p in title for p in label_pats):
            return m, "label"
    return None, None


mk = {m.get("groupItemTitle"): m for m in ev["markets"]}
PM_MATCH = {"D": ("democratic-party", ("Democratic Party", "(D)")),
            "R": ("republican-party", ("Republican Party", "(R)"))}
OUT["pm_event"] = {"title": ev["title"], "slug": ev["slug"], "endDate": ev["endDate"],
                   "volume": ev.get("volume"), "liquidity": ev.get("liquidity")}
OUT["pm_meta"] = {}
pm_hist = {}
for side in ("D", "R"):
    slug_part, label_pats = PM_MATCH[side]
    m, how = pick(ev["markets"], slug_part, label_pats)
    if m is None:
        problem("missing_pm_market", slug_part,
                "Polymarket winner event no longer returns a %s market by slug (*%s*) or by "
                "label %s — settlement or relabeling suspected. Markets present: %s"
                % (side, slug_part, list(label_pats),
                   ", ".join(sorted(str(x) for x in mk)) or "(none)"))
        OUT["pm_meta"][side] = dict(PM_BLANK, token_id=PM_D if side=="D" else PM_R)
        continue
    if how == "label":
        problem("pm_slug_changed", slug_part,
                "Polymarket %s market was found by LABEL, not slug — the slug no longer "
                "contains '%s'. Still collected, but the stable key has moved and the "
                "matcher should be updated." % (side, slug_part))
    tok = PM_D if side=="D" else PM_R
    book = kalshi.fetch("https://clob.polymarket.com/book", {"token_id": tok}).json()
    bids = sorted([(float(x["price"]), float(x["size"])) for x in book.get("bids",[])], reverse=True)
    asks = sorted([(float(x["price"]), float(x["size"])) for x in book.get("asks",[])])
    OUT["pm_meta"][side] = {
        "question": m["question"], "slug": m["slug"], "condition_id": m.get("conditionId"),
        "token_id": tok,
        "best_bid": bids[0][0] if bids else None, "best_ask": asks[0][0] if asks else None,
        "bid_size": bids[0][1] if bids else None, "ask_size": asks[0][1] if asks else None,
        "last_trade": m.get("lastTradePrice"), "volume": m.get("volumeNum"),
        "liquidity": m.get("liquidityNum"), "one_day_change": m.get("oneDayPriceChange"),
        "start": m.get("startDate"),
    }

# History is keyed by token, not by label, so it is still worth pulling even if a
# market got relabelled out from under the lookup above.
for side, tok in (("D",PM_D), ("R",PM_R)):
    try:
        h = kalshi.field(kalshi.fetch("https://clob.polymarket.com/prices-history",
                                      {"market": tok, "interval":"max", "fidelity":1440},
                                      timeout=60), "history")
        for p in h:
            pm_hist.setdefault(d(p["t"]), {})[side] = p["p"]   # last write wins = latest that day
    except (kalshi.ApiError, kalshi.SchemaError) as e:
        problem("pm_history_fetch_failed", side,
                "daily price history for the %s winner market did not come back: %s" % (side, e))
OUT["pm_history"] = pm_hist

# ---------- Kalshi ----------
now = int(time.time()); start = now - 500*86400
OUT["k_meta"] = {}
k_hist = {}
for side, tk in (("D","HOUSEPA7-26-D"), ("R","HOUSEPA7-26-R")):
    try:
        m = kalshi.field(kalshi.get("/trade-api/v2/markets/"+tk), "market")
        ob = kalshi.field(kalshi.get("/trade-api/v2/markets/%s/orderbook"%tk, {"depth":10}), "orderbook_fp")
    except (kalshi.ApiError, kalshi.SchemaError) as e:
        problem("missing_kalshi_market", tk,
                "Kalshi winner market %s no longer resolves — delist, re-ticker or settlement "
                "suspected: %s" % (tk, e))
        OUT["k_meta"][side] = dict(K_BLANK, ticker=tk)
        continue
    yb = sorted([(float(p), float(s)) for p,s in (ob.get("yes_dollars") or [])], reverse=True)
    nb = sorted([(float(p), float(s)) for p,s in (ob.get("no_dollars") or [])], reverse=True)
    OUT["k_meta"][side] = {
        "ticker": tk, "event": m.get("event_ticker"), "title": m.get("title"),
        "candidate": m.get("yes_sub_title"), "status": m.get("status"),
        "open_time": m.get("open_time"), "close_time": m.get("close_time"),
        "yes_bid": yb[0][0] if yb else None, "yes_bid_size": yb[0][1] if yb else None,
        "no_bid": nb[0][0] if nb else None, "no_bid_size": nb[0][1] if nb else None,
        "yes_ask": round(1-nb[0][0], 4) if nb else None,
        "yes_book": yb[:5], "no_book": nb[:5],
    }
    cs = []
    try:
        cs = kalshi.field(kalshi.get("/trade-api/v2/series/HOUSEPA7/markets/%s/candlesticks"%tk,
                                     {"start_ts":start, "end_ts":now, "period_interval":1440}),
                          "candlesticks")
    except (kalshi.ApiError, kalshi.SchemaError) as e:
        problem("kalshi_history_fetch_failed", tk,
                "candlestick history for %s did not come back: %s" % (tk, e))
    for c in cs:
        day = d(c["end_period_ts"])
        pr = c.get("price") or {}
        row = k_hist.setdefault(day, {})
        row[side] = {
            "yes_bid": float(c["yes_bid"]["close_dollars"]) if c.get("yes_bid",{}).get("close_dollars") else None,
            "yes_ask": float(c["yes_ask"]["close_dollars"]) if c.get("yes_ask",{}).get("close_dollars") else None,
            "close": float(pr["close_dollars"]) if pr.get("close_dollars") else None,
            "prev":  float(pr["previous_dollars"]) if pr.get("previous_dollars") else None,
            "vol": float(c.get("volume_fp") or 0),
            "oi": float(c.get("open_interest_fp") or 0),
        }
    OUT["k_meta"][side]["candles"] = len(cs)
OUT["k_history"] = k_hist

OUT["problems"] = PROBLEMS

json.dump(OUT, open("data.json","w"), indent=1)
print("pm days:", len(pm_hist), min(pm_hist) if pm_hist else "-", max(pm_hist) if pm_hist else "-")
print("k  days:", len(k_hist), min(k_hist) if k_hist else "-", max(k_hist) if k_hist else "-")
print("PM  D bid/ask:", OUT["pm_meta"]["D"]["best_bid"], OUT["pm_meta"]["D"]["best_ask"],
      "| R:", OUT["pm_meta"]["R"]["best_bid"], OUT["pm_meta"]["R"]["best_ask"])
print("KAL D bid/ask:", OUT["k_meta"]["D"]["yes_bid"], OUT["k_meta"]["D"]["yes_ask"],
      "| R:", OUT["k_meta"]["R"]["yes_bid"], OUT["k_meta"]["R"]["yes_ask"])
if PROBLEMS:
    print("problems:", len(PROBLEMS))
