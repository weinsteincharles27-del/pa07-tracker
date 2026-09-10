"""Kalshi threshold ladders: margin of victory and voter turnout.

These are survival curves, not exclusive brackets, so the arithmetic that turns
them into buckets is the whole risk surface. The regression these guard is real:
the Republican rungs are DISPLAYED descending, and the first version differenced
neighbouring ROWS, which shifted every Republican bucket by one and inflated that
side from 0.235 to 0.572 — a plausible-looking distribution that summed to 1.33.
"""
import json
import support
from openpyxl import load_workbook

WB = "PA-07_House_Election_Tracker.xlsx"


def _sheet():
    return load_workbook(support.project(WB))["Margin of Victory"]


def _k3():
    return json.load(open(support.project("k3refs.json")))


def _rows_by_strike(ws, k3):
    """Map (side, strike) -> row, read back out of the built sheet."""
    out = {}
    for r in range(k3["K0"], k3["KN"] + 1):
        label = ws.cell(r, 1).value or ""
        strike = ws.cell(r, 2).value
        if strike is None:
            continue
        side = "D" if "Democrat" in label else "R"
        out[(side, float(strike))] = r
    return out


def test_bucket_formulas_are_keyed_to_strikes_not_row_order():
    ws, k3 = _sheet(), _k3()
    rows = _rows_by_strike(ws, k3)
    assert rows, "no ladder rows found"
    for side in ("D", "R"):
        strikes = sorted(s for (sd, s) in rows if sd == side)
        assert strikes, "no %s rungs" % side
        for i, st in enumerate(strikes):
            r = rows[(side, st)]
            f = ws.cell(r, 7).value or ""
            if i + 1 < len(strikes):
                nxt = rows[(side, strikes[i + 1])]
                # P(>= st) - P(>= next strike OUT), whatever row that lands on
                assert "E%d-E%d" % (r, nxt) in f.replace(" ", ""), \
                    "%s>=%g bucket should difference row %d against row %d, got %s" % (
                        side, st, r, nxt, f)
            else:
                # outermost rung is open-ended: its own probability, undifferenced
                assert "E%d" % r in f and "-E" not in f.replace(" ", ""), \
                    "%s>=%g is the outermost rung and must not be differenced: %s" % (side, st, f)


def test_republican_side_is_displayed_descending():
    """The layout that caused the bug is deliberate — keep it, and keep it tested."""
    ws, k3 = _sheet(), _k3()
    rows = _rows_by_strike(ws, k3)
    r_rows = sorted((r, s) for (sd, s), r in rows.items() if sd == "R")
    strikes_in_row_order = [s for _, s in r_rows]
    assert strikes_in_row_order == sorted(strikes_in_row_order, reverse=True), \
        "Republican rungs should read descending: %s" % strikes_in_row_order


def test_zero_to_three_buckets_reference_the_innermost_rung():
    ws, k3 = _sheet(), _k3()
    rows = _rows_by_strike(ws, k3)
    for side, ref_row in (("R", k3["R03"]), ("D", k3["D03"])):
        inner = rows[(side, min(s for (sd, s) in rows if sd == side))]
        f = (ws.cell(ref_row, 7).value or "").replace(" ", "")
        assert "E%d" % inner in f, \
            "%s 0-3 bucket must difference the winner market against the innermost rung " \
            "(row %d), got %s" % (side, inner, f)
        assert "MAX(0," in f, "%s 0-3 bucket must clamp: two independent markets can invert" % side


def test_zero_to_three_buckets_use_their_own_side_of_the_winner_market():
    """A side swap here — R reading the Democratic winner cell — would leave every
    formula shaped correctly and every total plausible, so nothing else catches it."""
    ws, k3 = _sheet(), _k3()
    refs = json.load(open(support.project("refs.json")))
    for side, row, want, wrong in (("R", k3["R03"], refs["K_MID_R"], refs["K_MID_D"]),
                                   ("D", k3["D03"], refs["K_MID_D"], refs["K_MID_R"])):
        f = (ws.cell(row, 7).value or "").replace(" ", "")
        assert "Kalshi!E%d" % want in f, \
            "%s 0-3 must read the %s winner row (E%d), got %s" % (side, side, want, f)
        assert "Kalshi!E%d" % wrong not in f, \
            "%s 0-3 is reading the OTHER party's winner row (E%d): %s" % (side, wrong, f)


def test_tossup_buckets_sit_in_the_middle_of_the_axis():
    """The ladder is one continuous axis from a big R win to a big D win, and a bar
    chart of it should read as a distribution — not a spike at the far right."""
    ws, k3 = _sheet(), _k3()
    rows = _rows_by_strike(ws, k3)
    r_rows = [r for (sd, _s), r in rows.items() if sd == "R"]
    d_rows = [r for (sd, _s), r in rows.items() if sd == "D"]
    assert max(r_rows) < k3["R03"] < k3["D03"] < min(d_rows), (
        "expected R rungs, R 0-3, D 0-3, then D rungs; got R=%s R03=%d D03=%d D=%s"
        % (sorted(r_rows), k3["R03"], k3["D03"], sorted(d_rows)))


def test_negative_bucket_is_clamped_not_rendered():
    """P(R>=3) sat above P(R wins) on 30 Aug 2026. A probability of -1.5% must
    never reach the distribution; the consistency check reports it instead."""
    ws, k3 = _sheet(), _k3()
    for row in (k3["R03"], k3["D03"]):
        assert "MAX(0," in (ws.cell(row, 7).value or "")


def test_turnout_ladder_has_a_residual_row_below_the_lowest_threshold():
    wb = load_workbook(support.project(WB))
    ws, k3 = wb["Voter Turnout"], _k3()
    f = (ws.cell(k3["T0"], 7).value or "").replace(" ", "")
    assert "1-E" in f, "the below-lowest-threshold bucket is the residual 1-P(above it): %s" % f


def test_collect3_flags_a_non_monotone_ladder():
    """P(x >= 6) can never exceed P(x >= 3). If it does, a derived bucket goes
    negative and the distribution is meaningless — say so rather than render it."""
    with support.sandbox(), support.fake_network() as up:
        up.invert_mov_rung = True
        support.run_script("collect3.py")
        d3 = support.read_json("data3.json")
    assert any(p["kind"] == "non_monotone_ladder" for p in d3["problems"]), d3["problems"]


def test_collect3_survives_a_delisted_event():
    """These settle on 3 Nov 2026; a vanished event must not kill the collector."""
    with support.sandbox(), support.fake_network() as up:
        up.missing_events = {"KXMIDTERMVOTETURN-PA07"}
        support.run_script("collect3.py")
        d3 = support.read_json("data3.json")
    assert any(p["kind"] == "missing_event" for p in d3["problems"]), d3["problems"]
    assert d3["turnout"]["rungs"] == []
    assert d3["mov_d"]["rungs"], "the other ladders should still have been collected"
