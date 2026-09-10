import json, time, datetime, requests, kalshi

def d(ts): return datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")

OUT = {}
PROBLEMS = []          # machine-readable; refresh.py turns these into loud alerts

def problem(kind, what, detail):
    """Record a data problem rather than dying on it, or losing it to stdout.

    A missing bracket used to raise KeyError and a failed history pull used to
    print and move on, leaving an empty column that renders as innocuous blanks.
    Both now leave a trace refresh.py can shout about.
    """
    PROBLEMS.append({"kind": kind, "what": what, "detail": detail})
    print("PROBLEM %s [%s] %s" % (kind, what, detail))

# ---------- Polymarket: margin of victory ladder ----------
ev = kalshi.fetch("https://gamma-api.polymarket.com/events/834502").json()
OUT["mov_event"] = {"title": ev["title"], "slug": ev["slug"], "id": ev["id"],
                    "volume": ev.get("volume"), "liquidity": ev.get("liquidity"),
                    "startDate": ev.get("startDate"), "endDate": ev.get("endDate")}
ORDER = ["Republican 6%+", "Republican 3-6%", "Republican 0-3%",
         "Democrat 0-3%", "Democrat 3-6%", "Democrat 6-9%", "Democrat 9-12%",
         "Democrat 12-15%", "Democrat 15-18%", "Democrat 18%+"]
# signed midpoint of each bracket, in margin points (D positive)
MID = {"Republican 6%+": -8.0, "Republican 3-6%": -4.5, "Republican 0-3%": -1.5,
       "Democrat 0-3%": 1.5, "Democrat 3-6%": 4.5, "Democrat 6-9%": 7.5,
       "Democrat 9-12%": 10.5, "Democrat 12-15%": 13.5, "Democrat 15-18%": 16.5,
       "Democrat 18%+": 20.0}
by = {m.get("groupItemTitle"): m for m in ev["markets"]}

def tradeable(m):
    """Is this outcome actually live, or just a placeholder sitting in the event?

    Polymarket seeds these events with unused slots — 'Person A', 'Person B',
    'Other' — carrying active=false and zero volume. They are not omissions from
    ORDER, they are outcomes nobody can trade, and alerting on them fires three
    times on every single run forever. An alert that always fires is an alert
    nobody reads, so the bar is: the venue says it is active, AND it shows either
    real volume or a genuine two-sided quote.
    """
    if not m.get("active") or m.get("closed") or m.get("archived"):
        return False
    if (m.get("volumeNum") or 0) > 0:
        return True
    bid, ask = m.get("bestBid"), m.get("bestAsk")
    return bid is not None and ask is not None and bid > 0 and ask < 1


# A bracket that exists upstream but not in ORDER is never fetched, and the
# workbook looks complete while missing part of the distribution. Say so — but
# only for one that can actually be traded.
for name, m in sorted(by.items(), key=lambda kv: str(kv[0])):
    if name in ORDER or not tradeable(m):
        continue
    problem("unexpected_pm_bracket", str(name),
            "Polymarket margin ladder lists a live, tradeable bracket '%s' that is not in ORDER, "
            "so it is not being collected — the distribution in the workbook is incomplete." % name)

OUT["mov"] = []
mov_hist = {}
for name in ORDER:
    m = by.get(name)
    if m is None:
        problem("missing_pm_bracket", name,
                "Polymarket margin ladder no longer returns a '%s' bracket — settlement or "
                "relabeling suspected. Brackets present: %s"
                % (name, ", ".join(sorted(str(x) for x in by)) or "(none)"))
        continue
    tok = json.loads(m["clobTokenIds"])[0]
    book = kalshi.fetch("https://clob.polymarket.com/book", {"token_id": tok}).json()
    bids = sorted([(float(x["price"]), float(x["size"])) for x in book.get("bids", [])], reverse=True)
    asks = sorted([(float(x["price"]), float(x["size"])) for x in book.get("asks", [])])
    OUT["mov"].append({
        "bracket": name, "midpoint": MID[name], "slug": m["slug"], "token": tok,
        "best_bid": bids[0][0] if bids else None, "best_ask": asks[0][0] if asks else None,
        "bid_size": bids[0][1] if bids else None, "ask_size": asks[0][1] if asks else None,
        "last": m.get("lastTradePrice"), "volume": m.get("volumeNum"),
        "liquidity": m.get("liquidityNum"),
    })
    try:
        h = kalshi.field(kalshi.fetch("https://clob.polymarket.com/prices-history",
                                      {"market": tok, "interval": "max", "fidelity": 1440},
                                      timeout=60), "history")
        for p in h:
            mov_hist.setdefault(d(p["t"]), {})[name] = p["p"]
    except Exception as e:
        problem("mov_history_fetch_failed", name,
                "daily history for margin bracket '%s' did not come back, so its history column "
                "is blank for this run: %s" % (name, e))
OUT["mov_history"] = mov_hist

# ---------- Kalshi: PA Democratic seat count ladder ----------
now = int(time.time()); start = now - 500 * 86400
ms = kalshi.field(kalshi.get("/trade-api/v2/markets",
                             {"event_ticker": "KXHOUSEWINSTATE-PAD", "limit": 50}), "markets")
KORD = ["KXHOUSEWINSTATE-PAD-B7", "KXHOUSEWINSTATE-PAD-E7", "KXHOUSEWINSTATE-PAD-E8",
        "KXHOUSEWINSTATE-PAD-E9", "KXHOUSEWINSTATE-PAD-E10", "KXHOUSEWINSTATE-PAD-E11",
        "KXHOUSEWINSTATE-PAD-E12", "KXHOUSEWINSTATE-PAD-A12"]
KMID = {"KXHOUSEWINSTATE-PAD-B7": 6, "KXHOUSEWINSTATE-PAD-E7": 7, "KXHOUSEWINSTATE-PAD-E8": 8,
        "KXHOUSEWINSTATE-PAD-E9": 9, "KXHOUSEWINSTATE-PAD-E10": 10, "KXHOUSEWINSTATE-PAD-E11": 11,
        "KXHOUSEWINSTATE-PAD-E12": 12, "KXHOUSEWINSTATE-PAD-A12": 13}
DEAD = ("settled", "finalized", "closed", "determined")
bym = {m["ticker"]: m for m in ms}

for tk, m in sorted(bym.items()):
    if tk in KORD or (m.get("status") or "").lower() in DEAD:
        continue
    problem("unexpected_kalshi_bracket", tk,
            "Kalshi seat ladder lists a live market %s (status %s) that is not in KORD, so it is "
            "not being collected and it carries no assumed seat count — the seat distribution in "
            "the workbook is incomplete." % (tk, m.get("status")))

OUT["seats"] = []
seat_hist = {}
for tk in KORD:
    m = bym.get(tk)
    if m is None:
        problem("missing_kalshi_bracket", tk,
                "Kalshi seat ladder no longer returns %s — delist, re-ticker or settlement "
                "suspected. Tickers present: %s" % (tk, ", ".join(sorted(bym)) or "(none)"))
        continue
    try:
        ob = kalshi.field(kalshi.get("/trade-api/v2/markets/%s/orderbook" % tk, {"depth": 5}),
                          "orderbook_fp") or {}
    except (kalshi.ApiError, kalshi.SchemaError) as e:
        problem("seat_book_fetch_failed", tk,
                "order book for seat bracket %s did not come back: %s" % (tk, e))
        ob = {}
    yb = sorted([(float(p), float(s)) for p, s in (ob.get("yes_dollars") or [])], reverse=True)
    nb = sorted([(float(p), float(s)) for p, s in (ob.get("no_dollars") or [])], reverse=True)
    OUT["seats"].append({
        "ticker": tk, "label": m.get("yes_sub_title"), "midpoint": KMID[tk],
        "yes_bid": yb[0][0] if yb else None, "yes_bid_size": yb[0][1] if yb else None,
        "no_bid": nb[0][0] if nb else None,
        "yes_ask": round(1 - nb[0][0], 4) if nb else None,
    })
    try:
        cs = kalshi.field(kalshi.get("/trade-api/v2/series/KXHOUSEWINSTATE/markets/%s/candlesticks" % tk,
                                     {"start_ts": start, "end_ts": now, "period_interval": 1440}),
                          "candlesticks")
        for c in cs:
            yb_ = (c.get("yes_bid") or {}).get("close_dollars")
            ya_ = (c.get("yes_ask") or {}).get("close_dollars")
            if yb_ is None and ya_ is None:
                continue
            seat_hist.setdefault(d(c["end_period_ts"]), {})[tk] = {
                "bid": float(yb_) if yb_ else None, "ask": float(ya_) if ya_ else None}
    except Exception as e:
        problem("seat_history_fetch_failed", tk,
                "candlestick history for seat bracket %s did not come back, so its history column "
                "is blank for this run: %s" % (tk, e))
OUT["seat_history"] = seat_hist

# ---------- Kalshi: PA-07 subject inventory ----------
inv = []
for st in ["HOUSEPA7", "KXPA07D"]:
    try:
        events = kalshi.field(kalshi.get("/trade-api/v2/events", {"series_ticker": st, "limit": 50}),
                              "events") or []
    except (kalshi.ApiError, kalshi.SchemaError) as e:
        problem("inventory_fetch_failed", st, "could not list events for series %s: %s" % (st, e))
        continue
    for e in events:
        try:
            mk = kalshi.field(kalshi.get("/trade-api/v2/markets",
                                         {"event_ticker": e["event_ticker"], "limit": 100}), "markets") or []
        except (kalshi.ApiError, kalshi.SchemaError) as err:
            problem("inventory_fetch_failed", e["event_ticker"],
                    "could not list markets for event %s: %s" % (e["event_ticker"], err))
            mk = []
        inv.append({"series": st, "event": e["event_ticker"], "title": e.get("title"),
                    "sub": e.get("sub_title"), "n_markets": len(mk),
                    "tickers": [m["ticker"] for m in mk]})
OUT["kalshi_inventory"] = inv

OUT["problems"] = PROBLEMS

json.dump(OUT, open("data2.json", "w"), indent=1)
print("MOV brackets:", len(OUT["mov"]), "| mov hist days:", len(mov_hist),
      (min(mov_hist), max(mov_hist)) if mov_hist else "")
print("Seat brackets:", len(OUT["seats"]), "| seat hist days:", len(seat_hist),
      (min(seat_hist), max(seat_hist)) if seat_hist else "")
for i in OUT["kalshi_inventory"]:
    print("  inv:", i["event"], i["title"], i["n_markets"])
if PROBLEMS:
    print("problems:", len(PROBLEMS))
