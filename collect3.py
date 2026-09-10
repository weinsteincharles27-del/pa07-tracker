"""Kalshi PA-07 margin of victory and voter turnout.

Both are THRESHOLD ladders, not bracket ladders: each market pays if the value
lands at or above a strike, so probabilities must fall monotonically as the
strike rises. That shape is different from Polymarket's mutually-exclusive
brackets and is handled differently downstream — differencing adjacent
thresholds is what turns a survival curve back into buckets.

  KXMIDTERMMOV-PA07D   Democratic margin >= 3, 6, 9, 12, 15 pts
  KXMIDTERMMOV-PA07R   Republican margin >= 3, 6, 9 pts
  KXMIDTERMVOTETURN-PA07  turnout above 310K, 320K, 340K, 360K, 370K
"""
import json, time, datetime, kalshi

def d(ts):
    return datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")

OUT = {}
PROBLEMS = []


def problem(kind, what, detail):
    PROBLEMS.append({"kind": kind, "what": what, "detail": detail})
    print("PROBLEM %s [%s] %s" % (kind, what, detail))


EVENTS = [
    ("mov_d", "KXMIDTERMMOV-PA07D", "KXMIDTERMMOV", "Democratic margin"),
    ("mov_r", "KXMIDTERMMOV-PA07R", "KXMIDTERMMOV", "Republican margin"),
    ("turnout", "KXMIDTERMVOTETURN-PA07", "KXMIDTERMVOTETURN", "Voter turnout"),
]

now = int(time.time())
start = now - 500 * 86400


def top_of_book(ticker):
    """Best YES bid and the YES ask implied by the best NO bid.

    Kalshi's market object still returns null for yes_bid/yes_ask on these, the
    same as the winner markets, so top-of-book has to come from the orderbook.
    """
    try:
        ob = kalshi.get("/trade-api/v2/markets/%s/orderbook" % ticker,
                        {"depth": 5}).json().get("orderbook_fp", {})
    except Exception as e:
        problem("orderbook_fail", ticker, "Could not read the order book: %s" % e)
        return {}
    yb = sorted([(float(p), float(s)) for p, s in (ob.get("yes_dollars") or [])], reverse=True)
    nb = sorted([(float(p), float(s)) for p, s in (ob.get("no_dollars") or [])], reverse=True)
    return {"yes_bid": yb[0][0] if yb else None,
            "yes_bid_size": yb[0][1] if yb else None,
            "no_bid": nb[0][0] if nb else None,
            "yes_ask": round(1 - nb[0][0], 4) if nb else None}


for key, event, series, label in EVENTS:
    try:
        ev = kalshi.get("/trade-api/v2/events/" + event).json().get("event", {})
    except Exception as e:
        problem("missing_event", event,
                "%s event is gone (%s) — settlement or relabeling suspected. That subject "
                "will be blank in the workbook." % (label, e))
        OUT[key] = {"event": event, "title": None, "rungs": []}
        continue

    try:
        ms = kalshi.get("/trade-api/v2/markets",
                        {"event_ticker": event, "limit": 100}).json().get("markets", [])
    except Exception as e:
        problem("missing_markets", event, "%s markets could not be listed: %s" % (label, e))
        ms = []
    if not ms:
        problem("no_markets", event,
                "%s event returned no markets — nothing to track for this subject." % label)

    rungs, hist = [], {}
    for m in sorted(ms, key=lambda x: (x.get("floor_strike") if x.get("floor_strike") is not None else 0)):
        tk = m["ticker"]
        strike = m.get("floor_strike")
        if strike is None:
            problem("no_strike", tk,
                    "Market has no floor_strike, so its threshold is unknown and it is skipped.")
            continue
        rung = {"ticker": tk, "label": m.get("yes_sub_title"), "strike": float(strike),
                "status": m.get("status"), "cap": m.get("cap_strike")}
        rung.update(top_of_book(tk))
        rungs.append(rung)

        try:
            cs = kalshi.get("/trade-api/v2/series/%s/markets/%s/candlesticks" % (series, tk),
                            {"start_ts": start, "end_ts": now, "period_interval": 1440}
                            ).json()["candlesticks"]
        except Exception as e:
            problem("history_fail", tk,
                    "Daily history for %s failed (%s), so its column is empty for this run — "
                    "blank here means missing, not zero." % (tk, e))
            continue
        for c in cs:
            yb = (c.get("yes_bid") or {}).get("close_dollars")
            ya = (c.get("yes_ask") or {}).get("close_dollars")
            if yb is None and ya is None:
                continue
            hist.setdefault(d(c["end_period_ts"]), {})[tk] = {
                "bid": float(yb) if yb else None, "ask": float(ya) if ya else None}

    # A threshold ladder that is not monotone is mispriced or misread: P(x >= 6)
    # can never exceed P(x >= 3). Worth saying out loud rather than quietly
    # rendering a distribution with a negative bucket in it.
    mids = [(r["strike"], (r["yes_bid"] + r["yes_ask"]) / 2)
            for r in rungs if r.get("yes_bid") is not None and r.get("yes_ask") is not None]
    for (s1, p1), (s2, p2) in zip(mids, mids[1:]):
        if p2 > p1 + 1e-9:
            problem("non_monotone_ladder", event,
                    "%s: P(>=%g) = %.3f is higher than P(>=%g) = %.3f. A threshold ladder must "
                    "fall as the strike rises, so a derived bucket here is negative."
                    % (label, s2, p2, s1, p1))

    OUT[key] = {"event": event, "series": series, "label": label,
                "title": ev.get("title"), "sub_title": ev.get("sub_title"),
                "rungs": rungs}
    OUT[key + "_history"] = hist

OUT["problems"] = PROBLEMS
json.dump(OUT, open("data3.json", "w"), indent=1)

for key, event, series, label in EVENTS:
    n = len(OUT[key]["rungs"])
    h = OUT.get(key + "_history") or {}
    print("%-8s %-26s rungs=%d hist days=%d %s"
          % (key, event, n, len(h), (min(h), max(h)) if h else ""))
if PROBLEMS:
    print("problems:", len(PROBLEMS))
