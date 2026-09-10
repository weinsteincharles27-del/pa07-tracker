"""Kalshi margin-of-victory ladder and the Voter Turnout sheet.

Kalshi states margin and turnout as THRESHOLD markets ("3+ pts", "Above 340K"),
so each rung is P(value >= strike) — a survival curve, not a set of mutually
exclusive brackets. Differencing adjacent rungs turns it back into buckets.

Two consequences drive the design here:

  * The lowest margin rung is ">= 3 pts", so the 0-3 bucket is not quoted. It has
    to come from the winner market: P(win by 0-3) = P(win) - P(win by 3+). That
    reaches across two independent Kalshi markets.
  * Those two markets are quoted independently and can disagree. When the margin
    rung is bid above the winner market, the subtraction goes NEGATIVE, which is
    not a probability. The display clamps at zero and the CONSISTENCY CHECK block
    reports, from live cells, whether the inversion is only a midpoint artifact
    (the spreads overlap) or a genuinely executable edge. Do not restate today's
    numbers here — they move, and a frozen figure in a comment goes stale on the
    very next run.
"""
import json, datetime
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.comments import Comment

D3 = json.load(open("data3.json"))
R = json.load(open("refs.json"))
MV = json.load(open("movrefs.json"))
ASOF = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

F = "Arial"
BLUE = Font(name=F, size=10, color="0000FF"); BLACK = Font(name=F, size=10)
GREEN = Font(name=F, size=10, color="008000"); BOLD = Font(name=F, size=10, bold=True)
TITLE = Font(name=F, size=16, bold=True, color="1F3864")
SUB = Font(name=F, size=9, italic=True, color="595959")
SECT = Font(name=F, size=11, bold=True, color="FFFFFF")
HDR = Font(name=F, size=9, bold=True, color="FFFFFF")
NOTE = Font(name=F, size=9, italic=True, color="595959")
SECTF = PatternFill("solid", fgColor="1F3864"); HDRF = PatternFill("solid", fgColor="4472C4")
DEMF = PatternFill("solid", fgColor="DEEBF7"); REPF = PatternFill("solid", fgColor="FCE4E4")
YEL = PatternFill("solid", fgColor="FFFF00"); GREY = PatternFill("solid", fgColor="F2F2F2")
BAND = PatternFill("solid", fgColor="F7F9FC")
thin = Side(style="thin", color="BFBFBF"); BOX = Border(left=thin, right=thin, top=thin, bottom=thin)
PCT = '0.0%'; PCT2 = '0.00%'; DIFF = '+0.0%;-0.0%;0.0%'; DATE = 'yyyy-mm-dd'
NUM = '#,##0;(#,##0);-'; PTS = '+0.00" pts";-0.00" pts";0.00" pts"'
KVOT = '#,##0,"K"'

# Open-ended rungs have no upper edge, so their representative value is a
# judgement call. Everything else uses the true centre of the bucket.
D_TOP_MID = 18.0        # "Democrats, 15+ pts"
R_TOP_MID = -11.0       # "Republicans, 9+ pts"
TURN_LOW_MID = 295000   # below the lowest quoted threshold (310K)
TURN_TOP_MID = 385000   # above the highest quoted threshold (370K)
TURNOUT_2024 = 403314   # actual 2024 PA-07 House vote, Mackenzie 50.5 / Wild 49.5

wb = load_workbook("_stage2b.xlsx")


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


def note(ws, r, text, span):
    c = ws.cell(r, 1, text); c.font = NOTE
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=span)
    return r + 1


def need(n, what):
    if n < 1:
        raise SystemExit("FATAL: %s came back empty — refusing to write an inverted row "
                         "range. Re-run collect3.py before building." % what)
    return n


KD, KR = R["K_MID_D"], R["K_MID_R"]          # Kalshi winner mid rows
mv = wb["Margin of Victory"]

# =====================================================================
# Kalshi margin ladder, appended to the existing Margin of Victory sheet
# =====================================================================
if "KALSHI MARGIN LADDER" in str([mv.cell(x, 1).value for x in range(1, mv.max_row + 1)]):
    raise SystemExit("FATAL: the Kalshi margin section is already on this sheet. build6.py "
                     "appends below whatever build2b.py wrote and is not idempotent — "
                     "rebuild from build2b.py rather than re-running this script.")
r = mv.max_row + 3
r = section(mv, r, "KALSHI MARGIN LADDER — threshold form (KXMIDTERMMOV-PA07D / -PA07R)", 11)
LH = headers(mv, r, ["Rung", "Threshold (pts)", "YES Bid", "YES Ask", "Mid P(margin ≥ strike)",
                     "Bucket", "Bucket Prob", "Representative (pts)", "Prob × Points",
                     "Ticker", ""])
K0 = LH

rungs = {}
for side, key in (("D", "mov_d"), ("R", "mov_r")):
    rungs[side] = sorted(D3[key]["rungs"], key=lambda x: x["strike"])
    need(len(rungs[side]), "Kalshi %s margin ladder" % side)

# One continuous axis: biggest Republican win at the top, down through the two
# tossup buckets in the MIDDLE, out to the biggest Democratic win. The 0-3 rows
# sit where they belong on that axis rather than being tacked on the end, so a
# bar chart of column G reads as a distribution instead of a spike at the edge.
order = ([("rung", "R", x) for x in reversed(rungs["R"])]
         + [("derived", "R", None), ("derived", "D", None)]
         + [("rung", "D", x) for x in rungs["D"]])

rowof, derived_row = {}, {}
for i, (kind, side, rung) in enumerate(order):
    rr = LH + i
    fill = DEMF if side == "D" else REPF
    if kind == "rung":
        rowof[(side, rung["strike"])] = rr
        put(mv, rr, 1, rung["label"], BOLD, None, fill)
        put(mv, rr, 2, rung["strike"], BLUE, '0')
        put(mv, rr, 3, rung.get("yes_bid"), BLUE, PCT)
        put(mv, rr, 4, rung.get("yes_ask"), BLUE, PCT)
        put(mv, rr, 5, '=IF(COUNT(C{0}:D{0})=2,(C{0}+D{0})/2,"")'.format(rr), BLACK, PCT2)
        put(mv, rr, 10, rung["ticker"], BLUE)
    else:
        derived_row[side] = rr
        put(mv, rr, 1, "%s, 0-3 pts" % ("Democrats" if side == "D" else "Republicans"),
            BOLD, None, fill)
        put(mv, rr, 10, "(from winner market)", BLUE)
KN = LH + len(order) - 1

# Bucket probabilities are derived from STRIKE VALUES, never from row adjacency.
# The Republican rungs are displayed descending, and differencing neighbouring
# ROWS on that side shifts every Republican bucket by one — it inflated the
# Republican side from 0.235 to 0.572 before this was keyed off the strikes.
for side, win_row, top_mid, sign in (("R", KR, R_TOP_MID, -1), ("D", KD, D_TOP_MID, +1)):
    strikes = [x["strike"] for x in rungs[side]]
    for i, st in enumerate(strikes):
        rr = rowof[(side, st)]
        outer = strikes[i + 1] if i + 1 < len(strikes) else None
        if outer is not None:
            put(mv, rr, 6, "%g-%g pts (%s)" % (st, outer, side), BLACK)
            put(mv, rr, 7, '=IFERROR(MAX(0,E{0}-E{1}),"")'.format(rr, rowof[(side, outer)]),
                BLACK, PCT2)
            put(mv, rr, 8, sign * (st + outer) / 2.0, BLUE, '+0.0;-0.0;0.0')
        else:
            put(mv, rr, 6, "%g+ pts (%s)" % (st, side), BLACK)
            put(mv, rr, 7, '=IFERROR(E{0},"")'.format(rr), BLACK, PCT2)
            put(mv, rr, 8, top_mid, BLUE, '+0.0;-0.0;0.0')
        put(mv, rr, 9, '=IFERROR(G{0}*H{0},"")'.format(rr), BLACK, '0.000')

    # innermost rung: the 0-3 bucket has to come from the winner market
    inner = rowof[(side, strikes[0])]
    dr = derived_row[side]
    put(mv, dr, 6, "0-3 pts (%s)" % side, BLACK)
    put(mv, dr, 7, '=IFERROR(MAX(0,Kalshi!E{0}-E{1}),"")'.format(win_row, inner), BLACK, PCT2, YEL)
    put(mv, dr, 8, sign * 1.5, BLUE, '+0.0;-0.0;0.0')
    put(mv, dr, 9, '=IFERROR(G{0}*H{0},"")'.format(dr), BLACK, '0.000')

INNER_R = rowof[("R", rungs["R"][0]["strike"])]
INNER_D = rowof[("D", rungs["D"][0]["strike"])]
R03, D03 = derived_row["R"], derived_row["D"]
BLAST = KN

mv.cell(LH - 1, 8).comment = Comment(
    "ASSUMPTION: the representative margin for each bucket, signed so Democratic wins are "
    "positive. Closed buckets use their true centre. The two open-ended rungs are judgement "
    "calls — 'Democrats, %g+ pts' is taken as %+.1f and 'Republicans, %g+ pts' as %+.1f. Both "
    "feed the expected margin below; change them here and it updates."
    % (rungs["D"][-1]["strike"], D_TOP_MID, rungs["R"][-1]["strike"], R_TOP_MID), "Tracker")
mv.cell(R03, 7).comment = Comment(
    "Kalshi quotes no 0-3 rung, so this is P(wins) from the winner market minus P(wins by 3+) "
    "from this ladder — two independently quoted markets. When their spreads overlap the "
    "subtraction can go NEGATIVE; MAX(0,...) keeps a negative probability out of the "
    "distribution, and the CONSISTENCY CHECK below reports whether the inversion is a midpoint "
    "artifact or a genuinely executable edge. Whatever the clamp discards is not shown "
    "anywhere else, so read that check before trusting this bucket.", "Tracker")

r = KN + 1
r += 1
put(mv, r, 1, "TOTAL", BOLD, None, GREY)
put(mv, r, 7, '=SUM(G{0}:G{1})'.format(K0, BLAST), BOLD, PCT2, YEL)
put(mv, r, 9, '=SUM(I{0}:I{1})'.format(K0, BLAST), BOLD, '0.000')
KTOT = r
mv.cell(r, 7).comment = Comment(
    "Buckets are derived from two separate markets, so this does not have to land on exactly "
    "100%. A large miss means the winner market and the margin ladder disagree about the race.",
    "Tracker")
r += 2

r = section(mv, r, "KALSHI IMPLIED READ & CROSS-VENUE COMPARISON", 11)
put(mv, r, 1, "Kalshi expected margin (D−R)", BOLD)
put(mv, r, 2, '=IFERROR(SUM(I{0}:I{1}),"")'.format(K0, BLAST), BOLD, PTS, YEL); KEM = r; r += 1
put(mv, r, 1, "Polymarket expected margin (D−R)", BOLD)
put(mv, r, 2, '=B{0}'.format(MV["EM"]), GREEN, PTS); PEM = r; r += 1
put(mv, r, 1, "Difference (Kalshi − Polymarket)", BOLD)
put(mv, r, 2, '=IFERROR(B{0}-B{1},"")'.format(KEM, PEM), BOLD, PTS, YEL); r += 1
put(mv, r, 1, "Kalshi P(D wins by 3+ pts)", BOLD)
put(mv, r, 2, '=IFERROR(E{0},"")'.format(INNER_D), BLACK, PCT2); r += 1
put(mv, r, 1, "Kalshi P(margin under 3 pts either way)", BOLD)
put(mv, r, 2, '=IFERROR(G{0}+G{1},"")'.format(R03, D03), BLACK, PCT2, YEL)
mv.cell(r, 2).comment = Comment(
    "This is the sum of the two clamped 0-3 buckets, so it is the figure MOST exposed to the "
    "clamp: whenever an inversion is clamped away, the discarded probability is silently "
    "missing from here and this reads too high. The expected margin above barely moves under "
    "the clamp (a 0-3 bucket carries a small representative value either way), but this one "
    "does. Check the consistency verdict below before quoting it.", "Tracker")
r += 2

r = section(mv, r, "CONSISTENCY CHECK — winner market vs margin ladder", 11)
put(mv, r, 1, "P(R wins) − P(R wins by 3+), on mids", BOLD)
put(mv, r, 2, '=IFERROR(Kalshi!E{0}-E{1},"")'.format(KR, INNER_R), BLACK, DIFF); CHK = r; r += 1
put(mv, r, 1, "Same, using executable prices", BOLD)
put(mv, r, 2, '=IFERROR(C{0}-Kalshi!D{1},"")'.format(INNER_R, KR), BLACK, DIFF); CHK2 = r
mv.cell(r, 2).comment = Comment(
    "Sell the 3+ rung at its bid, buy the winner at its ask. Positive means the inversion "
    "is actually tradeable; negative means it sits inside the spread and is only an artifact "
    "of quoting both markets at their midpoints.", "Tracker")
r += 1
put(mv, r, 1, "Verdict", BOLD)
# CHK is P(wins) - P(wins by 3+) on mids: an inversion makes it NEGATIVE.
# CHK2 is the executable version; positive means the edge is actually tradeable.
put(mv, r, 2, ('=IF(B{0}="","",IF(B{0}>0,"REAL — the 3+ rung is bid above the winner ask",'
               'IF(B{1}<0,"Artifact — mids invert but the spread covers it; bucket clamped to 0",'
               '"Consistent — no inversion")))').format(CHK2, CHK), BOLD, None, YEL)
mv.merge_cells(start_row=r, start_column=2, end_row=r, end_column=11)
r += 1
r = note(mv, r, "Kalshi and Polymarket describe the same margin with different instruments: Kalshi "
                "sells thresholds (\"3+ pts\"), Polymarket sells brackets (\"3-6%\"). Neither is more "
                "correct; a persistent gap between the two expected margins is a genuine disagreement "
                "worth reading, not a bug.", 11)
r += 1

r = section(mv, r, "KALSHI MARGIN — DAILY HISTORY (mid of closing bid and ask)", 11)
mh = {}
for key in ("mov_d_history", "mov_r_history"):
    for day, per in (D3.get(key) or {}).items():
        mh.setdefault(day, {}).update(per)
# Only the quoted rungs have a ticker and a history; the two derived 0-3 rows
# come from the winner market and have no series of their own.
tickers = [rung["ticker"] for kind, _side, rung in order if kind == "rung"]
labels = [rung["label"] for kind, _side, rung in order if kind == "rung"]
HH = headers(mv, r, ["Date"] + labels + [""] * max(0, 10 - len(labels)))
mdays = sorted(mh)
for i, day in enumerate(mdays):
    rr = HH + i
    put(mv, rr, 1, datetime.datetime.strptime(day, "%Y-%m-%d"), BLUE, DATE)
    for j, tk in enumerate(tickers):
        rec = (mh.get(day) or {}).get(tk)
        v = None
        if rec:
            b, a = rec.get("bid"), rec.get("ask")
            if b is not None and a is not None: v = (b + a) / 2
            elif a is not None: v = a
            elif b is not None: v = b
        put(mv, rr, 2 + j, v, BLUE, PCT)
    if i % 2:
        for c in range(1, len(tickers) + 2): mv.cell(rr, c).fill = BAND
KHF = HH
KHL = HH + need(len(mdays), "Kalshi margin history") - 1
r = KHL + 1
r = note(mv, r, "Each column is P(margin ≥ that threshold), so the columns are nested rather than "
                "exclusive and must fall from left to right within each party.", 11)

# =====================================================================
# SHEET: Voter Turnout
# =====================================================================
tn = wb.create_sheet("Voter Turnout")
tn.sheet_view.showGridLines = False
tn["A1"] = "Voter Turnout — PA-07 (Kalshi)"; tn["A1"].font = TITLE
tn["A2"] = ("Kalshi KXMIDTERMVOTETURN-PA07: how many ballots the PA-07 House race draws on "
            "3 Nov 2026, quoted as thresholds. Pulled %s." % ASOF)
tn["A2"].font = SUB
for k, v in {"A": 20, "B": 15, "C": 12, "D": 12, "E": 17, "F": 18, "G": 14,
             "H": 18, "I": 15, "J": 13}.items():
    tn.column_dimensions[k].width = v

r = 4
r = section(tn, r, "MARKET METADATA", 10)
T = D3["turnout"]
for lbl, val in [("Event", T["event"]), ("Series", T.get("series")),
                 ("Question", T.get("title")), ("Resolution", "3 Nov 2026"),
                 ("Thresholds quoted", len(T["rungs"]))]:
    put(tn, r, 1, lbl, BOLD); put(tn, r, 2, val, BLUE, NUM if lbl == "Thresholds quoted" else None)
    tn.merge_cells(start_row=r, start_column=2, end_row=r, end_column=7); r += 1
r += 1

r = section(tn, r, "THRESHOLD LADDER", 10)
TH = headers(tn, r, ["Rung", "Threshold", "YES Bid", "YES Ask", "Mid P(turnout ≥ strike)",
                     "Bucket", "Bucket Prob", "Representative Turnout", "Prob × Turnout", ""])
T0 = TH
rungs = sorted(T["rungs"], key=lambda x: x["strike"])
need(len(rungs), "turnout ladder")
# Below the lowest quoted threshold is not a market, it is the residual.
rr = TH
put(tn, rr, 1, "Below %s" % ("{:,.0f}K".format(rungs[0]["strike"] / 1000)), BOLD, None, GREY)
put(tn, rr, 6, "under %.0fK" % (rungs[0]["strike"] / 1000), BLACK)
put(tn, rr, 7, '=IFERROR(MAX(0,1-E{0}),"")'.format(TH + 1), BLACK, PCT2)
put(tn, rr, 8, TURN_LOW_MID, BLUE, KVOT)
put(tn, rr, 9, '=IFERROR(G{0}*H{0},"")'.format(rr), BLACK, '#,##0')
tn.cell(rr, 7).comment = Comment(
    "Not a quoted market — the residual, 1 minus P(turnout above the lowest threshold).", "Tracker")
for i, rung in enumerate(rungs):
    rr = TH + 1 + i
    nxt = rungs[i + 1] if i + 1 < len(rungs) else None
    put(tn, rr, 1, rung["label"], BOLD)
    put(tn, rr, 2, rung["strike"], BLUE, KVOT)
    put(tn, rr, 3, rung.get("yes_bid"), BLUE, PCT)
    put(tn, rr, 4, rung.get("yes_ask"), BLUE, PCT)
    put(tn, rr, 5, '=IF(COUNT(C{0}:D{0})=2,(C{0}+D{0})/2,"")'.format(rr), BLACK, PCT2)
    if nxt:
        put(tn, rr, 6, "%.0fK–%.0fK" % (rung["strike"] / 1000, nxt["strike"] / 1000), BLACK)
        put(tn, rr, 7, '=IFERROR(MAX(0,E{0}-E{1}),"")'.format(rr, rr + 1), BLACK, PCT2)
        put(tn, rr, 8, (rung["strike"] + nxt["strike"]) / 2.0, BLUE, KVOT)
    else:
        put(tn, rr, 6, "above %.0fK" % (rung["strike"] / 1000), BLACK)
        put(tn, rr, 7, '=IFERROR(E{0},"")'.format(rr), BLACK, PCT2)
        put(tn, rr, 8, TURN_TOP_MID, BLUE, KVOT)
    put(tn, rr, 9, '=IFERROR(G{0}*H{0},"")'.format(rr), BLACK, '#,##0')
TN = TH + len(rungs)
TTOT = TN + 1
put(tn, TTOT, 1, "TOTAL", BOLD, None, GREY)
put(tn, TTOT, 7, '=SUM(G{0}:G{1})'.format(T0, TN), BOLD, PCT2, YEL)
put(tn, TTOT, 9, '=SUM(I{0}:I{1})'.format(T0, TN), BOLD, '#,##0')
tn.cell(TH - 1, 8).comment = Comment(
    "ASSUMPTION: the representative turnout for each bucket. Closed buckets use their true "
    "centre. The two open-ended ones are judgement calls — below the lowest threshold is taken "
    "as %s and above the highest as %s. Both feed the expected-turnout figure; change them here "
    "and it updates." % ("{:,}".format(TURN_LOW_MID), "{:,}".format(TURN_TOP_MID)), "Tracker")
r = TTOT + 2

r = section(tn, r, "IMPLIED READ", 10)
put(tn, r, 1, "Expected turnout", BOLD)
put(tn, r, 2, '=IFERROR(SUM(I{0}:I{1}),"")'.format(T0, TN), BOLD, '#,##0', YEL); TEXP = r; r += 1
put(tn, r, 1, "Modal bucket", BOLD)
put(tn, r, 2, '=IFERROR(INDEX($F${0}:$F${1},MATCH(MAX($G${0}:$G${1}),$G${0}:$G${1},0)),"")'.format(T0, TN), BOLD); r += 1
put(tn, r, 1, "P(turnout above 340K)", BOLD)
put(tn, r, 2, '=IFERROR(INDEX($E${0}:$E${1},MATCH(340000,$B${0}:$B${1},0)),"")'.format(T0, TN), BLACK, PCT2); r += 1
put(tn, r, 1, "2024 PA-07 House turnout", BOLD); put(tn, r, 2, TURNOUT_2024, BLUE, '#,##0'); T24 = r; r += 1
put(tn, r, 1, "Implied change vs 2024", BOLD)
put(tn, r, 2, '=IFERROR(B{0}/B{1}-1,"")'.format(TEXP, T24), BOLD, DIFF); r += 1
tn.cell(T24, 2).comment = Comment(
    "403,314 ballots were cast in the 2024 PA-07 House race (Mackenzie 50.5%% / Wild 49.5%%), "
    "per the certified count as reported by Ballotpedia and AP. NOTE: 2024 was a presidential "
    "year and 2026 is a midterm, so a double-digit fall here is the normal pattern, not a "
    "collapse — do not read the change line as a turnout warning.", "Tracker")
r = note(tn, r, "Turnout is a genuine driver here, not trivia: PA-07 was decided by about a point in "
                "2024, so which electorate shows up plausibly decides the seat.", 10)
r += 1

r = section(tn, r, "DAILY HISTORY (mid of closing bid and ask)", 10)
th = D3.get("turnout_history") or {}
tks = [x["ticker"] for x in rungs]
tlabels = [x["label"] for x in rungs]
TH2 = headers(tn, r, ["Date"] + tlabels + [""] * max(0, 9 - len(tlabels)))
tdays = sorted(th)
for i, day in enumerate(tdays):
    rr = TH2 + i
    put(tn, rr, 1, datetime.datetime.strptime(day, "%Y-%m-%d"), BLUE, DATE)
    for j, tk in enumerate(tks):
        rec = (th.get(day) or {}).get(tk)
        v = None
        if rec:
            b, a = rec.get("bid"), rec.get("ask")
            if b is not None and a is not None: v = (b + a) / 2
            elif a is not None: v = a
            elif b is not None: v = b
        put(tn, rr, 2 + j, v, BLUE, PCT)
    if i % 2:
        for c in range(1, len(tks) + 2): tn.cell(rr, c).fill = BAND
TF = TH2
TL = TH2 + need(len(tdays), "turnout history") - 1
r = TL + 1
r = note(tn, r, "Columns are nested, not exclusive: each is P(turnout ≥ that threshold), so within a "
                "row they must fall from left to right. Kalshi began quoting this ladder on %s."
                % (min(tdays) if tdays else "n/a"), 10)
tn.freeze_panes = tn.cell(TH2, 2)

# D_TOP_MID/R_TOP_MID travel out with the row anchors for the same reason the
# turnout midpoints already did: export_site.py has to reproduce this ladder's
# expected margin, and a second copy of the constants in a second file is a
# guaranteed future disagreement between the sheet and the site.
json.dump({"TURN_LOW_MID": TURN_LOW_MID, "TURN_TOP_MID": TURN_TOP_MID,
           "D_TOP_MID": D_TOP_MID, "R_TOP_MID": R_TOP_MID,
           "TURNOUT_2024": TURNOUT_2024,
           "K0": K0, "KN": KN, "KTOT": KTOT, "KEM": KEM, "R03": R03, "D03": D03,
           "KHF": KHF, "KHL": KHL, "T0": T0, "TN": TN, "TTOT": TTOT, "TEXP": TEXP,
           "TF": TF, "TL": TL, "N_MOV": len(order), "N_TURN": len(rungs)},
          open("k3refs.json", "w"))
wb.save("_stage2c.xlsx")
print("stage2c ok — Kalshi margin rows %d-%d, turnout rows %d-%d, hist %d/%d days"
      % (K0, KN, T0, TN, len(mdays), len(tdays)))
