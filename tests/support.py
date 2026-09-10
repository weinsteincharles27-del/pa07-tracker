"""Shared scaffolding for the PA-07 tracker tests.

Everything here is offline. The single seam into the network is requests.get,
which the fakes below replace; nothing in this suite opens a socket.

Set PA07_TEST_SRC to a directory holding a pristine copy of the tracker to run
the same suite against unfixed code — that is how each test was confirmed to
fail before its fix and pass after.
"""
import contextlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures")
SRC = os.environ.get("PA07_TEST_SRC") or ROOT

os.environ.setdefault("KALSHI_KEY_PATH", os.path.join(ROOT, "kalshi_key.pem"))

_loaded = {}


def load(name):
    """Import a tracker module from SRC, cached, registered under its plain name
    so the modules find each other the way they do in production."""
    if name in _loaded:
        return _loaded[name]
    here = os.getcwd()
    spec = importlib.util.spec_from_file_location(name, os.path.join(SRC, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)          # refresh.py chdirs to its own dir
    finally:
        os.chdir(here)
    _loaded[name] = mod
    return mod


def script(name):
    return os.path.join(SRC, name)


@contextlib.contextmanager
def attrs(obj, **kw):
    """Temporarily set attributes on a module or object."""
    missing = object()
    old = {k: getattr(obj, k, missing) for k in kw}
    for k, v in kw.items():
        setattr(obj, k, v)
    try:
        yield obj
    finally:
        for k, v in old.items():
            if v is missing:
                delattr(obj, k)
            else:
                setattr(obj, k, v)


@contextlib.contextmanager
def sandbox(data=False, workbook=None):
    """A throwaway working directory, made current for the duration.

    `data=True` seeds it with the frozen data.json / data2.json fixtures, so
    snapshot() has something real to read.
    """
    d = tempfile.mkdtemp(prefix="pa07-test-")
    here = os.getcwd()
    try:
        os.makedirs(os.path.join(d, "archive"))
        if data:
            for f in ("data.json", "data2.json"):
                shutil.copy(os.path.join(FIX, f), os.path.join(d, f))
        if workbook is not None:
            with open(os.path.join(d, "PA-07_House_Election_Tracker.xlsx"), "wb") as fh:
                fh.write(workbook)
        os.chdir(d)
        yield d
    finally:
        os.chdir(here)
        shutil.rmtree(d, ignore_errors=True)


def project(*parts):
    """Path inside the real project directory, for tests that inspect the built
    workbook rather than running the pipeline in a sandbox."""
    return os.path.join(ROOT, *parts)


def read_json(path):
    with open(path) as f:
        return json.load(f)


def write_json(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=1)


# --------------------------------------------------------------- fake network

class FakeResponse(object):
    def __init__(self, url, payload=None, status=200, text=None):
        self.url = url
        self.status_code = status
        self._payload = payload
        self.text = text if text is not None else json.dumps(payload)

    def json(self):
        if self._payload is None:
            raise ValueError("no JSON object could be decoded")
        return self._payload


class Upstream(object):
    """Plausible-but-frozen replies for every endpoint the collectors touch.

    Tests mutate the public attributes to inject a rename, a delist, a newly
    activated bracket or a failing history call, then run the collector for real.
    """

    PM_BRACKETS = ["Republican 6%+", "Republican 3-6%", "Republican 0-3%",
                   "Democrat 0-3%", "Democrat 3-6%", "Democrat 6-9%", "Democrat 9-12%",
                   "Democrat 12-15%", "Democrat 15-18%", "Democrat 18%+"]
    SEAT_TICKERS = ["KXHOUSEWINSTATE-PAD-B7", "KXHOUSEWINSTATE-PAD-E7", "KXHOUSEWINSTATE-PAD-E8",
                    "KXHOUSEWINSTATE-PAD-E9", "KXHOUSEWINSTATE-PAD-E10", "KXHOUSEWINSTATE-PAD-E11",
                    "KXHOUSEWINSTATE-PAD-E12", "KXHOUSEWINSTATE-PAD-A12"]

    LADDERS = {
        "KXMIDTERMMOV-PA07D": ["KXMIDTERMMOV-PA07D-P%d" % s for s in (3, 6, 9, 12, 15)],
        "KXMIDTERMMOV-PA07R": ["KXMIDTERMMOV-PA07R-P%d" % s for s in (3, 6, 9)],
        "KXMIDTERMVOTETURN-PA07": ["KXMIDTERMVOTETURN-PA07-%d" % s
                                   for s in (310000, 320000, 340000, 360000, 370000)],
    }
    LADDER_STRIKES = {t: float(t.rsplit("-", 1)[-1].lstrip("P"))
                      for ts in LADDERS.values() for t in ts}

    def __init__(self):
        # (display label, slug) — Polymarket changed the LABELS on 10 Sep 2026
        # while the slugs stayed put, so the two must be settable independently.
        self.winner_labels = ["Democratic Party", "Republican Party"]
        self.winner_slugs = ["will-the-democratic-party-win-the-pa-07-house-seat",
                             "will-the-republican-party-win-the-pa-07-house-seat"]
        self.mov_labels = list(self.PM_BRACKETS)
        self.mov_placeholders = []    # inactive slots, e.g. "Person A"
        self.seat_tickers = list(self.SEAT_TICKERS)
        self.winner_tickers = ["HOUSEPA7-26-D", "HOUSEPA7-26-R"]
        self.missing_events = set()   # event tickers that 404
        self.invert_mov_rung = False  # break ladder monotonicity on purpose
        self.status_for = {}          # url substring -> status code
        self.history_fail = set()     # token/ticker whose history call 500s
        self.calls = []

    # -- payload builders ------------------------------------------------
    def _pm_market(self, label, i):
        return {"groupItemTitle": label, "question": "Will %s win PA-07?" % label,
                "slug": (self.winner_slugs[i] if i < len(self.winner_slugs)
                         else "pa07-%d" % i), "conditionId": "0xcond%d" % i,
                "clobTokenIds": json.dumps(["tok%d" % i, "tok%dn" % i]),
                "lastTradePrice": 0.9, "volumeNum": 1000.0, "liquidityNum": 500.0,
                "oneDayPriceChange": 0.01, "startDate": "2025-12-16T18:15:39Z",
                "bestBid": 0.80, "bestAsk": 0.88,
                "active": True, "closed": False, "archived": False}

    def _pm_placeholder(self, label, i):
        """An unused outcome slot, exactly as Polymarket seeds them: flagged
        inactive, no volume, and quoted 0/1 because nothing rests on either side."""
        m = self._pm_market(label, i)
        m.update({"active": False, "volumeNum": 0.0, "liquidityNum": 0.0,
                  "lastTradePrice": 0.0, "bestBid": 0.0, "bestAsk": 1.0})
        return m

    def _book(self):
        return {"bids": [{"price": "0.80", "size": "11"}], "asks": [{"price": "0.88", "size": "51"}]}

    def _history(self):
        return {"history": [{"t": 1767225600, "p": 0.8}, {"t": 1767312000, "p": 0.82}]}

    def _candles(self):
        return {"candlesticks": [
            {"end_period_ts": 1767225600, "price": {"close_dollars": "0.80", "previous_dollars": "0.79"},
             "yes_bid": {"close_dollars": "0.72"}, "yes_ask": {"close_dollars": "0.87"},
             "volume_fp": 10, "open_interest_fp": 100},
            {"end_period_ts": 1767312000, "price": {"close_dollars": "0.81", "previous_dollars": "0.80"},
             "yes_bid": {"close_dollars": "0.73"}, "yes_ask": {"close_dollars": "0.88"},
             "volume_fp": 12, "open_interest_fp": 110}]}

    # -- the seam --------------------------------------------------------
    def get(self, url, params=None, headers=None, timeout=None, **kw):
        params = params or {}
        self.calls.append((url, dict(params)))
        for frag, code in self.status_for.items():
            if frag in url:
                return FakeResponse(url, {"error": {"code": "forced", "message": "injected %d" % code}},
                                    status=code)

        if url.endswith("/events/106187"):
            return FakeResponse(url, {
                "title": "PA-07 House winner", "slug": "pa-07-winner", "endDate": "2026-11-03T00:00:00Z",
                "volume": 1.0, "liquidity": 2.0,
                "markets": [self._pm_market(l, i) for i, l in enumerate(self.winner_labels)]})

        if url.endswith("/events/834502"):
            return FakeResponse(url, {
                "title": "PA-07 margin", "slug": "pa-07-margin", "id": 834502,
                "volume": 1.0, "liquidity": 2.0,
                "startDate": "2026-01-01T00:00:00Z", "endDate": "2026-11-03T00:00:00Z",
                "markets": ([self._pm_market(l, i) for i, l in enumerate(self.mov_labels)]
                            + [self._pm_placeholder(l, 900 + i)
                               for i, l in enumerate(self.mov_placeholders)])})

        if url.endswith("clob.polymarket.com/book"):
            return FakeResponse(url, self._book())

        if url.endswith("prices-history"):
            if params.get("market") in self.history_fail:
                return FakeResponse(url, {"error": "boom"}, status=500)
            return FakeResponse(url, self._history())

        # ---- Kalshi ----
        if "/candlesticks" in url:
            tk = url.rsplit("/markets/", 1)[-1].split("/")[0]
            if tk in self.history_fail:
                return FakeResponse(url, {"error": "boom"}, status=500)
            return FakeResponse(url, self._candles())

        if url.endswith("/orderbook"):
            tk = url.rsplit("/markets/", 1)[-1].split("/")[0]
            # A threshold ladder must fall as the strike rises; price each rung off
            # its strike so the fake data is monotone the way the real market is.
            if tk in self.LADDER_STRIKES:
                st = self.LADDER_STRIKES[tk]
                p = max(0.05, min(0.9, 0.7 - 0.04 * st)) if st < 100 else \
                    max(0.05, min(0.9, 0.9 - (st - 300000) / 100000.0))
                if self.invert_mov_rung and tk.endswith("-P6"):
                    p = 0.95      # P(>=6) above P(>=3): impossible, must be reported
                return FakeResponse(url, {"orderbook_fp": {
                    "yes_dollars": [["%.2f" % max(0.01, p - 0.02), "40"]],
                    "no_dollars": [["%.2f" % max(0.01, 1 - p - 0.02), "40"]]}})
            return FakeResponse(url, {"orderbook_fp": {"yes_dollars": [["0.72", "9"], ["0.71", "350"]],
                                                       "no_dollars": [["0.13", "25"], ["0.12", "22"]]}})

        if "/trade-api/v2/events/" in url:
            ev = url.rsplit("/", 1)[-1]
            if ev in self.missing_events:
                return FakeResponse(url, {"error": {"code": "not_found"}}, status=404)
            return FakeResponse(url, {"event": {
                "event_ticker": ev, "title": "PA-07 %s" % ev, "sub_title": "PA-07",
                "series_ticker": ev.rsplit("-", 1)[0]}})

        if "/trade-api/v2/markets/" in url:
            tk = url.rsplit("/", 1)[-1]
            if tk not in self.winner_tickers:
                return FakeResponse(url, {"error": {"code": "not_found"}}, status=404)
            return FakeResponse(url, {"market": {
                "ticker": tk, "event_ticker": "HOUSEPA7-26", "title": "PA-07",
                "yes_sub_title": "Bob Brooks", "status": "active",
                "open_time": "2025-07-01T14:00:00Z", "close_time": "2027-11-03T15:00:00Z"}})

        if url.endswith("/trade-api/v2/markets"):
            ev = params.get("event_ticker")
            if ev in self.LADDERS:
                if ev in self.missing_events:
                    return FakeResponse(url, {"markets": []})
                return FakeResponse(url, {"markets": [
                    {"ticker": t, "yes_sub_title": t.rsplit("-", 1)[-1], "status": "active",
                     "floor_strike": self.LADDER_STRIKES[t], "cap_strike": None}
                    for t in self.LADDERS[ev]]})
            if ev == "KXHOUSEWINSTATE-PAD":
                return FakeResponse(url, {"markets": [
                    {"ticker": t, "yes_sub_title": t.rsplit("-", 1)[-1], "status": "active"}
                    for t in self.seat_tickers]})
            return FakeResponse(url, {"markets": [{"ticker": "HOUSEPA7-26-D"}]})

        if url.endswith("/trade-api/v2/events"):
            return FakeResponse(url, {"events": [
                {"event_ticker": params.get("series_ticker", "X") + "-26",
                 "title": "PA-07", "sub_title": "sub"}]})

        raise AssertionError("test upstream has no rule for %s %r" % (url, params))


@contextlib.contextmanager
def fake_network(upstream=None):
    """Replace requests.get everywhere, and drop the retry backoff to zero."""
    import requests
    up = upstream or Upstream()
    kalshi = load("kalshi")
    zero = {"BACKOFF": 0.0} if hasattr(kalshi, "BACKOFF") else {}
    with attrs(requests, get=up.get), attrs(kalshi, **zero):
        yield up


def run_script(name):
    """Execute collect.py / collect2.py in the current directory, as __main__."""
    import runpy
    runpy.run_path(script(name), run_name="__main__")
