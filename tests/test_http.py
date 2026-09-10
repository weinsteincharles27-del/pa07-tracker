"""AUTH-2 / AUTH-3 / NET-3 (status is checked and reported) and NET-1 (retry)."""
import requests

import support

kalshi = support.load("kalshi")


class Recorder(object):
    """requests.get stand-in returning a scripted sequence of outcomes."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.headers = []

    def __call__(self, url, params=None, headers=None, timeout=None, **kw):
        self.headers.append(headers or {})
        out = self.outcomes[min(len(self.headers), len(self.outcomes)) - 1]
        if isinstance(out, Exception):
            raise out
        return support.FakeResponse(url, out[1], status=out[0])

    @property
    def attempts(self):
        return len(self.headers)


def test_auth2_kalshi_401_raises_with_status_and_body():
    """A revoked key must name itself, not surface as a KeyError three frames on."""
    body = {"error": {"code": "invalid_signature", "message": "signature verification failed"}}
    rec = Recorder((401, body))
    with support.attrs(requests, get=rec), support.attrs(kalshi, BACKOFF=0.0):
        try:
            kalshi.get("/trade-api/v2/markets/HOUSEPA7-26-D")
        except kalshi.ApiError as e:
            msg = str(e)
        else:
            raise AssertionError("a 401 was accepted as a usable response")
    assert "401" in msg, msg
    assert "Kalshi" in msg, msg
    assert "signature verification failed" in msg, msg
    assert rec.attempts == 1, "a 401 is a real answer and must not be retried"


def test_auth3_401_message_points_at_key_and_clock():
    """AUTH-3: the signature covers a ms timestamp, so skew looks like a 401."""
    rec = Recorder((403, {"error": "forbidden"}))
    with support.attrs(requests, get=rec), support.attrs(kalshi, BACKOFF=0.0):
        try:
            kalshi.get("/trade-api/v2/exchange/status")
        except kalshi.ApiError as e:
            msg = str(e)
        else:
            raise AssertionError("a 403 was accepted as a usable response")
    assert "clock" in msg.lower(), msg
    assert "KEY_ID" in msg, msg


def test_net3_polymarket_non_2xx_raises():
    rec = Recorder((502, {"m": "bad gateway"}))
    with support.attrs(requests, get=rec), support.attrs(kalshi, BACKOFF=0.0):
        try:
            kalshi.fetch("https://gamma-api.polymarket.com/events/106187")
        except kalshi.ApiError as e:
            msg = str(e)
        else:
            raise AssertionError("a 502 was accepted as a usable response")
    assert "502" in msg and "Polymarket" in msg, msg


def test_net1_retries_transient_failures_then_succeeds():
    """One transient blip must not lose a whole scheduled refresh."""
    rec = Recorder(requests.ConnectionError("reset"), (503, {"m": "later"}), (200, {"market": {"ok": 1}}))
    with support.attrs(requests, get=rec), support.attrs(kalshi, BACKOFF=0.0):
        r = kalshi.get("/trade-api/v2/markets/HOUSEPA7-26-D")
    assert r.status_code == 200
    assert rec.attempts == 3, rec.attempts
    # every attempt was signed afresh rather than replaying a stale timestamp
    assert all(h.get("KALSHI-ACCESS-SIGNATURE") for h in rec.headers)


def test_net1_gives_up_after_the_attempt_budget():
    rec = Recorder((503, {"m": "later"}))
    with support.attrs(requests, get=rec), support.attrs(kalshi, BACKOFF=0.0):
        try:
            kalshi.fetch("https://clob.polymarket.com/book")
        except kalshi.ApiError as e:
            assert e.status == 503
        else:
            raise AssertionError("gave back a 503 as success")
    assert rec.attempts == kalshi.ATTEMPTS


def test_net1_does_not_retry_a_4xx():
    rec = Recorder((404, {"error": "not_found"}))
    with support.attrs(requests, get=rec), support.attrs(kalshi, BACKOFF=0.0):
        try:
            kalshi.get("/trade-api/v2/markets/GONE")
        except kalshi.ApiError:
            pass
    assert rec.attempts == 1, "a 404 was retried; that only burns the timeout budget"


def test_net1_timeout_is_retried_and_finally_reported():
    rec = Recorder(requests.Timeout("timed out"))
    with support.attrs(requests, get=rec), support.attrs(kalshi, BACKOFF=0.0):
        try:
            kalshi.fetch("https://clob.polymarket.com/prices-history")
        except kalshi.ApiError as e:
            assert "Timeout" in str(e), str(e)
        else:
            raise AssertionError("a timeout was swallowed")
    assert rec.attempts == kalshi.ATTEMPTS


def test_net3_schema_miss_names_the_url_and_keys():
    """Once status is known good, a missing key is a real schema change."""
    rec = Recorder((200, {"markets": []}))
    with support.attrs(requests, get=rec), support.attrs(kalshi, BACKOFF=0.0):
        r = kalshi.get("/trade-api/v2/markets/HOUSEPA7-26-D")
        try:
            kalshi.field(r, "market")
        except kalshi.SchemaError as e:
            assert "market" in str(e) and "markets" in str(e), str(e)
        else:
            raise AssertionError("a missing top-level key passed unnoticed")
