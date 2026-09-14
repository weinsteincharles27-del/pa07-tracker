# PA-07 House Election Tracker

Self-updating workbook tracking the Pennsylvania 7th congressional district race
(Bob Brooks (D) vs Rep. Ryan Mackenzie (R)), election **3 November 2026**.

Output: `PA-07_House_Election_Tracker.xlsx` — 13 sheets, ~6,400 formulas, 13 native charts.

Sheet order: Summary · Charts · Distributions · Polymarket · Kalshi ·
Margin of Victory · Voter Turnout · PA Seat Count · Polls ·
**Forecast & Aggregators** · **Campaign Finance** · Venue Comparison · Notes & Sources.

Margin of victory is tracked on BOTH venues and compared on one sheet; voter
turnout is Kalshi-only.

The two chart sheets hold native Excel charts bound to cell ranges on the data
sheets — nothing is rasterised, so every chart redraws itself on each refresh.
Also reachable at `~/Downloads/PA-07_House_Election_Tracker.xlsx` (a symlink to this file).

## Schedule

A launchd agent refreshes everything **at login/wake and at 07:12, 13:12 and 19:12 local**.

```
~/Library/LaunchAgents/com.charlieweinstein.pa07-tracker.plist
```

| Command | What it does |
|---|---|
| `launchctl list \| grep pa07` | Is it loaded? Second column is the last exit code (0 = good) |
| `launchctl kickstart -k gui/$(id -u)/com.charlieweinstein.pa07-tracker` | Run it right now |
| `launchctl unload -w ~/Library/LaunchAgents/com.charlieweinstein.pa07-tracker.plist` | Turn it off |
| `launchctl load -w ~/Library/LaunchAgents/com.charlieweinstein.pa07-tracker.plist` | Turn it back on |
| `./run.sh` | Refresh by hand |
| `tail -30 logs/refresh.log` | What happened on recent runs |
| `cat status.json` | Full machine-readable result of the last run |

To change the times, edit the `StartCalendarInterval` block in the plist, then
unload and load it again.

## Live prices on the site

Polymarket is read straight from the reader's browser once a minute; it sends
the CORS header that allows it. Kalshi does not, and returns 403 to any request
that carries an `Origin` header, so a server reads it instead:

- `.github/workflows/kalshi-live.yml` runs `kalshi_book.py` every ten minutes
  and rewrites `kalshi-live.json` on the `live-data` branch (always a single
  commit; the job amends and force-pushes). The page reads it from
  raw.githubusercontent.com, which caches for five minutes, so Kalshi on the
  page is at most about fifteen minutes old. Public market data needs no key.
- `api/kalshi.js` is the same read as a Vercel function. If the repository is
  ever pointed at Vercel, the page finds `/api/kalshi` first and Kalshi becomes
  live to the second, with no change to the page.

Both live figures sit next to the committed snapshot with their own timestamp
and never overwrite it. GitHub disables scheduled workflows after 60 days
without a push; a commit to any branch restarts them. Endpoints and poll
interval are in `site/assets/live-config.js`.

## Who writes what

`site/data/*.json` and `site/PA-07_House_Election_Tracker.xlsx` are written
by the refresh job on `main`, three times a day, and by nothing else. Never
edit or commit them on a branch: CI refuses a pull request that touches them,
because by review time the bot will have rewritten them and the branch will
conflict. Page configuration goes in `site/assets/`; anything data-shaped
comes out of the pipeline on the next run.

## What a refresh does

1. Pulls live books + full daily history from Polymarket (CLOB + Gamma) and Kalshi (Trade API v2).
2. Pulls the margin-of-victory ladder and the PA Democratic seat-count ladder.
3. Re-reads the poll CSV.
4. Rebuilds all 13 sheets, charts included.
5. Audits every formula for bad references, out-of-range lookups and unsupported functions.
6. Archives a dated copy in `archive/`.
7. Writes `status.json` with notes on what changed and alerts worth acting on.

Alerts fire on: a new PA-07 poll, a >5pp move in either venue, a Kalshi market
status change, a cross-venue pair total under 1.00 (gross arbitrage), a poll CSV
older than 14 days, and election day passing.

## Tests

```bash
python3 tests/run_tests.py
```

133 offline tests covering every bug found in the audit rounds — network
failures, auth errors, market renames at settlement, corrupt state, run-lock
contention, and each alerting rule. They monkeypatch `requests` and the
filesystem; none of them touch the network.

Three gates must all pass before the scheduler is trusted:

| Gate | Checks |
|---|---|
| `python3 check.py` | Formula structure, blank-target references, chart ranges |
| `python3 verify.py` | Evaluates every formula (~13k cells) for errors |
| `python3 tests/run_tests.py` | Behaviour of the data and alerting layer |

**A green gate is not proof the numbers are right.** Every bug the audit found
produced a valid, non-erroring, wrong value. `check.py`'s blank-target check and
chart validation exist because two such bugs shipped past clean runs of the other
two gates. When you change a formula, verify its output against `data.json`.

## Outside sources

Three third-party sources live in `sources/*.json`, refreshed by hand rather than
on the schedule (they are one-off extractions, not APIs the pipeline polls):

| File | What it is | How it is treated |
|---|---|---|
| `pollsmax.json` | Statistical forecast + 231 daily trend points + methodology | An independent view; charted against the market |
| `cityandstate.json` | Third-party odds tracker | **Display only.** Feeds no calculation |
| `fec.json` | Campaign finance via OpenFEC | Its own sheet; finance, not polling |

`build7.py` builds each section only if its file is present, so a missing or
corrupt source degrades to a missing section rather than a broken build.

**City & State is sponsored content** that resells a Kalshi feed, disagrees with
Kalshi's own API by ~9 points, and shows two contradictory numbers on one page.
It is logged as a data-quality observation. A test asserts no formula consumes it.

**FEC figures are stale by construction.** Candidate totals come from quarterly
filings; independent expenditures report continuously. The two halves of that
sheet are not as-of the same date, and the sheet says so.

To refresh these, re-run the extraction and overwrite the JSON — the schema is
documented by the existing files.

## Threshold vs bracket markets

The two venues sell different instruments for the same question:

- **Polymarket** sells mutually exclusive **brackets** ("Democrat 3-6%") that sum to 100%.
- **Kalshi** sells nested **thresholds** ("Democrats, 3+ pts") where each rung is
  `P(value >= strike)`, so probabilities must FALL as the strike rises.

Differencing adjacent Kalshi rungs recovers buckets; `collect3.py` checks the
monotonicity that makes that valid. Kalshi quotes no 0-3 rung, so the two tossup
buckets are derived as `P(wins) - P(wins by 3+)` — reaching across two
independently quoted markets, which can invert. That case is clamped at zero and
reported by the CONSISTENCY CHECK block rather than rendered as a negative
probability.

**A note on interpreting the Kalshi ladder:** an inversion is not automatically a
mispricing. Check the verdict cell — it distinguishes a midpoint artifact (the
spreads overlap) from a genuinely executable edge, using bid/ask rather than mids.

## Updating the polls

The poll data comes from the NYT/538 house-poll file. **Save new copies to
`~/pa07-tracker/house.csv`**, not to Downloads.

macOS TCC blocks background agents from reading `~/Downloads`, `~/Documents` and
`~/Desktop` unless the binary has Full Disk Access. A CSV left in Downloads is
picked up only when you run `./run.sh` yourself — the scheduled runs cannot see
it and will keep using the last copy in this directory. `pollsrc.py` handles both
cases and the run reports which file it used.

## Files

| File | Role |
|---|---|
| `refresh.py` | Orchestrator. Runs everything, diffs against `state.json`, writes `status.json` |
| `run.sh` | launchd wrapper — env, logging, log rotation |
| `kalshi.py` | RSA-PSS request signing for the Kalshi API |
| `pollsrc.py` | Finds a readable poll CSV, works around the TCC restriction |
| `collect.py` | Polymarket + Kalshi winner markets |
| `collect2.py` | Margin-of-victory ladder, seat-count ladder, Kalshi subject inventory |
| `build.py` | Polymarket and Kalshi sheets |
| `build2.py` | Polls sheet (reads the CSV) |
| `build2b.py` | Margin of Victory and PA Seat Count sheets |
| `collect3.py` | Kalshi margin-of-victory and voter-turnout ladders |
| `build6.py` | Kalshi margin section + Voter Turnout sheet (runs after `build2b.py`) |
| `build7.py` | Forecast & Aggregators + Campaign Finance, from `sources/*.json` |
| `build3.py` | Venue Comparison and Summary sheets |
| `build5.py` | Charts and Distributions sheets (runs before `build4.py`) |
| `build4.py` | Notes & Sources, sheet order, final save |
| `check.py` | Fast structural audit of every formula |
| `verify.py` | Full formula evaluation (slow, needs `formulas`); run by hand |
| `state.json` | Previous run's figures, for change detection |
| `status.json` | Last run's full result |

## Credentials

`kalshi_key.pem` (mode 600, directory 700) holds the Kalshi RSA private key;
the key ID is in `kalshi.py`. Both are used only to sign read-only market
requests.

**This key was pasted into a chat transcript.** Rotate it in your Kalshi account
settings when convenient — drop the replacement into `kalshi_key.pem` and update
`KEY_ID` in `kalshi.py`. Nothing else needs to change.

## Dependencies

`openpyxl`, `requests`, `cryptography` (installed for `/usr/bin/python3 --user`).
`formulas` is only needed for `verify.py`.
