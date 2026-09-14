"""Top of book for both PA-07 winner markets on Kalshi, unsigned.

Public market data needs no key. The market object itself returns null for
yes_bid and yes_ask, so the quote comes from the order book: the best YES bid
is the top of yes_dollars, and the YES ask is one minus the best NO bid.

Written to be the whole of what the `live-data` branch runs, so it must work
with nothing but the standard library. `python3 kalshi_book.py out.json`.
"""
import datetime
import json
import sys
import urllib.request

BASE = "https://api.elections.kalshi.com/trade-api/v2/markets"
TICKERS = {"D": "HOUSEPA7-26-D", "R": "HOUSEPA7-26-R"}


def book(ticker):
    req = urllib.request.Request(BASE + "/" + ticker + "/orderbook?depth=5",
                                 headers={"Accept": "application/json",
                                          "User-Agent": "pa07-tracker (github actions)"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def top(raw):
    ob = raw.get("orderbook_fp") or {}
    yes = sorted(((float(p), float(s)) for p, s in ob.get("yes_dollars") or []), reverse=True)
    no = sorted(((float(p), float(s)) for p, s in ob.get("no_dollars") or []), reverse=True)
    bid = yes[0][0] if yes else None
    ask = round(1 - no[0][0], 4) if no else None
    mid = round((bid + ask) / 2, 4) if bid is not None and ask is not None else None
    return {"yes_bid": bid, "yes_ask": ask, "mid": mid,
            "bid_size": yes[0][1] if yes else None,
            "ask_size": no[0][1] if no else None}


def snapshot():
    out = {"at": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
           .isoformat().replace("+00:00", "Z"),
           "source": "github-actions", "tickers": TICKERS}
    for side, ticker in TICKERS.items():
        out[side] = top(book(ticker))
    return out


if __name__ == "__main__":
    snap = snapshot()
    path = sys.argv[1] if len(sys.argv) > 1 else "kalshi-live.json"
    with open(path, "w") as f:
        json.dump(snap, f, indent=1)
        f.write("\n")
    print(json.dumps({k: snap[k] for k in ("at", "D", "R")}))
