"""Outside sources: PollsMax forecast, City & State tracker, FEC finance.

Ordered by which would have caught a real bug. Two already did: the model-minus-
market gap read a blank model cell as 0 and reported the market price itself as
the "gap", and the cash advantage subtracted by ROW POSITION, which would flip
sign the day the FEC API returned candidates in a different order.
"""
import json
import support
from openpyxl import load_workbook

WB = "PA-07_House_Election_Tracker.xlsx"


def _wb():
    return load_workbook(support.project(WB))


def _fec():
    return json.load(open(support.project("sources", "fec.json")))


def _find(ws, needle, col=1, limit=90):
    for r in range(1, limit):
        v = ws.cell(r, col).value
        if isinstance(v, str) and needle.lower() in v.lower():
            return r
    return None


# ------------------------------------------------- silent-wrong-number guards

def test_cash_advantage_is_matched_by_name_not_row_position():
    """The FEC API returns candidates in no guaranteed order. A positional
    subtraction gives a correct-looking dollar figure with the wrong sign."""
    ws = _wb()["Campaign Finance"]
    r = _find(ws, "Cash advantage")
    assert r, "cash advantage row not found"
    f = (ws.cell(r, 2).value or "").replace(" ", "")
    assert "MATCH(" in f, "must look the candidates up by name, got %s" % f
    fec = _fec()
    dem = next(c for c in fec["candidates"]
               if c.get("receipts") is not None and c["party"].upper().startswith("DEM"))
    rep = next(c for c in fec["candidates"]
               if c.get("receipts") is not None and c["party"].upper().startswith("REP"))
    dn, rn = dem["name"].replace(" ", ""), rep["name"].replace(" ", "")
    assert dn in f and rn in f, \
        "both filed candidates should be named in the formula: %s" % f
    # the Democrat must be the minuend, or the sign silently inverts
    assert f.index(dn) < f.index(rn), \
        "Democrat must come first so a negative reads as a Republican advantage: %s" % f


def test_model_minus_market_gap_is_blank_when_the_model_is_missing():
    """An absent forecast leaves the model cell empty, and an empty cell reads as
    0 — the unguarded subtraction reported the market price itself as the gap."""
    ws = _wb()["Forecast & Aggregators"]
    r = _find(ws, "Gap (market")
    assert r, "gap row not found"
    f = (ws.cell(r, 2).value or "").replace(" ", "")
    assert "ISNUMBER" in f, "gap must be guarded against a blank model cell: %s" % f


def test_never_filed_candidates_are_not_shown_as_zero():
    """Four minor candidates never filed with the FEC. Rendering them as $0 would
    claim they raised nothing, which is a different and unsupported statement."""
    ws = _wb()["Campaign Finance"]
    fec = _fec()
    unfiled = [c["name"] for c in fec["candidates"] if c.get("receipts") is None]
    assert unfiled, "fixture should contain at least one never-filed candidate"
    for name in unfiled:
        r = _find(ws, name)
        assert r, "candidate %s missing from the sheet" % name
        assert ws.cell(r, 3).value is None, "%s receipts must be blank, not 0" % name
        assert "never filed" in str(ws.cell(r, 8).value).lower(), \
            "%s should be marked as never having filed" % name


def test_totals_ignore_unfiled_candidates_rather_than_counting_them_as_zero():
    ws = _wb()["Campaign Finance"]
    fec = _fec()
    r = next((x for x in range(1, 90)
              if str(ws.cell(x, 1).value or "").strip() == "TOTAL"), None)
    assert r, "totals row not found"
    expected = sum(c["receipts"] or 0 for c in fec["candidates"])
    # the formula sums the column; blanks contribute nothing, which is what we want
    assert "SUM(" in (ws.cell(r, 3).value or "")
    assert expected > 0


# --------------------------------------------------------- honesty guarantees

def test_city_and_state_feeds_no_calculation_anywhere():
    """It is sponsored content reselling a feed it disagrees with by ~9 points.
    It may be displayed; it must never be an input."""
    wb = _wb()
    for name in wb.sheetnames:
        ws = wb[name]
        for row in ws.iter_rows():
            for cell in row:
                v = cell.value
                if isinstance(v, str) and v.startswith("="):
                    assert "Forecast & Aggregators" not in v or "B5" not in v, \
                        "%s!%s appears to consume the tracker's cell: %s" % (name, cell.coordinate, v)


def test_campaign_finance_states_both_material_caveats_on_the_sheet():
    """Timing and what-the-money-was-for both change how the totals read. A code
    comment or a Notes-sheet line is not where a reader meets the numbers."""
    ws = _wb()["Campaign Finance"]
    text = " ".join(str(ws.cell(r, c).value) for r in range(1, 90)
                    for c in range(1, 10) if ws.cell(r, c).value).lower()
    assert "primary" in text, "the primary-vs-general spending caveat is missing from the sheet"
    assert "transfer" in text, "the joint-fundraising transfer caveat is missing from the sheet"
    assert "stale" in text or "not as-of the same date" in text, \
        "the staleness caveat is missing from the sheet"


def test_fec_coverage_date_is_visible_not_just_in_a_comment():
    ws = _wb()["Campaign Finance"]
    r = _find(ws, "current through")
    assert r, "coverage-through row not found"
    assert ws.cell(r, 2).value, "coverage date must be a visible cell value"


# ------------------------------------------------------------ trend lookup

def test_model_trend_market_lookup_is_blank_guarded():
    """INDEX onto a blank Polymarket cell returns 0, which would read as a market
    price of 0.0% and make the model-minus-market column wildly wrong."""
    ws = _wb()["Forecast & Aggregators"]
    hdr = None
    for r in range(1, 90):
        if str(ws.cell(r, 7).value or "").startswith("Polymarket P(Dem)"):
            hdr = r
            break
    assert hdr, "trend market-lookup column not found"
    f = (ws.cell(hdr + 1, 7).value or "").replace(" ", "")
    assert "INDEX(" in f and "MATCH(" in f, "expected an INDEX/MATCH lookup: %s" % f
    assert '=0,""' in f, "must treat an INDEX hit of 0 as blank: %s" % f
    g = (ws.cell(hdr + 1, 8).value or "").replace(" ", "")
    assert "ISNUMBER" in g, "model-minus-market must be guarded on both sides: %s" % g
