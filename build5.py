"""Chart sheets.

Native Excel charts bound to cell ranges, so they redraw from live data on every
refresh — nothing is rasterised or hardcoded.
"""
import json, datetime
from openpyxl import load_workbook
from openpyxl.chart import LineChart, BarChart, Reference, Series
from openpyxl.chart.axis import ChartLines
from openpyxl.chart.shapes import GraphicalProperties
from openpyxl.chart.layout import Layout, ManualLayout
from openpyxl.chart.text import RichText
from openpyxl.drawing.text import (RichTextProperties, Paragraph, ParagraphProperties,
                                   CharacterProperties)
from openpyxl.chart.label import DataLabelList
from openpyxl.drawing.line import LineProperties
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.comments import Comment

V = json.load(open("vrefs.json")); P = json.load(open("prefs.json")); MV = json.load(open("movrefs.json"))
import os
F7 = json.load(open("f7refs.json")) if os.path.exists("f7refs.json") else {}
K3 = json.load(open("k3refs.json"))
ASOF = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

F = "Arial"
BLACK = Font(name=F, size=10); BOLD = Font(name=F, size=10, bold=True)
BLUE = Font(name=F, size=10, color="0000FF"); GREEN = Font(name=F, size=10, color="008000")
TITLE = Font(name=F, size=16, bold=True, color="1F3864")
SUB = Font(name=F, size=9, italic=True, color="595959")
SECT = Font(name=F, size=11, bold=True, color="FFFFFF")
NOTE = Font(name=F, size=9, italic=True, color="595959")
SECTF = PatternFill("solid", fgColor="1F3864")
GREY = PatternFill("solid", fgColor="F2F2F2")
thin = Side(style="thin", color="BFBFBF"); BOX = Border(left=thin, right=thin, top=thin, bottom=thin)
PCT = '0.0%'; PCT2 = '0.00%'; PTS = '+0.00" pts";-0.00" pts";0.00" pts"'

# one palette across every chart
C_PM   = "2E5FA3"   # Polymarket  - blue
C_KAL  = "E8802B"   # Kalshi      - orange
C_DEM  = "2E5FA3"
C_REP  = "C0392B"
C_REF  = "9AA5B1"   # reference lines - grey
C_NEU  = "6B7C93"

wb = load_workbook("_stage3.xlsx")

def section(ws, row, text, width):
    ws.cell(row, 1, text).font = SECT
    for c in range(1, width + 1): ws.cell(row, c).fill = SECTF
    return row + 1

def note(ws, row, text, span):
    c = ws.cell(row, 1, text); c.font = NOTE
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=span)
    return row + 1

# Axis lines are drawn dark and solid so the plot is anchored; gridlines are
# drawn much lighter so they sit behind the data instead of competing with it.
AXIS_COLOUR = "44546A"      # dark slate — the frame
GRID_COLOUR = "EDEFF3"      # very light — reference only, never competes with data
LABEL_COLOUR = "3B3B3B"
AXIS_W = 12700              # EMU, ~1pt
GRID_W = 6350               # EMU, ~0.5pt

# One full-width exhibit per row. Two-up at 17.4cm left every chart too small to
# read a 200-point series in; a single 25cm column is the readable shape, and it
# is also how these get pasted into a deck.
CH_W = 25.4                 # cm
CH_H = 12.4                 # cm
CH_PITCH = 29               # rows between chart anchors, at 15pt per row


def _axis_line(colour, width):
    return GraphicalProperties(ln=LineProperties(solidFill=colour, w=width))


def _para(size, colour, bold=False):
    """A properties-only paragraph: no runs (a run becomes the literal text
    "None" after build4.py reloads the workbook) but WITH endParaRPr, without
    which the paragraph counts as empty and its sizing is thrown away."""
    cp = CharacterProperties(sz=size, b=bold, solidFill=colour)
    return Paragraph(r=[], pPr=ParagraphProperties(defRPr=cp),
                     endParaRPr=CharacterProperties(sz=size, b=bold, solidFill=colour))


def _rich(size, colour, bold=False, rot=None):
    body = RichTextProperties(rot=rot, vert="horz") if rot is not None else RichTextProperties()
    return RichText(bodyPr=body, p=[_para(size, colour, bold)])


def _tick_text(size=900, colour=LABEL_COLOUR):
    """Tick-label styling. openpyxl needs the full RichText scaffold for this."""
    return RichText(bodyPr=RichTextProperties(), p=[_para(size, colour)])


def yscale(chart, lo=None, hi=None, unit=None):
    """Pin the value axis. Excel's autoscale anchors at zero, which flattens a
    series that never goes near it."""
    if lo is not None:
        chart.y_axis.scaling.min = lo
    if hi is not None:
        chart.y_axis.scaling.max = hi
    if unit is not None:
        chart.y_axis.majorUnit = unit
    return chart


def axes(chart, ynum='0%', xrot=None):
    """Make both axes legible: solid dark line, outward ticks, readable labels.

    tickLblPos="low" is the important one. The default is "nextTo", which draws
    the category labels AT the axis line — and on any chart whose values cross
    zero the axis line runs through the middle of the plot, so the dates end up
    printed across the data. "low" pins them under the plot area where they
    belong, whatever the values do.
    """
    for ax in (chart.x_axis, chart.y_axis):
        ax.delete = False
        ax.spPr = _axis_line(AXIS_COLOUR, AXIS_W)
        ax.majorTickMark = "out"
        ax.minorTickMark = "none"
        ax.tickLblPos = "low"
        ax.txPr = _tick_text()
    chart.y_axis.number_format = ynum
    # Gridlines on the value axis only, and kept faint.
    chart.y_axis.majorGridlines = ChartLines(spPr=_axis_line(GRID_COLOUR, GRID_W))
    chart.x_axis.majorGridlines = None
    if xrot is not None:
        chart.x_axis.txPr = RichText(
            bodyPr=RichTextProperties(rot=xrot, vert="horz"),
            p=[Paragraph(r=[], pPr=ParagraphProperties(
                defRPr=CharacterProperties(sz=800, solidFill=LABEL_COLOUR)))])
    return chart


def style(chart, title, ytitle, xtitle=None, ynum='0%', height=CH_H, width=CH_W,
          xrot=None, bottom=0.19):
    """Chart frame plus an EXPLICIT plot-area layout.

    openpyxl emits no <c:layout>, so Excel auto-fits the plot and will happily
    let a rotated date axis or a rotated y-axis title overlap the plotted data.
    Reserving the margins by hand is the only reliable fix; `bottom` is the share
    of the frame kept clear underneath for angled date labels.
    """
    chart.title = title
    chart.style = None
    chart.height = height
    chart.width = width
    chart.y_axis.title = ytitle
    if xtitle:
        chart.x_axis.title = xtitle
    axes(chart, ynum=ynum, xrot=xrot)
    # Title and axis titles sized deliberately rather than left to Excel's default.
    if chart.title is not None:
        chart.title.tx.rich.p[0].pPr = ParagraphProperties(
            defRPr=CharacterProperties(sz=1200, b=True, solidFill="1F3864"))
    for ax, rot in ((chart.y_axis, -5400000), (chart.x_axis, None)):
        if ax.title is not None:
            ax.title.tx.rich.p[0].pPr = ParagraphProperties(
                defRPr=CharacterProperties(sz=950, b=False, solidFill=LABEL_COLOUR))
    if chart.legend is not None:
        chart.legend.position = "t"
        chart.legend.overlay = False
        chart.legend.txPr = _tick_text(900)
    chart.layout = Layout(manualLayout=ManualLayout(
        xMode="edge", yMode="edge",
        x=0.075, y=0.17, w=0.895, h=max(0.30, 1.0 - 0.17 - bottom)))
    return chart

def line(series, colour, width_emu=20000, dashed=False):
    lp = LineProperties(solidFill=colour, w=width_emu)
    if dashed:
        lp.prstDash = "dash"
    series.graphicalProperties.line = lp
    series.smooth = False
    return series

# =====================================================================
# SHEET: Charts  (time series)
# =====================================================================
ch = wb.create_sheet("Charts")
ch.sheet_view.showGridLines = False
ch["A1"] = "Charts — Race Trajectory"; ch["A1"].font = TITLE
ch["A2"] = ("Every chart is bound to the cell ranges on the data sheets, so all of them redraw automatically "
            "each time the tracker refreshes. Built %s." % ASOF)
ch["A2"].font = SUB
for col in "ABCDEFGHIJKLMN":
    ch.column_dimensions[col].width = 13

VH, VL = V["VH"], V["VL"]
KF, KL = V["KF"], V["KL"]
PMF, PML = V["PMF"], V["PML"]

# --- 1. Democratic win probability, both venues -----------------------
c1 = LineChart()
# headers() returns the first DATA row, so the header sits at VH-1.
dates = Reference(wb["Venue Comparison"], min_col=12, min_row=VH, max_row=VL)
for col, colour, dash in ((2, C_PM, False), (3, C_KAL, False), (11, C_REF, True)):
    ref = Reference(wb["Venue Comparison"], min_col=col, min_row=VH - 1, max_row=VL)
    s = Series(ref, title_from_data=True)
    line(s, colour, 22000 if not dash else 12000, dash)
    c1.series.append(s)
c1.set_categories(dates)
style(c1, "Democratic win probability — Polymarket vs Kalshi", "Implied probability")
yscale(c1, 0.30, 0.95, 0.10)
c1.x_axis.tickLblSkip = 30
c1.x_axis.tickMarkSkip = 30
c1.x_axis.number_format = 'mmm-yy'
ch.add_chart(c1, "A4")

# --- 2. Cross-venue divergence ---------------------------------------
c2 = LineChart()
ref = Reference(wb["Venue Comparison"], min_col=4, min_row=VH - 1, max_row=VL)
s = Series(ref, title_from_data=True); line(s, C_NEU, 20000)
c2.series.append(s)
c2.set_categories(dates)
style(c2, "Cross-venue divergence (Polymarket − Kalshi)", "Percentage points", ynum='0.0%')
yscale(c2, -0.40, 0.40, 0.10)
c2.x_axis.tickLblSkip = 30
c2.x_axis.tickMarkSkip = 30
c2.x_axis.number_format = 'mmm-yy'
ch.add_chart(c2, "A33")

# --- 3. Kalshi bid/ask band (liquidity) -------------------------------
c3 = LineChart()
kdates = Reference(wb["Kalshi"], min_col=13, min_row=KF, max_row=KL)
for col, colour in ((2, C_DEM), (3, C_KAL)):
    ref = Reference(wb["Kalshi"], min_col=col, min_row=KF - 1, max_row=KL)
    s = Series(ref, title_from_data=True); line(s, colour, 16000)
    c3.series.append(s)
c3.set_categories(kdates)
style(c3, "Kalshi Democratic contract — bid vs ask", "Price / implied probability")
yscale(c3, 0.30, 1.00, 0.10)
c3.x_axis.tickLblSkip = 45
c3.x_axis.tickMarkSkip = 45
c3.x_axis.number_format = 'mmm-yy'
ch.add_chart(c3, "A62")

# --- 4. Kalshi open interest ------------------------------------------
c4 = LineChart()
ref = Reference(wb["Kalshi"], min_col=12, min_row=KF - 1, max_row=KL)
s = Series(ref, title_from_data=True); line(s, "5B8C5A", 20000)
c4.series.append(s)
c4.set_categories(kdates)
style(c4, "Kalshi open interest — how much money is on the race", "Contracts", ynum='#,##0')
c4.x_axis.tickLblSkip = 45
c4.x_axis.tickMarkSkip = 45
c4.x_axis.number_format = 'mmm-yy'
ch.add_chart(c4, "A91")

# --- 5. Polymarket overround ------------------------------------------
c5 = LineChart()
pdates = Reference(wb["Polymarket"], min_col=11, min_row=PMF, max_row=PML)
ref = Reference(wb["Polymarket"], min_col=4, min_row=PMF - 1, max_row=PML)
s = Series(ref, title_from_data=True); line(s, "8E6FB3", 18000)
c5.series.append(s)
c5.set_categories(pdates)
style(c5, "Polymarket pricing efficiency — Dem + Rep price", "Sum of the two YES prices", ynum='0.0%')
yscale(c5, 0.90, 1.10, 0.05)
c5.x_axis.tickLblSkip = 30
c5.x_axis.tickMarkSkip = 30
c5.x_axis.number_format = 'mmm-yy'
ch.add_chart(c5, "A120")

# --- 6. Polymarket Dem vs Rep -----------------------------------------
c6 = LineChart()
for col, colour in ((2, C_DEM), (3, C_REP)):
    ref = Reference(wb["Polymarket"], min_col=col, min_row=PMF - 1, max_row=PML)
    s = Series(ref, title_from_data=True); line(s, colour, 22000)
    c6.series.append(s)
c6.set_categories(pdates)
style(c6, "Polymarket — Democratic vs Republican price", "Implied probability")
yscale(c6, 0.0, 1.0, 0.20)
c6.x_axis.tickLblSkip = 30
c6.x_axis.tickMarkSkip = 30
c6.x_axis.number_format = 'mmm-yy'
ch.add_chart(c6, "A149")

# --- 7. model vs market, same date axis -------------------------------
if F7.get("PM_TREND_FIRST"):
    TF, TL = F7["PM_TREND_FIRST"], F7["PM_TREND_LAST"]
    c13 = LineChart()
    tdates = Reference(wb["Forecast & Aggregators"], min_col=9, min_row=TF, max_row=TL)
    for col, colour, dash in ((2, "8E6FB3", False), (7, C_PM, False)):
        ref = Reference(wb["Forecast & Aggregators"], min_col=col, min_row=TF - 1, max_row=TL)
        s_ = Series(ref, title_from_data=True); line(s_, colour, 22000, dash)
        c13.series.append(s_)
    c13.set_categories(tdates)
    style(c13, "Model vs market — Brooks win probability", "Probability")
    yscale(c13, 0.30, 0.95, 0.10)
    c13.x_axis.tickLblSkip = 30
    c13.x_axis.tickMarkSkip = 30
    ch.add_chart(c13, "A178")
    NOTE_ROW = 207
else:
    NOTE_ROW = 178

r = NOTE_ROW
r = note(ch, r, "Chart 7 — the PollsMax model against Polymarket, matched day by day. The two answer "
                "the same question by different means, so a persistent gap is a claim that one of "
                "them is mispriced.", 16)
r = note(ch, r, "Chart 1 — the headline. The dashed grey line is even odds; both venues have held Brooks above it "
                "since late April 2026.", 16)
r = note(ch, r, "Chart 2 — a persistent gap is normal: different fees, capital costs and user bases. It is not "
                "tradeable unless the two ASK prices sum below 100%, which is the check on the Summary sheet.", 16)
r = note(ch, r, "Chart 3 — the gap between the two lines is the bid-ask spread. A narrowing band means the market "
                "is getting more confident and more liquid.", 16)
r = note(ch, r, "Chart 5 — a fair pair of prices sums to 100%. Below that, buying both sides locks in a profit; "
                "above it, the venue is charging a spread.", 16)

# =====================================================================
# SHEET: Distributions
# =====================================================================
ds = wb.create_sheet("Distributions")
ds.sheet_view.showGridLines = False
ds["A1"] = "Charts — Distributions & Polls"; ds["A1"].font = TITLE
ds["A2"] = ("What the market thinks the result will look like, and how that squares with the polling. "
            "Built %s." % ASOF)
ds["A2"].font = SUB
for col, w in {"A": 24, "B": 13, "C": 13, "D": 13, "E": 12, "F": 12, "G": 12, "H": 12}.items():
    ds.column_dimensions[col].width = w

# --- 7. Margin-of-victory distribution --------------------------------
c7 = BarChart(); c7.type = "col"; c7.gapWidth = 40
ref = Reference(wb["Margin of Victory"], min_col=6, min_row=MV["L0"] - 1, max_row=MV["LN"])
cats = Reference(wb["Margin of Victory"], min_col=1, min_row=MV["L0"], max_row=MV["LN"])
c7.add_data(ref, titles_from_data=True); c7.set_categories(cats)
c7.series[0].graphicalProperties.solidFill = C_DEM
style(c7, "Margin of victory — implied probability by bracket", "Normalised probability", ynum='0%')
c7.legend = None
ds.add_chart(c7, "A4")

# --- 8. PA Democratic seat count --------------------------------------
c8 = BarChart(); c8.type = "col"; c8.gapWidth = 40
ref = Reference(wb["PA Seat Count"], min_col=7, min_row=MV["K0"] - 1, max_row=MV["KN"])
cats = Reference(wb["PA Seat Count"], min_col=1, min_row=MV["K0"], max_row=MV["KN"])
c8.add_data(ref, titles_from_data=True); c8.set_categories(cats)
c8.series[0].graphicalProperties.solidFill = "5B8C5A"
style(c8, "PA Democratic House seats — implied probability", "Normalised probability", ynum='0%')
c8.legend = None
# Buckets run from 0.5% to 33.5% — a 65x spread, so the tail bars are slivers.
# Print the values the way charts 9 and 10 already do.
c8.dLbls = DataLabelList(); c8.dLbls.showVal = True
ds.add_chart(c8, "A33")

# --- helper table: margin comparison ----------------------------------
r = 178
r = section(ds, r, "MARKETS vs POLLS — margin in percentage points", 8)
HR = r
for i, (lbl, f) in enumerate([
        ("Weighted poll margin", "=Polls!B{0}*100".format(P["WM"])),
        ("Adjusted poll margin", "=Polls!B{0}*100".format(P["ADJ"])),
        ("Market-implied margin", "='Margin of Victory'!B{0}".format(MV["EM"]))]):
    ds.cell(HR + i, 1, lbl).font = BOLD
    ds.cell(HR + i, 1).border = BOX
    c = ds.cell(HR + i, 2, f); c.font = GREEN; c.number_format = '0.00'; c.border = BOX
ds.cell(HR, 3, "Positive favours Brooks (D). Poll margins are scaled from fractions to points "
               "so all three bars share one axis.").font = NOTE

c9 = BarChart(); c9.type = "col"; c9.gapWidth = 60
ref = Reference(ds, min_col=2, min_row=HR, max_row=HR + 2)
cats = Reference(ds, min_col=1, min_row=HR, max_row=HR + 2)
c9.add_data(ref, titles_from_data=False); c9.set_categories(cats)
c9.series[0].graphicalProperties.solidFill = C_DEM
style(c9, "Markets vs polls — implied margin (D−R)", "Percentage points", ynum='0.0')
c9.legend = None
c9.dLbls = DataLabelList(); c9.dLbls.showVal = True
ds.add_chart(c9, "A120")

# --- helper table: primary calibration --------------------------------
r = HR + 4
r = section(ds, r, "DEMOCRATIC PRIMARY — what the polls said vs what happened", 8)
CR = r
QS, QE, ACT = P["QS"], P["QE"], P["ACT"]
for i, row in enumerate(range(QS, QE + 1)):
    ds.cell(CR + i, 1, "=Polls!A{0}&\" (\"&TEXT(Polls!E{0},\"d mmm\")&\")\"".format(row)).font = GREEN
    ds.cell(CR + i, 1).border = BOX
    c = ds.cell(CR + i, 2, "=Polls!H{0}".format(row)); c.font = GREEN; c.number_format = PCT; c.border = BOX
n = QE - QS + 1
ds.cell(CR + n, 1, "ACTUAL RESULT").font = BOLD; ds.cell(CR + n, 1).border = BOX
c = ds.cell(CR + n, 2, "=Polls!H{0}".format(ACT)); c.font = GREEN; c.number_format = PCT
c.border = BOX; c.fill = PatternFill("solid", fgColor="E2EFDA")

c10 = BarChart(); c10.type = "col"; c10.gapWidth = 50
ref = Reference(ds, min_col=2, min_row=CR, max_row=CR + n)
cats = Reference(ds, min_col=1, min_row=CR, max_row=CR + n)
c10.add_data(ref, titles_from_data=False); c10.set_categories(cats)
c10.series[0].graphicalProperties.solidFill = C_DEM
style(c10, "Brooks in primary polling vs the actual result", "Share of the primary vote", ynum='0%')
c10.legend = None
c10.dLbls = DataLabelList(); c10.dLbls.showVal = True
ds.add_chart(c10, "A149")

# --- 11. Kalshi margin threshold curve --------------------------------
c11 = BarChart(); c11.type = "col"; c11.gapWidth = 40
ref = Reference(wb["Margin of Victory"], min_col=7, min_row=K3["K0"] - 1, max_row=K3["D03"])
cats = Reference(wb["Margin of Victory"], min_col=6, min_row=K3["K0"], max_row=K3["D03"])
c11.add_data(ref, titles_from_data=True); c11.set_categories(cats)
c11.series[0].graphicalProperties.solidFill = C_KAL
style(c11, "Kalshi margin — probability by bucket", "Derived probability", ynum='0%')
c11.legend = None
ds.add_chart(c11, "A62")

# --- 12. Turnout: nested thresholds, so a survival curve reads better --
c12 = LineChart()
ref = Reference(wb["Voter Turnout"], min_col=5, min_row=K3["T0"] + 1, max_row=K3["TN"])
cats = Reference(wb["Voter Turnout"], min_col=1, min_row=K3["T0"] + 1, max_row=K3["TN"])
sr = Series(ref, title_from_data=False); line(sr, "5B8C5A", 22000)
c12.series.append(sr)
c12.set_categories(cats)
style(c12, "Voter turnout — P(turnout at or above each threshold)", "Probability", ynum='0%')
yscale(c12, 0.0, 0.80, 0.20)
c12.legend = None
ds.add_chart(c12, "A91")

r = CR + n + 2
r = note(ds, r, "Every primary poll understated Brooks, the last of them by 15 points, because 31-53% of "
                "respondents were undecided. Worth remembering when reading the single general-election poll.", 16)
r = note(ds, r, "Chart 11 differences Kalshi's nested thresholds into buckets; the two 0-3 buckets come from "
                "the winner market, since Kalshi quotes no 0-3 rung. Chart 12 is deliberately a curve, not bars — "
                "those thresholds are nested, so bars would imply an exclusivity the market does not have.", 16)
r = note(ds, r, "The margin chart mixes sources on purpose: the poll bars come from one Democratic-sponsored "
                "survey, the market bar from Polymarket's bracket ladder. Treat the gap as a question, not a signal.", 16)

wb.save("_stage4.xlsx")
print("stage4 ok — Charts + Distributions added")
