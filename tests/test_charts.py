"""Chart rendering: the properties a reader actually sees.

check.py validates that charts point at the right DATA. Nothing validated how
they LOOK, and three separate visual defects shipped as a result — black-looking
gridlines, category labels printed across the plot, and a literal "None" on all
26 axes. These are the regression guards for that.

All of this is read from the SAVED workbook, not from build5.py's intentions:
two of the three defects only appeared after build4.py's reload-and-resave.
"""
import re
import zipfile
import collections
import xml.etree.ElementTree as ET

import support

C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
SD = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
NS = {"c": C, "a": A}
WB = "PA-07_House_Election_Tracker.xlsx"

AXIS_COLOUR = "44546A"
GRID_COLOUR = "EDEFF3"
ROW_PT = 15.0          # sheetFormatPr defaultRowHeight
EMU_PER_CM = 360000.0


def _charts():
    z = zipfile.ZipFile(support.project(WB))
    names = sorted((n for n in z.namelist() if re.match(r"xl/charts/chart\d+\.xml", n)),
                   key=lambda s: int(re.search(r"(\d+)", s.split("/")[-1]).group(1)))
    return z, names


def _direct_line(ax):
    """The axis's OWN line. majorGridlines also holds an spPr and precedes it in
    the schema, so anything less specific than a direct-child scan finds the
    gridline colour and reports a false pass."""
    for e in list(ax):
        if e.tag == "{%s}spPr" % C:
            sf = e.find("a:ln/a:solidFill/a:srgbClr", NS)
            return sf.get("val") if sf is not None else None
    return None


def test_no_literal_text_leaks_into_axis_labels():
    """openpyxl defaults Paragraph(r=...) to one EMPTY run, and build4.py's
    reload-and-resave turns that empty <a:t> into the string "None" — on every
    axis of every chart. Passing r=[] keeps txPr a pure formatting scaffold."""
    z, names = _charts()
    offenders = []
    for n in names:
        root = ET.fromstring(z.read(n))
        for axtag in ("catAx", "valAx"):
            for ax in root.findall(".//c:%s" % axtag, NS):
                tx = ax.find("c:txPr", NS)
                if tx is None:
                    continue
                for t in tx.iter("{%s}t" % A):
                    if (t.text or "").strip():
                        offenders.append("%s %s: %r" % (n.split("/")[-1], axtag, t.text))
    assert not offenders, "axis formatting must carry no literal text: %s" % offenders[:6]


def test_category_labels_are_pinned_below_the_plot():
    """The default, "nextTo", draws labels AT the axis line — which on a chart
    crossing zero runs through the middle of the data."""
    z, names = _charts()
    for n in names:
        root = ET.fromstring(z.read(n))
        for axtag in ("catAx", "valAx"):
            for ax in root.findall(".//c:%s" % axtag, NS):
                pos = ax.find("c:tickLblPos", NS)
                assert pos is not None and pos.get("val") == "low", \
                    "%s %s tickLblPos=%s" % (n.split("/")[-1], axtag,
                                             pos.get("val") if pos is not None else None)


def test_every_chart_has_an_explicit_plot_area_layout():
    """Without a manualLayout Excel auto-fits, and rotated labels or the y-axis
    title are free to overlap the plotted data."""
    z, names = _charts()
    for n in names:
        root = ET.fromstring(z.read(n))
        ml = root.find(".//c:plotArea/c:layout/c:manualLayout", NS)
        assert ml is not None, "%s has no manual plot-area layout" % n.split("/")[-1]
        g = {e.tag.split("}")[1]: float(e.get("val")) for e in ml
             if e.tag.endswith(("}x", "}y", "}w", "}h"))}
        assert g["x"] + g["w"] <= 1.0 + 1e-9, "%s plot overflows horizontally" % n
        assert g["y"] + g["h"] <= 1.0 + 1e-9, "%s plot overflows vertically" % n


def test_gridlines_are_light_and_only_on_the_value_axis():
    z, names = _charts()
    for n in names:
        root = ET.fromstring(z.read(n))
        for val in root.findall(".//c:valAx", NS):
            gl = val.find("c:majorGridlines", NS)
            assert gl is not None, "%s value axis lost its gridlines" % n
            sf = gl.find("c:spPr/a:ln/a:solidFill/a:srgbClr", NS)
            assert sf is not None and sf.get("val") == GRID_COLOUR, \
                "%s gridline colour is %s, not %s — an unstyled gridline renders dark" % (
                    n.split("/")[-1], sf.get("val") if sf is not None else None, GRID_COLOUR)
        for cat in root.findall(".//c:catAx", NS):
            assert cat.find("c:majorGridlines", NS) is None, \
                "%s has vertical gridlines, which just add noise on a date axis" % n


def test_axis_lines_are_dark_enough_to_frame_the_plot():
    z, names = _charts()
    for n in names:
        root = ET.fromstring(z.read(n))
        for axtag in ("catAx", "valAx"):
            for ax in root.findall(".//c:%s" % axtag, NS):
                assert _direct_line(ax) == AXIS_COLOUR, \
                    "%s %s axis line is %s" % (n.split("/")[-1], axtag, _direct_line(ax))


def test_charts_do_not_overlap_each_other():
    """Chart height and anchor spacing are set independently, so raising one
    without the other silently squeezes the gap. It once fell to 1.25 mm."""
    z, _ = _charts()
    worst = []
    for dn in (x for x in z.namelist() if re.match(r"xl/drawings/drawing\d+\.xml", x)):
        root = ET.fromstring(z.read(dn))
        bycol = collections.defaultdict(list)
        for tag in ("twoCellAnchor", "oneCellAnchor"):
            for anc in root.findall("{%s}%s" % (SD, tag)):
                f = anc.find("{%s}from" % SD)
                ext = anc.find("{%s}ext" % SD)
                if f is None or ext is None:
                    continue
                bycol[int(f.find("{%s}col" % SD).text)].append(
                    (int(f.find("{%s}row" % SD).text), int(ext.get("cy"))))
        for col, items in bycol.items():
            items.sort()
            for (r1, cy1), (r2, _cy2) in zip(items, items[1:]):
                gap_cm = (r2 - r1) * ROW_PT / 72.0 * 2.54
                clearance = gap_cm - cy1 / EMU_PER_CM
                worst.append((clearance, dn.split("/")[-1], col, r1, r2))
    assert worst, "no anchored charts found"
    worst.sort()
    c, dn, col, r1, r2 = worst[0]
    assert c >= 0.5, ("charts nearly touch: %.2f cm clearance in %s column %d, rows %d->%d. "
                      "Widen the anchor gap or reduce chart height." % (c, dn, col, r1, r2))


def test_tick_labels_carry_an_explicit_size():
    """Rotation was dropped once the charts went full-width — at 25cm a date axis
    fits ~11 flat labels comfortably, and the rotated version rendered as
    oversized unrotated text. What still matters is that the size is pinned:
    left to its own devices the renderer scales tick text with the chart, and
    the enlarged charts came back with date labels dwarfing the plot."""
    z, names = _charts()
    for n in names:
        root = ET.fromstring(z.read(n))
        for axtag in ("catAx", "valAx"):
            for ax in root.findall(".//c:%s" % axtag, NS):
                tx = ax.find("c:txPr", NS)
                assert tx is not None, "%s %s has no text properties" % (n, axtag)
                pr = tx.find("a:p/a:pPr/a:defRPr", NS)
                assert pr is not None and pr.get("sz"), \
                    "%s %s tick labels have no pinned size" % (n.split("/")[-1], axtag)
                assert 700 <= int(pr.get("sz")) <= 1200, \
                    "%s %s tick size %s is outside a legible range" % (
                        n.split("/")[-1], axtag, pr.get("sz"))


def test_value_axes_are_scaled_to_the_data_not_to_zero():
    """A probability series living between 40% and 90% plotted against a 0-100%
    axis wastes half the frame and flattens every move in it."""
    z, names = _charts()
    scaled = 0
    for n in names:
        root = ET.fromstring(z.read(n))
        for val in root.findall(".//c:valAx", NS):
            sc = val.find("c:scaling", NS)
            if sc is not None and (sc.find("c:min", NS) is not None
                                   or sc.find("c:max", NS) is not None):
                scaled += 1
    assert scaled >= 6, "expected explicit axis bounds on the probability charts, got %d" % scaled
