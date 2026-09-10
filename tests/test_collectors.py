"""SCHEMA-1 (renames/delists degrade), SCHEMA-2 (unexpected live brackets) and
NET-2 (a failed per-bracket history pull leaves a trace, not just an empty column).

Each test runs the real collector against a fake upstream and asserts it neither
dies nor lies.
"""
import support


def problems(path):
    return support.read_json(path).get("problems") or []


# ------------------------------------------------------------------ SCHEMA-1

def test_schema1_a_label_rename_alone_is_survivable():
    """Polymarket renamed both winner markets on 10 Sep 2026 — "Democratic Party"
    became "Bob Brooks (D)" — and an exact-label lookup collected nothing at all.
    The slug did not move, so matching on slug rides straight through it."""
    with support.sandbox(), support.fake_network() as up:
        up.winner_labels = ["Bob Brooks (D)", "Ryan Mackenzie (R)"]
        support.run_script("collect.py")
        d = support.read_json("data.json")
    assert d["problems"] == [], "a pure label rename should be a non-event: %s" % d["problems"]
    assert d["pm_meta"]["D"]["best_bid"] == 0.80
    assert d["pm_meta"]["R"]["best_bid"] == 0.80


def test_schema1_a_slug_change_falls_back_to_the_label_and_says_so():
    """If the stable key itself moves, keep collecting via the label but flag it —
    silently depending on a fallback is how the next break goes unnoticed."""
    with support.sandbox(), support.fake_network() as up:
        up.winner_slugs = ["pa07-renamed-d", "pa07-renamed-r"]
        support.run_script("collect.py")
        d = support.read_json("data.json")
    assert any(p["kind"] == "pm_slug_changed" for p in d["problems"]), d["problems"]
    assert d["pm_meta"]["D"]["best_bid"] == 0.80, "should still have collected via the label"


def test_schema1_losing_both_slug_and_label_degrades_honestly():
    with support.sandbox(), support.fake_network() as up:
        up.winner_labels = ["Something Else", "Republican Party"]
        up.winner_slugs = ["pa07-gone", "will-the-republican-party-win-the-pa-07-house-seat"]
        support.run_script("collect.py")          # must not raise KeyError
        d = support.read_json("data.json")
    assert any(p["kind"] == "missing_pm_market" for p in d["problems"]), d["problems"]
    # the shape survives, with honest blanks rather than invented numbers
    assert d["pm_meta"]["D"]["best_bid"] is None and d["pm_meta"]["D"]["missing"] is True
    assert d["pm_meta"]["R"]["best_bid"] == 0.80
    # history is keyed by token, so it is still collected
    assert d["pm_history"], "price history was dropped along with the label"


def test_schema1_kalshi_winner_delist_does_not_kill_the_collector():
    with support.sandbox(), support.fake_network() as up:
        up.winner_tickers = ["HOUSEPA7-26-R"]     # D re-tickered / delisted -> 404
        support.run_script("collect.py")
        d = support.read_json("data.json")
    assert any(p["kind"] == "missing_kalshi_market" and p["what"] == "HOUSEPA7-26-D"
               for p in d["problems"]), d["problems"]
    assert d["k_meta"]["D"]["status"] == "missing"
    assert d["k_meta"]["R"]["yes_bid"] == 0.72, "the surviving side stopped being collected"


def test_schema1_margin_bracket_rename_does_not_kill_the_collector():
    with support.sandbox(), support.fake_network() as up:
        up.mov_labels = [l for l in up.mov_labels if l != "Democrat 18%+"]
        support.run_script("collect2.py")
        d2 = support.read_json("data2.json")
    assert any(p["kind"] == "missing_pm_bracket" and p["what"] == "Democrat 18%+"
               for p in d2["problems"]), d2["problems"]
    assert len(d2["mov"]) == 9, "the rest of the ladder should still be collected"
    assert "Democrat 18%+" not in [b["bracket"] for b in d2["mov"]]


def test_schema1_seat_ticker_delist_does_not_kill_the_collector():
    with support.sandbox(), support.fake_network() as up:
        up.seat_tickers = [t for t in up.seat_tickers if t != "KXHOUSEWINSTATE-PAD-A12"]
        support.run_script("collect2.py")
        d2 = support.read_json("data2.json")
    assert any(p["kind"] == "missing_kalshi_bracket" and p["what"] == "KXHOUSEWINSTATE-PAD-A12"
               for p in d2["problems"]), d2["problems"]
    assert len(d2["seats"]) == 7


# ------------------------------------------------------------------ SCHEMA-2

def test_schema2_newly_activated_margin_bracket_is_reported():
    with support.sandbox(), support.fake_network() as up:
        up.mov_labels = up.mov_labels + ["Democrat 21%+"]
        support.run_script("collect2.py")
        d2 = support.read_json("data2.json")
    hit = [p for p in d2["problems"] if p["kind"] == "unexpected_pm_bracket"]
    assert hit and hit[0]["what"] == "Democrat 21%+", d2["problems"]
    assert "incomplete" in hit[0]["detail"], hit[0]["detail"]


def test_schema2_inactive_placeholder_outcomes_stay_silent():
    """Polymarket seeds these events with unused slots — 'Person A', 'Person B',
    'Other' — carrying active=false and zero volume. Alerting on them fired three
    times on every single run, which is how people learn to ignore alerts."""
    with support.sandbox(), support.fake_network() as up:
        up.mov_placeholders = ["Person A", "Person B", "Other"]
        support.run_script("collect2.py")
        d2 = support.read_json("data2.json")
    hits = [p for p in d2["problems"] if p["kind"] == "unexpected_pm_bracket"]
    assert hits == [], hits
    assert len(d2["mov"]) == 10, len(d2["mov"])


def test_schema2_newly_activated_seat_bracket_is_reported():
    with support.sandbox(), support.fake_network() as up:
        up.seat_tickers = up.seat_tickers + ["KXHOUSEWINSTATE-PAD-E13"]
        support.run_script("collect2.py")
        d2 = support.read_json("data2.json")
    hit = [p for p in d2["problems"] if p["kind"] == "unexpected_kalshi_bracket"]
    assert hit and hit[0]["what"] == "KXHOUSEWINSTATE-PAD-E13", d2["problems"]


# --------------------------------------------------------------------- NET-2

def test_net2_failed_margin_history_is_recorded_not_just_printed():
    """An empty history column renders as innocuous blanks; only a recorded
    problem tells anyone the column is blank because a fetch failed."""
    with support.sandbox(), support.fake_network() as up:
        up.history_fail = {"tok9"}                # the last bracket's CLOB token
        support.run_script("collect2.py")
        d2 = support.read_json("data2.json")
    hit = [p for p in d2["problems"] if p["kind"] == "mov_history_fetch_failed"]
    assert hit, d2["problems"]
    assert hit[0]["what"] == "Democrat 18%+", hit
    # the bracket is still quoted live; it is only its history that is missing
    assert "Democrat 18%+" in [b["bracket"] for b in d2["mov"]]
    assert all("Democrat 18%+" not in day for day in d2["mov_history"].values())


def test_net2_failed_seat_history_is_recorded_not_just_printed():
    with support.sandbox(), support.fake_network() as up:
        up.history_fail = {"KXHOUSEWINSTATE-PAD-E9"}
        support.run_script("collect2.py")
        d2 = support.read_json("data2.json")
    hit = [p for p in d2["problems"] if p["kind"] == "seat_history_fetch_failed"]
    assert hit and hit[0]["what"] == "KXHOUSEWINSTATE-PAD-E9", d2["problems"]


def test_clean_run_records_no_problems():
    """The guard rails must not cry wolf on a healthy pull."""
    with support.sandbox(), support.fake_network():
        support.run_script("collect.py")
        support.run_script("collect2.py")
        assert problems("data.json") == []
        assert problems("data2.json") == []
        d2 = support.read_json("data2.json")
        assert len(d2["mov"]) == 10 and len(d2["seats"]) == 8
