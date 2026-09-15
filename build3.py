import json, datetime
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.comments import Comment

R = json.load(open("refs.json")); P = json.load(open("prefs.json"))
MV = json.load(open("movrefs.json")); DA = json.load(open("data.json"))
K3 = json.load(open("k3refs.json"))
ASOF = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

F = "Arial"
BLUE = Font(name=F, size=10, color="0000FF"); BLACK = Font(name=F, size=10)
GREEN = Font(name=F, size=10, color="008000"); BOLD = Font(name=F, size=10, bold=True)
TITLE = Font(name=F, size=16, bold=True, color="1F3864")
SUB = Font(name=F, size=9, italic=True, color="595959")
SECT = Font(name=F, size=11, bold=True, color="FFFFFF")
HDR = Font(name=F, size=9, bold=True, color="FFFFFF")
BIG = Font(name=F, size=20, bold=True, color="1F3864")
NOTE = Font(name=F, size=9, italic=True, color="595959")
SECTF = PatternFill("solid", fgColor="1F3864"); HDRF = PatternFill("solid", fgColor="4472C4")
DEMF = PatternFill("solid", fgColor="DEEBF7"); REPF = PatternFill("solid", fgColor="FCE4E4")
YEL = PatternFill("solid", fgColor="FFFF00"); GREY = PatternFill("solid", fgColor="F2F2F2")
BAND = PatternFill("solid", fgColor="F7F9FC")
thin = Side(style="thin", color="BFBFBF"); BOX = Border(left=thin, right=thin, top=thin, bottom=thin)
PCT = '0.0%'; PCT2 = '0.00%'; DIFF = '+0.0%;-0.0%;0.0%'; USD = '$#,##0;($#,##0);-'
NUM = '#,##0;(#,##0);-'; DATE = 'yyyy-mm-dd'; PTS = '+0.00" pts";-0.00" pts";0.00" pts"'
SEATS = '0.00" seats"'

wb = load_workbook("_stage2d.xlsx")

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

PMF, PML = R["PM_FIRST"], R["PM_LAST"]; KF, KL = R["K_FIRST"], R["K_LAST"]
PMD, PMR, PMS = R["PM_MID_D"], R["PM_MID_R"], R["PM_SUM"]
KD, KR, KS = R["K_MID_D"], R["K_MID_R"], R["K_SUM"]
PMVOL = R["PM_VOL"]          # Polymarket METADATA "Volume ($)" row, threaded from build.py

def need(n, what):
    """Refuse to build a row range out of an empty series.

    VL is VH + len(series) - 1, so an empty series gives VL < VH and every chart
    Reference built from the pair comes out inverted. Fail loudly instead.
    """
    if n < 1:
        raise SystemExit("FATAL: %s came back empty — refusing to write an inverted row "
                         "range. Re-run the collector before building." % what)
    return n

# =====================================================================
# SHEET: Venue Comparison
# =====================================================================
vc = wb.create_sheet("Venue Comparison")
vc["A1"] = "Venue Comparison — Polymarket vs Kalshi"; vc["A1"].font = TITLE
vc["A2"] = ("Daily Democratic win probability on both venues, joined on date with INDEX/MATCH so the join survives "
            "a data refresh. Built %s." % ASOF)
vc["A2"].font = SUB
for k, v in {"A": 13, "B": 15, "C": 15, "D": 15, "E": 13, "F": 15, "G": 15, "H": 15, "I": 17,
             "J": 13, "K": 11, "L": 11}.items():
    vc.column_dimensions[k].width = v

r = 4
r = section(vc, r, "DIVERGENCE SUMMARY", 11)
VS = r
for i, (lbl, f, fmt) in enumerate([
        ("Current Polymarket Dem (mid)", '=Polymarket!D{0}'.format(PMD), PCT2),
        ("Current Kalshi Dem (mid)", '=Kalshi!E{0}'.format(KD), PCT2),
        ("Current divergence (PM − Kalshi)", '=B{0}-B{1}'.format(VS, VS + 1), DIFF),
        ("Mean absolute divergence (overlap)", None, PCT2),
        ("Max absolute divergence", None, PCT2),
        ("Overlapping days", None, NUM),
        ("Days listed but not comparable", None, NUM)]):
    put(vc, VS + i, 1, lbl, BOLD)
    put(vc, VS + i, 2, f, GREEN if i < 2 else BLACK, fmt, YEL if i == 2 else None)
vc.cell(VS + 2, 2).comment = Comment(
    "Positive means Polymarket prices the Democrat higher than Kalshi does. Persistent gaps reflect different fee "
    "structures, capital costs and user bases rather than a free lunch — the tradeable gap is the cross-venue ask "
    "total on the Summary sheet, not this mid-to-mid difference.", "Tracker")
r = VS + 8
r = section(vc, r, "DAILY SERIES", 12)
VH = headers(vc, r, ["Date", "Polymarket Dem", "Kalshi Dem (mid)", "Divergence (PM − K)", "Abs Divergence",
                     "Polymarket Rep", "Kalshi Rep (mid)", "Cheapest Dem", "Cheapest Rep", "Pair Total",
                     "Even odds", "Axis label"])
pmdays = sorted(DA["pm_history"])

def lookup(sheet, col, first, last, row):
    """INDEX/MATCH that returns blank, not zero, when the matched cell is empty.

    INDEX onto an empty cell yields 0, which would otherwise read as a price of
    0.000 and corrupt every statistic downstream. The =0 test catches that; a
    genuine 0.000 quote does not occur in a live market.
    """
    idx = 'INDEX({0}!${1}${2}:${1}${3},MATCH($A{4},{0}!$A${2}:$A${3},0))'.format(sheet, col, first, last, row)
    return '=IFERROR(IF({0}=0,"",{0}),"")'.format(idx)

for i, day in enumerate(pmdays):
    rr = VH + i
    put(vc, rr, 1, datetime.datetime.strptime(day, "%Y-%m-%d"), BLUE, DATE)
    put(vc, rr, 2, lookup("Polymarket", "B", PMF, PML, rr), GREEN, PCT)
    put(vc, rr, 3, lookup("Kalshi", "D", KF, KL, rr), GREEN, PCT)
    put(vc, rr, 4, '=IF(AND(ISNUMBER(B{0}),ISNUMBER(C{0})),B{0}-C{0},"")'.format(rr), BLACK, DIFF)
    put(vc, rr, 5, '=IF(ISNUMBER(D{0}),ABS(D{0}),"")'.format(rr), BLACK, PCT2)
    put(vc, rr, 6, lookup("Polymarket", "C", PMF, PML, rr), GREEN, PCT)
    put(vc, rr, 7, lookup("Kalshi", "G", KF, KL, rr), GREEN, PCT)
    put(vc, rr, 8, '=IF(AND(ISNUMBER(B{0}),ISNUMBER(C{0})),MIN(B{0},C{0}),"")'.format(rr), BLACK, PCT)
    put(vc, rr, 9, '=IF(AND(ISNUMBER(F{0}),ISNUMBER(G{0})),MIN(F{0},G{0}),"")'.format(rr), BLACK, PCT)
    put(vc, rr, 10, '=IF(AND(ISNUMBER(H{0}),ISNUMBER(I{0})),H{0}+I{0},"")'.format(rr), BLACK, PCT2)
    put(vc, rr, 11, 0.5, BLUE, PCT)
    # Literal month text, not a date, and only on the first row of each month.
    # Category axes fed from date cells get re-formatted and auto-sized by the
    # renderer, which ignored every numFmt, font size and label-density setting
    # written into the chart XML. Plain text leaves nothing to reinterpret, and
    # blanking the rest gives exactly one tick label per month without relying
    # on tickLblSkip, which was ignored too.
    # Every row carries a label: the renderer picks which ticks to show and
    # ignores tickLblSkip, so blanking the others just loses them. "17 Dec" is
    # short enough not to dominate the axis and unique enough that no two shown
    # ticks read the same, which "Dec-25" repeated could not promise.
    put(vc, rr, 12, datetime.datetime.strptime(day, "%Y-%m-%d").strftime("%d %b"), BLUE)
    if i % 2:
        for c in range(1, 13): vc.cell(rr, c).fill = BAND
VL = VH + need(len(pmdays), "Polymarket daily price history") - 1
vc.cell(VH - 1, 8).comment = Comment(
    "Columns H-J use mid prices, not executable asks, because the daily history carries no book. Treat the Pair Total "
    "as indicative only; the executable version is the arbitrage check on the Summary sheet, built from live "
    "top-of-book.", "Tracker")
for i, f in ((3, '=IFERROR(AVERAGE(E{0}:E{1}),"")'.format(VH, VL)),
             (4, '=IFERROR(MAX(E{0}:E{1}),"")'.format(VH, VL)),
             (5, '=COUNT(D{0}:D{1})'.format(VH, VL)),
             (6, '=COUNT(A{0}:A{1})-COUNT(D{0}:D{1})'.format(VH, VL))):
    vc.cell(VS + i, 2).value = f
vc.cell(VS + 6, 2).comment = Comment(
    "Days listed in the series that produce no divergence: either the date predates Kalshi's history, or one venue "
    "had no quote that day. Polymarket is missing a Democratic price on 2026-07-29 and a Republican price on "
    "2026-04-18; those days are excluded rather than read as a price of zero.", "Tracker")
vc.freeze_panes = vc.cell(VH, 2)

# =====================================================================
# SHEET: Summary
# =====================================================================
sm = wb.create_sheet("Summary")
sm["A1"] = "PA-07 House Election Winner — Tracker"; sm["A1"].font = TITLE
sm["A2"] = ("Pennsylvania's 7th Congressional District, general election 3 Nov 2026. Green = pulled from another "
            "sheet, black = calculated, blue = entered fact, yellow = key output or assumption. Built %s." % ASOF)
sm["A2"].font = SUB
for k, v in {"A": 34, "B": 16, "C": 17, "D": 16, "E": 16, "F": 16, "G": 16, "H": 18}.items():
    sm.column_dimensions[k].width = v

r = 4
r = section(sm, r, "HEADLINE", 8)
put(sm, r, 1, "Consensus Democratic win probability", BOLD)
put(sm, r, 2, '=AVERAGE(Polymarket!D{0},Kalshi!E{1})'.format(PMD, KD), BIG, PCT, YEL)
sm.merge_cells(start_row=r, start_column=2, end_row=r, end_column=3); sm.row_dimensions[r].height = 30
put(sm, r, 4, "Equal-weighted mean of the two venue mids. Not liquidity-weighted — Polymarket carries the larger book.", NOTE, None, None, None, False)
HEAD = r; r += 1
put(sm, r, 1, "Consensus Republican win probability", BOLD)
put(sm, r, 2, '=AVERAGE(Polymarket!D{0},Kalshi!E{1})'.format(PMR, KR), BIG, PCT, YEL)
sm.merge_cells(start_row=r, start_column=2, end_row=r, end_column=3); sm.row_dimensions[r].height = 30
put(sm, r, 4, "Bob Brooks (D) vs incumbent Ryan Mackenzie (R).", NOTE, None, None, None, False); r += 1
put(sm, r, 1, "Market-implied margin (D−R)", BOLD)
put(sm, r, 2, "='Margin of Victory'!B{0}".format(MV["EM"]), BIG, PTS, YEL)
sm.merge_cells(start_row=r, start_column=2, end_row=r, end_column=3); sm.row_dimensions[r].height = 30
put(sm, r, 4, "Expected margin from Polymarket's bracket ladder.", NOTE, None, None, None, False); r += 2

r = section(sm, r, "RACE AT A GLANCE", 8)
facts = [("District", "Pennsylvania 7th (Lehigh Valley: Lehigh, Northampton, part of Monroe)"),
         ("Election date", None),
         ("Days until election", None),
         ("Republican nominee", "Ryan Mackenzie (incumbent, serving since 3 Jan 2025)"),
         ("Democratic nominee", "Bob Brooks (president, PA Professional Fire Fighters Association)"),
         ("Democratic primary", "19 May 2026 — Brooks won with ~41.4% over Crosswell, McClure, Obando-Derstine"),
         ("Republican primary", "19 May 2026 — Mackenzie unopposed"),
         ("2024 House result", "Mackenzie (R) 50.4% – Wild (D) 49.4% (R+1.0; narrowest PA House margin of 2024)"),
         ("Cook PVI", "R+1"),
         ("2024 presidential", "Trump +1 (2026 GBAO sample recall: 47–46)"),
         ("Cook Political Report", "Toss Up"),
         ("Sabato's Crystal Ball", "Toss-up (moved from Lean D on 1 Feb 2026)"),
         ("Inside Elections", "Toss-up")]
for lbl, val in facts:
    put(sm, r, 1, lbl, BOLD)
    if lbl == "Days until election":
        put(sm, r, 2, '=DATE(2026,11,3)-TODAY()', BLACK, NUM)
    elif lbl == "Election date":
        put(sm, r, 2, datetime.datetime(2026, 11, 3), BLUE, DATE)
    else:
        put(sm, r, 2, val, BLUE)
    sm.merge_cells(start_row=r, start_column=2, end_row=r, end_column=8); r += 1
r += 1

r = section(sm, r, "LIVE MARKET SNAPSHOT — WINNER", 8)
MS = headers(sm, r, ["Venue", "Dem Mid", "Rep Mid", "Sum of Mids", "Overround (vig)", "Dem Bid-Ask",
                     "Dem Normalised", "Depth / Volume"])
put(sm, MS, 1, "Polymarket", BOLD, None, GREY)
put(sm, MS, 2, '=Polymarket!D{0}'.format(PMD), GREEN, PCT2, DEMF)
put(sm, MS, 3, '=Polymarket!D{0}'.format(PMR), GREEN, PCT2, REPF)
put(sm, MS, 4, '=Polymarket!D{0}'.format(PMS), GREEN, PCT2)
put(sm, MS, 5, '=B{0}+C{0}-1'.format(MS), BLACK, DIFF)
put(sm, MS, 6, '=Polymarket!E{0}'.format(PMD), GREEN, DIFF)
put(sm, MS, 7, '=IFERROR(B{0}/D{0},"")'.format(MS), BLACK, PCT)
put(sm, MS, 8, '=Polymarket!B{0}+Polymarket!C{0}'.format(PMVOL), GREEN, USD)
put(sm, MS + 1, 1, "Kalshi", BOLD, None, GREY)
put(sm, MS + 1, 2, '=Kalshi!E{0}'.format(KD), GREEN, PCT2, DEMF)
put(sm, MS + 1, 3, '=Kalshi!E{0}'.format(KR), GREEN, PCT2, REPF)
put(sm, MS + 1, 4, '=Kalshi!E{0}'.format(KS), GREEN, PCT2)
put(sm, MS + 1, 5, '=B{0}+C{0}-1'.format(MS + 1), BLACK, DIFF)
put(sm, MS + 1, 6, '=Kalshi!F{0}'.format(KD), GREEN, DIFF)
put(sm, MS + 1, 7, '=IFERROR(B{0}/D{0},"")'.format(MS + 1), BLACK, PCT)
put(sm, MS + 1, 8, '=Kalshi!G{0}+Kalshi!G{1}'.format(KD, KR), GREEN, USD)
put(sm, MS + 2, 1, "Consensus (equal weight)", BOLD, None, YEL)
for col in (2, 3, 4, 5, 6, 7):
    put(sm, MS + 2, col, '=AVERAGE({0}{1}:{0}{2})'.format(chr(64 + col), MS, MS + 1), BOLD,
        DIFF if col in (5, 6) else PCT2)
put(sm, MS + 2, 8, '=SUM(H{0}:H{1})'.format(MS, MS + 1), BOLD, USD)
sm.cell(MS - 1, 8).comment = Comment(
    "The Polymarket figure is lifetime USD volume across the two party markets; the Kalshi figure is resting size at "
    "top of book only. They are not like-for-like — read each against its own venue over time.", "Tracker")
r = MS + 4

r = section(sm, r, "OTHER SUBJECTS TRACKED", 8)
SUBH = headers(sm, r, ["Subject", "Venue", "Key figure", "Value", "Sheet", "", "", ""])
subs = [("Winner (party)", "Polymarket + Kalshi", "Consensus P(Dem)", '=B{0}'.format(HEAD), "Polymarket / Kalshi", PCT2),
        ("Margin of victory", "Polymarket only", "Expected margin (D−R)", "='Margin of Victory'!B{0}".format(MV["EM"]), "Margin of Victory", PTS),
        ("Margin of victory", "Polymarket only", "P(margin under 3 pts)", "='Margin of Victory'!B{0}".format(MV["P3"]), "Margin of Victory", PCT2),
        ("Voter turnout", "Kalshi only", "Expected ballots cast", "='Voter Turnout'!B{0}".format(K3["TEXP"]), "Voter Turnout", '#,##0'),
        ("PA Democratic seats", "Kalshi only", "Expected seats of 17", "='PA Seat Count'!B{0}".format(MV["ES"]), "PA Seat Count", SEATS),
        ("Dem primary (settled)", "Kalshi + polls", "Brooks actual result", "=Polls!H{0}".format(P["ACT"]), "Polls", PCT)]
for i, (subj, ven, key, val, sheet, fmt) in enumerate(subs):
    rr = SUBH + i
    put(sm, rr, 1, subj, BOLD); put(sm, rr, 2, ven, BLACK); put(sm, rr, 3, key, BLACK)
    put(sm, rr, 4, val, GREEN, fmt, YEL); put(sm, rr, 5, sheet, BLACK)
    if i % 2:
        for c in range(1, 9):
            if c != 4: sm.cell(rr, c).fill = BAND
r = SUBH + len(subs)
r = note(sm, r, "Kalshi also quotes a margin-of-victory ladder (KXMIDTERMMOV-PA07D/R), but too thinly to "
                "use: most rungs have no two-sided quote, so it is collected and not shown. Turnout is "
                "Kalshi-only. PA-07 still has no entry in Kalshi's closest-race market, and its PA-07 "
                "nominee and 2024 events return no tradeable markets. Full inventory on Notes & Sources.", 8)
r += 1

r = section(sm, r, "CROSS-VENUE ARBITRAGE CHECK (live, executable prices)", 8)
AR = r
put(sm, r, 1, "Cheapest Dem YES ask", BOLD)
put(sm, r, 2, '=MIN(Polymarket!C{0},Kalshi!D{1})'.format(PMD, KD), BLACK, PCT2)
put(sm, r, 3, '=IF(Polymarket!C{0}<=Kalshi!D{1},"Polymarket","Kalshi")'.format(PMD, KD), BLACK, None, GREY); r += 1
put(sm, r, 1, "Cheapest Rep YES ask", BOLD)
put(sm, r, 2, '=MIN(Polymarket!C{0},Kalshi!D{1})'.format(PMR, KR), BLACK, PCT2)
put(sm, r, 3, '=IF(Polymarket!C{0}<=Kalshi!D{1},"Polymarket","Kalshi")'.format(PMR, KR), BLACK, None, GREY); r += 1
put(sm, r, 1, "Total cost of both legs", BOLD); put(sm, r, 2, '=B{0}+B{1}'.format(AR, AR + 1), BOLD, PCT2, YEL); r += 1
put(sm, r, 1, "Gross edge per $1 payout", BOLD); put(sm, r, 2, '=1-B{0}'.format(r - 1), BOLD, DIFF, YEL); EDGE = r; r += 1
put(sm, r, 1, "Arbitrage present?", BOLD)
put(sm, r, 2, '=IF(B{0}>0,"YES — gross, before fees","No")'.format(EDGE), BOLD)
sm.merge_cells(start_row=r, start_column=2, end_row=r, end_column=4)
sm.cell(r, 2).comment = Comment(
    "Buying both YES legs guarantees a $1 payout, since exactly one party wins. Any 'YES' here is gross of Kalshi "
    "trading fees (quadratic, roughly 7c x p x (1-p) per contract), Polymarket gas and spread, the size actually "
    "resting at those asks, and the capital tied up until November 2026. Small negative edges are the normal state.", "Tracker")
r += 2

def asof(col, off):
    """Polymarket column `col`, N calendar days before the latest date in the series.

    Row arithmetic is not calendar arithmetic. The daily history has real gaps —
    11, 9 and 4 days across spring 2026 — so the row PML-30 can hold a price from
    a date that is not 30 days old at all. MATCH(...,1) against the ascending date
    column returns the most recent row on or before the target date instead. It
    returns #N/A when the history does not reach back that far, and IFERROR turns
    that into a blank, so a short series can no longer pull a metadata cell from
    above the block into a "90 days ago" label. INDEX onto an empty price cell
    yields 0, guarded here exactly the way lookup() guards it.
    """
    m = 'MATCH(Polymarket!$A${0}-{1},Polymarket!$A${2}:$A${0},1)'.format(PML, off, PMF)
    idx = 'INDEX(Polymarket!${0}${1}:${0}${2},{3})'.format(col, PMF, PML, m)
    return '=IFERROR(IF({0}=0,"",{0}),"")'.format(idx)

r = section(sm, r, "MOMENTUM — Polymarket Democratic price", 8)
MO = r
for lbl, off in [("Latest", 0), ("7 days ago", 7), ("30 days ago", 30), ("90 days ago", 90)]:
    put(sm, r, 1, lbl, BOLD); put(sm, r, 2, asof("B", off), GREEN, PCT)
    if off: put(sm, r, 3, '=IF(AND(ISNUMBER(B{0}),ISNUMBER(B{1})),B{0}-B{1},"")'.format(MO, r), BLACK, DIFF)
    else: put(sm, r, 3, "change vs latest", NOTE, None, None, None, False)
    put(sm, r, 4, asof("A", off), GREEN, DATE)
    r += 1
put(sm, MO, 5, "date actually used", NOTE, None, None, None, False)
sm.cell(MO, 4).comment = Comment(
    "The date the lookup landed on, not the date the label asks for. Each row targets the latest "
    "date in the Polymarket series minus N days and takes the most recent quote on or before it, "
    "because the daily history has gaps (11, 9 and 4 days across spring 2026) and a row offset "
    "would silently read a different calendar date. Where the two differ, this column is the "
    "honest one. A blank price and a blank date together mean the history does not reach back "
    "that far.", "Tracker")
put(sm, r, 1, "Series high", BOLD); put(sm, r, 2, '=MAX(Polymarket!B{0}:B{1})'.format(PMF, PML), BLACK, PCT); r += 1
put(sm, r, 1, "Series low", BOLD); put(sm, r, 2, '=MIN(Polymarket!B{0}:B{1})'.format(PMF, PML), BLACK, PCT); r += 1
put(sm, r, 1, "Series start (17 Dec 2025)", BOLD); put(sm, r, 2, '=Polymarket!B{0}'.format(PMF), GREEN, PCT)
put(sm, r, 3, '=IF(AND(ISNUMBER(B{0}),ISNUMBER(B{1})),B{0}-B{1},"")'.format(MO, r), BLACK, DIFF); r += 2

r = section(sm, r, "MARKETS vs POLLS", 8)
MP = r
put(sm, r, 1, "Weighted poll margin (D−R)", BOLD); put(sm, r, 2, "=Polls!B{0}".format(P["WM"]), GREEN, DIFF); PMARG = r; r += 1
put(sm, r, 1, "House-effect adjusted poll margin", BOLD); put(sm, r, 2, "=Polls!B{0}".format(P["ADJ"]), GREEN, DIFF); PADJ = r; r += 1
put(sm, r, 1, "Market-implied margin (ladder)", BOLD); put(sm, r, 2, "='Margin of Victory'!B{0}".format(MV["EM"]), GREEN, PTS); MMARG = r; r += 1
put(sm, r, 1, "Market − polls (raw)", BOLD)
put(sm, r, 2, '=IFERROR(B{0}/100-B{1},"")'.format(MMARG, PMARG), BLACK, DIFF); r += 1
put(sm, r, 1, "Market − polls (adjusted)", BOLD)
put(sm, r, 2, '=IFERROR(B{0}/100-B{1},"")'.format(MMARG, PADJ), BLACK, DIFF); DIFFR = r; r += 1
put(sm, r, 1, "Read", BOLD)
put(sm, r, 2, '=IF(B{0}="","",IF(B{0}>0,"Markets more bullish on Brooks than the adjusted polls","Markets less bullish on Brooks than the adjusted polls"))'.format(DIFFR), NOTE)
sm.merge_cells(start_row=r, start_column=2, end_row=r, end_column=8); r += 1
put(sm, r, 1, "Polls in average", BOLD); put(sm, r, 2, '=COUNT(Polls!L{0}:L{1})'.format(P["PSTART"], P["PEND"]), BLACK, NUM); r += 1
put(sm, r, 1, "Days since most recent poll", BOLD)
put(sm, r, 2, '=IFERROR(TODAY()-MAX(Polls!E{0}:E{1}),"")'.format(P["PSTART"], P["PEND"]), BLACK, NUM); r += 1
r = note(sm, r, "The ladder's expected margin is in percentage points, so it is divided by 100 to compare with the poll "
                "margin, which is stored as a fraction. One public general-election poll exists and it is "
                "Democratic-sponsored, so the adjusted line is the fairer comparison.", 8)
r += 1

r = section(sm, r, "DATA FRESHNESS", 8)
put(sm, r, 1, "Snapshot pulled", BOLD); put(sm, r, 2, ASOF, BLUE)
sm.merge_cells(start_row=r, start_column=2, end_row=r, end_column=5); r += 1
put(sm, r, 1, "Polymarket winner history", BOLD)
put(sm, r, 2, '=TEXT(Polymarket!A{0},"yyyy-mm-dd")&" to "&TEXT(Polymarket!A{1},"yyyy-mm-dd")&"  ("&COUNT(Polymarket!A{0}:A{1})&" days)"'.format(PMF, PML), BLACK)
sm.merge_cells(start_row=r, start_column=2, end_row=r, end_column=5); r += 1
put(sm, r, 1, "Kalshi winner history", BOLD)
put(sm, r, 2, '=TEXT(Kalshi!A{0},"yyyy-mm-dd")&" to "&TEXT(Kalshi!A{1},"yyyy-mm-dd")&"  ("&COUNT(Kalshi!A{0}:A{1})&" days)"'.format(KF, KL), BLACK)
sm.merge_cells(start_row=r, start_column=2, end_row=r, end_column=5); r += 1
put(sm, r, 1, "Polls source", BOLD)
put(sm, r, 2, "house.csv (NYT / 538 house-poll file) — PA-07 rows: 1 general, 4 primary", BLUE)
sm.merge_cells(start_row=r, start_column=2, end_row=r, end_column=8); r += 1
put(sm, r, 1, "Refresh", BOLD)
put(sm, r, 2, "See Notes & Sources for the exact API call behind every blue cell.", NOTE)
sm.merge_cells(start_row=r, start_column=2, end_row=r, end_column=8)

json.dump({"VH": VH, "VL": VL, "PMF": PMF, "PML": PML, "KF": KF, "KL": KL,
           "MS": MS, "MP": MP, "HEAD": HEAD},
          open("vrefs.json", "w"))
wb.save("_stage3.xlsx")
print("stage3 ok")
