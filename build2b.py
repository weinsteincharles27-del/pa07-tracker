import json, datetime
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.comments import Comment

D2 = json.load(open("data2.json"))
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
SECTF = PatternFill("solid", fgColor="1F3864"); HDRF = PatternFill("solid", fgColor="4472C4")
DEMF = PatternFill("solid", fgColor="DEEBF7"); REPF = PatternFill("solid", fgColor="FCE4E4")
YEL = PatternFill("solid", fgColor="FFFF00"); GREY = PatternFill("solid", fgColor="F2F2F2")
BAND = PatternFill("solid", fgColor="F7F9FC")
thin = Side(style="thin", color="BFBFBF"); BOX = Border(left=thin, right=thin, top=thin, bottom=thin)
PCT = '0.0%'; PCT2 = '0.00%'; DIFF = '+0.0%;-0.0%;0.0%'; USD = '$#,##0;($#,##0);-'
NUM = '#,##0;(#,##0);-'; DATE = 'yyyy-mm-dd'; PTS = '+0.00" pts";-0.00" pts";0.00" pts"'
SEATS = '0.00" seats"'

wb = load_workbook("_stage2.xlsx")

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
    """Refuse to build a row range out of an empty ladder.

    LN is LH + len(ladder) - 1, so an empty ladder gives LN < LH and every chart
    Reference built from the pair comes out inverted. Fail loudly instead.
    """
    if n < 1:
        raise SystemExit("FATAL: %s came back empty — refusing to write an inverted row "
                         "range. Re-run the collector before building." % what)
    return n

# =====================================================================
# SHEET: Margin of Victory  (Polymarket)
# =====================================================================
mv = wb.create_sheet("Margin of Victory")
mv["A1"] = "Margin of Victory — PA-07 (Polymarket)"; mv["A1"].font = TITLE
mv["A2"] = ("The PA-07 winning margin, quoted on BOTH venues: Polymarket as exclusive brackets "
            "(below) and Kalshi as nested thresholds (further down, with the two compared). "
            "Pulled %s." % ASOF)
mv["A2"].font = SUB
for k, v in {"A": 21, "B": 13, "C": 12, "D": 12, "E": 12, "F": 13, "G": 13, "H": 12, "I": 13,
             "J": 13, "K": 13}.items():
    mv.column_dimensions[k].width = v

r = 4
r = section(mv, r, "MARKET METADATA", 10)
me = D2["mov_event"]
for lbl, val, fmt in [("Event", me["title"], None), ("Slug", me["slug"], None),
                      ("Event id", int(me["id"]), NUM), ("Opened", me["startDate"][:10], None),
                      ("Resolution date", me["endDate"][:10], None),
                      ("Volume ($)", me["volume"], USD), ("Liquidity ($)", me["liquidity"], USD),
                      ("Brackets listed", len(D2["mov"]), NUM)]:
    put(mv, r, 1, lbl, BOLD); put(mv, r, 2, val, BLUE, fmt)
    mv.merge_cells(start_row=r, start_column=2, end_row=r, end_column=6); r += 1
r += 1

r = section(mv, r, "LIVE BRACKET LADDER", 10)
LH = headers(mv, r, ["Bracket", "Signed Midpoint (pts)", "Best Bid", "Best Ask", "Mid",
                     "Normalised Prob", "Cumulative", "Volume ($)", "Liquidity ($)", "Prob × Midpoint"])
L0 = LH
n = need(len(D2["mov"]), "Polymarket margin-of-victory bracket ladder")
LN = LH + n - 1
TOT = LN + 1
for i, b in enumerate(D2["mov"]):
    rr = LH + i
    fill = REPF if b["bracket"].startswith("Republican") else DEMF
    put(mv, rr, 1, b["bracket"], BOLD, None, fill)
    put(mv, rr, 2, b["midpoint"], BLUE, '+0.0;-0.0;0.0')
    put(mv, rr, 3, b["best_bid"], BLUE, PCT)
    put(mv, rr, 4, b["best_ask"], BLUE, PCT)
    put(mv, rr, 5, '=(C{0}+D{0})/2'.format(rr), BLACK, PCT2)
    put(mv, rr, 6, '=IFERROR(E{0}/$E${1},"")'.format(rr, TOT), BLACK, PCT2)
    put(mv, rr, 7, '=IFERROR(SUM($F${0}:F{1}),"")'.format(L0, rr), BLACK, PCT)
    put(mv, rr, 8, b["volume"], BLUE, USD)
    put(mv, rr, 9, b["liquidity"], BLUE, USD)
    put(mv, rr, 10, '=IFERROR(F{0}*B{0},"")'.format(rr), BLACK, '0.000')
put(mv, TOT, 1, "TOTAL", BOLD, None, GREY)
put(mv, TOT, 5, '=SUM(E{0}:E{1})'.format(L0, LN), BOLD, PCT2, YEL)
put(mv, TOT, 6, '=SUM(F{0}:F{1})'.format(L0, LN), BOLD, PCT2)
put(mv, TOT, 8, '=SUM(H{0}:H{1})'.format(L0, LN), BOLD, USD)
put(mv, TOT, 9, '=SUM(I{0}:I{1})'.format(L0, LN), BOLD, USD)
put(mv, TOT, 10, '=SUM(J{0}:J{1})'.format(L0, LN), BOLD, '0.000')
mv.cell(TOT, 5).comment = Comment(
    "Sum of the ten bracket mids. Exactly one bracket must pay out, so a fair ladder sums to 100%. This one sums "
    "well above that because several brackets are quoted with very wide bid-ask spreads on thin volume, which "
    "inflates the mid. The Normalised column rescales to 100% and is the column to read.", "Tracker")
mv.cell(LH - 1, 2).comment = Comment(
    "ASSUMPTION: the signed centre of each bracket in margin points, positive for a Democratic win. Closed brackets "
    "use their true midpoint (0-3% -> 1.5). The two open-ended brackets are judgement calls: 'Democrat 18%+' is "
    "set to +20.0 and 'Republican 6%+' to -8.0. Both feed the expected-margin figure below; change them here and it "
    "updates.", "Tracker")
r = TOT + 2

r = section(mv, r, "IMPLIED DISTRIBUTION", 10)
S = r
put(mv, r, 1, "P(Democrat wins) — from ladder", BOLD)
put(mv, r, 2, '=IFERROR(SUMIF($A${0}:$A${1},"Democrat*",$F${0}:$F${1}),"")'.format(L0, LN), BOLD, PCT2, DEMF); PD = r; r += 1
put(mv, r, 1, "P(Republican wins) — from ladder", BOLD)
put(mv, r, 2, '=IFERROR(SUMIF($A${0}:$A${1},"Republican*",$F${0}:$F${1}),"")'.format(L0, LN), BOLD, PCT2, REPF); PR = r; r += 1
put(mv, r, 1, "Expected margin (D−R)", BOLD)
put(mv, r, 2, '=IFERROR(SUM(J{0}:J{1}),"")'.format(L0, LN), BOLD, PTS, YEL); EM = r; r += 1
put(mv, r, 1, "P(margin under 3 pts either way)", BOLD)
put(mv, r, 2, '=IFERROR(SUMIFS($F${0}:$F${1},$B${0}:$B${1},">-3",$B${0}:$B${1},"<3"),"")'.format(L0, LN), BLACK, PCT2); P3 = r; r += 1
put(mv, r, 1, "P(margin under 6 pts either way)", BOLD)
put(mv, r, 2, '=IFERROR(SUMIFS($F${0}:$F${1},$B${0}:$B${1},">-6",$B${0}:$B${1},"<6"),"")'.format(L0, LN), BLACK, PCT2); P6 = r
mv.cell(P3, 2).comment = Comment(
    "Both 'under N pts' lines sum the Normalised column over every bracket whose signed midpoint "
    "in column B falls strictly inside ±N, rather than matching bracket labels by name. The labels "
    "come straight from the Polymarket API, so an en-dash for a hyphen, a spacing change or a "
    "split bracket would silently drop a term from a name-matched sum; the midpoint is numeric and "
    "survives all of that. The two open-ended brackets are included on the strength of the assumed "
    "midpoints noted on the ladder header — 'Republican 6%+' at -8.0 sits outside both thresholds, "
    "so editing that assumption inside ±6 would move it into the under-6 figure.", "Tracker"); r += 2

r = section(mv, r, "CROSS-CHECK vs THE WINNER MARKET", 10)
put(mv, r, 1, "Winner market — Polymarket Dem mid", BOLD)
put(mv, r, 2, '=Polymarket!D{0}'.format(R["PM_MID_D"]), GREEN, PCT2); W1 = r; r += 1
put(mv, r, 1, "Margin ladder — P(Democrat wins)", BOLD)
put(mv, r, 2, '=B{0}'.format(PD), BLACK, PCT2); r += 1
put(mv, r, 1, "Discrepancy (ladder − winner)", BOLD)
put(mv, r, 2, '=IFERROR(B{0}-B{1},"")'.format(PD, W1), BOLD, DIFF, YEL); r += 1
r = note(mv, r, "Both markets describe the same event on the same venue, so a large gap is a sign the thin margin ladder "
                "is mispriced rather than a signal about the race. The winner market carries far more volume; trust it first.", 10)
r += 1

r = section(mv, r, "DAILY BRACKET HISTORY", 11)
brackets = [b["bracket"] for b in D2["mov"]]
HH = headers(mv, r, ["Date"] + brackets)
hist = D2["mov_history"]
days = sorted(hist)
for i, day in enumerate(days):
    rr = HH + i
    put(mv, rr, 1, datetime.datetime.strptime(day, "%Y-%m-%d"), BLUE, DATE)
    for j, b in enumerate(brackets):
        put(mv, rr, 2 + j, hist[day].get(b), BLUE, PCT)
    if i % 2:
        for c in range(1, 12): mv.cell(rr, c).fill = BAND
MH_LAST = HH + len(days) - 1
r = MH_LAST + 1
r = note(mv, r, "All ten brackets, daily closes from CLOB /prices-history at fidelity=1440. The market opened "
                "11 Aug 2026, so the series is only %d days long and the brackets are thin — read it as a sanity check "
                "on the ladder above, not as a trend." % len(days), 11)
mv.freeze_panes = mv.cell(HH, 2)
MOV_REFS = {"PD": PD, "PR": PR, "EM": EM, "P3": P3, "P6": P6, "TOT": TOT, "L0": L0, "LN": LN}

# =====================================================================
# SHEET: PA Seat Count  (Kalshi)
# =====================================================================
sc = wb.create_sheet("PA Seat Count")
sc["A1"] = "PA Democratic House Seats — Kalshi (KXHOUSEWINSTATE-PAD)"; sc["A1"].font = TITLE
sc["A2"] = ("How many of Pennsylvania's 17 House seats Democrats win on 3 Nov 2026. PA-07 is one of the seats in "
            "this count, so the ladder is a state-level read on the same question. Pulled %s." % ASOF)
sc["A2"].font = SUB
for k, v in {"A": 20, "B": 12, "C": 12, "D": 13, "E": 12, "F": 14, "G": 12, "H": 14, "I": 13, "J": 13}.items():
    sc.column_dimensions[k].width = v

r = 4
r = section(sc, r, "MARKET METADATA", 10)
for lbl, val in [("Event", "KXHOUSEWINSTATE-PAD"),
                 ("Question", "How many House seats will Democrats win in Pennsylvania?"),
                 ("Resolution", "On Nov 3, 2026"),
                 ("Series", "KXHOUSEWINSTATE"),
                 ("Brackets listed", len(D2["seats"]))]:
    put(sc, r, 1, lbl, BOLD); put(sc, r, 2, val, BLUE, NUM if lbl == "Brackets listed" else None)
    sc.merge_cells(start_row=r, start_column=2, end_row=r, end_column=7); r += 1
r += 1

r = section(sc, r, "LIVE BRACKET LADDER", 10)
KH = headers(sc, r, ["Bracket", "Seats (assumed)", "YES Bid", "NO Bid", "YES Ask", "Mid",
                     "Normalised Prob", "Cumulative", "Prob × Seats", ""])
K0 = KH
kn = need(len(D2["seats"]), "Kalshi PA seat-count bracket ladder")
KN = KH + kn - 1
KTOT = KN + 1
for i, b in enumerate(D2["seats"]):
    rr = KH + i
    put(sc, rr, 1, b["label"], BOLD, None, GREY)
    put(sc, rr, 2, b["midpoint"], BLUE, NUM)
    put(sc, rr, 3, b["yes_bid"], BLUE, PCT)
    put(sc, rr, 4, b["no_bid"], BLUE, PCT)
    put(sc, rr, 5, '=IF(ISNUMBER(D{0}),1-D{0},"")'.format(rr), BLACK, PCT)
    put(sc, rr, 6, '=IF(COUNT(C{0},E{0})=2,(C{0}+E{0})/2,IF(ISNUMBER(E{0}),E{0}/2,""))'.format(rr), BLACK, PCT2)
    put(sc, rr, 7, '=IFERROR(F{0}/$F${1},"")'.format(rr, KTOT), BLACK, PCT2)
    put(sc, rr, 8, '=IFERROR(SUM($G${0}:G{1}),"")'.format(K0, rr), BLACK, PCT)
    put(sc, rr, 9, '=IFERROR(G{0}*B{0},"")'.format(rr), BLACK, '0.000')
put(sc, KTOT, 1, "TOTAL", BOLD, None, GREY)
put(sc, KTOT, 6, '=SUM(F{0}:F{1})'.format(K0, KN), BOLD, PCT2, YEL)
put(sc, KTOT, 7, '=SUM(G{0}:G{1})'.format(K0, KN), BOLD, PCT2)
put(sc, KTOT, 9, '=SUM(I{0}:I{1})'.format(K0, KN), BOLD, '0.000')
sc.cell(KH, 6).comment = Comment(
    "Two brackets ('Below 7' and 'Above 12') have no resting YES bid at all — only an ask. For those the mid formula "
    "falls back to half the ask rather than dropping the bracket, which keeps the ladder summing sensibly. Both are "
    "quoted at 1-2c, so the choice barely moves the expected-seats figure.", "Tracker")
sc.cell(KH - 1, 2).comment = Comment(
    "ASSUMPTION: seat count assumed for each bracket. Exact brackets (7 through 12) use their own number. The two "
    "open-ended brackets are judgement calls: 'Below 7' is set to 6 and 'Above 12' to 13.", "Tracker")
r = KTOT + 2

r = section(sc, r, "IMPLIED READ", 10)
put(sc, r, 1, "Expected Democratic seats", BOLD)
put(sc, r, 2, '=IFERROR(SUM(I{0}:I{1}),"")'.format(K0, KN), BOLD, SEATS, YEL); ES = r; r += 1
put(sc, r, 1, "Modal bracket", BOLD)
put(sc, r, 2, '=IFERROR(INDEX($A${0}:$A${1},MATCH(MAX($G${0}:$G${1}),$G${0}:$G${1},0)),"")'.format(K0, KN), BOLD); r += 1
put(sc, r, 1, "P(9 or more seats)", BOLD)
put(sc, r, 2, '=IFERROR(SUMIF($B${0}:$B${1},">=9",$G${0}:$G${1}),"")'.format(K0, KN), BLACK, PCT2); r += 1
put(sc, r, 1, "PA seats held by Democrats now", BOLD); put(sc, r, 2, 8, BLUE, NUM); CUR = r; r += 1
put(sc, r, 1, "Implied net gain", BOLD)
put(sc, r, 2, '=IFERROR(B{0}-B{1},"")'.format(ES, CUR), BOLD, '+0.00;-0.00;0.00'); r += 1
r = note(sc, r, "PA's delegation is 17 seats. The 8-seat current baseline is entered by hand as the Democratic count "
                "going into the 2026 cycle — check it against the current delegation before relying on the net-gain line. "
                "A market expectation above that baseline is consistent with Democrats favoured to flip PA-07.", 10)
r += 1

r = section(sc, r, "DAILY BRACKET HISTORY (mid of YES bid and derived ask)", 10)
labels = [b["label"] for b in D2["seats"]]
tickers = [b["ticker"] for b in D2["seats"]]
SH = headers(sc, r, ["Date"] + labels + [""])
shist = D2["seat_history"]
sdays = sorted(shist)
for i, day in enumerate(sdays):
    rr = SH + i
    put(sc, rr, 1, datetime.datetime.strptime(day, "%Y-%m-%d"), BLUE, DATE)
    for j, tk in enumerate(tickers):
        rec = shist[day].get(tk)
        v = None
        if rec:
            bid, ask = rec.get("bid"), rec.get("ask")
            if bid is not None and ask is not None: v = (bid + ask) / 2
            elif ask is not None: v = ask / 2
            elif bid is not None: v = bid
        put(sc, rr, 2 + j, v, BLUE, PCT)
    if i % 2:
        for c in range(1, 11): sc.cell(rr, c).fill = BAND
r = SH + len(sdays)
r = note(sc, r, "Kalshi began quoting this ladder on 20 Aug 2026, so the history is only %d days long. Values are the "
                "mid of the daily closing YES bid and the ask derived from the closing NO bid; where only one side "
                "closed, the same fallback as the live ladder applies." % len(sdays), 10)
sc.freeze_panes = sc.cell(SH, 2)

MOV_REFS.update({"ES": ES, "K0": K0, "KN": KN, "KTOT": KTOT, "CUR": CUR})
json.dump(MOV_REFS, open("movrefs.json", "w"))
wb.save("_stage2b.xlsx")
print("stage2b ok — MOV ladder %d-%d total %d | seats %d-%d total %d" % (L0, LN, TOT, K0, KN, KTOT))
