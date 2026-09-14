"""The site data export.

Every test here exists because the equivalent mistake produced a plausible,
non-erroring, wrong number somewhere in this project already. The export step is
the last chance to catch one before it becomes a chart.
"""
import json
import os

import support


def ex():
    return support.load("export_site")


def seed(d, **files):
    """Write JSON fixtures into the current sandbox."""
    for name, obj in files.items():
        path = name.replace("__", "/") + ".json"
        if "/" in path:
            os.makedirs(os.path.join(d, os.path.dirname(path)), exist_ok=True)
        support.write_json(os.path.join(d, path), obj)


def ladder(*pairs):
    return {"rungs": [{"ticker": "KX-P%g" % s, "label": "%g+" % s, "strike": s,
                       "yes_bid": b, "yes_ask": a} for s, b, a in pairs]}


# ------------------------------------------------------------------ flattening

def test_history_flattens_to_sorted_date_value_pairs():
    e = ex()
    out = e.flat({"2026-03-02": {"D": 0.5}, "2026-01-01": {"D": 0.4}}, lambda r: r.get("D"))
    assert out == [["2026-01-01", 0.4], ["2026-03-02", 0.5]]


def test_missing_days_are_omitted_not_zeroed():
    """The daily series have real gaps. A gap rendered as 0.0 is a price of zero
    on a chart, which is how this project once produced a -75pp daily change."""
    e = ex()
    out = e.flat({"2026-01-01": {"D": 0.4}, "2026-01-02": {}, "2026-01-03": {"D": 0.6}},
                 lambda r: r.get("D"))
    assert [d for d, _ in out] == ["2026-01-01", "2026-01-03"]
    assert all(v != 0 for _, v in out)


def test_a_one_sided_book_is_separated_from_the_price_line():
    """Kalshi's closing book on four days in Aug 2026 was a one-cent bid against
    an 84-cent ask. Its midpoint of 42.5% is arithmetic, not a price, and on the
    headline chart it reads as the market briefly calling the race a tossup."""
    e = ex()
    data = {"pm_history": {},
            "k_history": {"2026-08-13": {"D": {"yes_bid": 0.64, "yes_ask": 0.85}},
                          "2026-08-14": {"D": {"yes_bid": 0.04, "yes_ask": 0.84}}}}
    s = e.market_series(data, {}, {}, None, e.FALLBACK_MIDS)
    assert [d for d, _ in s["k_dem_tight"]] == ["2026-08-13"]
    assert [d for d, _ in s["k_dem_wide"]] == ["2026-08-14"]
    # Nothing is deleted: the raw mid is still exported for anyone who wants it.
    assert len(s["k_dem"]) == 2
    assert dict(s["k_dem_spread"])["2026-08-14"] == 0.8


def test_a_one_sided_kalshi_day_is_kept_out_of_the_consensus():
    e = ex()
    data = {"pm_history": {"2026-08-14": {"D": 0.79}},
            "k_history": {"2026-08-14": {"D": {"yes_bid": 0.04, "yes_ask": 0.84}}}}
    s = e.market_series(data, {}, {}, None, e.FALLBACK_MIDS)
    assert s["consensus_dem"] == []


def test_consensus_only_exists_on_days_both_venues_quoted():
    e = ex()
    data = {"pm_history": {"2026-01-01": {"D": 0.60}, "2026-01-02": {"D": 0.62}},
            "k_history": {"2026-01-01": {"D": {"yes_bid": 0.50, "yes_ask": 0.52}}}}
    s = e.market_series(data, {}, {}, None, e.FALLBACK_MIDS)
    assert [d for d, _ in s["consensus_dem"]] == ["2026-01-01"]
    assert s["consensus_dem"][0][1] == 0.555
    assert s["divergence"][0][1] == 0.09


# --------------------------------------------------------------- Kalshi ladder

def test_bucket_labels_come_from_the_ladder_not_from_what_is_quoted():
    """On 10 Sep 2026 the Democratic ladder had an ask on every rung and a bid on
    almost none. Keying the buckets off only the two-sided rungs collapsed five
    rungs to one and re-labelled "6+ pts" with the 15+ representative value."""
    e = ex()
    rows, _ = e.kalshi_buckets({3.0: None, 6.0: 0.30, 9.0: None, 12.0: None, 15.0: None},
                               {3.0: 0.20, 6.0: 0.10, 9.0: 0.05},
                               0.79, 0.21, e.FALLBACK_MIDS)
    d_labels = [r["label"] for r in rows if r["side"] == "D"]
    assert d_labels == ["0-3 pts", "3-6 pts", "6-9 pts", "9-12 pts", "12-15 pts", "15+ pts"]
    top = [r for r in rows if r["label"] == "15+ pts"][0]
    assert top["points"] == e.FALLBACK_MIDS["D_TOP_MID"]
    assert [r["prob"] for r in rows if r["side"] == "D"].count(None) == 6


def test_buckets_are_keyed_to_strikes_not_row_order():
    """Republican rungs are displayed descending. Differencing neighbouring rows
    on that side once inflated the Republican mass from 0.235 to 0.572."""
    e = ex()
    rows, _ = e.kalshi_buckets({3.0: 0.30}, {3.0: 0.20, 6.0: 0.10, 9.0: 0.05},
                               0.79, 0.21, e.FALLBACK_MIDS)
    by = {r["label"]: r["prob"] for r in rows if r["side"] == "R"}
    assert by["3-6 pts"] == 0.10          # 0.20 - 0.10, not 0.10 - 0.05
    assert by["6-9 pts"] == 0.05
    assert by["9+ pts"] == 0.05


def test_negative_tossup_bucket_is_clamped_and_the_discard_is_reported():
    """P(wins) - P(wins by 3+) reaches across two independently quoted markets
    and can invert. The clamp keeps the chart readable; the discarded amount is
    the whole evidence that the two markets disagree, so it must survive."""
    e = ex()
    rows, discarded = e.kalshi_buckets({3.0: 0.60}, {3.0: 0.20},
                                       0.50, 0.30, e.FALLBACK_MIDS)
    tossup = [r for r in rows if r["side"] == "D" and r["derived"]][0]
    assert tossup["prob"] == 0.0
    assert tossup["raw"] == -0.1
    assert discarded["D"] == -0.1
    assert discarded["R"] == 0.0


def test_expected_margin_skips_days_with_an_incomplete_ladder():
    """An expectation over half a distribution is a confident wrong number."""
    e = ex()
    data3 = {"mov_d": ladder((3.0, 0.5, 0.6), (6.0, 0.3, 0.4)),
             "mov_r": ladder((3.0, 0.1, 0.2)),
             "mov_d_history": {"2026-01-01": {"KX-P3": {"bid": .5, "ask": .6},
                                              "KX-P6": {"bid": .3, "ask": .4}},
                               "2026-01-02": {"KX-P3": {"bid": .5, "ask": .6}}},
             "mov_r_history": {"2026-01-01": {"KX-P3": {"bid": .1, "ask": .2}},
                               "2026-01-02": {"KX-P3": {"bid": .1, "ask": .2}}}}
    data = {"k_history": {d: {"D": {"yes_bid": .7, "yes_ask": .8},
                              "R": {"yes_bid": .2, "yes_ask": .3}}
                          for d in ("2026-01-01", "2026-01-02")}}
    got = e.k_expected_margin(data, data3, e.FALLBACK_MIDS)
    assert [d for d, _ in got] == ["2026-01-01"]


# ---------------------------------------------------------- Polymarket ladder

def test_expected_margin_is_normalised_before_weighting():
    """Raw mids on this ladder sum well above 1.00 because several brackets are
    quoted with very wide spreads. Weighting raw mids inherits the overround."""
    e = ex()
    data2 = {"mov": [{"bracket": "Democrat 0-3%", "midpoint": 1.5},
                     {"bracket": "Republican 0-3%", "midpoint": -1.5}],
             "mov_history": {"2026-01-01": {"Democrat 0-3%": 0.75,
                                            "Republican 0-3%": 0.75}}}
    assert e.pm_expected_margin(data2) == [["2026-01-01", 0.0]]


def test_distribution_normalises_to_one_and_keeps_the_raw_total():
    e = ex()
    data2 = {"mov": [{"bracket": "Democrat 0-3%", "midpoint": 1.5,
                      "best_bid": 0.5, "best_ask": 0.7, "volume": 1.0},
                     {"bracket": "Republican 0-3%", "midpoint": -1.5,
                      "best_bid": 0.3, "best_ask": 0.5, "volume": 1.0}]}
    d = e.distributions({}, data2, {}, e.FALLBACK_MIDS)["polymarket_margin"]
    assert round(sum(b["normalised"] for b in d["brackets"]), 6) == 1.0
    assert d["raw_total"] == 1.0
    assert d["brackets"][0]["spread"] == 0.2


# ------------------------------------------------------------------ the polls

def test_partisan_lean_is_mapped_the_way_the_polls_sheet_maps_it():
    """house.csv spells it DEM; the Polls sheet sums over D. Reading the raw
    column gave net partisan sponsorship of 0.00, so the house-effect haircut
    silently did nothing to the one poll it exists for."""
    e = ex()
    with support.sandbox():
        block = e.poll_block({"polls": [{"pollster": "GBAO", "partisan": "DEM",
                                         "start_date": "2026-06-29", "end_date": "2026-07-02",
                                         "sample_size": 550, "dem_pct": 47.0, "rep_pct": 43.0}]})
    assert block["polls"][0]["partisan"] == "D"
    assert block["average"]["net_partisan"] == 1.0
    assert block["average"]["adjusted_margin"] < block["average"]["margin"]


def test_poll_origin_is_recorded_because_the_two_sources_disagree():
    """PollsMax records the same GBAO poll with no partisan tag. "One poll" and
    "one poll, seen through a third party" are not the same claim.

    CI has no house.csv, which is 2.9 MB covering every 2026 House race and is not
    in the repository, so the fallback path is the one CI actually takes.
    """
    e = ex()
    pollsrc = support.load("pollsrc")

    def gone():
        raise FileNotFoundError("no house.csv, as in CI")

    with support.sandbox(), support.attrs(pollsrc, resolve=gone):
        block = e.poll_block({"polls": [{"pollster": "GBAO", "dem_pct": 47.0, "rep_pct": 43.0,
                                         "end_date": "2026-07-02"}]})
    assert block["origin"] == "sources/pollsmax.json"
    assert block["polls"][0]["assumed_n"] is True


# --------------------------------------------------------------- whole export

def test_build_writes_every_file_and_a_manifest_listing_them():
    e = ex()
    with support.sandbox(data=True) as d:
        seed(d, data3={"problems": []})
        written = e.build(out_dir=os.path.join(d, "site", "data"), copy_workbook=False)
        man = support.read_json(os.path.join(d, "site", "data", "manifest.json"))
    assert set(written) >= {"series.json", "series-full.json", "distribution.json",
                            "polls.json", "finance.json", "caveats.json",
                            "headline.json", "manifest.json"}
    assert set(man["files"]) == set(written) - {"manifest.json"}
    assert man["race"]["election"] == "2026-11-03"


def test_windowed_series_is_a_subset_of_the_full_one():
    e = ex()
    with support.sandbox(data=True) as d:
        seed(d, data3={"problems": []})
        e.build(out_dir=os.path.join(d, "site", "data"), window_days=5, copy_workbook=False)
        win = support.read_json(os.path.join(d, "site", "data", "series.json"))
        full = support.read_json(os.path.join(d, "site", "data", "series-full.json"))
    assert win["full"] == "data/series-full.json"
    for name, points in win["series"].items():
        assert points == [p for p in full["series"][name] if p[0] >= win["from"]]
        assert len(points) <= len(full["series"][name])


def test_a_missing_source_degrades_to_a_gap_not_a_crash():
    """build7.py omits a section rather than failing the build when a source is
    gone. The export follows the same rule, and CI has no house.csv at all."""
    e = ex()
    with support.sandbox() as d:
        seed(d, data={"problems": []}, data2={"problems": []}, data3={"problems": []})
        written = e.build(out_dir=os.path.join(d, "site", "data"), copy_workbook=False)
        dv = support.read_json(os.path.join(d, "site", "data", "divergence.json"))
    assert written
    # with no history there is nothing to compare, and that must be a gap, not a crash
    assert dv["divergence"]["days_joined"] == 0
    assert dv["divergence"]["current"] is None
    assert dv["divergence"]["episodes"] == []


def live_config():
    """The page's live-price config is hand-maintained JS whose object literal
    is strict JSON, so the tests can read exactly what the browser reads."""
    src = open(support.script("site/assets/live-config.js")).read()
    obj = src[src.index("{", src.index("window.PA07_LIVE")):src.rindex("}") + 1]
    return json.loads(obj)


def test_kalshi_goes_through_a_server_never_the_browser():
    """Kalshi answers any browser request with 403, so the page must never be
    told to call it directly. Every endpoint it is given is either a path next
    to the page (a deployed function) or the raw copy of the live-data branch,
    and the direct Kalshi host must not appear."""
    k = live_config()["kalshi"]
    assert k["endpoints"], "no live endpoint for Kalshi"
    for u in k["endpoints"]:
        assert "kalshi.com" not in u
        assert u == "api/kalshi" or u.startswith("https://raw.githubusercontent.com/")
    assert any(u.endswith("/live-data/kalshi-live.json") for u in k["endpoints"])


def test_kalshi_live_endpoints_agree_with_the_workflow_and_the_function():
    """Three places must name the same tickers and the same file: the book
    reader the Actions job runs, the Vercel function, and the page's endpoint
    list. Drift here is silent at build time and only shows as a page with a
    permanently stale Kalshi row."""
    e = ex()
    reader = open(support.script("kalshi_book.py")).read()
    fn = open(support.script("api/kalshi.js")).read()
    wf = open(support.script(".github/workflows/kalshi-live.yml")).read()
    for t in ("HOUSEPA7-26-D", "HOUSEPA7-26-R"):
        assert t in reader and t in fn
    assert "kalshi_book.py live/kalshi-live.json" in wf
    assert "ref: live-data" in wf
    raw = [u for u in live_config()["kalshi"]["endpoints"] if u.startswith("https://")][0]
    assert raw.endswith("/live-data/kalshi-live.json")
    # the freshness chip and the live panel both key on this id
    assert any(f["id"] == "kalshi" and f["kind"] == "live"
               for f in e.freshness({}, {}, {}, {}, {}, {}, {}, "/nonexistent"))


def test_live_config_matches_the_collector():
    """The page and collect.py must look up the same markets. Polymarket renamed
    these outcomes mid-cycle while the slugs held, so the slug is the stable key
    and there must be exactly one copy of it in the repository."""
    src = open(support.script("collect.py")).read()
    pm = live_config()["polymarket"]
    assert pm["slugs"]["D"].startswith("will-the-democratic-party")
    for slug in pm["slugs"].values():
        assert slug.split("will-the-")[1].split("-win")[0] in src
    assert pm["winner_event"].startswith("https://gamma-api.polymarket.com/events/")
    assert pm["poll_seconds"] >= 30, "polling a public API faster than this is rude"


def test_the_page_never_reads_live_config_from_the_manifest():
    """site/data is written by the refresh job and only by the refresh job. A
    branch that also edited a file there conflicted with the bot on merge, so
    page configuration must not pass through the manifest."""
    e = ex()
    assert not hasattr(e, "LIVE")
    for name in ("live.js", "app.js", "dashboard.js"):
        assert "manifest.live" not in open(support.script("site/assets/" + name)).read(), name
    assert "live-config.js" in open(support.script("site/index.html")).read()


def test_ladder_midpoints_agree_with_the_builder():
    """Rule 1: assumptions travel through the ref JSONs. This asserts the
    fallback copy has not drifted from build6.py, which is the authority."""
    e = ex()
    src = open(support.script("build6.py")).read()
    for name, value in e.FALLBACK_MIDS.items():
        line = [l for l in src.splitlines() if l.startswith(name + " ")][0]
        assert float(line.split("=")[1].split("#")[0].strip()) == float(value)


def test_export_carries_the_load_bearing_caveats():
    """These are the readings that make the headline number wrong, and the
    workbook puts each one on the sheet it applies to rather than in an
    appendix. They may not quietly stop being exported."""
    e = ex()
    with support.sandbox(data=True) as d:
        seed(d, data3={"problems": []})
        e.build(out_dir=os.path.join(d, "site", "data"), copy_workbook=False)
        cav = support.read_json(os.path.join(d, "site", "data", "caveats.json"))
    ids = {c["id"] for c in cav["caveats"]}
    assert {"one-poll", "city-and-state", "fec-asof", "thin-markets",
            "kalshi-clamp", "equal-weight", "hand-curated"} <= ids
    assert all(c["headline"] and c["body"] for c in cav["caveats"])
    assert cav["city_and_state"]["display_only"] is True


def test_every_assumption_says_why_it_was_chosen():
    e = ex()
    with support.sandbox(data=True) as d:
        seed(d, data3={"problems": []})
        e.build(out_dir=os.path.join(d, "site", "data"), copy_workbook=False)
        cav = support.read_json(os.path.join(d, "site", "data", "caveats.json"))
    assert len(cav["assumptions"]) >= 8
    for a in cav["assumptions"]:
        assert a["what"] and a["value"] and a["why"]


def test_headline_reuses_the_notes_the_pipeline_already_wrote():
    """diff() produces the alert strings. Re-deriving them in the browser would
    be a second implementation of the alerting rules."""
    e = ex()
    with support.sandbox(data=True) as d:
        seed(d, data3={"problems": []},
             status={"snapshot": {"pm_dem": 0.79, "consensus_dem": 0.79},
                     "notes": ["a note"], "alerts": ["LARGE MOVE: something"]})
        e.build(out_dir=os.path.join(d, "site", "data"), copy_workbook=False)
        head = support.read_json(os.path.join(d, "site", "data", "headline.json"))
    assert head["origin"] == "status.json"
    assert head["alerts"] == ["LARGE MOVE: something"]
    assert head["snapshot"]["consensus_dem"] == 0.79


def test_freshness_is_reported_per_source():
    """No part of the page may borrow another part's timestamp. The hand-curated
    sources can be arbitrarily older than the market data beside them."""
    e = ex()
    with support.sandbox(data=True) as d:
        seed(d, data3={"problems": []})
        e.build(out_dir=os.path.join(d, "site", "data"), copy_workbook=False)
        man = support.read_json(os.path.join(d, "site", "data", "manifest.json"))
    kinds = {f["id"]: f["kind"] for f in man["freshness"]}
    assert kinds["polymarket"] == "live"
    assert kinds["kalshi"] == "live"           # via a server, see live-config.js
    assert kinds["kalshi_ladders"] == "snapshot"
    assert kinds["pollsmax"] == "manual"
    assert all(f.get("detail") for f in man["freshness"])


def test_no_credential_reaches_the_export():
    """The export reads sources that sit beside two private keys. Nothing that
    looks like either may end up in a file destined for a public site."""
    e = ex()
    with support.sandbox(data=True) as d:
        seed(d, data3={"problems": []})
        out = os.path.join(d, "site", "data")
        e.build(out_dir=out, copy_workbook=False)
        blob = "".join(open(os.path.join(out, f)).read() for f in os.listdir(out))
    # The needles are assembled rather than written out. The pre-commit leak
    # check is a `git diff --cached -S` for the PEM header, and a test file
    # holding that string verbatim would make the check fire on every commit
    # until someone stopped reading it.
    for needle in (" ".join(("BEGIN", "RSA")), "PRIVATE KEY", "api_key",
                   "KALSHI_KEY", "fec_key"):
        assert needle not in blob


def test_export_does_not_chdir_out_from_under_the_caller():
    """refresh.py chdirs to the project root at import. Adopting that would make
    the export write into the repository no matter where it was pointed."""
    e = ex()
    with support.sandbox(data=True) as d:
        seed(d, data3={"problems": []})
        e.build(out_dir=os.path.join(d, "site", "data"), copy_workbook=False)
        assert os.path.realpath(os.getcwd()) == os.path.realpath(d)
    assert os.path.exists(os.path.join(d)) is False


def test_json_is_written_compactly():
    """~230 KB of daily history across every series, served to a phone. Pretty
    printing it costs about a third of that in whitespace."""
    e = ex()
    with support.sandbox(data=True) as d:
        seed(d, data3={"problems": []})
        out = os.path.join(d, "site", "data")
        e.build(out_dir=out, copy_workbook=False)
        text = open(os.path.join(out, "series.json")).read()
    assert ", " not in text and json.loads(text)
