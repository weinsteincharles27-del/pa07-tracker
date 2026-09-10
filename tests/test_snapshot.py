"""NET-4 (one-sided or empty books) and the snapshot fields the alerts rest on."""
import os

import support

refresh = support.load("refresh")
pollsrc = support.load("pollsrc")

CSV = os.path.join(support.FIX, "house_pa07.csv")


def with_data(mutate=None):
    """Seed a sandbox from the frozen fixtures, optionally mangling data.json."""
    box = support.sandbox(data=True)
    d = box.__enter__()
    if mutate:
        data = support.read_json("data.json")
        mutate(data)
        support.write_json("data.json", data)
    return box, d


def snap(mutate=None):
    box, d = with_data(mutate)
    try:
        os.environ["PA07_POLLS_CSV"] = CSV
        with support.attrs(pollsrc, STAMP=os.path.join(d, "pollstamp.json")):
            return refresh.snapshot()
    finally:
        os.environ.pop("PA07_POLLS_CSV", None)
        box.__exit__(None, None, None)


def test_net4_both_asks_missing_yields_none_not_a_crash():
    """Empty or one-sided books are plausible at settlement. min() over an empty
    generator used to raise here — after the workbook had already been saved."""
    def blank(d):
        d["pm_meta"]["D"]["best_ask"] = None
        d["k_meta"]["D"]["yes_ask"] = None
    s = snap(blank)
    assert s["pair_ask_total"] is None


def test_net4_one_sided_book_still_prices_the_pair():
    def blank(d):
        d["pm_meta"]["D"]["best_ask"] = None      # Kalshi still quotes a D ask
    s = snap(blank)
    assert s["pair_ask_total"] is not None


def test_net4_diff_tolerates_a_none_pair_total():
    notes, alerts = refresh.diff({"pair_ask_total": 1.06}, {"pair_ask_total": None})
    assert not any("arbitrage" in a for a in alerts)


def test_snapshot_records_per_series_history_lengths():
    """DQ-3 needs per-bracket counts; a whole-map count cannot see one blank column."""
    s = snap()
    assert set(s["pm_series_days"]) == {"D", "R"}
    assert len(s["mov_series_days"]) == 10
    assert len(s["seat_series_days"]) == 8
    assert s["mov_history_days"] > 0 and s["seat_history_days"] > 0


def test_snapshot_records_poll_values_for_revision_detection():
    s = snap()
    assert s["poll_values"], "no per-poll numbers captured"
    a_general = [v for v in s["poll_values"].values() if any(k.startswith("general/") for k in v)]
    assert a_general, s["poll_values"]
    assert s["polls_total"] == 5 and s["polls_general"] == 1


def test_snapshot_surfaces_collector_problems():
    def hurt(d):
        d["problems"] = [{"kind": "missing_pm_market", "what": "Democratic Party",
                          "detail": "no longer returns a 'Democratic Party' market"}]
    s = snap(hurt)
    assert s["collector_problems"], s
    notes, alerts = refresh.diff({"run_utc": s["run_utc"]}, s)
    assert any("Democratic Party" in a for a in alerts), alerts
