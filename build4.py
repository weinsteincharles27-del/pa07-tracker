import json, datetime
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment

D2 = json.load(open("data2.json"))
ASOF = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
F = "Arial"
BOLD = Font(name=F, size=10, bold=True)
TITLE = Font(name=F, size=16, bold=True, color="1F3864")
SUB = Font(name=F, size=9, italic=True, color="595959")
SECT = Font(name=F, size=11, bold=True, color="FFFFFF")
NOTE = Font(name=F, size=10)
MONO = Font(name="Courier New", size=9)
SECTF = PatternFill("solid", fgColor="1F3864")
YEL = PatternFill("solid", fgColor="FFFF00")

wb = load_workbook("_stage4.xlsx")
ns = wb.create_sheet("Notes & Sources")
ns["A1"] = "Notes, Sources & Refresh"; ns["A1"].font = TITLE
ns["A2"] = ("Everything behind the numbers: where each cell came from, what is assumed, and how to pull it again. "
            "Built %s." % ASOF)
ns["A2"].font = SUB
ns.column_dimensions["A"].width = 31
ns.column_dimensions["B"].width = 118

def sect(row, text):
    ns.cell(row, 1, text).font = SECT
    for c in (1, 2): ns.cell(row, c).fill = SECTF
    return row + 1

def line(row, a, b, fb=NOTE, hl=False):
    ns.cell(row, 1, a).font = BOLD
    ns.cell(row, 1).alignment = Alignment(vertical="top")
    c = ns.cell(row, 2, b); c.font = fb
    c.alignment = Alignment(wrap_text=True, vertical="top")
    if hl: c.fill = YEL
    ns.row_dimensions[row].height = max(15, 13 * (1 + len(b) // 106))
    return row + 1

r = 4
r = sect(r, "COLOUR CONVENTION")
for a, b in [
    ("Blue text", "A hardcoded value - pulled from an API, read out of house.csv, or typed in from a cited source. These are the only cells you overwrite when refreshing."),
    ("Black text", "A formula. Do not overwrite; it recalculates from the blue and green cells."),
    ("Green text", "A link to another sheet in this workbook."),
    ("Yellow fill", "Either a key output worth reading first, or an assumption you are meant to change."),
]:
    r = line(r, a, b)
r += 1

r = sect(r, "SHEETS")
for a, b in [
    ("Summary", "Dashboard. Consensus probability, market-implied margin, race facts, live snapshot, every subject tracked, cross-venue arbitrage check, momentum, and markets-vs-polls."),
    ("Polymarket", "Winner market: metadata, live order book, and 233 days of daily prices for the Democratic and Republican YES contracts."),
    ("Kalshi", "Winner market: metadata, live order book with five levels of depth, and 410 days of daily candlesticks."),
    ("Margin of Victory", "Polymarket's ten-bracket ladder on the winning margin, with the implied distribution, expected margin, and a cross-check against the winner market."),
    ("PA Seat Count", "Kalshi's ladder on how many of Pennsylvania's 17 House seats Democrats win. PA-07 is one of them, so it is a state-level read on the same question."),
    ("Polls", "General-election and Democratic-primary polling from house.csv, a recency-weighted average, the district and incumbent profile from GovTrack, and supplementary approval numbers."),
    ("Venue Comparison", "The two venues' daily Democratic probability joined on date, with divergence and an indicative historical pair-cost column."),
]:
    r = line(r, a, b)
r += 1

r = sect(r, "SUBJECT INVENTORY - what each venue actually lists for PA-07")
for a, b, hl in [
    ("Winner (party)", "Polymarket 'PA-07 House Election Winner' (event 106187) and Kalshi HOUSEPA7-26. Both venues, both liquid. This is the workbook's spine.", False),
    ("Margin of victory", "BOTH venues. Polymarket 'PA-07 House Election Margin of Victory' (event 834502), ten exclusive brackets. Kalshi KXMIDTERMMOV-PA07D and -PA07R, eight threshold rungs ('Democrats, 3+ pts'). CORRECTION: an earlier version of this workbook said Kalshi had no PA-07 margin market. That was wrong - the search behind it matched series tickers, and Kalshi files these under a national series (KXMIDTERMMOV) with per-district EVENT tickers, so a series-level search cannot find them.", True),
    ("Voter turnout", "Kalshi KXMIDTERMVOTETURN-PA07, five thresholds from 310K to 370K. Kalshi-only; Polymarket lists no turnout market for this district. PA-07 was decided by about a point in 2024, so turnout is a plausible decider rather than trivia.", True),
    ("Threshold vs bracket", "The two venues sell different instruments for the same question. Polymarket sells mutually exclusive brackets that sum to 100%. Kalshi sells nested thresholds, where each rung is P(value >= strike) and probabilities must FALL as the strike rises. Differencing adjacent Kalshi rungs recovers buckets; collect3.py checks the monotonicity that makes that valid.", False),
    ("Democratic nominee", "Kalshi KXPA07D-26 and Polymarket 'PA-07 Democratic Primary Winner' (event 287013). Settled on 19 May 2026; the Kalshi event returns no tradeable markets now. Kept as polling calibration on the Polls sheet, not tracked live.", False),
    ("2024 PA-07 race", "Kalshi HOUSEPA7-24 exists as an event but returns no markets. Not tracked.", False),
    ("Closest House race", "Kalshi KXCLOSESTHOUSE-27JAN03 lists 34 districts for 2026. PA-01 is included; PA-07 is NOT, so there is nothing to track here.", False),
    ("PA Democratic seat count", "Kalshi KXHOUSEWINSTATE-PAD, eight brackets. Tracked on its own sheet as state-level context.", False),
    ("Placeholder outcomes", "The Polymarket winner event also carries outcomes A-E and 'Other', and the margin event carries 'Person A', 'Person B' and 'Other'. All are inactive with zero volume and are excluded.", False),
]:
    r = line(r, a, b, hl=hl)
r += 1

r = sect(r, "MARKET IDENTIFIERS")
for a, b in [
    ("Polymarket winner", "event 106187, slug pa-07-house-election-winner; markets will-the-democratic-party-win-the-pa-07-house-seat / will-the-republican-party-win-the-pa-07-house-seat"),
    ("Polymarket margin", "event 834502, slug pa-07-house-margin-of-victory-2026"),
    ("Kalshi winner", "series HOUSEPA7, event HOUSEPA7-26, markets HOUSEPA7-26-D (Bob Brooks) and HOUSEPA7-26-R (Ryan Mackenzie)"),
    ("Kalshi seat count", "series KXHOUSEWINSTATE, event KXHOUSEWINSTATE-PAD, markets -B7, -E7 through -E12, -A12"),
    ("Kalshi margin", "series KXMIDTERMMOV, events KXMIDTERMMOV-PA07D (rungs P3/P6/P9/P12/P15) and -PA07R (P3/P6/P9)"),
    ("Kalshi turnout", "series KXMIDTERMVOTETURN, event KXMIDTERMVOTETURN-PA07, markets -310000/-320000/-340000/-360000/-370000"),
    ("Kalshi close time", "HOUSEPA7-26 closes 2027-11-03, a year after the election - a settlement backstop, not the election date. Days-to-election counts to 2026-11-03."),
]:
    r = line(r, a, b)
r += 1

r = sect(r, "API CALLS BEHIND THE BLUE CELLS")
for a, b, mono in [
    ("Polymarket metadata", "GET https://gamma-api.polymarket.com/events/<event_id>", True),
    ("Polymarket book", "GET https://clob.polymarket.com/book?token_id=<token>", True),
    ("Polymarket history", "GET https://clob.polymarket.com/prices-history?market=<token>&interval=max&fidelity=1440", True),
    ("  fidelity", "In minutes; 1440 gives one point per day. Returns {history: [{t: unix_seconds, p: price}]}.", False),
    ("Dem winner token", "37713776886536763857380242322222367371582682723176215910322979366716585040762", True),
    ("Rep winner token", "56412855186822728853119072474894085602768054645914780515455268260878947887549", True),
    ("Kalshi base", "https://api.elections.kalshi.com", True),
    ("Kalshi auth", "Every request signed with RSA-PSS / SHA-256 over (timestamp_ms + method + path), sent as KALSHI-ACCESS-KEY, KALSHI-ACCESS-SIGNATURE and KALSHI-ACCESS-TIMESTAMP headers. Salt length = digest length.", False),
    ("Kalshi market", "GET /trade-api/v2/markets/<ticker>", True),
    ("Kalshi book", "GET /trade-api/v2/markets/<ticker>/orderbook?depth=10", True),
    ("Kalshi history", "GET /trade-api/v2/series/<series>/markets/<ticker>/candlesticks?start_ts=&end_ts=&period_interval=1440", True),
    ("Kalshi discovery", "GET /trade-api/v2/series  then filter locally - there is no keyword search endpoint, and /trade-api/v2/search/series returns 404.", False),
    ("  discovery caveat", "Filtering SERIES by ticker or title misses any market filed under a national series with per-district events - which is how margin and turnout are filed. Enumerate /trade-api/v2/events per candidate series and match on the EVENT ticker. Beware word-boundary regexes too: PA-?0?7\\b does not match 'PA07D', which is exactly how the margin market was missed the first time.", False),
]:
    r = line(r, a, b, MONO if mono else NOTE)
r += 1

r = sect(r, "POLLING SOURCE - house.csv")
for a, b in [
    ("File", "/Users/charlieweinstein/Downloads/house.csv - the NYT / 538 house-poll file, 5,041 rows covering every 2026 House race."),
    ("Filter", "state = PA and seat_number = 7, which yields 26 rows across 5 distinct poll_ids: 1 general-election poll and 4 Democratic-primary polls."),
    ("Shape", "The file is one row per candidate per question, so rows were pivoted by poll_id into one row per poll."),
    ("General poll", "GBAO for House Majority PAC, 29 June - 2 July 2026, likely voters, Brooks 47 - Mackenzie 43. Marked partisan = DEM in the file."),
    ("Primary polls", "Change Research (Dec 2025), GBAO/CPC PAC (Feb-Mar and Apr 2026), Tavern Research (May 2026). All four understated Brooks, who took ~41.4%; each poll carried 31-53% undecided."),
    ("Empty fields", "numeric_grade, pollscore, transparency_score and MoE are empty for every PA-07 poll in the file, so no pollster-quality weighting is applied. sample_size is also empty for the general poll - see the assumption below."),
    ("Coverage caveat", "One public general-election poll exists for this race, and it is Democratic-sponsored. The polling average is a single data point wearing a weighting scheme; the market sheets are far better populated."),
]:
    r = line(r, a, b)
ns.cell(r - 1, 2).fill = YEL
r += 1

r = sect(r, "GOVTRACK")
for a, b in [
    ("Page", "govtrack.us/congress/members/PA/7 and the member profile at govtrack.us/congress/members/ryan_mackenzie/457017"),
    ("Used for", "The district and incumbent profile on the Polls sheet: tenure, age, caucus, committee assignments, sponsorship mix and the missed-votes record."),
    ("Missed votes", "13 of 645 roll calls between Jan 2025 and Jul 2026 (2.0%), which GovTrack calls on par with the 2.0% median among sitting representatives."),
    ("Access note", "The page rejects a plain fetch with HTTP 403; it was retrieved with a normal browser user-agent."),
    ("Redistricting caveat", "GovTrack warns that some states are changing districts for 2026 and that its map reflects the 2024 lines. Confirm PA-07's boundaries before treating district-level history as like-for-like."),
]:
    r = line(r, a, b)
ns.cell(r - 1, 2).fill = YEL
r += 1

r = sect(r, "METHOD NOTES")
for a, b in [
    ("Price as probability", "A contract paying $1 if the outcome happens trades at its implied probability, so $0.755 reads as 75.5%. Every price column is percent-formatted for that reason."),
    ("Mid price", "(best bid + best ask) / 2. Used rather than last trade, which on thin markets can be stale by days."),
    ("Kalshi YES ask", "Kalshi's REST market object returned null for yes_bid, yes_ask, volume and open_interest on these markets, so top-of-book comes from the orderbook endpoint. A YES ask is derived as 1 minus the best NO bid, since buying YES at p and selling NO at 1-p are the same trade."),
    ("Normalised probability", "Each outcome's mid divided by the sum of mids across the group, which strips out the overround so the set sums to 100%."),
    ("Overround / vig", "Sum of mids minus 1. On the margin ladder this runs far above 100% because several thin brackets are quoted with very wide spreads, which inflates their mid - read the normalised column, not the raw one."),
    ("Expected margin", "Sum of (normalised probability x signed bracket midpoint) across the ladder, in percentage points, positive for a Democratic win."),
    ("Kalshi volume column", "The winner history sums Democratic and Republican contract volume; open interest takes the larger of the two legs rather than the sum, since they are two sides of one race."),
    ("Date alignment", "All dates are UTC days. Venue Comparison joins with INDEX/MATCH on the date value, so the join survives a refresh that changes row counts."),
    ("Missing cells", "Some early Kalshi days have no closing bid or ask. Those cells are left blank and every dependent formula is guarded, so gaps propagate as blanks rather than as zeros or errors."),
]:
    r = line(r, a, b)
r += 1

r = sect(r, "ASSUMPTIONS - values not taken from any source")
for a, b in [
    ("Margin bracket midpoints", "Margin of Victory, column B. Closed brackets use their true centre (0-3% -> 1.5). The open-ended ones are judgement calls: 'Democrat 18%+' = +20.0, 'Republican 6%+' = -8.0. They drive the expected-margin figure."),
    ("Seat bracket midpoints", "PA Seat Count, column B. Exact brackets use their own number; 'Below 7' = 6 and 'Above 12' = 13."),
    ("Seat ladder mid fallback", "'Below 7' and 'Above 12' have an ask but no resting bid, so their mid falls back to half the ask. Both quote at 1-2c, so this barely moves the expected-seats figure."),
    ("Current PA Democratic seats", "8, entered by hand on the PA Seat Count sheet as the baseline for the net-gain line. Verify against the current delegation before relying on it."),
    ("General poll sample size", "550 likely voters, used because the sample_size field is empty in house.csv; it is the figure Pollsmax reports for the same GBAO survey. Sample size only affects weighting, and with one poll in the log it changes nothing."),
    ("Poll recency half-life", "45 days. A poll's weight halves every 45 days - a reasonable default for a race still ten weeks out, not a fitted value."),
    ("Partisan house-effect haircut", "3.0 pp, subtracted from the weighted margin in proportion to net partisan sponsorship. This matters here: the only general-election poll is Democratic-sponsored, so the adjusted margin is the more conservative read."),
    ("Consensus weighting", "Equal weight between the two venues on the winner market. Polymarket carries materially more volume, so a liquidity weighting would tilt toward it."),
]:
    r = line(r, a, b, hl=True)
r += 1

r = sect(r, "OUTSIDE SOURCES ADDED 30 AUG 2026")
for a, b_, hl in [
    ("PollsMax", "pollsmax.com/2026-us-house/pennsylvania-7/ — swept with Playwright, since the content is client-side rendered and a plain fetch returns almost nothing. Supplies a statistical forecast (win probability, projected vote share, 231 daily trend points with simulation bands) and a documented methodology. Its polling average rests on the SAME single GBAO poll already in house.csv, so it adds no new polling — its value is the model, not the polls.", False),
    ("  PollsMax caveats", "Their page labels the GBAO poll '(B)' in embedded JSON but '(D)' elsewhere, and their own methodology admits only (D)/(R) as partisan tags. Their forecast page also claims a 'last updated' timestamp 11 days newer than the last plotted data point. Both are logged in sources/pollsmax.json under extraction_problems.", False),
    ("City & State PA", "cityandstatepa.com/prediction-markets/races/pa-07-house — a third-party odds tracker. Recorded as a DATA-QUALITY observation, never as an input. It resells a Kalshi feed via an aggregator (PredictionEdge) yet disagrees with Kalshi's own API by roughly 9 points, and shows two different Brooks probabilities on the same page (72% and 78%). It carries no PA-07 polling at all, never names the Republican candidate, and publishes no timestamps.", True),
    ("  sponsorship", "That entire section of the site is labelled SPONSORED CONTENT, its publisher states editorial staff were not involved, and its calls to action are affiliate trading links. Nothing from it feeds any calculation here.", True),
    ("FEC / OpenFEC", "api.open.fec.gov — campaign finance for the 2026 cycle, NOT polling. Candidate receipts, disbursements, cash on hand, and independent expenditures. API key lives in fec_key.txt (mode 600) and never appears in any output file.", False),
    ("  FEC staleness", "Periodic totals come from the July Quarterly, covering through 30 JUNE 2026 — roughly two months stale on arrival, and widening until the October Quarterly (~15 Oct, covering through 30 Sep). Independent expenditures report continuously and are fresher than the candidate totals, so the two halves of the Campaign Finance sheet are not as-of the same date.", True),
    ("  FEC caveat", "Most of the ~$2.76M in outside spending logged against this race was spent 6-18 May 2026 inside the contested Democratic PRIMARY, not the Brooks-vs-Mackenzie general. And $1.78M of Mackenzie's receipts is a transfer from a wound-down joint fundraising committee, not fresh donor money. Read the totals with both facts in hand.", True),
]:
    r = line(r, a, b_, hl=hl)
r += 1

r = sect(r, "OTHER SOURCES")
for a, b in [
    ("Race ratings", "Cook Political Report (race 483941), Sabato's Crystal Ball and Inside Elections - all Toss-up as of February 2026."),
    ("Aggregators", "pollsmax.com/2026-us-house/pennsylvania-7/ and pollingsource.com/house/PA-07"),
    ("Primary result", "Ballotpedia's 19 May 2026 report: Brooks ~41.4% at about 74% counted, ahead of Crosswell, McClure and Obando-Derstine."),
    ("Supplementary numbers", "House Majority Forward figures reported by PoliticsPA without field dates, sample size or MoE, and predating the May primary. Not in house.csv; logged as supplementary only."),
]:
    r = line(r, a, b)
r += 1

r = sect(r, "REFRESHING")
for a, b in [
    ("What to overwrite", "Only blue cells. On the market sheets that means the order-book blocks and the newest rows of each history table; append new dates at the bottom and copy the formula columns down."),
    ("Adding a poll", "Type into the next blank blue row of the general-election log on the Polls sheet. Columns L-O are already formulated through the end of the block."),
    ("Extending formulas", "Venue Comparison covers the Polymarket date range. If you append rows to the market sheets, extend that sheet's summary ranges and its MATCH ranges to match."),
    ("Recalculation", "This file was written by openpyxl, which stores formulas without cached results, so it is flagged to recalculate on open. Excel, LibreOffice and Numbers will compute every cell the moment you open it."),
    ("Credential note", "The Kalshi RSA private key used to pull this data was shared in plaintext chat. Rotate it in your Kalshi account settings and keep the replacement in a key file or environment variable, never in a document."),
]:
    r = line(r, a, b)
ns.cell(r - 1, 2).fill = YEL

order = ["Summary", "Charts", "Distributions", "Polymarket", "Kalshi",
         "Margin of Victory", "Voter Turnout", "PA Seat Count", "Polls",
         "Forecast & Aggregators", "Campaign Finance", "Venue Comparison",
         "Notes & Sources"]
order = [n for n in order if n in wb.sheetnames]
wb._sheets = [wb[n] for n in order]
wb.active = 0
for s in wb.worksheets:
    s.sheet_view.showGridLines = False
wb.calculation.fullCalcOnLoad = True

wb.save("PA-07_House_Election_Tracker.xlsx")
print("order:", [s.title for s in wb.worksheets])
