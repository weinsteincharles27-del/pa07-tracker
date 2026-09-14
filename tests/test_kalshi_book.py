"""The unsigned book reader that feeds the live Kalshi row on the site.

It runs on a bare GitHub runner with only the standard library, so it is
tested the same way: urllib is stubbed, nothing else is imported."""
import io
import json
import urllib.request

import support

kb = support.load("kalshi_book")


class Stub(object):
    def __init__(self, books):
        self.books = books
        self.urls = []

    def __call__(self, req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else req
        self.urls.append(url)
        ticker = url.split("/markets/")[1].split("/")[0]
        return io.BytesIO(json.dumps(self.books[ticker]).encode())


def test_yes_ask_is_one_minus_the_best_no_bid_and_top_is_by_price_not_order():
    """Kalshi lists levels in whatever order it likes; the best level is the
    highest price on each side, never the first row."""
    raw = {"orderbook_fp": {"yes_dollars": [["0.70", "5"], ["0.74", "160"], ["0.72", "9"]],
                            "no_dollars": [["0.20", "1"], ["0.25", "90.86"], ["0.24", "8"]]}}
    t = kb.top(raw)
    assert t["yes_bid"] == 0.74 and t["bid_size"] == 160
    assert t["yes_ask"] == 0.75 and t["ask_size"] == 90.86
    assert t["mid"] == 0.745


def test_an_empty_side_is_null_not_zero():
    t = kb.top({"orderbook_fp": {"yes_dollars": [], "no_dollars": [["0.30", "1"]]}})
    assert t["yes_bid"] is None and t["mid"] is None and t["yes_ask"] == 0.7
    t = kb.top({})
    assert t == {"yes_bid": None, "yes_ask": None, "mid": None, "bid_size": None, "ask_size": None}


def test_snapshot_reads_both_tickers_unsigned_and_stamps_utc():
    stub = Stub({"HOUSEPA7-26-D": {"orderbook_fp": {"yes_dollars": [["0.74", "1"]], "no_dollars": [["0.25", "1"]]}},
                 "HOUSEPA7-26-R": {"orderbook_fp": {"yes_dollars": [["0.28", "1"]], "no_dollars": [["0.71", "1"]]}}})
    with support.attrs(urllib.request, urlopen=stub):
        s = kb.snapshot()
    assert sorted(stub.urls) == [kb.BASE + "/HOUSEPA7-26-D/orderbook?depth=5",
                                 kb.BASE + "/HOUSEPA7-26-R/orderbook?depth=5"]
    assert s["D"]["mid"] == 0.745 and s["R"]["mid"] == 0.285
    assert s["at"].endswith("Z") and "T" in s["at"]
    assert s["source"] == "github-actions"
    # the page keys on these names
    assert set(s) >= {"at", "source", "D", "R", "tickers"}


def test_the_vercel_function_returns_the_same_shape():
    """The page cannot tell which server answered, so both must agree on the
    field names. Checked textually: there is no node on this machine."""
    fn = open(support.script("api/kalshi.js")).read()
    for key in ("yes_bid", "yes_ask", "mid", "bid_size", "ask_size", "at:", "source:", "tickers"):
        assert key in fn, key
    assert "Access-Control-Allow-Origin" in fn
