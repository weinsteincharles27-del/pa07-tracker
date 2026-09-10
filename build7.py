"""Model forecast, third-party aggregators, and campaign finance.

Three outside sources, each answering a different question and each needing its
own health warning:

  PollsMax      a statistical forecast (polls + fundamentals + Monte Carlo).
                Genuinely independent of the markets, so the gap between the two
                is the most informative number on the sheet.
  City & State  a third-party odds tracker. It resells a Kalshi feed, disagrees
                with Kalshi, disagrees with ITSELF, and is sponsored content.
                Recorded as a data-quality observation, not as a price.
  FEC           campaign finance, not polling at all. Filings lag by months, so
                the coverage-through date is displayed next to every figure.

Each section is built only if its source file is present, so a failed extraction
degrades to a missing section rather than a broken build.
"""
import json, os, datetime
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.comments import Comment

R = json.load(open("refs.json"))
ASOF = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

F = "Arial"
BLUE = Font(name=F, size=10, color="0000FF"); BLACK = Font(name=F, size=10)
GREEN = Font(name=F, size=10, color="008000"); BOLD = Font(name=F, size=10, bold=True)
TITLE = Font(name=F, size=16, bold=True, color="1F3864")
SUB = Font(name=F, size=9, italic=True, color="595959")
SECT = Font(name=F, size=11, bold=True, color="FFFFFF")
HDR = Font(name=F, size=9, bold=True, color="FFFFFF")
NOTE = Font(name=F, size=9, italic=True, color="595959")
BIG = Font(name=F, size=18, bold=True, color="1F3864")
WARN = Font(name=F, size=9, italic=True, color="9C2B2B")
SECTF = PatternFill("solid", fgColor="1F3864"); HDRF = PatternFill("solid", fgColor="4472C4")
DEMF = PatternFill("solid", fgColor="DEEBF7"); REPF = PatternFill("solid", fgColor="FCE4E4")
YEL = PatternFill("solid", fgColor="FFFF00"); GREY = PatternFill("solid", fgColor="F2F2F2")
BAND = PatternFill("solid", fgColor="F7F9FC"); WARNF = PatternFill("solid", fgColor="FDEDED")
thin = Side(style="thin", color="BFBFBF"); BOX = Border(left=thin, right=thin, top=thin, bottom=thin)
PCT = '0.0%'; PCT2 = '0.00%'; DIFF = '+0.0%;-0.0%;0.0%'; DATE = 'yyyy-mm-dd'
NUM = '#,##0;(#,##0);-'; USD = '$#,##0;($#,##0);-'; PTS = '+0.0" pts";-0.0" pts";0.0" pts"'


def load(name):
    p = os.path.join("sources", name)
    if not os.path.exists(p):
        return None
    try:
        with open(p) as f:
            return json.load(f)
    except ValueError:
        return None


PM = load("pollsmax.json")
CS = load("cityandstate.json")
FEC = load("fec.json")

wb = load_workbook("_stage2c.xlsx")


def section(ws, row, text, width):
    ws.cell(row, 1, text).font = SECT
    for c in range(1, width + 1): ws.cell(row, c).fill = SECTF
    return row + 1


def headers(ws, row, cols):
    for i, h in enumerate(cols, 1):
        c = ws.cell(row, i, h); c.font = HDR; c.fill = HDRF; c.border = BOX
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[row].height = 30
    return row + 1


def put(ws, r, c, v, font=BLACK, fmt=None, fill=None, align=None, border=True):
    cell = ws.cell(r, c, v); cell.font = font
    if fmt: cell.number_format = fmt
    if fill: cell.fill = fill
    if align: cell.alignment = Alignment(horizontal=align)
    if border: cell.border = BOX
    return cell


def note(ws, r, text, span, font=NOTE):
    c = ws.cell(r, 1, text); c.font = font
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=span)
    ws.cell(r, 1).alignment = Alignment(wrap_text=True, vertical="top")
    if len(text) > 150:
        ws.row_dimensions[r].height = 13 * (1 + len(text) // 150)
    return r + 1


def block(ws, r, label, text, span=9, width=None):
    """A labelled paragraph — used for the methodology prose."""
    put(ws, r, 1, label, BOLD)
    c = put(ws, r, 2, text or "—", BLUE)
    ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=span)
    c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[r].height = max(14, 11 * (1 + len(text or "") // 110))
    return r + 1


PMD, KD = R["PM_MID_D"], R["K_MID_D"]
REFS = {}

# =====================================================================
# SHEET: Forecast & Aggregators
# =====================================================================
fa = wb.create_sheet("Forecast & Aggregators")
fa.sheet_view.showGridLines = False
fa["A1"] = "Forecast & Aggregators"; fa["A1"].font = TITLE
fa["A2"] = ("Outside views of PA-07: a statistical forecast, a third-party odds tracker, and what "
            "each disagrees with the markets about. Compiled %s." % ASOF)
fa["A2"].font = SUB
for k, v in {"A": 26, "B": 15, "C": 15, "D": 15, "E": 14, "F": 14, "G": 14,
             "H": 14, "I": 14}.items():
    fa.column_dimensions[k].width = v

r = 4
r = section(fa, r, "MODEL vs MARKET — the headline disagreement", 9)
MKT = r
put(fa, r, 1, "Market consensus P(Dem)", BOLD)
put(fa, r, 2, '=AVERAGE(Polymarket!D{0},Kalshi!E{1})'.format(PMD, KD), BIG, PCT, YEL)
fa.merge_cells(start_row=r, start_column=2, end_row=r, end_column=3); fa.row_dimensions[r].height = 26
put(fa, r, 4, "Equal-weighted mean of the two venue mids, read directly from their APIs.",
    NOTE, None, None, None, False)
r += 1
put(fa, r, 1, "PollsMax model P(Dem)", BOLD)
fp = (PM or {}).get("forecast") or {}
put(fa, r, 2, fp.get("dem_win_prob"), BIG, PCT, YEL)
fa.merge_cells(start_row=r, start_column=2, end_row=r, end_column=3); fa.row_dimensions[r].height = 26
put(fa, r, 4, "Polls plus fundamentals through a Monte Carlo, not a traded price.",
    NOTE, None, None, None, False)
MODEL = r; r += 1
put(fa, r, 1, "Gap (market − model)", BOLD)
put(fa, r, 2, '=IF(AND(ISNUMBER(B{0}),ISNUMBER(B{1})),B{0}-B{1},"")'.format(MKT, MODEL),
    BOLD, DIFF, YEL)
GAP = r; r += 1
put(fa, r, 1, "Projected margin (model)", BOLD)
put(fa, r, 2, fp.get("projected_margin"), BLUE, '+0.0" pts";-0.0" pts";0.0" pts"')
put(fa, r, 4, "Model's central vote-margin estimate, D positive.", NOTE, None, None, None, False)
r += 1
put(fa, r, 1, "Rating (model)", BOLD)
put(fa, r, 2, ((PM or {}).get("ratings") or {}).get("label")
   if isinstance((PM or {}).get("ratings"), dict) else None, BLUE)
r += 1
fa.cell(GAP, 2).comment = Comment(
    "These answer different questions and are not expected to agree exactly. The model is a "
    "vote-share estimate pushed through a margin-to-odds curve; the market is what people will "
    "pay. A model projecting a ~1-point race is mechanically near a coin flip, while traders "
    "pricing the same race well above 50% are expressing confidence the model's uncertainty "
    "band does not. Read a large gap as a question about which is mispriced, not as an error "
    "in either.", "Tracker")
r = note(fa, r, "A gap this wide is the single most interesting number in this workbook: the model "
                "projects a roughly one-point race yet the markets price the Democrat far above "
                "even odds. Either the market knows something the fundamentals do not, or it is "
                "overconfident about a tossup.", 9)
r += 1

# ---------------- PollsMax ----------------
if PM:
    r = section(fa, r, "POLLSMAX — forecast detail", 9)
    fc = PM.get("forecast") or {}
    av = PM.get("average") or {}
    for lbl, val, fmt in [
            ("Brooks (D) win probability", fc.get("dem_win_prob"), PCT),
            ("Mackenzie (R) win probability", fc.get("rep_win_prob"), PCT),
            ("Projected margin (D−R)", fc.get("projected_margin"), '+0.0" pts";-0.0" pts";0.0" pts"'),
            ("Polling average — Brooks", (av.get("dem_pct") or 0) / 100.0 if av.get("dem_pct") is not None else None, PCT),
            ("Polling average — Mackenzie", (av.get("rep_pct") or 0) / 100.0 if av.get("rep_pct") is not None else None, PCT),
            ("Polling average margin", (av.get("margin") or 0) / 100.0 if av.get("margin") is not None else None, DIFF),
            ("Polls in their average", len(PM.get("polls") or []), NUM),
            ("Average as of", av.get("as_of"), None),
            ("Retrieved", PM.get("retrieved_utc"), None)]:
        put(fa, r, 1, lbl, BOLD); put(fa, r, 2, val, BLUE, fmt)
        fa.merge_cells(start_row=r, start_column=2, end_row=r, end_column=4); r += 1
    iv = fc.get("interval")
    if iv:
        r = note(fa, r, "Uncertainty band: %s" % iv, 9)
    r += 1

    r = section(fa, r, "POLLSMAX — methodology, in their words", 9)
    m = PM.get("methodology") or {}
    for lbl, key in [("Summary", "summary"), ("Weighting", "weighting"),
                     ("Recency", "recency"), ("Pollster quality", "pollster_quality"),
                     ("House effects", "house_effects"), ("Forecast model", "forecast_model")]:
        r = block(fa, r, lbl, m.get(key))
    w = (PM.get("extra") or {}).get("forecast_input_weights_this_race")
    if isinstance(w, dict):
        r = block(fa, r, "Input weights (PA-07)",
                  "; ".join("%s = %s" % (k, v) for k, v in w.items() if k != "note"))
    r = note(fa, r, "Their polling average rests on ONE poll, and that poll is Democratic-sponsored. "
                    "By their own description the forecast leans mostly on fundamentals and an "
                    "editorial rating rather than on polling, which is worth knowing before treating "
                    "it as an independent check on the market.", 9)
    r += 1

    # ---- daily foredcast trend ----
    ts = ((PM.get("extra") or {}).get("forecast_trend_series") or {})
    wp = ts.get("win_probability_pct") or {}
    vs = ts.get("vote_share_pct") or {}
    dates = wp.get("dates") or vs.get("dates") or []
    if dates:
        r = section(fa, r, "POLLSMAX — daily forecast trend", 9)
        TH = headers(fa, r, ["Date", "Brooks win prob (model)", "Upper", "Lower",
                             "Brooks vote share", "Mackenzie vote share",
                             "Polymarket P(Dem) same day", "Model − market", "Axis label"])
        def col(d, k):
            v = d.get(k)
            return v if isinstance(v, list) else []
        bw, bu, bl = col(wp, "brooks_win_prob_pct"), col(wp, "brooks_win_prob_upper"), col(wp, "brooks_win_prob_lower")
        bv, mv = col(vs, "brooks_pct"), col(vs, "mackenzie_pct")
        for i, day in enumerate(dates):
            rr = TH + i
            try:
                put(fa, rr, 1, datetime.datetime.strptime(day, "%Y-%m-%d"), BLUE, DATE)
            except (ValueError, TypeError):
                put(fa, rr, 1, day, BLUE)
            for c, arr in ((2, bw), (3, bu), (4, bl), (5, bv), (6, mv)):
                v = arr[i] if i < len(arr) else None
                put(fa, rr, c, (v / 100.0) if isinstance(v, (int, float)) else None, BLUE, PCT)
            # Pull the market price for the SAME calendar day so model and market
            # share one date axis and can be charted against each other. INDEX onto
            # a blank cell returns 0, so guard it the way build3.py's lookup() does.
            idx = ('INDEX(Polymarket!$B${0}:$B${1},MATCH($A{2},Polymarket!$A${0}:$A${1},0))'
                   .format(R["PM_FIRST"], R["PM_LAST"], rr))
            put(fa, rr, 7, '=IFERROR(IF({0}=0,"",{0}),"")'.format(idx), GREEN, PCT)
            put(fa, rr, 8, '=IF(AND(ISNUMBER(B{0}),ISNUMBER(G{0})),B{0}-G{0},"")'.format(rr),
                BLACK, DIFF)
            try:
                put(fa, rr, 9, datetime.datetime.strptime(day, "%Y-%m-%d").strftime("%d %b"), BLUE)
            except (ValueError, TypeError):
                put(fa, rr, 9, str(day), BLUE)
            if i % 2:
                for c in range(1, 9): fa.cell(rr, c).fill = BAND
        REFS["PM_TREND_FIRST"] = TH
        REFS["PM_TREND_LAST"] = TH + len(dates) - 1
        fa.cell(TH - 1, 7).comment = Comment(
            "Polymarket's Democratic price on the same calendar date, matched exactly — blank "
            "where the market has no quote for that day. This is what makes the model and the "
            "market directly comparable: same day, same question, two different ways of "
            "answering it.", "Tracker")
        r = TH + len(dates)
        last = dates[-1] if dates else "n/a"
        r = note(fa, r, "Series runs %s to %s. NOTE: PollsMax's own page claims a later 'last updated' "
                        "time than the final plotted point — their chart data stops at %s, so the "
                        "headline figures above may be fresher than this trend."
                        % (dates[0], last, last), 9)
        r += 1
    fa.freeze_panes = fa.cell(4, 1)

# ---------------- third-party trackers ----------------
if CS:
    r = section(fa, r, "THIRD-PARTY ODDS TRACKERS — treat as a data-quality check, not a price", 9)
    mo = CS.get("market_odds") or {}
    TR = headers(fa, r, ["Tracker", "Their P(Dem)", "Venue claimed", "Our direct read",
                         "Gap vs ours", "As of", "", "", ""])
    put(fa, TR, 1, "City & State PA", BOLD)
    put(fa, TR, 2, mo.get("dem_prob"), BLUE, PCT)
    put(fa, TR, 3, ", ".join(mo.get("venues") or []) or "—", BLUE)
    put(fa, TR, 4, '=Kalshi!E{0}'.format(KD), GREEN, PCT)
    put(fa, TR, 5, '=IFERROR(B{0}-D{0},"")'.format(TR), BLACK, DIFF, YEL)
    put(fa, TR, 6, mo.get("as_of") or "not stated", BLUE)
    REFS["CS_ROW"] = TR
    fa.cell(TR, 5).comment = Comment(
        "City & State says it sources Kalshi (via an aggregator, PredictionEdge). We read Kalshi "
        "directly from its API, so a gap here is drift in their pipeline, not a difference of "
        "opinion about the race. Their own page also shows TWO different Brooks numbers that "
        "disagree with each other.", "Tracker")
    r = TR + 1
    for n in (CS.get("notes") or [])[:6]:
        r = note(fa, r, "• " + n, 9)
    r = note(fa, r, "⚠ The City & State prediction-markets section is labelled SPONSORED CONTENT — its "
                    "publisher states editorial staff were not involved, and its calls to action are "
                    "affiliate trading links. Nothing here is used as an input to any figure in this "
                    "workbook; it is logged so the discrepancy is visible.", 9, WARN)
    fa.cell(r - 1, 1).fill = WARNF
    r += 1

# =====================================================================
# SHEET: Campaign Finance
# =====================================================================
if FEC:
    cf = wb.create_sheet("Campaign Finance")
    cf.sheet_view.showGridLines = False
    cf["A1"] = "Campaign Finance — PA-07 (FEC)"; cf["A1"].font = TITLE
    cf["A2"] = ("Money raised and spent in the 2026 PA-07 race, from the OpenFEC API. This is "
                "finance, not polling. Compiled %s." % ASOF)
    cf["A2"].font = SUB
    for k, v in {"A": 26, "B": 18, "C": 16, "D": 16, "E": 16, "F": 16, "G": 16,
                 "H": 18, "I": 14}.items():
        cf.column_dimensions[k].width = v

    r = 4
    cov = FEC.get("coverage_through")
    r = section(cf, r, "COVERAGE", 9)
    put(cf, r, 1, "Figures current through", BOLD)
    put(cf, r, 2, cov or "not stated", BLUE, None, YEL)
    cf.merge_cells(start_row=r, start_column=2, end_row=r, end_column=4)
    cf.cell(r, 2).comment = Comment(
        "FEC filings lag by months — quarterly for most House committees. Everything on this "
        "sheet is as of this date, NOT today, and the gap widens every day until the next "
        "filing deadline. Do not read a stale cash-on-hand figure as current.", "Tracker")
    r += 1
    put(cf, r, 1, "Retrieved", BOLD); put(cf, r, 2, FEC.get("retrieved_utc"), BLUE)
    cf.merge_cells(start_row=r, start_column=2, end_row=r, end_column=4); r += 2

    r = section(cf, r, "CANDIDATE TOTALS — 2026 cycle", 9)
    CH = headers(cf, r, ["Candidate", "Party", "Receipts", "Disbursements", "Cash on Hand",
                         "Individual", "PAC", "Filed?", "Through"])
    cands = FEC.get("candidates") or []
    for i, c in enumerate(cands):
        rr = CH + i
        party = (c.get("party") or "").upper()
        fill = DEMF if party.startswith("DEM") or party == "D" else (
            REPF if party.startswith("REP") or party == "R" else None)
        put(cf, rr, 1, c.get("name"), BOLD, None, fill)
        put(cf, rr, 2, c.get("party"), BLUE)
        for col, key in ((3, "receipts"), (4, "disbursements"), (5, "cash_on_hand"),
                         (6, "individual_contributions"), (7, "pac_contributions")):
            put(cf, rr, col, c.get(key), BLUE, USD)
        # A candidate who never filed must not read as one who raised nothing.
        filed = c.get("receipts") is not None
        put(cf, rr, 8, "yes" if filed else "never filed", BLACK if filed else NOTE,
            None, None if filed else GREY)
        put(cf, rr, 9, (c.get("coverage_through") or cov) if filed else "—", BLUE)
    CN = CH + max(len(cands), 1) - 1
    TOT = CN + 1
    put(cf, TOT, 1, "TOTAL", BOLD, None, GREY)
    for col in (3, 4, 5, 6, 7):
        put(cf, TOT, col, '=SUM({0}{1}:{0}{2})'.format(chr(64 + col), CH, CN), BOLD, USD)
    REFS["FEC_FIRST"], REFS["FEC_LAST"] = CH, CN
    r = TOT + 2

    r = section(cf, r, "DERIVED", 9)
    # The two candidates who actually filed, identified by party rather than by
    # position. FEC returns candidates in no guaranteed order, and a positional
    # subtraction would silently flip sign the day that order changes.
    filed_c = [c for c in cands if c.get("receipts") is not None]
    dem = next((c for c in filed_c if (c.get("party") or "").upper().startswith("DEM")), None)
    rep = next((c for c in filed_c if (c.get("party") or "").upper().startswith("REP")), None)
    if dem and rep:
        nm = ('INDEX($E${0}:$E${1},MATCH("{2}",$A${0}:$A${1},0))'.format(CH, CN, dem["name"]),
              'INDEX($E${0}:$E${1},MATCH("{2}",$A${0}:$A${1},0))'.format(CH, CN, rep["name"]))
        put(cf, r, 1, "Cash advantage: %s (D) - %s (R)" % (dem["name"], rep["name"]), BOLD)
        put(cf, r, 2, '=IFERROR({0}-{1},"")'.format(*nm), BOLD, USD, YEL)
        put(cf, r, 4, "Negative means the Republican holds more cash.", NOTE, None, None, None, False)
        cf.cell(r, 2).comment = Comment(
            "Matched on candidate NAME, not row position: the FEC API returns candidates in no "
            "guaranteed order, and a positional subtraction would silently flip sign the day "
            "that order changed.", "Tracker")
        r += 1
        put(cf, r, 1, "Combined receipts", BOLD)
        put(cf, r, 2, '=SUM(C{0}:C{1})'.format(CH, CN), BLACK, USD); r += 1
        put(cf, r, 1, "Burn rate (disbursed / raised)", BOLD)
        put(cf, r, 2, '=IFERROR(SUM(D{0}:D{1})/SUM(C{0}:C{1}),"")'.format(CH, CN), BLACK, PCT); r += 1
    r += 1

    ies = FEC.get("independent_expenditures") or []
    if ies:
        r = section(cf, r, "INDEPENDENT EXPENDITURES", 9)
        IH = headers(cf, r, ["Target", "Support / Oppose", "Amount", "Committee", "As of",
                             "", "", "", ""])
        for i, e in enumerate(ies):
            rr = IH + i
            so = (e.get("support_oppose") or "").upper()
            put(cf, rr, 1, e.get("target_candidate"), BOLD)
            put(cf, rr, 2, "Support" if so == "S" else ("Oppose" if so == "O" else so), BLACK,
                None, DEMF if so == "S" else REPF)
            put(cf, rr, 3, e.get("amount"), BLUE, USD)
            put(cf, rr, 4, e.get("committee"), BLUE)
            put(cf, rr, 5, e.get("as_of"), BLUE)
        IN_ = IH + len(ies) - 1
        put(cf, IN_ + 1, 1, "TOTAL", BOLD, None, GREY)
        put(cf, IN_ + 1, 3, '=SUM(C{0}:C{1})'.format(IH, IN_), BOLD, USD)
        r = IN_ + 3
        r = note(cf, r, "Outside money is reported continuously rather than quarterly, so these figures "
                        "are usually fresher than the candidate totals above — the two are not "
                        "as-of the same date.", 9)
        r += 1

    r = section(cf, r, "READ THE MONEY WITH THESE TWO FACTS", 9)
    r = note(cf, r, "1. TIMING. Candidate totals above come from the July Quarterly and are current only "
                    "through %s — roughly two months stale on arrival, widening until the October "
                    "Quarterly. Independent expenditures below report continuously and are FRESHER. "
                    "The two halves of this sheet are not as-of the same date."
                    % (cov or "the stated date"), 9)
    r = note(cf, r, "2. WHAT THE MONEY WAS FOR. Most of the outside spending logged here was spent in "
                    "May 2026 inside the contested Democratic PRIMARY, not against Mackenzie in the "
                    "general — so it is not evidence of general-election engagement. And a large share "
                    "of Mackenzie's receipts is a transfer from a wound-down joint fundraising "
                    "committee rather than fresh donor money, which inflates his receipts line "
                    "relative to actual fundraising.", 9)
    r += 1

    for n in (FEC.get("notes") or [])[:8]:
        r = note(cf, r, "• " + n, 9)
    if FEC.get("extraction_problems"):
        r = note(cf, r, "Extraction problems: " + "; ".join(FEC["extraction_problems"][:4]), 9, WARN)

json.dump(REFS, open("f7refs.json", "w"))
wb.save("_stage2d.xlsx")
print("stage2d ok — forecast %s | city&state %s | fec %s"
      % ("yes" if PM else "no", "yes" if CS else "no", "yes" if FEC else "no"))
