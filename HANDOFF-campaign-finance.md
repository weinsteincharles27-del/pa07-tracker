# Handoff — Campaign Finance (FEC) & Migrating Data Correctly

**Project:** `~/pa07-tracker/` — a self-updating Excel tracker for the PA-07 US House race
(Bob Brooks (D) vs Rep. Ryan Mackenzie (R), election **3 Nov 2026**).
**Scope of this document:** the Campaign Finance sheet, and the conventions any new data
source must follow to migrate in without producing silently wrong numbers.
**Written:** 3 Sep 2026. Read `README.md` first for the overall project; this is the deep dive.

---

## 0. Read this before you touch anything

Every bug found in this project so far — and there have been many — shared one property:
**it produced a valid, non-erroring, wrong number.** `check.py` reported zero problems and
`verify.py` reported zero formula errors while the workbook displayed a −75% daily price
change, a probability distribution summing to 133%, and a "gap" that was actually the market
price itself.

So: **passing the gates is necessary and nowhere near sufficient.** Whenever you add or change
a number, recompute it independently from the source JSON in Python and compare. There is a
worked example of how to do that in §5.

Use `/usr/bin/python3` explicitly. A Python 3.14 at `/usr/local/bin/python3` shadows the system
one on `PATH` and does not have `openpyxl`, `requests`, `cryptography`, `formulas` or `fitz`
installed. `run.sh` hardcodes the right interpreter; your shell does not.

---

## 1. Credentials

| What | Where | Mode | Used by |
|---|---|---|---|
| FEC / OpenFEC API key | `~/pa07-tracker/fec_key.txt` | `600` | the FEC extraction (manual, see §3) |
| Kalshi RSA private key | `~/pa07-tracker/kalshi_key.pem` | `600` | `kalshi.py`, every scheduled run |
| Kalshi key ID | `kalshi.py:23` (`KEY_ID`) | in source | `kalshi.py` |

The project directory itself is mode `700`.

**The secret values are deliberately NOT reproduced in this document.** Both live in
mode-`600` files inside a `700` directory; copying them into a `644` markdown file would be a
downgrade in hygiene for no benefit. Read them at the point of use:

```bash
FEC_KEY="$(cat ~/pa07-tracker/fec_key.txt)"
curl -s "https://api.open.fec.gov/v1/candidates/search/?state=PA&district=07&cycle=2026&office=H&api_key=$FEC_KEY"
```

Rules that are enforced by convention and worth keeping:

- The FEC key must never appear in `sources/fec.json`, in any committed script, or in any log.
  Verify after any extraction run: `grep -rl "$(cat fec_key.txt)" . && echo LEAKED`
- `kalshi.py` reads its key from `KALSHI_KEY_PATH` (default: the `.pem` beside it), so tests
  can point it elsewhere without touching the real key.

**Both keys were pasted into a chat transcript and should be rotated.**
- *Kalshi:* rotate in account settings, drop the new PEM into `kalshi_key.pem`, update
  `KEY_ID` in `kalshi.py:23`. Nothing else changes. Note that a `KEY_ID`/PEM mismatch produces
  a 401 that `kalshi.py` now surfaces as `ApiError: 401 from Kalshi: …` rather than a bare
  `KeyError` three frames later.
- *FEC:* request a new key at `api.data.gov`, overwrite `fec_key.txt`, keep mode `600`.
  Low urgency — the key is read-only against public data and only gates rate limits.

---

## 2. What the Campaign Finance sheet is

Sheet **`Campaign Finance`**, built by `build7.py`, sourced from `sources/fec.json`.
70 rows. This is **campaign finance, not polling** — do not merge it into the Polls sheet or
the polling average.

Layout (row numbers as of this writing — read them from the sheet, do not hardcode; see §4):

| Row | Section |
|---|---|
| 4–6 | `COVERAGE` — "Figures current through", "Retrieved" |
| 8–16 | `CANDIDATE TOTALS — 2026 cycle` + `TOTAL` row |
| 18–21 | `DERIVED` — cash advantage, combined receipts, burn rate |
| 23–54 | `INDEPENDENT EXPENDITURES` (29 rows) + `TOTAL` |
| 58+ | `READ THE MONEY WITH THESE TWO FACTS` + extraction notes |

Current headline figures (coverage through **2026-06-30**):

| | Brooks (D) | Mackenzie (R) |
|---|---|---|
| Receipts | $2,392,215 | $4,357,405 |
| Cash on hand | $1,018,423 | **$2,938,717** |

### The two caveats that change the reading

These are on the sheet itself (row 58 onward), not just in the notes, and there is a test
asserting they stay there. **Do not remove them without understanding why they exist:**

1. **The two halves are not as-of the same date.** Candidate totals come from the July
   Quarterly (through 30 Jun 2026). Independent expenditures report continuously and are
   fresher. Next candidate refresh is the October Quarterly, ~15 Oct, covering through 30 Sep.
2. **Most of the money was not spent on this fight.** Of ~$2.78M in outside spending, the two
   largest players spent between 6–18 May 2026 inside the contested *Democratic primary*, not
   against Mackenzie. And ~$1.78M of Mackenzie's receipts is a transfer from a wound-down
   joint fundraising committee, not fresh donor money. A naive reading of "Mackenzie raised
   $4.36M vs Brooks's $2.39M" is wrong in a way that matters.

### Traps already hit here

- **`cash advantage` used to subtract by row position.** The FEC API returns candidates in no
  guaranteed order, so a correct-looking dollar figure would have appeared with the wrong sign
  the day that order changed. It is now `INDEX(...MATCH("Bob Brooks"...)) - INDEX(...MATCH("Ryan
  Mackenzie"...))`, matched by name, Democrat first. Guarded by
  `test_cash_advantage_is_matched_by_name_not_row_position`.
- **Four of the six candidates never filed.** Their financial fields are `null`, not `0`.
  Rendering `$0` would assert they raised nothing, which is a different and unsupported claim.
  They show blank with an explicit `never filed` marker in the `Filed?` column. `SUM()` over
  the column ignores blanks, which is the behaviour we want. Guarded by
  `test_never_filed_candidates_are_not_shown_as_zero`.

### Refreshing the FEC data

It is **not** on the schedule — `sources/*.json` are one-off extractions, and `refresh.py`
only re-reads them. To update:

1. Re-extract from the OpenFEC API into `sources/fec.json`, preserving the existing schema
   exactly (`build7.py` reads those key names). Endpoints that were used:
   `/v1/candidates/search/`, `/v1/candidate/{id}/totals/`, `/v1/candidate/{id}/committees/`,
   `/v1/schedules/schedule_e/` (independent expenditures).
2. Keep `coverage_through` accurate — it is displayed prominently and is the whole basis of
   caveat 1.
3. Use `null`, never `0`, for anything the API does not report.
4. Run the pipeline and the gates (§5).

If `sources/fec.json` is missing or corrupt, `build7.py` **omits the sheet** and the build
still succeeds — `build4.py`'s sheet-order list filters to sheets that exist. That is tested;
don't "fix" it into a hard failure.

---

## 3. Migrating data correctly — the conventions

This is the part that has caused every real bug. Four rules.

### Rule 1 — Row anchors travel through the ref JSONs. Never hardcode a cross-sheet row.

Each build script computes the rows it wrote and hands them on in a JSON file. Producer →
consumer chain:

| File | Written by | Notable keys |
|---|---|---|
| `refs.json` | `build.py` | `PM_FIRST/PM_LAST`, `K_FIRST/K_LAST`, `PM_MID_D/R`, `PM_VOL` |
| `prefs.json` | `build2.py` | `PSTART/PEND`, `QS/QE`, `ACT`, `WM`, `ADJ` |
| `movrefs.json` | `build2b.py` | `L0/LN`, `K0/KN`, `EM`, `ES`, `P3/P6` |
| `k3refs.json` | `build6.py` | `K0/KN`, `KEM`, `R03/D03`, `T0/TN`, `TEXP`, `TURN_*` |
| `vrefs.json` | `build3.py` | `VH/VL`, `MS`, `HEAD` |
| `f7refs.json` | `build7.py` | `FEC_FIRST/FEC_LAST`, `PM_TREND_FIRST/LAST`, `CS_ROW` |

**The one hardcoded cross-sheet literal that ever existed was a bug** (`=Polymarket!B12+…`,
which would have silently pointed at a different metadata row the moment anyone reordered that
block). I then reintroduced the same anti-pattern in `build6.py` within an hour of fixing it,
so treat this as easy to get wrong: if you write a formula naming another sheet, the row must
come from a ref dict.

### Rule 2 — `headers()` returns the FIRST DATA ROW, not the header row.

Every builder has `def headers(ws, row, cols): …; return row + 1`. So a stored anchor is the
first data row and **its header lives at `anchor - 1`**. This has produced two separate bugs:
chart series titles reading a data row as the series name (and silently dropping the first
data point), and axis ranges off by one.

When building a chart: values range starts at `anchor - 1` with `title_from_data=True`;
categories range starts at `anchor`.

### Rule 3 — `INDEX` onto a blank cell returns **0**, not blank.

This is the single most productive source of wrong numbers in the project. A missing price read
as `0.000` and produced a −75 percentage-point daily change, and a 73.5pp cross-venue
divergence that was pure fiction.

Guard every lookup. The established pattern (see `build3.py`'s `lookup()` / `asof()` helpers):

```python
idx = 'INDEX(Sheet!$B${first}:$B${last},MATCH($A{row},Sheet!$A${first}:$A${last},0))'
formula = '=IFERROR(IF({0}=0,"",{0}),"")'.format(idx)
```

`IFERROR` alone is **not** enough — it catches errors, not blanks. Note also that
`ISNUMBER(INDEX(blank))` is `TRUE`, because the blank became `0`. Test `<>0` explicitly.
A genuine `0.000` does not occur in these markets, so treating 0 as missing is safe here.

Same trap on plain arithmetic: a blank cell in `B5-B6` reads as zero. That is how the
model-vs-market "gap" came to display the market price itself when the forecast was absent.
Guard with `IF(AND(ISNUMBER(B5),ISNUMBER(B6)),B5-B6,"")`.

### Rule 4 — Row arithmetic is not calendar arithmetic.

The daily histories have **real gaps** (Polymarket: 11, 9 and 4 days across spring 2026;
Kalshi: six more in June–July). `PML - 30` is therefore not "30 days ago" — measured against
live data, 32 of 205 cells in the 30-day change column were computing over the wrong window.

Look up by date with `MATCH(target_date, date_column, 1)` (match type 1 needs an ascending
column, which these are), and withhold the cell when the nearest earlier date is too stale to
justify the label. See `build.py`'s `change()` and `build3.py`'s `asof()`.

### Also worth knowing

- **Threshold vs bracket markets.** Kalshi sells nested thresholds (`P(margin ≥ 3)`);
  Polymarket sells exclusive brackets. Differencing adjacent Kalshi rungs recovers buckets —
  but do that off **strike values**, never row adjacency. The Republican rungs are displayed
  descending, and differencing neighbouring rows inflated that side from 0.235 to 0.572 and
  produced a distribution summing to 1.33. Guarded by `test_bucket_formulas_are_keyed_to_strikes_not_row_order`.
- **Two independently quoted markets can disagree into a negative probability.** The 0-3 margin
  buckets are `P(wins) − P(wins by 3+)` across two Kalshi markets and can go negative. They are
  clamped with `MAX(0,…)` and a consistency check reports whether the inversion is a midpoint
  artifact (spreads overlap) or a genuinely executable edge, using bid/ask rather than mids.
- **String replacements fail silently.** Two of my "corrections" did not apply because the
  target text wrapped differently than I assumed, and I reported them as done. If you patch by
  string replacement, `assert` that the content changed and re-grep the built artifact.

---

## 4. Reading rows out of the sheet instead of hardcoding them

Tests and analysis should locate rows by content, because sections move whenever anything above
them grows:

```python
def find(ws, needle, col=1, limit=90):
    for r in range(1, limit):
        v = ws.cell(r, col).value
        if isinstance(v, str) and needle.lower() in v.lower():
            return r
```

One live gotcha: searching for `"TOTAL"` also matches the section heading
`"CANDIDATE TOTALS — 2026 cycle"`. Match the standalone row exactly
(`str(...).strip() == "TOTAL"`). That mistake cost a false test failure.

---

## 5. Verifying a change

```bash
cd ~/pa07-tracker
launchctl unload -w ~/Library/LaunchAgents/com.charlieweinstein.pa07-tracker.plist   # pause first

# offline rebuild (collect*.py hit the network; skip them, the data*.json already exist)
for b in build.py build2.py build2b.py build6.py build7.py build3.py build5.py build4.py; do
  /usr/bin/python3 $b || break
done

/usr/bin/python3 check.py            # must end "TOTAL PROBLEMS: 0"
/usr/bin/python3 tests/run_tests.py  # 100 passed, 0 failed
/usr/bin/python3 verify.py           # "ERROR CELLS : 0"  (slow, ~4 min)
./run.sh                             # full live end-to-end, must exit 0

launchctl load -w ~/Library/LaunchAgents/com.charlieweinstein.pa07-tracker.plist    # restore
```

**Then do the part the gates cannot do.** Recompute independently and compare — this is what
caught the 1.33-summing distribution and the wrong-signed cash advantage:

```python
import warnings; warnings.filterwarnings("ignore")
import formulas, json
xl = formulas.ExcelModel().loads("PA-07_House_Election_Tracker.xlsx").finish()
sol = xl.calculate()
V = {}
for k, v in sol.items():
    if "]CAMPAIGN FINANCE'!" in k.upper():
        try: V[k.upper().split("]", 1)[1].replace("'", "")] = v.value[0, 0]
        except Exception: pass

fec = json.load(open("sources/fec.json"))
expected = sum(c["receipts"] or 0 for c in fec["candidates"])
print(V.get("CAMPAIGN FINANCE!C16"), "vs", expected)   # TOTAL receipts
```

Relevant test files: `tests/test_sources.py` (FEC, forecast, tracker isolation),
`tests/test_ladders.py` (threshold arithmetic), `tests/test_charts.py` (rendering),
`tests/support.py` (`project()` for real-file paths, `sandbox()`, `fake_network()`).

---

## 6. Operational notes

- **Pause the scheduler while working.** It fires at login/wake and 07:12/13:12/19:12 local and
  will rebuild underneath you. `run.sh` takes an `flock`, so a manual run and a scheduled one
  cannot interleave — but the file on disk will still change.
- **`refresh.py` publishes only after the audit passes.** On an audit failure it restores the
  previously-good workbook with `os.replace`, skips the archive, and leaves `state.json` alone.
  A scheduled run at 2026-09-03T11:13Z did exactly this. Exit codes: `0` clean, `1` refresh
  failed, `2` built but audit found problems.
- **The audit log now records categories,** not just `TOTAL PROBLEMS: n` — that count alone was
  useless for diagnosing the 11:13 failure, which has not recurred and was never identified.
- **`~/Desktop/PA07_House_Election_Tracker.xlsx` and the Downloads equivalent are symlinks** to
  the live build. Note the Desktop one has no hyphen in `PA07`. A stale *copy* on the Desktop
  once caused a whole round of "the charts are broken" that was really "you are looking at
  yesterday's file". macOS TCC blocks the launchd agent from writing into `~/Desktop` and
  `~/Downloads`, which is why they are links and not copies.
- **Poll CSVs go in `~/pa07-tracker/house.csv`**, not Downloads — same TCC restriction.

## 7. Open items in this area

- The FEC data will be ~3.5 months stale by the October Quarterly. Worth re-extracting ~15 Oct.
- `sources/fec.json`'s `extraction_problems` records that the primary-vs-general split of
  independent expenditure was established by spot-check, not a full record-by-record
  classification. If that distinction starts mattering, redo it properly.
- A `$11,000` pro-Brooks buy by SEED-PAC (24-hour notice, filed 2026-08-19) was added by hand
  because it postdated the aggregate endpoint's indexing. Check whether FEC's aggregate has
  since absorbed it, to avoid double-counting on the next extraction.
- Nothing reconciles FEC spending against the market or the model. A "money vs odds" comparison
  is an obvious next exhibit and does not exist yet.
