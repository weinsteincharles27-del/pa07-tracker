"""RSA-PSS request signing for the Kalshi trade API.

Also the home of the shared HTTP helper the collectors use for their unsigned
Polymarket calls: kalshi.py is the only module collect.py and collect2.py both
already import, so the retry/status logic lives here rather than in a third file.

Every request goes through one place that

  * retries transient failures (timeouts, connection resets, 5xx, 429) with a
    short exponential backoff — a refresh makes ~30 sequential calls and one
    blip should not lose the whole scheduled run, and
  * checks status_code before anybody calls .json(), so a revoked key or a bad
    gateway reads as "401 from Kalshi: ..." instead of surfacing as a bare
    KeyError several frames later with the real message never logged.

A 4xx is a real answer, not a blip, so it is never retried.
"""
import base64, time, json, os, sys, urllib.parse
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

def _key_id():
    """Kalshi access-key id, from the environment or a local file.

    It is an identifier rather than a secret, but this repository is meant to be
    public and there is no reason to publish it beside the knowledge that a
    matching private key exists. KALSHI_KEY_ID lets CI supply it as a secret.
    """
    env = os.environ.get("KALSHI_KEY_ID")
    if env:
        return env.strip()
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kalshi_key_id.txt")
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        raise SystemExit(
            "FATAL: no Kalshi key id. Set KALSHI_KEY_ID, or put the id in %s." % path)


KEY_ID = _key_id()
BASE = "https://api.elections.kalshi.com"

ATTEMPTS = 3            # total tries per request
BACKOFF = 1.0           # seconds before the first retry, doubled after that
RETRY_STATUS = (408, 425, 429, 500, 502, 503, 504)

KEY_PATH = os.environ.get("KALSHI_KEY_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "kalshi_key.pem"))
with open(KEY_PATH, "rb") as f:
    PK = serialization.load_pem_private_key(f.read(), password=None)


class ApiError(RuntimeError):
    """A request that never came back as a usable 2xx.

    Carries the status code and a slice of the body, so status.json names the
    actual failure instead of whatever KeyError it would have caused downstream.
    """

    def __init__(self, venue, url, status, body):
        self.venue, self.url, self.status, self.body = venue, url, status, body
        if not status:
            head = "no response from %s: %s" % (venue, url)
        else:
            head = "%d from %s: %s" % (status, venue, url)
            if status in (401, 403) and venue == "Kalshi":
                head += ("  [check the key is not revoked, that KEY_ID matches the PEM, and "
                         "that the clock is right — the signature covers a ms timestamp]")
        RuntimeError.__init__(self, head + "\n  " + " ".join((body or "").split())[:400])


class SchemaError(RuntimeError):
    """A 2xx response whose shape is not the one the collector expects."""


def _send(build, venue, url):
    """Run build() with retries. build() is a thunk, not a prepared request, so
    a retried Kalshi call re-signs with a fresh timestamp rather than replaying
    a stale one."""
    delay = BACKOFF
    for attempt in range(1, ATTEMPTS + 1):
        try:
            r = build()
        except (requests.Timeout, requests.ConnectionError) as e:
            if attempt == ATTEMPTS:
                raise ApiError(venue, url, 0, "%s: %s" % (type(e).__name__, e))
        else:
            if 200 <= r.status_code < 300:
                return r
            if r.status_code not in RETRY_STATUS or attempt == ATTEMPTS:
                raise ApiError(venue, url, r.status_code, r.text)
        time.sleep(delay)
        delay *= 2


def get(path, params=None):
    """Signed GET against the Kalshi trade API. Raises ApiError on non-2xx."""
    url = BASE + path

    def send():
        ts = str(int(time.time() * 1000))
        msg = (ts + "GET" + path).encode()
        sig = PK.sign(msg,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256())
        h = {"KALSHI-ACCESS-KEY": KEY_ID,
             "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode(),
             "KALSHI-ACCESS-TIMESTAMP": ts,
             "Accept": "application/json"}
        return requests.get(url, headers=h, params=params, timeout=30)

    return _send(send, "Kalshi", url)


def fetch(url, params=None, timeout=30, venue="Polymarket"):
    """Unsigned GET with the same retry and status checking. Raises ApiError."""
    return _send(lambda: requests.get(url, params=params, timeout=timeout), venue, url)


def field(resp, key):
    """Pull a required top-level key out of a JSON body.

    Only reached once the status is known good, so a miss here means the shape
    really did change — say so, with the URL and the keys we did get.
    """
    try:
        j = resp.json()
    except ValueError:
        raise SchemaError("%s returned non-JSON (%d): %s"
                          % (resp.url, resp.status_code, resp.text[:200]))
    if not isinstance(j, dict) or key not in j:
        got = sorted(j)[:12] if isinstance(j, dict) else type(j).__name__
        raise SchemaError("%s: no %r in the response (got %s)" % (resp.url, key, got))
    return j[key]


if __name__ == "__main__":
    r = get("/trade-api/v2/exchange/status")
    print("status:", r.status_code, r.text[:200])
