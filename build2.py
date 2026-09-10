import os, json, csv, datetime, collections
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.comments import Comment

import pollsrc
CSV = pollsrc.resolve()
ASOF = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
TODAY = datetime.datetime.utcnow().date()

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
BAND = PatternFill("solid", fgColor="F7F9FC"); EXF = PatternFill("solid", fgColor="EDEDED")
WINF = PatternFill("solid", fgColor="E2EFDA")
thin = Side(style="thin", color="BFBFBF"); BOX = Border(left=thin, right=thin, top=thin, bottom=thin)
PCT = '0.0%'; PCT2 = '0.00%'; DIFF = '+0.0%;-0.0%;0.0%'; NUM = '#,##0;(#,##0);-'; DATE = 'yyyy-mm-dd'

# ---------------- parse the NYT / 538 house-poll file ----------------
rows = [r for r in csv.DictReader(open(CSV)) if r["state"] == "PA" and r["seat_number"] == "7"]


def num(v, default=None):
    """Parse a numeric CSV field, or return `default` when it is blank or junk.

    house.csv is a 2.9 MB third-party file and its fields are not guaranteed
    populated — the sample_size column is already empty for the one general
    poll. An unguarded float() on a single empty pct cell aborts the build, and
    since refresh.py treats any build failure as fatal, one bad cell upstream
    costs every scheduled refresh until a human notices. Skip the row instead.
    """
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


polls = collections.OrderedDict()
skipped = []
for r in rows:
    pct = num(r["pct"])
    if pct is None:
        skipped.append("%s/%s" % (r.get("poll_id", "?")[:8], r.get("candidate_name") or r.get("answer") or "?"))
        continue
    p = polls.setdefault(r["poll_id"], {"meta": r, "ans": {}})
    p["ans"][r["candidate_name"] or r["answer"]] = pct
if skipped:
    print("WARNING: skipped %d PA-07 row(s) with an unreadable pct: %s"
          % (len(skipped), ", ".join(skipped[:8])))

def dt(s):
    return datetime.datetime.strptime(s, "%m/%d/%y")

general = [p for p in polls.values() if p["meta"]["stage"] == "general"]
primary = [p for p in polls.values() if p["meta"]["stage"] == "primary"]
general.sort(key=lambda p: dt(p["meta"]["end_date"]))
primary.sort(key=lambda p: dt(p["meta"]["end_date"]))
print("general polls:", len(general), "primary polls:", len(primary))

wb = load_workbook("_stage1.xlsx")
po = wb.create_sheet("Polls")

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
def note(ws, r, text, span=15):
    c = ws.cell(r, 1, text); c.font = NOTE
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=span)
    return r + 1

po["A1"] = "Polls — PA-07"; po["A1"].font = TITLE
po["A2"] = ("General-election and Democratic-primary polling for Pennsylvania's 7th, from the NYT/538 house-poll file "
            "(house.csv), plus the district and incumbent profile from GovTrack. Percentages stored as fractions. "
            "Compiled %s." % ASOF)
po["A2"].font = SUB
for k, v in {"A": 22, "B": 26, "C": 10, "D": 11, "E": 11, "F": 9, "G": 8, "H": 8,
             "I": 11, "J": 12, "K": 12, "L": 11, "M": 9, "N": 11, "O": 11}.items():
    po.column_dimensions[k].width = v

r = 4
put(po, r, 1, "HOW TO USE THIS SHEET", BOLD, None, YEL); r += 1
for t in ["Add a general-election poll by typing into the next blank blue row of the log below — rows are pre-formulated to row 28, so columns L to O fill themselves.",
          "Percentages are percent-formatted, so type 47% (not 47). Sponsor Lean must be D, R or None.",
          "The three yellow cells in POLLING AVERAGE drive the weighting. Change them and everything downstream updates.",
          "A greyed EXAMPLE row at the bottom shows the expected format. It sits outside every averaged range and can be deleted."]:
    r = note(po, r, "• " + t)
r += 1

# ---------------- general election log ----------------
r = section(po, r, "GENERAL ELECTION POLL LOG — Brooks (D) vs Mackenzie (R)", 15)
PH = headers(po, r, ["Pollster", "Sponsor / Client", "Sponsor Lean", "Field Start", "Field End", "Sample",
                     "Pop.", "MoE", "Brooks (D)", "Mackenzie (R)", "Other / Undecided", "Margin (D−R)",
                     "Days Ago", "Recency Weight", "Poll Weight"])
LEAN = {"DEM": "D", "REP": "R", "": "None"}
PSTART = PH
NG = max(len(general), 1)
NBLANK = 12
PEND = PH + NG + NBLANK - 1
# The log body is written further down, once the POLLING AVERAGE input rows exist —
# its Days Ago and Recency Weight columns point at them. See "general election log body".
po.cell(PH - 1, 3).comment = Comment(
    "Taken from the 'partisan' field of house.csv: DEM -> D, REP -> R, empty -> None. Drives the "
    "house-effect adjustment below.", "Tracker")
r = PEND + 1
r = note(po, r, "Source: house.csv (NYT / 538 house-poll file), rows filtered to state = PA and seat_number = 7, stage = general. "
                "The pollster-rating fields (numeric_grade, pollscore, transparency_score) are empty for every PA-07 poll in that file.")
r += 1

# ---------------- polling average ----------------
r = section(po, r, "POLLING AVERAGE", 15)
put(po, r, 1, "Reference date (as of)", BOLD); put(po, r, 2, TODAY, BLUE, DATE, YEL)
ASOF_ROW = r; r += 1
put(po, r, 1, "Recency half-life (days)", BOLD); put(po, r, 2, 45, BLUE, NUM, YEL)
po.cell(r, 2).comment = Comment("A poll's weight halves every N days. 45 is a reasonable default for a race still "
    "ten weeks out, not a fitted value. Shorten it to make the average more reactive.", "Tracker")
HL_ROW = r; r += 1
put(po, r, 1, "Partisan house-effect haircut", BOLD); put(po, r, 2, 0.03, BLUE, PCT, YEL)
po.cell(r, 2).comment = Comment("ASSUMPTION — not from any source. Sponsor-released partisan polls have historically "
    "favoured their sponsor by roughly 3-4 points on the margin. This is subtracted in proportion to net partisan "
    "sponsorship. Set to 0 to disable.", "Tracker")
HE_ROW = r; r += 2
AVG_REST = r          # the rest of the average block resumes here, after the log body

# ---------------- general election log body ----------------
# Written here rather than under its own section heading so that the Days Ago and
# Recency Weight formulas can name $B$ASOF_ROW and $B$HL_ROW the first time they are
# written. The block used to emit literal "$B$ASOF" / "$B$HL" placeholders and patch
# them at the end of the script; anything returning early between the two passes
# shipped a workbook full of #NAME?. Cell addressing does not care about write order.
for i in range(NG + NBLANK):
    rr = PH + i
    g = general[i] if i < len(general) else None
    vals = [None] * 11
    if g:
        m = g["meta"]
        dem = next((v for k, v in g["ans"].items() if "Brooks" in k), None)
        rep = next((v for k, v in g["ans"].items() if "Mackenzie" in k), None)
        smp = int(num(m["sample_size"], 550))
        vals = [m["pollster"], m["sponsors"] or "(none)", LEAN.get(m["partisan"], "None"),
                dt(m["start_date"]), dt(m["end_date"]), smp, (m["population"] or "").upper(),
                None, dem / 100 if dem else None, rep / 100 if rep else None, None]
    for c, fmt in ((1, None), (2, None), (3, None), (4, DATE), (5, DATE), (6, NUM), (7, None),
                   (8, PCT), (9, PCT), (10, PCT), (11, PCT)):
        put(po, rr, c, vals[c - 1], BLUE, fmt, DEMF if c == 9 else (REPF if c == 10 else None))
    put(po, rr, 12, '=IF(COUNT(I{0}:J{0})=2,I{0}-J{0},"")'.format(rr), BLACK, DIFF)
    put(po, rr, 13, '=IF(ISNUMBER(E{0}),$B${1}-E{0},"")'.format(rr, ASOF_ROW), BLACK, NUM)
    put(po, rr, 14, '=IF(ISNUMBER(M{0}),0.5^(M{0}/$B${1}),"")'.format(rr, HL_ROW), BLACK, '0.000')
    put(po, rr, 15, '=IF(AND(ISNUMBER(F{0}),ISNUMBER(N{0})),F{0}*N{0},"")'.format(rr), BLACK, NUM)
    if i % 2:
        for c in range(1, 16):
            if c not in (9, 10): po.cell(rr, c).fill = BAND
po.cell(PH, 6).comment = Comment(
    "ASSUMPTION: the sample_size field is empty for this poll in house.csv. 550 likely voters is used, "
    "the figure Pollsmax reports for the same GBAO survey. Sample size only affects this poll's weight, "
    "and with one general-election poll in the log it changes nothing.", "Tracker")

r = AVG_REST
put(po, r, 1, "Polls in average", BOLD); put(po, r, 2, '=COUNT(L{0}:L{1})'.format(PSTART, PEND), BLACK, NUM); r += 1
put(po, r, 1, "Weighted Brooks (D)", BOLD)
put(po, r, 2, '=IFERROR(SUMPRODUCT(I{0}:I{1},O{0}:O{1})/SUM(O{0}:O{1}),"")'.format(PSTART, PEND), BLACK, PCT, DEMF); WD = r; r += 1
put(po, r, 1, "Weighted Mackenzie (R)", BOLD)
put(po, r, 2, '=IFERROR(SUMPRODUCT(J{0}:J{1},O{0}:O{1})/SUM(O{0}:O{1}),"")'.format(PSTART, PEND), BLACK, PCT, REPF); WR = r; r += 1
put(po, r, 1, "Weighted margin (D−R)", BOLD); put(po, r, 2, '=IFERROR(B{0}-B{1},"")'.format(WD, WR), BOLD, DIFF); WM = r; r += 1
put(po, r, 1, "Net partisan sponsorship", BOLD)
put(po, r, 2, '=IFERROR((SUMIF($C${0}:$C${1},"D",$O${0}:$O${1})-SUMIF($C${0}:$C${1},"R",$O${0}:$O${1}))/SUM($O${0}:$O${1}),"")'.format(PSTART, PEND), BLACK, '0.00'); NPS = r
po.cell(r, 2).comment = Comment("Weight-share of D-sponsored polls minus weight-share of R-sponsored polls. "
    "+1.00 means every poll in the average came from a Democratic sponsor.", "Tracker"); r += 1
put(po, r, 1, "Adjusted margin (D−R)", BOLD)
put(po, r, 2, '=IFERROR(B{0}-B{1}*B{2},"")'.format(WM, NPS, HE_ROW), BOLD, DIFF, YEL); ADJ = r; r += 1
put(po, r, 1, "Simple (unweighted) margin", BOLD)
put(po, r, 2, '=IFERROR(AVERAGE(L{0}:L{1}),"")'.format(PSTART, PEND), BLACK, DIFF); r += 1
put(po, r, 1, "Most recent poll date", BOLD)
put(po, r, 2, '=IFERROR(MAX(E{0}:E{1}),"")'.format(PSTART, PEND), BLACK, DATE); r += 1
put(po, r, 1, "Days since most recent poll", BOLD)
put(po, r, 2, '=IFERROR($B${0}-MAX(E{1}:E{2}),"")'.format(ASOF_ROW, PSTART, PEND), BLACK, NUM); r += 1
r = note(po, r, "Only one public general-election poll exists for PA-07 so far, and it is Democratic-sponsored. "
                "The average is a single data point wearing a weighting scheme — read the adjusted margin, and lean on the market sheets.")
r += 1

# ---------------- primary polls ----------------
CAND = ["Bob Brooks", "Lamont McClure", "Ryan Crosswell", "Carol Obando-Derstine"]
r = section(po, r, "DEMOCRATIC PRIMARY POLLS (settled 19 May 2026) — for calibration", 15)
QH = headers(po, r, ["Pollster", "Sponsor / Client", "Lean", "Field Start", "Field End", "Sample", "Pop.",
                     "Brooks", "McClure", "Crosswell", "Obando-Derstine", "Undecided", "Other",
                     "Brooks Lead", "Leader"])
QS = QH
for i, p in enumerate(primary):
    rr = QH + i
    m = p["meta"]
    put(po, rr, 1, m["pollster"], BLUE); put(po, rr, 2, m["sponsors"] or "(none)", BLUE)
    put(po, rr, 3, LEAN.get(m["partisan"], "None"), BLUE)
    put(po, rr, 4, dt(m["start_date"]), BLUE, DATE); put(po, rr, 5, dt(m["end_date"]), BLUE, DATE)
    put(po, rr, 6, num(m["sample_size"]), BLUE, NUM)
    put(po, rr, 7, (m["population"] or "").upper(), BLUE)
    for j, c in enumerate(CAND):
        v = p["ans"].get(c)
        put(po, rr, 8 + j, v / 100 if v is not None else None, BLUE, PCT, DEMF if j == 0 else None)
    und = next((v for k, v in p["ans"].items() if "know" in k.lower()), None)
    oth = sum(v for k, v in p["ans"].items()
              if k not in CAND and "know" not in k.lower())
    put(po, rr, 12, und / 100 if und is not None else None, BLUE, PCT)
    put(po, rr, 13, oth / 100 if oth else None, BLUE, PCT)
    put(po, rr, 14, '=IF(COUNT(H{0}:K{0})>1,H{0}-MAX(I{0}:K{0}),"")'.format(rr), BLACK, DIFF)
    put(po, rr, 15, '=IF(COUNT(H{0}:K{0})=0,"",INDEX($H${1}:$K${1},MATCH(MAX(H{0}:K{0}),H{0}:K{0},0)))'.format(rr, QH - 1), BLACK)
    if i % 2:
        for c in range(1, 16):
            if c != 8: po.cell(rr, c).fill = BAND
QE = QH + len(primary) - 1
rr = QE + 1
put(po, rr, 1, "ACTUAL RESULT", BOLD, None, WINF); put(po, rr, 2, "Primary, 19 May 2026", BOLD, None, WINF)
put(po, rr, 3, "—", BLACK, None, WINF); put(po, rr, 5, datetime.datetime(2026, 5, 19), BLUE, DATE, WINF)
put(po, rr, 8, 0.414, BLUE, PCT, WINF)
for c in (4, 6, 7, 9, 10, 11, 12, 13, 14, 15): put(po, rr, c, None, BLACK, None, WINF)
po.cell(rr, 8).comment = Comment("Brooks won with roughly 41.4% at about 74% of votes counted, per Ballotpedia's "
    "primary-night report. Recorded so the primary polls above can be scored: every poll understated him, "
    "largely because 31-53% of respondents were undecided.", "Tracker")
ACT = rr; rr += 1
rr = note(po, rr, "Source: house.csv, stage = primary. Undecided is the \"Don't know\" answer; Other pools "
                  "\"Someone else\" and \"Would not vote\". These markets are settled — the section is kept for calibration, "
                  "not tracking.")
r = rr + 1

# ---------------- GovTrack district profile ----------------
r = section(po, r, "DISTRICT & INCUMBENT PROFILE — GovTrack", 15)
GT = [("Incumbent", "Ryan Mackenzie (R)"),
      ("GovTrack profile", "govtrack.us/congress/members/ryan_mackenzie/457017"),
      ("Serving since", "2025-01-03"),
      ("Term ends", "2027-01-03"),
      ("Age", "44"),
      ("Next election", "2026"),
      ("Caucus", "Main Street Caucus"),
      ("Committees", "Education & Workforce (Chair, Workforce Protections subcttee); Foreign Affairs; Homeland Security"),
      ("Missed votes", "13 of 645 roll calls, Jan 2025 – Jul 2026 (2.0%) — on par with the 2.0% median among sitting representatives"),
      ("Top sponsorship areas", "Taxation 23%; Armed Forces & National Security 23%; Government Operations 18%; Health 9%"),
      ("PA senators", "John Fetterman (D, since 2023); Dave McCormick (R, since 2025)"),
      ("Redistricting caveat", "GovTrack notes some states are changing districts for 2026; its map reflects the 2024 lines. Confirm PA-07's boundaries before treating district-level history as like-for-like.")]
for lbl, val in GT:
    put(po, r, 1, lbl, BOLD); put(po, r, 2, val, BLUE)
    po.merge_cells(start_row=r, start_column=2, end_row=r, end_column=15)
    po.cell(r, 2).alignment = Alignment(wrap_text=True, vertical="top")
    if len(val) > 95: po.row_dimensions[r].height = 26
    r += 1
r += 1

# ---------------- supplementary ----------------
r = section(po, r, "SUPPLEMENTARY DISTRICT NUMBERS (no head-to-head)", 15)
r = headers(po, r, ["Source", "Sponsor", "Metric", "", "Favourable / Approve", "Unfavourable / Disapprove",
                    "Net", "", "", "", "", "", "", "", ""])
for src, spon, metric, fav, unf in [
    ("GBAO (29 Jun – 2 Jul 2026)", "House Majority PAC", "Trump favourability in PA-07", 0.44, 0.51),
    ("GBAO (29 Jun – 2 Jul 2026)", "House Majority PAC", "2024 recall: Trump vs Harris", 0.47, 0.46),
    ("House Majority Forward (n/d)", "House Majority Forward", "Mackenzie job approval", 0.27, 0.41),
    ("House Majority Forward (n/d)", "House Majority Forward", "Trump favourability in PA-07", 0.40, 0.56),
    ("House Majority Forward (n/d)", "House Majority Forward", "Trump job approval in PA-07", 0.41, 0.57)]:
    put(po, r, 1, src, BLUE); put(po, r, 2, spon, BLUE); put(po, r, 3, metric, BLUE)
    po.merge_cells(start_row=r, start_column=3, end_row=r, end_column=4)
    put(po, r, 5, fav, BLUE, PCT); put(po, r, 6, unf, BLUE, PCT)
    put(po, r, 7, '=E{0}-F{0}'.format(r), BLACK, DIFF); r += 1
r = note(po, r, "The 2024 recall line is the sample's remembered 2024 presidential vote, so its net reads as Trump's "
                "recalled margin. House Majority Forward figures were reported by PoliticsPA without field dates, sample "
                "size or MoE, and predate the May primary. Neither source appears in house.csv.")
r += 1

# ---------------- example row ----------------
r = section(po, r, "EXAMPLE ROW — format reference only, delete before use", 15)
r = headers(po, r, ["Pollster", "Sponsor / Client", "Sponsor Lean", "Field Start", "Field End", "Sample", "Pop.", "MoE",
                    "Brooks (D)", "Mackenzie (R)", "Other / Undecided", "Margin (D−R)", "Days Ago", "Recency Weight", "Poll Weight"])
ex = ["Emerson College", "Emerson / The Hill", "None", datetime.datetime(2026, 9, 14), datetime.datetime(2026, 9, 17),
      700, "LV", 0.037, 0.485, 0.455, 0.06]
for c, (v, fmt) in enumerate(zip(ex, [None, None, None, DATE, DATE, NUM, None, PCT, PCT, PCT, PCT]), 1):
    put(po, r, c, v, BLUE, fmt, EXF)
put(po, r, 12, '=I{0}-J{0}'.format(r), BLACK, DIFF, EXF)
put(po, r, 13, '=$B${0}-E{1}'.format(ASOF_ROW, r), BLACK, NUM, EXF)
put(po, r, 14, '=0.5^(M{0}/$B${1})'.format(r, HL_ROW), BLACK, '0.000', EXF)
put(po, r, 15, '=F{0}*N{0}'.format(r), BLACK, NUM, EXF)

po.freeze_panes = po.cell(PH, 1)

json.dump({"WD": WD, "WR": WR, "WM": WM, "ADJ": ADJ, "ASOF_ROW": ASOF_ROW, "HL_ROW": HL_ROW,
           "PSTART": PSTART, "PEND": PEND, "QS": QS, "QE": QE, "ACT": ACT},
          open("prefs.json", "w"))
wb.save("_stage2.xlsx")
print("stage2 ok — general log %d-%d, primary %d-%d" % (PSTART, PEND, QS, QE))
