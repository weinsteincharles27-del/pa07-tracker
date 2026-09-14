#!/usr/bin/env python3
"""Export the collected JSON into the compact files the static site reads.

The workbook is no longer the only output. This step sits at the end of the
pipeline, reads the same `data*.json` and `sources/*.json` the builders read,
and writes `site/data/*.json`: small, flat, browser-shaped.

Two rules shape everything here:

1. **Do not recompute what refresh.py already computes.** `snapshot()` derives
   the headline figures from the collected JSON rather than from the workbook,
   and `diff()` turns them into the notes and alerts a human actually reads.
   Both are imported and used as-is. A second implementation of "consensus
   probability" in JavaScript would be a second thing to get wrong, and this
   project's whole bug history is valid-looking wrong numbers.

2. **Histories flatten to [[date, value], ...].** The collectors store
   dict-of-dicts keyed by date because that is how they merge new days in.
   That shape costs the browser a sort and a key sweep on every redraw, and
   quadruples the byte count in quoted keys. Sorted pairs are what a chart
   wants.

The daily histories have real gaps (Polymarket lost 11, 9 and 4 days in spring
2026; Kalshi six more in June-July). Nothing here fills them: a missing day is
absent from the array, and the frontend breaks the line rather than drawing
through it. Interpolated data that looks like observed data is the same class
of mistake as INDEX-onto-blank returning zero.

Usage:
    /usr/bin/python3 export_site.py                 # writes site/data/
    /usr/bin/python3 export_site.py --out DIR       # somewhere else
    /usr/bin/python3 export_site.py --no-workbook   # skip the xlsx copy
"""
import csv
import datetime
import json
import math
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:                 # importable from a test sandbox
    sys.path.insert(0, HERE)

OUT_DIR = os.path.join("site", "data")
WB = "PA-07_House_Election_Tracker.xlsx"
ELECTION = datetime.date(2026, 11, 3)

# How much history the default payload carries. ~230 KB uncompressed across all
# series is fine on a laptop and not fine on a phone over cellular, so the page
# loads a window and fetches the rest only when asked. 180 days covers the whole
# Polymarket series-so-far plus room to grow before the election.
WINDOW_DAYS = 180

# A day where Kalshi's closing book is a penny bid against an 84-cent ask is not
# a 42% probability, it is an empty book. That happened on 14, 15, 18 and 19 Aug
# 2026 and puts four vertical spikes through the headline chart, each of which
# reads as "the market briefly thought this was a tossup". Days quoted wider than
# this are separated out rather than deleted: the page draws them as hollow
# points so the reader can see the book emptying instead of seeing a price move.
WIDE_SPREAD = 0.25

# Fallbacks for the ladder midpoints. build6.py is the authority and publishes
# them in k3refs.json; these exist so an export can still run against a checkout
# that has data*.json but has not built the workbook yet (CI does exactly that
# when a build step fails). They are asserted equal to build6.py's by the tests.
FALLBACK_MIDS = {"D_TOP_MID": 18.0, "R_TOP_MID": -11.0,
                 "TURN_LOW_MID": 295000, "TURN_TOP_MID": 385000}

# The only venue a browser can poll for itself. Polymarket answers gamma and
# clob requests with access-control-allow-origin: *; Kalshi sends no CORS header
# at all, its preflight is a bare 403, and every request must carry an RSA-PSS
# signature over a private key. Kalshi can therefore never be called from a page,
# so everything Kalshi on the site is a committed snapshot and the UI says so.
# Where the page polls live prices from is page configuration, not data, and
# lives in site/assets/live-config.js. Nothing under site/data is edited by
# hand: the refresh job owns that directory, and a branch that also touched it
# would conflict with the bot on every merge.


# ------------------------------------------------------------------- plumbing

def read_json(path, default=None):
    """Load JSON, or return `default` if it is missing or unreadable.

    Every source here is allowed to be absent. build7.py already degrades to a
    missing section rather than a failed build when sources/*.json goes away,
    and the site follows the same rule: a source that did not load renders as
    an explicit gap, not as a zero.
    """
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, separators=(",", ":"), sort_keys=True, default=str)
    return os.path.getsize(path)


def mid(a, b):
    return None if a is None or b is None else (a + b) / 2.0


def rnd(v, places=6):
    """Round for transport. Six places keeps every cent-quoted price exact and
    stops float noise from adding a kilobyte of 0.30000000000000004 per series."""
    return None if v is None else round(float(v), places)


def flat(hist, pick):
    """dict-of-dicts keyed by date -> [[date, value], ...], sorted, gaps dropped.

    `pick` returns the value for one day, or None to leave that day out. Days
    are left out rather than emitted as null so the frontend never has to decide
    whether a null means "no quote" or "zero".
    """
    out = []
    for day in sorted(hist or {}):
        try:
            v = pick(hist[day])
        except (TypeError, KeyError, IndexError):
            v = None
        if v is not None and not (isinstance(v, float) and math.isnan(v)):
            out.append([day, rnd(v)])
    return out


def since(points, cutoff):
    return [p for p in points if p[0] >= cutoff]


def refresh_module():
    """Import refresh.py without inheriting its chdir.

    refresh.py chdirs to its own directory at import time so a scheduled run
    always works from the project root. That is right for the scheduler and
    wrong here: this module is run from wherever the caller stands, and the
    tests deliberately stand in a sandbox holding fixture data.
    """
    cwd = os.getcwd()
    try:
        import refresh
        return refresh
    finally:
        os.chdir(cwd)


def figures():
    """(snapshot dict, notes, alerts) for the last known state of the race.

    Prefers status.json, which is the actual result of the last scheduled run,
    already diffed against the run before it, so its notes and alerts describe
    real movement between two real runs. Recomputing here would only ever be
    able to diff the current data against itself.

    Falls back to running snapshot()/diff() directly, which is what happens on a
    checkout that has collected data but has never completed a full refresh.
    """
    st = read_json("status.json")
    snap = (st or {}).get("snapshot")
    if snap:
        return snap, list(st.get("notes") or []), list(st.get("alerts") or []), "status.json"
    r = refresh_module()
    try:
        cur = r.snapshot()
    except (KeyError, TypeError, ValueError, OSError) as e:
        # snapshot() assumes a completed collection. A checkout with partial or
        # absent data*.json is a normal state in CI, and the site should render
        # with an empty headline rather than fail the whole export.
        return {}, [], ["The headline figures could not be computed from the collected data "
                        "(%s: %s). Everything below is from the last successful build."
                        % (type(e).__name__, e)], "unavailable"
    prev, _ = r.load_state()
    notes, alerts = r.diff(prev, cur)
    return cur, notes, alerts, "recomputed"


def midpoints():
    """Ladder representative values, read from build6.py's ref JSON where it
    exists. Rule 1 of the handoff: anchors and assumptions travel through the
    ref files, they are not copied into a second script."""
    k3 = read_json("k3refs.json") or {}
    return {k: k3.get(k, v) for k, v in FALLBACK_MIDS.items()}


# -------------------------------------------------------------------- series

def market_series(data, data2, data3, pollsmax, mids):
    """Every daily line the site draws, flattened and named."""
    pm_hist = (data or {}).get("pm_history") or {}
    k_hist = (data or {}).get("k_history") or {}

    def k(side, field):
        return flat(k_hist, lambda row: (row.get(side) or {}).get(field))

    def k_mid(side):
        return flat(k_hist, lambda row: mid((row.get(side) or {}).get("yes_bid"),
                                            (row.get(side) or {}).get("yes_ask")))

    def spread(side):
        return flat(k_hist, lambda row: (None if None in ((row.get(side) or {}).get("yes_bid"),
                                                          (row.get(side) or {}).get("yes_ask"))
                                         else (row[side]["yes_ask"] - row[side]["yes_bid"])))

    def by_width(side, wide):
        w = dict(spread(side))
        return [p for p in k_mid(side)
                if p[0] in w and ((w[p[0]] > WIDE_SPREAD) == wide)]

    out = {
        "pm_dem": flat(pm_hist, lambda r: r.get("D")),
        "pm_rep": flat(pm_hist, lambda r: r.get("R")),
        "k_dem": k_mid("D"),
        "k_dem_tight": by_width("D", False),
        "k_dem_wide": by_width("D", True),
        "k_dem_spread": spread("D"),
        "k_rep": k_mid("R"),
        "k_dem_bid": k("D", "yes_bid"),
        "k_dem_ask": k("D", "yes_ask"),
        "k_dem_oi": flat(k_hist, lambda r: max([(r.get(s) or {}).get("oi") or 0
                                                for s in ("D", "R")]) or None),
        "k_volume": flat(k_hist, lambda r: sum((r.get(s) or {}).get("vol") or 0
                                               for s in ("D", "R")) or None),
    }

    # Consensus only exists on days both venues quoted, and quoted two-sidedly.
    # Carrying one venue forward on a day the other is missing would draw a
    # "consensus" that is really one venue, which is the divergence chart's whole
    # subject; averaging in a one-cent-bid mid would do the same thing worse.
    pm_by_day = dict(out["pm_dem"])
    k_by_day = dict(out["k_dem_tight"])
    both = sorted(set(pm_by_day) & set(k_by_day))
    out["consensus_dem"] = [[d, rnd((pm_by_day[d] + k_by_day[d]) / 2.0)] for d in both]
    out["divergence"] = [[d, rnd(pm_by_day[d] - k_by_day[d])] for d in both]

    out["pm_margin"] = pm_expected_margin(data2)
    out["k_margin"] = k_expected_margin(data, data3, mids)

    trend = ((pollsmax or {}).get("extra") or {}).get("forecast_trend_series") or {}
    wp = trend.get("win_probability_pct") or {}
    vs = trend.get("vote_share_pct") or {}

    def paired(block, key, scale=1.0):
        dates, vals = block.get("dates") or [], block.get(key) or []
        return [[d, rnd(v * scale)] for d, v in zip(dates, vals) if v is not None]

    out["model_dem"] = paired(wp, "brooks_win_prob_pct", 0.01)
    out["model_dem_upper"] = paired(wp, "brooks_win_prob_upper", 0.01)
    out["model_dem_lower"] = paired(wp, "brooks_win_prob_lower", 0.01)

    d_share = dict(paired(vs, "brooks_pct"))
    r_share = dict(paired(vs, "mackenzie_pct"))
    out["model_margin"] = [[d, rnd(d_share[d] - r_share[d])]
                           for d in sorted(set(d_share) & set(r_share))]
    return out


def pm_expected_margin(data2):
    """Polymarket's implied margin per day, in points, positive for a Democrat.

    Normalised before weighting. The raw mids on this ladder sum well above 1.00
    because several brackets are quoted with very wide spreads, and an
    un-normalised expectation would inherit all of that overround.
    """
    hist = (data2 or {}).get("mov_history") or {}
    points = {b["bracket"]: b["midpoint"] for b in (data2 or {}).get("mov") or []}
    out = []
    for day in sorted(hist):
        row = {k: v for k, v in (hist[day] or {}).items()
               if k in points and isinstance(v, (int, float))}
        total = sum(row.values())
        if not row or total <= 0:
            continue
        out.append([day, rnd(sum(v / total * points[k] for k, v in row.items()), 4)])
    return out


def kalshi_buckets(mov_d, mov_r, win_d, win_r, mids):
    """Kalshi's nested thresholds differenced into exclusive buckets.

    Mirrors build6.py exactly, including the two things that are easy to get
    wrong and were both live bugs:

    - Buckets come off STRIKE values, never off row adjacency. The Republican
      rungs are displayed descending, and differencing neighbouring rows once
      inflated that side from 0.235 to 0.572 and produced a distribution
      summing to 1.33.
    - Kalshi quotes no 0-3 rung, so each side's tossup bucket is P(wins) from
      the winner market minus P(wins by 3+) from this ladder: a subtraction
      across two independently quoted markets, which can come out negative. It
      is clamped at zero, and the amount discarded is returned rather than
      thrown away: on the workbook that number lives only in a consistency
      check, and it is the difference between "the tossup is worth nothing" and
      "these two markets disagree".

    Rungs arrive as {strike: mid or None}, INCLUDING the rungs with no mid. That
    matters: on 10 Sep 2026 the Democratic ladder had a resting ask on every rung
    and a resting bid on almost none, so a dict of only the quoted strikes
    collapsed a five-rung ladder to one and re-labelled "6+ pts" with the 15+
    representative value of +18. The bucket set is defined by the ladder, not by
    what happens to be two-sided this minute; an unquoted bucket reports None and
    the page draws a gap.
    """
    rows, discarded = [], {}
    for side, ladder, win, top, sign in (("R", mov_r, win_r, mids["R_TOP_MID"], -1),
                                         ("D", mov_d, win_d, mids["D_TOP_MID"], +1)):
        strikes = sorted(ladder)
        side_rows = []
        for i, st in enumerate(strikes):
            outer = strikes[i + 1] if i + 1 < len(strikes) else None
            if outer is None:
                p, label, rep = ladder[st], "%g+ pts" % st, top
            elif None in (ladder[st], ladder[outer]):
                p, label, rep = None, "%g-%g pts" % (st, outer), sign * (st + outer) / 2.0
            else:
                p = max(0.0, ladder[st] - ladder[outer])
                label, rep = "%g-%g pts" % (st, outer), sign * (st + outer) / 2.0
            side_rows.append({"side": side, "label": label, "points": rep,
                              "prob": rnd(p, 4), "derived": False})
        inner = ladder[strikes[0]] if strikes else None
        raw = None if None in (win, inner) else win - inner
        if strikes:
            discarded[side] = rnd(min(0.0, raw), 4) if raw is not None else None
            side_rows.insert(0, {"side": side, "label": "0-%g pts" % strikes[0],
                                 "points": sign * strikes[0] / 2.0,
                                 "prob": rnd(max(0.0, raw), 4) if raw is not None else None,
                                 "derived": True,
                                 "raw": rnd(raw, 4) if raw is not None else None})
        # One continuous axis: biggest Republican win first, tossups in the
        # middle, biggest Democratic win last, so a bar chart of this reads as a
        # distribution instead of a spike at each edge.
        rows.extend(reversed(side_rows) if side == "R" else side_rows)
    return rows, discarded


def k_expected_margin(data, data3, mids):
    """Kalshi's implied margin per day, from the two threshold ladders plus the
    winner market for the 0-3 buckets."""
    def ladder_by_day(key):
        """{day: {strike: mid or None}} for every rung the ladder declares.

        A day where any rung failed to quote is kept but incomplete, and the
        caller drops it. Averaging over a partial ladder produces a confident
        expected margin computed from half a distribution.
        """
        declared = {}
        for x in (((data3 or {}).get(key) or {}).get("rungs") or []):
            declared[float(x["strike"])] = x["ticker"]
        out = {}
        for day, row in ((data3 or {}).get(key + "_history") or {}).items():
            quotes = {}
            for strike, ticker in declared.items():
                q = (row or {}).get(ticker) or {}
                quotes[strike] = mid(q.get("bid"), q.get("ask"))
            if quotes:
                out[day] = quotes
        return out

    d_days, r_days = ladder_by_day("mov_d"), ladder_by_day("mov_r")
    win = (data or {}).get("k_history") or {}
    out = []
    for day in sorted(set(d_days) & set(r_days)):
        w = win.get(day) or {}
        wd = mid((w.get("D") or {}).get("yes_bid"), (w.get("D") or {}).get("yes_ask"))
        wr = mid((w.get("R") or {}).get("yes_bid"), (w.get("R") or {}).get("yes_ask"))
        rows, _ = kalshi_buckets(d_days[day], r_days[day], wd, wr, mids)
        if not rows or any(r["prob"] is None for r in rows):
            continue
        total = sum(r["prob"] for r in rows)
        if total <= 0:
            continue
        # Normalised for the same reason as Polymarket: these buckets come off
        # two markets and are not obliged to sum to 1.00.
        out.append([day, rnd(sum(r["prob"] / total * r["points"] for r in rows), 4)])
    return out


# --------------------------------------------------------------- distribution

def distributions(data, data2, data3, mids):
    """The three cross-sections: margin, turnout, seats."""
    pm = []
    mov = (data2 or {}).get("mov") or []
    raw_total = sum(x for x in (mid(b.get("best_bid"), b.get("best_ask")) for b in mov)
                    if x is not None)
    for b in mov:
        m = mid(b.get("best_bid"), b.get("best_ask"))
        pm.append({
            "bracket": b["bracket"], "points": b["midpoint"],
            "bid": rnd(b.get("best_bid")), "ask": rnd(b.get("best_ask")),
            "mid": rnd(m, 4),
            "normalised": rnd(m / raw_total, 4) if (m is not None and raw_total) else None,
            "spread": rnd((b["best_ask"] - b["best_bid"]), 4)
                      if None not in (b.get("best_bid"), b.get("best_ask")) else None,
            "volume": rnd(b.get("volume"), 2),
        })

    def rung_mids(block):
        """Every declared rung, quoted or not. See kalshi_buckets on why."""
        return {float(x["strike"]): mid(x.get("yes_bid"), x.get("yes_ask"))
                for x in ((block or {}).get("rungs") or [])}

    km = (data or {}).get("k_meta") or {}
    kbuckets, discarded = kalshi_buckets(
        rung_mids((data3 or {}).get("mov_d")), rung_mids((data3 or {}).get("mov_r")),
        mid((km.get("D") or {}).get("yes_bid"), (km.get("D") or {}).get("yes_ask")),
        mid((km.get("R") or {}).get("yes_bid"), (km.get("R") or {}).get("yes_ask")),
        mids)

    turnout = {k: v for k, v in rung_mids((data3 or {}).get("turnout")).items()
               if v is not None}
    tstrikes = sorted(turnout)
    tbuckets = []
    for i, st in enumerate(tstrikes):
        nxt = tstrikes[i + 1] if i + 1 < len(tstrikes) else None
        if i == 0:
            tbuckets.append({"label": "Below %s" % fmt_k(st), "point": mids["TURN_LOW_MID"],
                             "prob": rnd(max(0.0, 1.0 - turnout[st]), 4), "open_ended": True})
        if nxt is None:
            tbuckets.append({"label": "Above %s" % fmt_k(st), "point": mids["TURN_TOP_MID"],
                             "prob": rnd(turnout[st], 4), "open_ended": True})
        else:
            tbuckets.append({"label": "%s-%s" % (fmt_k(st), fmt_k(nxt)),
                             "point": (st + nxt) / 2.0,
                             "prob": rnd(max(0.0, turnout[st] - turnout[nxt]), 4),
                             "open_ended": False})

    seats = []
    def seat_mid(b):
        # "Below 7" and "Above 12" have an ask and no resting bid. Half the ask
        # is build2b.py's fallback; both quote at a cent or two, so it moves the
        # expectation by almost nothing and beats dropping the bracket.
        if b.get("yes_bid") is not None and b.get("yes_ask") is not None:
            return (b["yes_bid"] + b["yes_ask"]) / 2.0
        if b.get("yes_ask") is not None:
            return b["yes_ask"] / 2.0
        return b.get("yes_bid")
    srows = (data2 or {}).get("seats") or []
    stotal = sum(seat_mid(b) or 0 for b in srows)
    for b in srows:
        m = seat_mid(b)
        seats.append({"label": b["label"], "seats": b["midpoint"], "ticker": b["ticker"],
                      "mid": rnd(m, 4),
                      "normalised": rnd(m / stotal, 4) if (m is not None and stotal) else None,
                      "bid_missing": b.get("yes_bid") is None})

    return {
        "polymarket_margin": {"brackets": pm, "raw_total": rnd(raw_total, 4),
                              "event": (data2 or {}).get("mov_event")},
        # A total over a ladder with unquoted rungs is a sum of half a
        # distribution and reads as "Kalshi thinks this race is 20% likely to
        # happen". Withheld rather than shown small.
        "kalshi_margin": {"buckets": kbuckets,
                          "total": (None if any(b["prob"] is None for b in kbuckets)
                                    else rnd(sum(b["prob"] for b in kbuckets), 4)),
                          "unquoted": sum(1 for b in kbuckets if b["prob"] is None),
                          "clamp_discarded": discarded},
        "turnout": {"rungs": [{"strike": s, "mid": rnd(turnout[s], 4)} for s in tstrikes],
                    "buckets": tbuckets,
                    "event": ((data3 or {}).get("turnout") or {}).get("event")},
        "seats": {"brackets": seats, "baseline": 8,
                  "expected": rnd(sum((seat_mid(b) or 0) / stotal * b["midpoint"]
                                      for b in srows), 3) if stotal else None},
    }



# ------------------------------------------------------------ divergence + moves

GENUINE_PP = 0.08        # a day counts toward an episode above this gap
EPISODE_MIN_DAYS = 3     # and an episode needs this many consecutive such days


def divergence_block(data, series):
    """When the two venues disagreed, by how much, and which of those days were
    real disagreements rather than an unquoted book.

    The largest apparent divergences in this history are not disagreements at
    all: on 14-19 Aug 2026 Kalshi's closing book was a one-cent bid against an
    84-cent ask, and the midpoint of that is 42.5%, which is arithmetic, not a
    price. Those days are separated out, not hidden, and every figure here is
    computed on the tight-book days only. The event annotations are left empty
    on purpose: they are filled from researched sources, never guessed.
    """
    pm = data.get("pm_history") or {}
    kh = data.get("k_history") or {}
    rows = []
    for day in sorted(pm):
        p = (pm.get(day) or {}).get("D")
        k = (kh.get(day) or {}).get("D") or {}
        b, a = k.get("yes_bid"), k.get("yes_ask")
        if p is None or b is None or a is None:
            continue
        rows.append({"date": day, "pm": p, "k": (a + b) / 2, "spread": a - b})
    tight = [r for r in rows if r["spread"] <= WIDE_SPREAD]
    wide = [r for r in rows if r["spread"] > WIDE_SPREAD]
    for r in rows:
        r["div"] = r["pm"] - r["k"]

    episodes, cur = [], []
    for r in tight:
        if abs(r["div"]) >= GENUINE_PP:
            cur.append(r)
        else:
            if len(cur) >= EPISODE_MIN_DAYS:
                episodes.append(cur)
            cur = []
    if len(cur) >= EPISODE_MIN_DAYS:
        episodes.append(cur)

    def ep(e):
        peak = max(e, key=lambda r: abs(r["div"]))
        return {"from": e[0]["date"], "to": e[-1]["date"], "days": len(e),
                "peak_date": peak["date"], "peak_pp": rnd(peak["div"] * 100, 1),
                "peak_pm": rnd(peak["pm"], 3), "peak_kalshi": rnd(peak["k"], 3),
                "mean_pp": rnd(sum(r["div"] for r in e) / len(e) * 100, 1),
                "direction": "kalshi_higher" if peak["div"] < 0 else "polymarket_higher",
                "events": []}

    def top(rs, n):
        return [{"date": r["date"], "pp": rnd(r["div"] * 100, 1), "pm": rnd(r["pm"], 3),
                 "kalshi": rnd(r["k"], 3), "kalshi_spread": rnd(r["spread"], 3)}
                for r in sorted(rs, key=lambda r: -abs(r["div"]))[:n]]

    absd = [abs(r["div"]) for r in tight] or [0.0]
    return {
        "days_joined": len(rows), "days_tight": len(tight), "days_wide": len(wide),
        "wide_threshold": WIDE_SPREAD,
        "mean_abs_pp": rnd(sum(absd) / len(absd) * 100, 1),
        "max_abs_pp": rnd(max(absd) * 100, 1),
        "direction_share_kalshi_higher": rnd(sum(1 for r in tight if r["div"] < 0) / max(1, len(tight)), 3),
        "episodes": [ep(e) for e in episodes],
        "largest_genuine": top(tight, 8),
        "artifact_days": top(wide, 8),
        "current": ({"date": rows[-1]["date"], "pp": rnd(rows[-1]["div"] * 100, 1)} if rows else None),
    }


def moves_block(series, snap):
    """How the odds have moved, in the terms a reader asks: over a week, a
    month, since the primary, and the biggest single days."""
    def at_or_before(points, target):
        best = None
        for p in points:
            if p[0] <= target:
                best = p
        return best

    def change(points, days):
        if not points:
            return None
        last = points[-1]
        target = (datetime.date.fromisoformat(last[0]) - datetime.timedelta(days=days)).isoformat()
        base = at_or_before(points, target)
        if base is None:
            return None
        gap = (datetime.date.fromisoformat(last[0]) - datetime.date.fromisoformat(base[0])).days
        if gap > days + 3:
            return None      # a gap wider than the window makes the label a lie
        return {"from": base[0], "to": last[0], "pp": rnd((last[1] - base[1]) * 100, 1),
                "start": rnd(base[1], 3), "end": rnd(last[1], 3)}

    def biggest_days(points, n=5):
        out = []
        for a, b in zip(points, points[1:]):
            da = datetime.date.fromisoformat(a[0]); db = datetime.date.fromisoformat(b[0])
            if (db - da).days == 1:
                out.append({"date": b[0], "pp": rnd((b[1] - a[1]) * 100, 1),
                            "from": rnd(a[1], 3), "to": rnd(b[1], 3)})
        return sorted(out, key=lambda x: -abs(x["pp"]))[:n]

    out = {}
    for key, label in (("consensus_dem", "consensus"), ("pm_dem", "polymarket"),
                       ("k_dem_tight", "kalshi")):
        pts = series.get(key) or []
        out[label] = {"d7": change(pts, 7), "d30": change(pts, 30), "d90": change(pts, 90),
                      "since_primary": (lambda b: b and {"from": b[0], "pp": rnd((pts[-1][1] - b[1]) * 100, 1),
                                                          "start": rnd(b[1], 3), "end": rnd(pts[-1][1], 3)})(
                          at_or_before(pts, "2026-05-19")) if pts else None,
                      "biggest_days": biggest_days(pts)}
    out["arbitrage"] = {
        "pair_ask_total": snap.get("pair_ask_total"),
        "gross_pp": rnd((1 - snap["pair_ask_total"]) * 100, 2) if snap.get("pair_ask_total") else None,
        "net_pp": rnd(snap["pair_net_edge"] * 100, 2) if snap.get("pair_net_edge") is not None else None,
        "top_ask_size": snap.get("top_ask_size"),
    }
    return out


def fmt_k(v):
    return "%gK" % (v / 1000.0)


# ---------------------------------------------------------------------- polls

def poll_block(pollsmax):
    """The polling picture, and the arithmetic that turns it into an average.

    Prefers house.csv, which is the real source and is what the Polls sheet
    reads. It is not in the repository (2.9 MB covering every 2026 House race)
    and is not present in CI, so the fallback is the same GBAO poll as recorded
    by PollsMax. Which one was used is exported, because "one poll" and "one
    poll, seen through a third party" are not the same claim.
    """
    half_life, haircut, assumed_n = 45.0, 0.03, 550
    # house.csv spells the partisan tag DEM/REP; build2.py's LEAN map turns those
    # into the D/R the Polls sheet sums over. Reading the raw column here gave a
    # net partisan sponsorship of 0.00 and an "adjusted" margin identical to the
    # unadjusted one, so the haircut silently did nothing on the one poll it exists
    # for.
    lean = {"DEM": "D", "REP": "R", "D": "D", "R": "R"}
    rows, origin = [], None
    try:
        import pollsrc
        path = pollsrc.resolve()
    except (ImportError, FileNotFoundError):
        path = None
    if path:
        origin = "house.csv"
        by_id = {}
        with open(path) as f:
            for r in csv.DictReader(f):
                if r.get("state") != "PA" or r.get("seat_number") != "7":
                    continue
                try:
                    pct = float(r["pct"])
                except (TypeError, ValueError, KeyError):
                    continue     # a blank pct is one unusable row, not a dead build
                p = by_id.setdefault(r["poll_id"], {"meta": r, "ans": {}})
                p["ans"][r.get("candidate_name") or r.get("answer")] = pct
        for p in by_id.values():
            m = p["meta"]
            if m.get("stage") != "general":
                continue
            dem = next((v for k, v in p["ans"].items() if k and "Brooks" in k), None)
            rep = next((v for k, v in p["ans"].items() if k and "Mackenzie" in k), None)
            try:
                n = int(float(m.get("sample_size")))
            except (TypeError, ValueError):
                n = assumed_n
            rows.append({"pollster": m.get("pollster"), "sponsor": m.get("sponsors") or None,
                         "partisan": lean.get((m.get("partisan") or "").upper()),
                         "start": iso(m.get("start_date")), "end": iso(m.get("end_date")),
                         "n": n, "assumed_n": m.get("sample_size") in (None, ""),
                         "population": (m.get("population") or "").upper() or None,
                         "dem": dem, "rep": rep,
                         "margin": None if None in (dem, rep) else round(dem - rep, 2)})
    if not rows:
        origin = "sources/pollsmax.json"
        for p in ((pollsmax or {}).get("polls") or []):
            dem, rep = p.get("dem_pct"), p.get("rep_pct")
            rows.append({"pollster": p.get("pollster"), "sponsor": p.get("sponsor"),
                         "partisan": lean.get((p.get("partisan") or "").upper()),
                         "start": p.get("start_date"), "end": p.get("end_date"),
                         "n": p.get("sample_size") or assumed_n,
                         "assumed_n": not p.get("sample_size"),
                         "population": p.get("population"), "dem": dem, "rep": rep,
                         "margin": None if None in (dem, rep) else round(dem - rep, 2)})
    rows.sort(key=lambda r: r.get("end") or "")

    today = datetime.date.today()
    wsum = dsum = rsum = dpart = rpart = 0.0
    for r in rows:
        if r["margin"] is None or not r.get("end"):
            continue
        age = (today - datetime.date(*map(int, r["end"].split("-")))).days
        w = r["n"] * 0.5 ** (age / half_life)
        r["days_ago"], r["weight"] = age, rnd(w, 2)
        wsum += w
        dsum += (r["dem"] or 0) * w
        rsum += (r["rep"] or 0) * w
        dpart += w if r["partisan"] == "D" else 0.0
        rpart += w if r["partisan"] == "R" else 0.0
    avg = {}
    if wsum:
        net = (dpart - rpart) / wsum
        weighted = dsum / wsum - rsum / wsum
        avg = {"dem": rnd(dsum / wsum, 2), "rep": rnd(rsum / wsum, 2),
               "margin": rnd(weighted, 2), "net_partisan": rnd(net, 3),
               "adjusted_margin": rnd(weighted - net * haircut * 100, 2)}

    f = (pollsmax or {}).get("forecast") or {}
    model = {"source": (pollsmax or {}).get("source"), "url": (pollsmax or {}).get("url"),
             "retrieved_utc": (pollsmax or {}).get("retrieved_utc"),
             "dem_win_prob": f.get("dem_win_prob"), "rep_win_prob": f.get("rep_win_prob"),
             "projected_margin": f.get("projected_margin"),
             "rating": ((pollsmax or {}).get("ratings") or {}).get("forecast_rating"),
             "methodology": (pollsmax or {}).get("methodology") or {},
             "extraction_problems": (pollsmax or {}).get("extraction_problems") or []}

    return {"origin": origin, "polls": rows, "average": avg, "model": model,
            "assumptions": {"half_life_days": half_life,
                            "house_effect_haircut_pp": haircut * 100,
                            "assumed_sample_size": assumed_n}}


def iso(us_date):
    """house.csv dates are m/d/yy. Everything the site touches is ISO."""
    try:
        return datetime.datetime.strptime(us_date, "%m/%d/%y").strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return None


# -------------------------------------------------------------------- finance

def finance_block(fec):
    if not fec:
        return None
    ie = fec.get("independent_expenditures") or []
    by_target = {}
    for x in ie:
        k = (x.get("target_candidate") or "?", x.get("support_oppose") or "?")
        by_target[k] = by_target.get(k, 0.0) + (x.get("amount") or 0.0)
    return {
        "coverage_through": fec.get("coverage_through"),
        "retrieved_utc": fec.get("retrieved_utc"),
        "cycle": fec.get("cycle"),
        "candidates": [{"name": c.get("name"), "party": c.get("party"),
                        "incumbent": c.get("incumbent"),
                        "receipts": c.get("receipts"), "disbursements": c.get("disbursements"),
                        "cash_on_hand": c.get("cash_on_hand"),
                        # null is not zero. Four of six candidates never filed,
                        # and rendering $0 asserts they raised nothing.
                        "filed": c.get("receipts") is not None}
                       for c in (fec.get("candidates") or [])],
        "independent_expenditure_total": round(sum(x.get("amount") or 0.0 for x in ie), 2),
        "independent_expenditures_by_target": [
            {"target": t, "support_oppose": so, "amount": round(v, 2)}
            for (t, so), v in sorted(by_target.items(), key=lambda kv: -kv[1])],
        "notes": fec.get("notes") or [],
        "extraction_problems": fec.get("extraction_problems") or [],
    }


# ---------------------------------------------- caveats, with the live numbers

def caveats(data, data2, data3, snap, polls, fec, cs):
    """The load-bearing warnings, carrying the numbers that make them concrete.

    These are not decoration. Every one of them is a way the headline figure can
    be read wrong, and the workbook puts each on the sheet it applies to rather
    than in a notes appendix. The site does the same, which is why they are
    generated here with live values rather than typed into the HTML: a caveat
    quoting a stale number is worse than no caveat.
    """
    out = []
    n_general = len([p for p in (polls or {}).get("polls") or [] if p.get("margin") is not None])
    partisan = [p for p in (polls or {}).get("polls") or [] if p.get("partisan")]
    out.append({
        "id": "one-poll", "severity": "high", "topic": "polls",
        "headline": ("Only %d public general-election poll%s exists, and %s Democratic-sponsored."
                     % (n_general, "" if n_general == 1 else "s",
                        "it is" if len(partisan) == n_general and n_general == 1
                        else "%d of them are" % len(partisan))),
        "body": "The average is a single data point wearing a weighting scheme. The recency "
                "weight, the sample-size weight and the house-effect haircut all still apply, "
                "and none of them add information the one poll does not have. Read the adjusted "
                "margin, and lean on the markets.",
    })

    cs_prob = ((cs or {}).get("market_odds") or {}).get("dem_prob")
    k_dem = (snap or {}).get("kalshi_dem")
    gap = None if None in (cs_prob, k_dem) else abs(cs_prob - k_dem) * 100
    out.append({
        "id": "city-and-state", "severity": "high", "topic": "sources",
        "headline": ("City & State is sponsored content that resells a Kalshi feed and "
                     + ("disagrees with Kalshi's own API by %.0f points." % gap if gap is not None
                        else "disagrees with Kalshi's own API.")),
        "body": "Its whole prediction-markets section carries a sponsored-content banner, its "
                "publisher states editorial staff were not involved, and its calls to action are "
                "affiliate trading links. It shows two different Brooks probabilities on one "
                "page, publishes no timestamps, and never names the Republican candidate. It is "
                "displayed here as a data-quality observation and feeds no calculation anywhere "
                "in this project, and a test asserts that.",
        "figures": {"city_and_state_dem": cs_prob, "kalshi_dem": rnd(k_dem, 4),
                    "gap_pp": rnd(gap, 1)},
    })

    out.append({
        "id": "fec-asof", "severity": "medium", "topic": "money",
        "headline": "The two halves of the money picture are not as of the same date.",
        "body": "Candidate totals come from the July Quarterly and cover through %s. "
                "Independent expenditures report continuously and are fresher. Most of the "
                "outside spending logged against this race went into the contested Democratic "
                "primary between 6 and 18 May 2026, not against Mackenzie, and $1.78M of "
                "Mackenzie's receipts is a transfer from a wound-down joint fundraising "
                "committee rather than fresh donations. \"Mackenzie raised $4.36M to Brooks's "
                "$2.39M\" is true and misleading at the same time."
                % ((fec or {}).get("coverage_through") or "an earlier quarter"),
        "figures": {"coverage_through": (fec or {}).get("coverage_through")},
    })

    spreads = [b["best_ask"] - b["best_bid"] for b in ((data2 or {}).get("mov") or [])
               if None not in (b.get("best_bid"), b.get("best_ask"))]
    mids_sum = sum(x for x in (mid(b.get("best_bid"), b.get("best_ask"))
                               for b in ((data2 or {}).get("mov") or [])) if x is not None)
    widest = max(spreads) * 100 if spreads else None
    out.append({
        "id": "thin-markets", "severity": "medium", "topic": "markets",
        "headline": ("The margin ladder is thin: the widest bracket is quoted %.0f cents "
                     "bid to ask." % widest) if widest else "The margin ladder is thin.",
        "body": "Wide spreads inflate every midpoint, so the raw mids across the ten brackets "
                "sum to well above 100%. Read the normalised column. The same caution applies to "
                "any single bracket quoted at a cent or two: that is an absence of interest, not "
                "a considered probability. The winner markets do it too. Kalshi's closing book "
                "on four days in August 2026 was a one-cent bid against an 84-cent ask, whose "
                "midpoint of 42.5% would otherwise appear on the headline chart as the market "
                "briefly calling the race a tossup.",
        "figures": {"widest_spread_pp": rnd(widest, 1), "raw_mid_total": rnd(mids_sum, 4)},
    })

    out.append({
        "id": "kalshi-clamp", "severity": "medium", "topic": "markets",
        "headline": "Kalshi's 0-3 point buckets are a subtraction across two separate markets.",
        "body": "Kalshi quotes no 0-3 rung, so each side's tossup bucket is P(wins) from the "
                "winner market minus P(wins by 3+) from the margin ladder. Two independently "
                "quoted markets can disagree into a negative probability. Negatives are clamped "
                "at zero so the distribution stays readable, and the amount the clamp threw away "
                "is shown beside the chart, because on the workbook it appears only in a consistency "
                "check, which is exactly where a reader would not look.",
    })

    out.append({
        "id": "equal-weight", "severity": "low", "topic": "markets",
        "headline": "Consensus is an equal-weighted average of the two venues, not a "
                    "liquidity-weighted one.",
        "body": "Polymarket carries the larger book on the winner market, so a liquidity "
                "weighting would tilt the consensus toward it. Equal weighting is a choice, and "
                "the two venue lines are plotted separately so the choice is visible rather "
                "than baked in.",
        "figures": {"pm_volume": ((data or {}).get("pm_event") or {}).get("volume")},
    })

    out.append({
        "id": "hand-curated", "severity": "low", "topic": "sources",
        "headline": "PollsMax, City & State and FEC are hand-curated extractions, not live feeds.",
        "body": "The scheduled refresh re-reads these files; it does not re-fetch them. Their "
                "own retrieval timestamps are shown wherever their numbers appear, and they can "
                "be arbitrarily older than the market data on the same screen.",
    })
    return out


# ---------------------------------------------------------------- assumptions

def assumptions(mids, polls, data2):
    """Every number on the site that came from judgement rather than a source.

    Mirrors the ASSUMPTIONS block on the workbook's Notes & Sources sheet. Kept
    in one list so the page can render them all in one place and none of them
    can quietly stop being displayed.
    """
    mov = {b["bracket"]: b["midpoint"] for b in (data2 or {}).get("mov") or []}
    pa = (polls or {}).get("assumptions") or {}
    return [
        {"what": "Polymarket open-ended bracket midpoints",
         "value": "Democrat 18%%+ = %+.1f, Republican 6%%+ = %+.1f"
                  % (mov.get("Democrat 18%+", 20.0), mov.get("Republican 6%+", -8.0)),
         "why": "Closed brackets use their true centre. The two open-ended ones have no centre, "
                "so a representative point was chosen. They drive the expected-margin figure."},
        {"what": "Kalshi open-ended rung midpoints",
         "value": "Democrats 15+ = %+.1f, Republicans 9+ = %+.1f"
                  % (mids["D_TOP_MID"], mids["R_TOP_MID"]),
         "why": "Same judgement call on the threshold ladder, where the outermost rung is "
                "unbounded above."},
        {"what": "Turnout representative points",
         "value": "below 310K = %s, above 370K = %s"
                  % ("{:,}".format(int(mids["TURN_LOW_MID"])),
                     "{:,}".format(int(mids["TURN_TOP_MID"]))),
         "why": "The turnout ladder's two tails are open-ended. 2024 turnout in this district "
                "was 403,314, which is above the top quoted threshold."},
        {"what": "Seat ladder midpoints and baseline",
         "value": "Below 7 = 6, Above 12 = 13, current Democratic baseline = 8",
         "why": "Exact brackets use their own number. The baseline is hand-entered and should be "
                "checked against the current delegation before the net-gain figure is trusted."},
        {"what": "Poll recency half-life",
         "value": "%g days" % pa.get("half_life_days", 45),
         "why": "A poll's weight halves every 45 days. A reasonable default for a race still "
                "months out, not a fitted value."},
        {"what": "Partisan house-effect haircut",
         "value": "%.1f pp" % pa.get("house_effect_haircut_pp", 3.0),
         "why": "Subtracted from the weighted margin in proportion to net partisan sponsorship. "
                "It matters here: the only general-election poll is Democratic-sponsored, so the "
                "adjusted margin is the more conservative read."},
        {"what": "General poll sample size",
         "value": "%d likely voters" % pa.get("assumed_sample_size", 550),
         "why": "The sample_size field is empty for this poll in house.csv; this is the figure "
                "PollsMax reports for the same GBAO survey. With one poll in the log it changes "
                "nothing."},
        {"what": "Seat ladder mid fallback",
         "value": "half the ask when no bid rests",
         "why": "'Below 7' and 'Above 12' have an ask and no resting bid. Both quote at a cent "
                "or two, so this barely moves the expected-seats figure."},
        {"what": "Wide-book threshold on the Kalshi history",
         "value": "%d cents bid to ask" % round(WIDE_SPREAD * 100),
         "why": "On 14, 15, 18 and 19 Aug 2026 Kalshi's closing book was a one-cent bid against "
                "an 84-cent ask. The midpoint of that is 42.5%, which is arithmetic, not a "
                "price. Days quoted wider than this are drawn as separate points rather than as "
                "part of the line, and are left out of the consensus series. Nothing is "
                "deleted: the raw mid is still in the full export."},
        {"what": "Kalshi fee model in the arbitrage check",
         "value": "0.07 x p x (1-p) per contract",
         "why": "Fees are largest exactly where these markets sit. A run on 29 Aug 2026 showed a "
                "1.00pp gross edge against 2.44pp of fees: a loss, reported as an arbitrage, "
                "until the net figure replaced the gross one."},
    ]


def definitions():
    """How each figure on the page is computed.

    Mirrors the DEFINITIONS block on the workbook's Notes & Sources sheet, in
    the export rather than in the HTML so the two can be compared and so a test
    can assert they are all still being shipped. Several of these read like
    pedantry and are not: "mid, not last trade" and "normalised, not raw" are
    each the fix for a wrong number that shipped.
    """
    return [
        ("Mid price",
         "(best bid + best ask) / 2. Used rather than last trade, which on books this thin "
         "can be days stale."),
        ("Kalshi YES ask",
         "Derived as 1 minus the best NO bid. Kalshi's REST market object returns null for "
         "yes_bid, yes_ask, volume and open interest on these markets, so top of book has to "
         "come from the order book. Buying YES at p and selling NO at 1-p are the same trade."),
        ("Normalised probability",
         "Each outcome's mid divided by the sum of mids across the group, which strips out "
         "the overround so the set sums to 100%."),
        ("Overround",
         "Sum of mids minus 1. On the margin ladder this runs well above 100% because several "
         "thin brackets are quoted with very wide spreads, and a wide spread inflates its own "
         "midpoint. Read the normalised figure, never the raw one."),
        ("Expected margin",
         "Sum of (normalised probability x signed bracket midpoint) across the ladder, in "
         "percentage points, positive for a Democratic win."),
        ("Consensus probability",
         "Equal-weighted mean of the two venue mids on the winner market. Not "
         "liquidity-weighted, though Polymarket carries the larger book."),
        ("Arbitrage edge",
         "Cheapest Democratic ask plus cheapest Republican ask, minus 1, minus an estimated "
         "Kalshi fee of 0.07 x p x (1-p) per contract. Gross edge alone is not a signal: a run "
         "on 29 Aug 2026 showed 1.00pp gross against 2.44pp of fees."),
        ("Kalshi open interest",
         "The larger of the two legs rather than their sum, since they are two sides of one "
         "race. Volume sums both."),
        ("Date alignment",
         "Every date here is a UTC day, and every join between venues is on the date value "
         "rather than on row position, so a refresh that changes row counts cannot shift a "
         "series against another."),
        ("Missing values",
         "A day a venue did not quote is absent from the series, not zero, and the chart "
         "breaks its line there. Nothing is interpolated."),
    ]


# ------------------------------------------------------------------ freshness

def freshness(data, data2, data3, pollsmax, cs, fec, snap, wb_path):
    """Per-source last-updated, so no part of the page can borrow another's."""
    def last(hist):
        return max(hist) if hist else None

    def mtime(path):
        try:
            return (datetime.datetime.utcfromtimestamp(os.path.getmtime(path))
                    .isoformat(timespec="seconds") + "Z")
        except OSError:
            return None

    return [
        {"id": "polymarket", "label": "Polymarket", "kind": "live",
         "detail": "Polled directly from your browser, and refreshed by the scheduled build.",
         "snapshot_utc": mtime("data.json"),
         "last_history_day": last((data or {}).get("pm_history")),
         "days": len((data or {}).get("pm_history") or {})},
        {"id": "kalshi", "label": "Kalshi", "kind": "live",
         "detail": "Read server-side every ten minutes; history from the scheduled build.",
         "snapshot_utc": mtime("data.json"),
         "last_history_day": last((data or {}).get("k_history")),
         "days": len((data or {}).get("k_history") or {})},
        {"id": "pm_margin", "label": "Polymarket margin ladder", "kind": "live",
         "detail": "Ten exclusive brackets. Polled live; history from the scheduled build.",
         "snapshot_utc": mtime("data2.json"),
         "last_history_day": last((data2 or {}).get("mov_history")),
         "days": len((data2 or {}).get("mov_history") or {})},
        {"id": "kalshi_ladders", "label": "Kalshi margin and turnout ladders", "kind": "snapshot",
         "detail": "Nested thresholds, signed requests only.",
         "snapshot_utc": mtime("data3.json"),
         "last_history_day": last((data3 or {}).get("mov_d_history")),
         "days": len((data3 or {}).get("mov_d_history") or {})},
        {"id": "polls", "label": "Polls (NYT/538 house file)", "kind": "manual",
         "detail": "Re-read on every scheduled run, but only changes when a new CSV is saved by "
                   "hand into the project directory.",
         "snapshot_utc": (snap or {}).get("polls_csv_mtime"),
         "content_since": (snap or {}).get("polls_content_since"),
         "content_age_days": (snap or {}).get("polls_content_age_days")},
        {"id": "pollsmax", "label": "PollsMax forecast", "kind": "manual",
         "detail": "A one-off extraction, not an API this pipeline polls.",
         "snapshot_utc": (pollsmax or {}).get("retrieved_utc")},
        {"id": "cityandstate", "label": "City & State PA", "kind": "manual",
         "detail": "Sponsored content. Display only, feeds no calculation.",
         "snapshot_utc": (cs or {}).get("retrieved_utc")},
        {"id": "workbook", "label": "Excel workbook", "kind": "build",
         "detail": "Rebuilt by every scheduled run, 13 sheets and 13 native charts.",
         "snapshot_utc": mtime(wb_path)},
    ]


# ----------------------------------------------------------------------- main

def build(out_dir=OUT_DIR, window_days=WINDOW_DAYS, copy_workbook=True):
    """Write every site/data file. Returns {filename: bytes}."""
    data = read_json("data.json") or {}
    data2 = read_json("data2.json") or {}
    data3 = read_json("data3.json") or {}
    pollsmax = read_json(os.path.join("sources", "pollsmax.json"))
    cs = read_json(os.path.join("sources", "cityandstate.json"))
    fec = read_json(os.path.join("sources", "fec.json"))

    snap, notes, alerts, origin = figures()
    mids = midpoints()

    os.makedirs(out_dir, exist_ok=True)
    series = market_series(data, data2, data3, pollsmax, mids)
    polls = poll_block(pollsmax)
    dist = distributions(data, data2, data3, mids)

    cutoff = (datetime.date.today() - datetime.timedelta(days=window_days)).isoformat()
    windowed = {k: since(v, cutoff) for k, v in series.items()}

    wb_here = os.path.abspath(WB)
    wb_out = os.path.join(os.path.dirname(out_dir.rstrip("/")) or ".", WB)
    have_wb = os.path.exists(wb_here)
    if copy_workbook and have_wb:
        # Pages can only serve what is committed, so the download link points at
        # a copy inside site/. It is the one large binary in this history; the
        # README says why and how to opt out.
        shutil.copy2(wb_here, wb_out)

    written = {}
    written["series.json"] = write_json(os.path.join(out_dir, "series.json"), {
        "window_days": window_days, "from": cutoff,
        "full": "data/series-full.json", "series": windowed})
    written["series-full.json"] = write_json(os.path.join(out_dir, "series-full.json"), {
        "window_days": None, "series": series})
    written["distribution.json"] = write_json(os.path.join(out_dir, "distribution.json"), dist)
    written["polls.json"] = write_json(os.path.join(out_dir, "polls.json"), polls)
    written["finance.json"] = write_json(os.path.join(out_dir, "finance.json"),
                                         finance_block(fec) or {})
    written["caveats.json"] = write_json(os.path.join(out_dir, "caveats.json"), {
        "caveats": caveats(data, data2, data3, snap, polls, fec, cs),
        "assumptions": assumptions(mids, polls, data2),
        "definitions": [{"term": t, "meaning": m} for t, m in definitions()],
        "city_and_state": {"url": (cs or {}).get("url"),
                           "dem_prob": ((cs or {}).get("market_odds") or {}).get("dem_prob"),
                           "rep_prob": ((cs or {}).get("market_odds") or {}).get("rep_prob"),
                           "retrieved_utc": (cs or {}).get("retrieved_utc"),
                           "display_only": True}})
    written["divergence.json"] = write_json(os.path.join(out_dir, "divergence.json"), {
        "divergence": divergence_block(data, series),
        "moves": moves_block(series, snap)})
    written["headline.json"] = write_json(os.path.join(out_dir, "headline.json"), {
        "snapshot": snap, "notes": notes, "alerts": alerts, "origin": origin})

    # The manifest lists the payload files and not itself: it is written last,
    # so its own size is not known while it is being serialised, and a size it
    # could only guess at is worse than an absent one.
    today = datetime.date.today()
    payload = dict(written)
    written["manifest.json"] = write_json(os.path.join(out_dir, "manifest.json"), {
        "generated_utc": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "race": {"district": "PA-07", "office": "US House",
                 "democrat": "Bob Brooks", "republican": "Ryan Mackenzie",
                 "election": ELECTION.isoformat(),
                 "days_to_election": (ELECTION - today).days},
        "colours": {"D": "#2E5FA3", "R": "#C0392B"},
        "freshness": freshness(data, data2, data3, pollsmax, cs, fec, snap, wb_here),
        "collector_problems": (list(data.get("problems") or [])
                               + list(data2.get("problems") or [])
                               + list(data3.get("problems") or [])),
        "workbook": {"available": bool(copy_workbook and have_wb),
                     "href": WB,
                     "bytes": os.path.getsize(wb_out) if (copy_workbook and have_wb) else None},
        "files": payload,
    })
    return written


def main(argv):
    out = OUT_DIR
    if "--out" in argv:
        out = argv[argv.index("--out") + 1]
    written = build(out_dir=out, copy_workbook="--no-workbook" not in argv)
    total = sum(written.values())
    for name in sorted(written):
        print("  %-20s %7d B" % (name, written[name]))
    print("site export ok: %d files, %.1f KB into %s" % (len(written), total / 1024.0, out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
