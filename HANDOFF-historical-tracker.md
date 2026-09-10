# Handoff — Historical PA-07 Tracker (new workbook)

**Goal:** a second workbook, `PA-07_Historical.xlsx`, carrying prediction-market data for
*previous* PA-07 elections alongside the *actual* certified results, so market forecasts can be
scored against what happened.

**Sibling project:** `~/pa07-tracker/` builds the live 2026 tracker. Read
`HANDOFF-campaign-finance.md` first — its §3 ("Migrating data correctly") is the rulebook, and
every convention there applies here unchanged. This document covers only what is *different*.

**Written:** 8 Sep 2026. Everything in §1 was verified against the live APIs on that date.

---

## 1. What actually exists — verified, not assumed

Do not plan around data that isn't there. I checked each of these directly:

| Source | Status | Detail |
|---|---|---|
| **Polymarket 2024 PA-07** | ✅ exists, tiny | `pa-07-election-wild-d-vs-mackenzie-r` (event 14095) |
| **Polymarket 2024 price history** | ⚠️ **4 daily points** | 2024-11-05 → 2024-11-08 only |
| **Kalshi 2024 PA-07** | ❌ **unavailable** | Event `HOUSEPA7-24` exists; returns **zero markets** under every status filter, and candlesticks 404 on all guessed tickers |
| **Kalshi 2026 primary** | ❌ unavailable | `KXPA07D-26` — same, zero markets |
| **FEC vote totals** | ❌ **not a results source** | `/v1/elections/` returns candidate names with `total_votes: null` for both 2024 and 2022 |
| **Polymarket 2022 PA-07** | ❓ unverified | A `2022-us-house-elections-…` slug appeared in search but the lookup failed; confirm scope before relying on it |

### The headline constraint

**There is almost no historical prediction-market time series for this district.** The 2024
Polymarket market opened 4 Nov 2024 — the day before the election — traded **$512 total**, and
yields four daily points. Kalshi's 2024 equivalent is gone from the API entirely.

So the workbook cannot be "the 2026 tracker, but for 2024". Reframe it as a **resolution and
calibration record**: what the market said at the moments it was quoted, versus what happened.
That is a genuinely useful artefact, but it is a much smaller one, and the next session should
tell the user that before building.

### The one genuinely interesting number found

Polymarket priced **Wild at 68.5%** on the morning of 5 Nov 2024. She **lost** to Mackenzie by
about one point. The series then collapses to 0.1495 by 8 Nov as results came in.

A market that was ~69% confident and wrong, on $512 of volume, is a legitimate calibration data
point — and it is directly relevant to how much weight the live tracker's current ~78% deserves.
It is arguably the single most valuable thing in this whole workbook. Treat it as one
observation, not a pattern.

---

## 2. The trap that will silently ruin this: PA-07 is not one place

**Read this before assembling any results table.**

Pennsylvania's district lines were redrawn by the state Supreme Court for 2018, and again for
2022. "PA-07" refers to fundamentally different geography across those eras:

- **Through 2016** — suburban Philadelphia, centred on Delaware County. The notoriously
  gerrymandered "Goofy Kicking Donald Duck" district. Held by Pat Meehan (R).
- **2018 onward** — the Lehigh Valley: Allentown, Bethlehem, Easton. Susan Wild (D).
- **2022 redraw** — still Lehigh Valley, boundaries adjusted.

Charting "PA-07 Democratic vote share, 2012–2024" as a single series would produce a clean,
plausible, **meaningless** line — a swing that is really a change of subject. This is the exact
class of silent-wrong-number the sibling project spent weeks eliminating, just at the level of
meaning rather than arithmetic.

**Requirement:** every results row carries a `district_era` field (`pre-2018`, `2018-2020`,
`2022-onward`), the workbook never plots across an era boundary without a visible break, and
the era change is stated on the sheet — not only in the notes. GovTrack itself warns about this;
see the redistricting caveat already on the live tracker's Polls sheet.

A second, smaller version of the same trap: **2018 and 2022 were the same lines but a different
electorate** (presidential vs midterm turnout). Note it; don't over-engineer for it.

---

## 3. Where the results must come from

Since FEC does not carry vote totals, results need a different source. In rough order of
preference:

1. **MIT Election Data & Science Lab** (Harvard Dataverse) — `U.S. House 1976–2022`, a clean
   authoritative CSV with candidate, party, votes, totalvotes per district-year. Best option
   for everything through 2022. **Does not cover 2024** — that has to come from elsewhere.
2. **PA Department of State** — official certified returns, the authority for any year. Manual
   or scraped.
3. **Ballotpedia / Wikipedia** — convenient, generally accurate, but secondary. Fine for
   cross-checking, not as the sole source for a certified number.

Whatever is chosen, record `source`, `retrieved_utc`, and whether the figure is **certified**
or a **reported/AP** count, per row. The live tracker's 2024 turnout figure was wrong by ~52,000
votes (351,000 entered by hand vs 403,314 actual) precisely because a number arrived without a
citation attached and nobody could check it.

Known-good anchors to validate any extraction against:

- **2024:** Mackenzie (R) 50.5%, Wild (D) 49.5%, **403,314** total votes — margin R+1.0.
- **2026 primary (D):** Brooks ~41.4%, over Crosswell, McClure, Obando-Derstine.

---

## 4. Proposed workbook shape

Keep it small. The data does not justify 13 sheets.

| Sheet | Contents |
|---|---|
| **Summary** | One screen: each past election, the market's last price, the actual result, and the error |
| **Election Results** | One row per candidate per cycle — votes, share, margin, turnout, `district_era`, source, certified flag |
| **Market Archive** | Whatever price history exists, per cycle. Will be 4 rows for 2024. Say so on the sheet |
| **Calibration** | Market-implied probability vs binary outcome. With n≈1, present it as a log, not a Brier score |
| **Notes & Sources** | Redistricting eras, per-source provenance, what could not be obtained and why |

Optional if the 2022 Polymarket market turns out to be district-level: fold it in. If it is a
national House-control market, it belongs nowhere near a PA-07 results table.

### Design cautions specific to this workbook

- **Do not compute a Brier score or calibration curve from one observation.** It will look
  rigorous and mean nothing. A table of "market said X, outcome was Y" is the honest form.
- **Do not interpolate** between the four 2024 points to manufacture a smoother series.
- **Show volume next to every market price.** $512 is the most important context for the 68.5%.
- Reuse the live tracker's colour convention (blue = hardcoded input, black = formula, green =
  cross-sheet link, yellow = key output or assumption) so the two workbooks read alike.

---

## 5. Conventions carried over from the live tracker

All four rules in `HANDOFF-campaign-finance.md` §3 apply. The two most likely to bite here:

- **`INDEX` onto a blank cell returns `0`, not blank.** Historical data will be sparse and
  full of gaps — this rule matters *more* here, not less. Guard every lookup with
  `=IFERROR(IF({idx}=0,"",{idx}),"")`; `IFERROR` alone catches errors, not blanks.
- **Row anchors travel through a ref JSON.** Never hardcode a cross-sheet row literal.

Also reusable as-is: `kalshi.py` (RSA request signing), the `check.py` audit, `verify.py`'s
full-formula evaluation, and `tests/support.py`. Credentials, paths and rotation are documented
in `HANDOFF-campaign-finance.md` §1 — the same keys serve both workbooks and should not be
copied anywhere new.

**Use `/usr/bin/python3` explicitly.** A Python 3.14 at `/usr/local/bin/python3` shadows the
system one on `PATH` and lacks every needed package.

### Should this be a separate pipeline?

Probably yes — a **one-shot build**, not a scheduled one. The data is historical and settled;
nothing about 2024 will change. Build it once, verify it, and leave it. Do not add it to
`refresh.py`'s `STEPS`, and do not put it behind the launchd agent.

---

## 6. Verification

Same gates as the live project, run against the new file:

```bash
cd ~/pa07-tracker
/usr/bin/python3 check.py            # adapt WB path; must end "TOTAL PROBLEMS: 0"
/usr/bin/python3 verify.py           # "ERROR CELLS : 0"
/usr/bin/python3 tests/run_tests.py  # existing 100 must still pass
```

And then the part that matters more: **recompute every derived number independently in Python
from the source data and compare against the workbook's evaluated cells.** Worked example in
`HANDOFF-campaign-finance.md` §5. Passing gates has never once, in this project, been sufficient
evidence that a number was right.

Tests worth writing for this workbook specifically:

- No chart or formula spans a `district_era` boundary.
- Every results row has a non-null `source` and `certified` flag.
- The 2024 total-votes figure equals 403,314 (guards against the hand-entered-number failure
  that already happened once).
- Market prices are never interpolated — row count equals the source's point count.

---

## 7. Decisions for the user before building

1. **Scope.** Given there are ~4 usable historical market data points, is this still worth
   building? A results-and-calibration record has real value; a "historical tracker" in the
   sense of the live one is not achievable from these sources. Worth confirming they want the
   former before spending the effort.
2. **How far back?** Results are readily available to 1976 via MIT, but anything before 2018 is
   a different district. Recommend **2018 onward** as the default, with pre-2018 included only
   if explicitly wanted and clearly fenced off.
3. **Other districts?** Kalshi and Polymarket carry many 2026 House races and some 2024 ones.
   If the goal is calibration, a *cross-district* sample would give real statistical power where
   PA-07 alone never can. That is a materially better use of the same machinery, and worth
   raising.

---

## 8. Quick reference

```
Polymarket 2024:  event 14095, slug pa-07-election-wild-d-vs-mackenzie-r
                  token (Wild): 46004854109910930163127760056103200967237877535614150051058183660940013649548
                  GET https://clob.polymarket.com/prices-history?market=<token>&interval=max&fidelity=1440
                  -> 4 points, 2024-11-05 (0.685) .. 2024-11-08 (0.1495); resolved Wild=0, Mackenzie=1

Kalshi 2024:      HOUSEPA7-24 — event exists, no markets, candlesticks 404. Not retrievable.

FEC:              finance only. /v1/elections/ has names but total_votes is null.
                  Key at ~/pa07-tracker/fec_key.txt (mode 600). Never copy the value elsewhere.
```
