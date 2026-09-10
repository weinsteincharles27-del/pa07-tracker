#!/usr/bin/env python3
"""PA-07 tracker refresh.

Pulls Polymarket + Kalshi live, re-reads the poll CSV, rebuilds the workbook,
audits every formula, archives a dated copy, and writes status.json describing
what changed since the previous run.

Deterministic and self-contained: no LLM required. The cron agent runs this,
reads status.json, and reports.

The published workbook and state.json move together or not at all. build4.py
saves straight onto the published filename and is not ours to change, so the
staging happens around it: the previous file is preserved first, the build
writes, check.py audits what was written, and only then is the result kept.
Anything that goes wrong from the audit onwards puts the preserved copy back
with os.replace, so the file on disk never runs ahead of the recorded state.

Exit codes:  0 = clean   1 = refresh failed   2 = built, but audit found problems
"""
import os, sys, json, glob, shutil, subprocess, datetime, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
WB = "PA-07_House_Election_Tracker.xlsx"
PRESERVED = WB + ".prev"          # rollback copy; only exists mid-run
STATE = "state.json"
STATUS = "status.json"
PUBLISH = os.environ.get("PA07_PUBLISH_TO", HERE)
ELECTION = datetime.date(2026, 11, 3)

ARCHIVE_KEEP = 30                 # dated copies retained in archive/
TRAIL_MAX = 12                    # ~4 days of runs, for cumulative-move detection
TRAIL_KEYS = ("consensus_dem", "pm_dem", "kalshi_dem")
MOVE_PP = 5.0                     # alert threshold, per step and cumulative
STALE_DAYS = 14                   # poll content age that warrants a nudge
GAP_HOURS = 8                     # scheduled slots are ~6 h apart

STEPS = ["collect.py", "collect2.py", "collect3.py", "build.py", "build2.py",
         "build2b.py", "build6.py", "build7.py", "build3.py", "build5.py", "build4.py"]

MOVES = [("consensus_dem", "Consensus P(Dem)"),
         ("pm_dem", "Polymarket Dem"),
         ("kalshi_dem", "Kalshi Dem")]

SERIES_TOTALS = [("pm_history_days", "Polymarket winner history"),
                 ("kalshi_history_days", "Kalshi winner history"),
                 ("mov_history_days", "Polymarket margin-ladder history"),
                 ("seat_history_days", "Kalshi seat-ladder history")]

SERIES_MAPS = [("pm_series_days", "Polymarket winner"),
               ("k_series_days", "Kalshi winner"),
               ("mov_series_days", "margin bracket"),
               ("seat_series_days", "seat bracket")]


def run(script):
    p = subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=600)
    if p.returncode != 0:
        raise RuntimeError("%s failed (exit %d)\nSTDOUT:\n%s\nSTDERR:\n%s"
                           % (script, p.returncode, p.stdout[-2000:], p.stderr[-3000:]))
    return p.stdout.strip()


# ------------------------------------------------------------------- staging

def preserve(path=WB):
    """Set the published workbook aside so a failed run can put it back."""
    if not os.path.exists(path):
        return None
    shutil.copy2(path, PRESERVED)
    return PRESERVED


def roll_back(bak, path=WB):
    """Atomically restore the preserved workbook. Same directory, so os.replace
    is a rename: a reader sees the old file or the new one, never a half-copy."""
    if not bak or not os.path.exists(bak):
        return False
    os.replace(bak, path)
    return True


def discard(bak):
    if bak and os.path.exists(bak):
        try:
            os.remove(bak)
        except OSError:
            pass


def load_state():
    """(previous snapshot or None, note).

    Unparseable state counts as missing. The rewrite that would repair it comes
    at the end of a run, so a hand-edited or truncated state.json used to raise
    on every future run and never self-heal — diffing, alerting and archiving
    stayed dead while the workbook kept updating.
    """
    if not os.path.exists(STATE):
        return None, None
    try:
        with open(STATE) as f:
            return json.load(f), None
    except (ValueError, OSError) as e:
        keep = STATE + ".corrupt"
        try:
            os.replace(STATE, keep)
            where = " The unreadable copy is in %s." % keep
        except OSError:
            where = ""
        return None, ("state.json could not be read (%s) and was reset, so this run has nothing "
                      "to diff against.%s" % (e, where))


def save_state(prev, cur):
    """Persist the snapshot plus a short trail of recent runs.

    The trail is what lets a move split across several runs get noticed: a diff
    against only the immediately previous run never sees +3pp followed by +3pp.
    """
    trail = [e for e in ((prev or {}).get("recent") or []) if isinstance(e, dict)]
    entry = {k: cur.get(k) for k in TRAIL_KEYS}
    entry["run_utc"] = cur.get("run_utc")
    trail.append(entry)
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(dict(cur, recent=trail[-TRAIL_MAX:]), f, indent=1)
    os.replace(tmp, STATE)


def archive(stamp):
    """Dated copy, plus bounded retention.

    The name carries the run time as well as the date — same-day reruns used to
    overwrite each other — and the caller only gets here once the audit passed,
    so a broken build can no longer replace a clean archived copy.
    """
    os.makedirs("archive", exist_ok=True)
    dest = os.path.join("archive", "PA-07_tracker_%s.xlsx" % stamp)
    shutil.copy2(WB, dest)
    have = sorted(glob.glob(os.path.join("archive", "PA-07_tracker_*.xlsx")))
    pruned = 0
    for old in have[:-ARCHIVE_KEEP] if len(have) > ARCHIVE_KEEP else []:
        try:
            os.remove(old)
            pruned += 1
        except OSError:
            pass
    return dest, pruned


def publish():
    """Copy the workbook to PA07_PUBLISH_TO (normally ~/Downloads).

    Four outcomes worth telling apart. The documented setup has ~/Downloads
    holding a symlink back to this file, which makes copy2 raise SameFileError
    on every single run — an OSError, and so previously indistinguishable from
    the TCC denial it was meant to catch. That is how Downloads could go stale
    for weeks without a word.
    """
    if not os.path.isdir(PUBLISH) or os.path.samefile(HERE, PUBLISH):
        return {"state": "same_dir"}
    dest = os.path.join(PUBLISH, WB)
    link = os.path.islink(dest)
    try:
        if os.path.exists(dest) and os.path.samefile(dest, WB):
            return {"state": "linked" if link else "same_file", "dest": dest}
        if link:
            return {"state": "stale_link", "dest": dest,
                    "error": "%s is a symlink but no longer resolves to the workbook — the "
                             "published copy is not this file." % dest}
        shutil.copy2(WB, dest)
        return {"state": "copied", "dest": dest}
    except shutil.SameFileError:
        return {"state": "linked" if link else "same_file", "dest": dest}
    except OSError as e:
        # macOS TCC blocks launchd agents from ~/Downloads and friends.
        return {"state": "failed", "dest": dest, "error": "%s: %s" % (type(e).__name__, e)}


def write_status(status):
    """Temp file, then rename, inside its own guard.

    status.json is the only thing the scheduler reads. It must never be left
    holding the previous run's ok:true because the write itself threw.
    """
    try:
        tmp = STATUS + ".tmp"
        with open(tmp, "w") as f:
            json.dump(status, f, indent=1, default=str)
        os.replace(tmp, STATUS)
        return True
    except Exception:
        try:
            os.remove(STATUS + ".tmp")
        except OSError:
            pass
        fallback = {"ok": False,
                    "error": "status.json could not be written in full",
                    "traceback": traceback.format_exc()[-2000:],
                    "started_utc": status.get("started_utc"),
                    "finished_utc": status.get("finished_utc")}
        try:
            with open(STATUS, "w") as f:
                json.dump(fallback, f, indent=1)
        except Exception:
            print("status.json could not be written:\n" + traceback.format_exc())
        return False


# ------------------------------------------------------------------ snapshot

def snapshot():
    """Key figures, read straight from the collected JSON rather than the workbook."""
    d = json.load(open("data.json"))
    d2 = json.load(open("data2.json"))
    pm, k = d["pm_meta"], d["k_meta"]

    def mid(bid, ask):
        return None if bid is None or ask is None else (bid + ask) / 2

    pm_d = mid(pm["D"]["best_bid"], pm["D"]["best_ask"])
    pm_r = mid(pm["R"]["best_bid"], pm["R"]["best_ask"])
    k_d = mid(k["D"]["yes_bid"], k["D"]["yes_ask"])
    k_r = mid(k["R"]["yes_bid"], k["R"]["yes_ask"])

    # margin ladder: normalised expected margin
    tot = sum(m for m in (mid(b["best_bid"], b["best_ask"]) or 0 for b in d2["mov"]))
    exp_margin = p_dem_ladder = None
    if tot:
        exp_margin = sum((mid(b["best_bid"], b["best_ask"]) or 0) / tot * b["midpoint"] for b in d2["mov"])
        p_dem_ladder = sum((mid(b["best_bid"], b["best_ask"]) or 0) / tot
                           for b in d2["mov"] if b["bracket"].startswith("Democrat"))

    # seat ladder: expected Democratic seats
    def seat_mid(b):
        if b["yes_bid"] is not None and b["yes_ask"] is not None:
            return (b["yes_bid"] + b["yes_ask"]) / 2
        if b["yes_ask"] is not None:
            return b["yes_ask"] / 2
        return b["yes_bid"]
    stot = sum(seat_mid(b) or 0 for b in d2["seats"])
    exp_seats = (sum((seat_mid(b) or 0) / stot * b["midpoint"] for b in d2["seats"])
                 if stot else None)

    # --- Kalshi threshold ladders (margin, turnout) ---------------------
    d3 = {}
    try:
        d3 = json.load(open("data3.json"))
    except (OSError, ValueError):
        pass

    def rung_mids(block):
        out = {}
        for x in (block or {}).get("rungs", []):
            b, a = x.get("yes_bid"), x.get("yes_ask")
            if b is not None and a is not None:
                out[str(x["strike"])] = (b + a) / 2
        return out

    mov_d, mov_r = rung_mids(d3.get("mov_d")), rung_mids(d3.get("mov_r"))
    turn = rung_mids(d3.get("turnout"))

    def expected_turnout(t):
        """Bucket-weighted turnout, mirroring the Voter Turnout sheet.

        The two open-ended representative values are build6.py's, read from
        k3refs.json rather than copied, so the sheet and this snapshot cannot
        drift apart.
        """
        if not t:
            return None
        try:
            k3 = json.load(open("k3refs.json"))
            low, top = k3["TURN_LOW_MID"], k3["TURN_TOP_MID"]
        except (OSError, ValueError, KeyError):
            low, top = 295000, 385000
        ks = sorted(float(k) for k in t)
        tot, prev = 0.0, 1.0
        for i, k in enumerate(ks):
            p = t[str(k)]
            nxt = ks[i + 1] if i + 1 < len(ks) else None
            if i == 0:
                tot += max(0.0, 1.0 - p) * low
            tot += (max(0.0, p - t[str(nxt)]) * ((k + nxt) / 2) if nxt else p * top)
            prev = p
        return tot

    import pollsrc
    try:
        csv_path = pollsrc.resolve()
    except FileNotFoundError:
        csv_path = None
    npolls = ngeneral = 0
    poll_ids, poll_values = [], {}
    content_since = content_age = None
    if csv_path:
        import csv as _csv
        with open(csv_path) as f:
            rows = [r for r in _csv.DictReader(f)
                    if r.get("state") == "PA" and r.get("seat_number") == "7"]
        seen = {}
        for r in rows:
            seen[r["poll_id"]] = r.get("stage")
            # what this poll actually reports, so a revision in place is visible
            who = r.get("answer") or r.get("candidate_name") or "?"
            poll_values.setdefault(r["poll_id"], {})["%s/%s" % (r.get("stage") or "?", who)] = r.get("pct")
        poll_ids = sorted(seen)
        npolls = len(seen)
        ngeneral = sum(1 for v in seen.values() if v == "general")
        content_since, _ = pollsrc.content_stamp(pollsrc.content_digest(rows))
        content_age = pollsrc.content_age_days(content_since)

    # Both sides can be None at settlement, on an empty book, or on a one-sided
    # one. min() over an empty generator raises, and this used to run after the
    # workbook had already been overwritten.
    cheapest_d = min((x for x in (pm["D"]["best_ask"], k["D"]["yes_ask"]) if x is not None),
                     default=None)
    cheapest_r = min((x for x in (pm["R"]["best_ask"], k["R"]["yes_ask"]) if x is not None),
                     default=None)
    pair = None if None in (cheapest_d, cheapest_r) else cheapest_d + cheapest_r

    def net_edge(a, b):
        """Edge on buying both YES legs, after the fee that actually gets charged.

        ASSUMPTION: Kalshi's trading fee is ~0.07 x p x (1-p) per contract, which
        is largest exactly where these markets sit and swamps a thin gross edge.
        A run on 29 Aug 2026 showed a 1.00pp gross edge against 2.44pp of fees —
        a 1.44pp LOSS reported as an arbitrage. Gross edge alone is not a signal.
        """
        if None in (a, b):
            return None
        fee = 0.07 * a * (1 - a) + 0.07 * b * (1 - b)
        return 1.0 - (a + b) - fee

    def per_series(hist, keys):
        return {str(x): sum(1 for v in hist.values() if x in v) for x in keys}

    return {
        "run_utc": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "days_to_election": (ELECTION - datetime.date.today()).days,
        "pm_dem": pm_d, "pm_rep": pm_r, "kalshi_dem": k_d, "kalshi_rep": k_r,
        "consensus_dem": (pm_d + k_d) / 2 if None not in (pm_d, k_d) else None,
        "divergence": pm_d - k_d if None not in (pm_d, k_d) else None,
        "expected_margin_pts": exp_margin,
        "p_dem_ladder": p_dem_ladder,
        "expected_dem_seats": exp_seats,
        "pair_ask_total": pair,
        "kalshi_mov_d": mov_d, "kalshi_mov_r": mov_r, "kalshi_turnout": turn,
        "expected_turnout": expected_turnout(turn),
        "pair_net_edge": net_edge(cheapest_d, cheapest_r),
        "top_ask_size": {"pm_dem": pm["D"].get("ask_size"), "pm_rep": pm["R"].get("ask_size")},
        "top_bid_size": {"pm_dem": pm["D"].get("bid_size"), "pm_rep": pm["R"].get("bid_size")},
        "pm_status": {"D": pm["D"].get("last_trade"), "R": pm["R"].get("last_trade")},
        "kalshi_status": {"D": k["D"]["status"], "R": k["R"]["status"]},
        "pm_history_days": len(d["pm_history"]),
        "kalshi_history_days": len(d["k_history"]),
        "mov_history_days": len(d2.get("mov_history") or {}),
        "seat_history_days": len(d2.get("seat_history") or {}),
        # per-series counts: one bracket whose history pull failed leaves an empty
        # column that reads as ordinary blanks unless it is counted on its own
        "pm_series_days": per_series(d["pm_history"], ("D", "R")),
        "k_series_days": per_series(d["k_history"], ("D", "R")),
        "mov_series_days": per_series(d2.get("mov_history") or {},
                                      [b["bracket"] for b in d2["mov"]]),
        "seat_series_days": per_series(d2.get("seat_history") or {},
                                       [b["ticker"] for b in d2["seats"]]),
        "mov_brackets": [b["bracket"] for b in d2["mov"]],
        "seat_brackets": [b["ticker"] for b in d2["seats"]],
        "collector_problems": (list(d.get("problems") or []) + list(d2.get("problems") or [])
                               + list(d3.get("problems") or [])),
        "polls_total": npolls, "polls_general": ngeneral, "poll_ids": poll_ids,
        "poll_values": poll_values,
        "polls_csv": csv_path,
        "polls_content_since": content_since,
        "polls_content_age_days": content_age,
        "polls_csv_mtime": (datetime.datetime.utcfromtimestamp(os.path.getmtime(csv_path))
                            .isoformat(timespec="seconds") + "Z") if csv_path else None,
    }


# ---------------------------------------------------------------------- diff

def diff(prev, cur):
    """Human-readable notes on what changed, plus anything needing attention."""
    notes, alerts = [], []

    # Collector-level problems come through whatever else happened: a rename or
    # a delist must never produce a plausible-looking workbook in silence.
    for p in cur.get("collector_problems") or []:
        alerts.append("DATA (%s): %s" % (p.get("kind", "problem"),
                                         p.get("detail") or p.get("what") or p))

    if cur.get("days_to_election") is not None and cur["days_to_election"] <= 0:
        alerts.append("Election day has passed. Markets will resolve; switch to settlement mode.")

    pair, net = cur.get("pair_ask_total"), cur.get("pair_net_edge")
    if pair is not None and pair < 1.0:
        gross = (1.0 - pair) * 100
        sizes = [v for v in (cur.get("top_ask_size") or {}).values() if v]
        depth = min(sizes) if sizes else None
        depth_txt = ("about $%.0f resting on the thinner leg" % depth) if depth else "unknown depth"
        if net is not None and net > 0:
            alerts.append("ARBITRAGE: pair asks total %.3f — %+.2fpp gross, %+.2fpp NET of "
                          "estimated Kalshi fees, %s." % (pair, gross, net * 100, depth_txt))
        else:
            notes.append("Pair asks total %.3f (%+.2fpp gross) but only %+.2fpp net of estimated "
                         "fees — not tradeable, so no alert." % (pair, gross, (net or 0) * 100))

    age = cur.get("polls_content_age_days")
    if age is not None and age >= STALE_DAYS:
        alerts.append("Poll CSV content is %d days old — unchanged since %s. Download a fresh "
                      "house.csv into ~/pa07-tracker/ to pick up new PA-07 polls."
                      % (age, cur.get("polls_content_since")))

    if not prev:
        notes.append("First recorded run — no previous snapshot to compare against.")
        return notes, alerts

    if prev.get("run_utc"):
        try:
            since = datetime.datetime.utcnow() - datetime.datetime.fromisoformat(
                prev["run_utc"].rstrip("Z"))
            if since.total_seconds() > GAP_HOURS * 3600:
                notes.append("Previous run was %.1f h ago; scheduled slots are ~6 h apart, so at "
                             "least one refresh was missed (asleep, or the agent was unloaded)."
                             % (since.total_seconds() / 3600.0))
        except ValueError:
            pass

    def pp(a, b):
        return None if None in (a, b) else (b - a) * 100

    trail = [e for e in (prev.get("recent") or []) if isinstance(e, dict)]
    for key, label in MOVES:
        d = pp(prev.get(key), cur.get(key))
        if d is not None and abs(d) >= 0.5:
            notes.append("%s moved %+.1f pp to %.1f%%" % (label, d, cur[key] * 100))
        if d is not None and abs(d) >= MOVE_PP:
            # Depth belongs in the text: 6pp on $3 of resting size is noise, the
            # same 6pp on a deep book is news, and the alert cannot tell them
            # apart on price alone.
            sizes = [v for v in (cur.get("top_ask_size") or {}).values() if v]
            depth = (" Top-of-book ask depth about $%.0f." % min(sizes)) if sizes else ""
            alerts.append("LARGE MOVE: %s shifted %+.1f pp since the last run.%s" % (label, d, depth))
            continue
        # A real move delivered as +3pp then +3pp never trips the step test, so
        # also measure against the oldest run still in the trail.
        older = [e for e in trail if e.get(key) is not None]
        cum = pp(older[0][key], cur.get(key)) if older else None
        if cum is not None and abs(cum) >= MOVE_PP:
            alerts.append("CUMULATIVE MOVE: %s has shifted %+.1f pp over the last %d runs (since "
                          "%s) without any single run crossing %.1f pp."
                          % (label, cum, len(older), older[0].get("run_utc") or "?", MOVE_PP))

    if None not in (prev.get("expected_margin_pts"), cur.get("expected_margin_pts")):
        dm = cur["expected_margin_pts"] - prev["expected_margin_pts"]
        if abs(dm) >= 0.5:
            notes.append("Market-implied margin moved %+.2f pts to D%+.2f"
                         % (dm, cur["expected_margin_pts"]))

    new_ids = set(cur.get("poll_ids", [])) - set(prev.get("poll_ids", []))
    if new_ids:
        alerts.append("NEW POLL(S): %d new PA-07 poll_id(s) in the CSV — %s"
                      % (len(new_ids), ", ".join(sorted(new_ids))))
    if cur.get("polls_general", 0) > prev.get("polls_general", 0):
        alerts.append("A new GENERAL-ELECTION poll appeared (now %d). The polling average is no "
                      "longer a single data point." % cur["polls_general"])

    # A poll revised under its existing poll_id changes the Polls sheet without
    # changing the id set — with one general poll in this race, that is the whole
    # polling average moving in silence.
    was_vals, now_vals = prev.get("poll_values") or {}, cur.get("poll_values") or {}
    for pid in sorted(set(was_vals) & set(now_vals)):
        a, b = was_vals[pid] or {}, now_vals[pid] or {}
        moved = ["%s %s -> %s" % (f, a.get(f, "-"), b.get(f, "-"))
                 for f in sorted(set(a) | set(b)) if a.get(f) != b.get(f)]
        if moved:
            alerts.append("POLL REVISED IN PLACE: %s kept its poll_id but its numbers changed — %s"
                          % (pid, "; ".join(moved)))

    for venue in ("D", "R"):
        was, now = prev.get("kalshi_status", {}).get(venue), cur.get("kalshi_status", {}).get(venue)
        if was and now and was != now:
            alerts.append("Kalshi %s market status changed: %s -> %s" % (venue, was, now))

    # History that shrank is a data loss, not a quiet Sunday. The old code only
    # tested whether the count grew and, when it had not, said something soothing.
    for key, label in SERIES_TOTALS:
        was, now = prev.get(key), cur.get(key)
        if was is None or now is None:
            continue
        if now < was:
            alerts.append("HISTORY SHRANK: %s went from %d days to %d. A fetch failed or the "
                          "upstream series was truncated — the workbook is missing data it had."
                          % (label, was, now))
        elif now == was and key == "pm_history_days":
            notes.append("Polymarket history did not gain a day — expected if this ran twice "
                         "in one UTC day.")

    for key, label in SERIES_MAPS:
        was, now = prev.get(key) or {}, cur.get(key) or {}
        for name in sorted(was):
            before = was.get(name)
            after = now.get(name)
            if not isinstance(before, int) or before == 0:
                continue
            if after is None:
                alerts.append("HISTORY SHRANK: the %s series '%s' had %d days of history last run "
                              "and is absent entirely this run." % (label, name, before))
            elif after < before:
                alerts.append("HISTORY SHRANK: %s '%s' went from %d days to %d — its history "
                              "column is short or blank this run." % (label, name, before, after))
    return notes, alerts


# ---------------------------------------------------------------------- main

def fmt(v, scale=1.0, spec="%.1f"):
    """Console formatting that survives a None — every figure here can be None
    once a market settles or a book empties."""
    return "n/a" if v is None else spec % (v * scale)


def main():
    started = datetime.datetime.utcnow()
    status = {"ok": False, "started_utc": started.isoformat(timespec="seconds") + "Z"}
    keep_new, bak = False, None
    try:
        import pollsrc
        csv_used, csv_note = pollsrc.sync()
        status["polls_csv"] = csv_used
        if csv_note:
            status["polls_csv_note"] = csv_note

        # From here on the published workbook is at risk: build4.py writes onto it.
        bak = preserve()
        status["rollback_available"] = bak is not None

        out = []
        for s in STEPS:
            out.append("%-13s %s" % (s, run(s)))
        status["steps"] = out

        audit = subprocess.run([sys.executable, "check.py"], capture_output=True, text=True, timeout=600)
        status["audit_exit"] = audit.returncode
        _out = audit.stdout.strip().splitlines()
        status["audit_tail"] = _out[-1:] or [""]
        # keep the category headings and their first few offending cells
        _detail = []
        for _i, _ln in enumerate(_out):
            if _ln.lstrip().startswith("###"):
                _detail.append(_ln.strip())
                _detail += [x.strip() for x in _out[_i + 1:_i + 4] if x.strip()]
        status["audit_detail"] = _detail[:40]

        cur = snapshot()
        prev, reset_note = load_state()
        notes, alerts = diff(prev, cur)
        if reset_note:
            notes.append(reset_note)
            alerts.append("state.json was unreadable and has been reset — this run could not diff "
                          "against the previous one. If it recurs, delete state.json by hand.")
        if status.get("polls_csv_note"):
            notes.append(status["polls_csv_note"])
        if not csv_used:
            alerts.append("No readable poll CSV — the Polls sheet could not be refreshed.")
        status.update({"snapshot": cur, "notes": notes, "alerts": alerts})

        if audit.returncode != 0:
            alerts.append("Audit found problems, so the freshly built workbook was NOT published: "
                          "the file on disk is still the last version that passed. Nothing was "
                          "archived and state.json was left alone.")
        else:
            # Commit: archive, publish and record state together. If any of this
            # throws we fall through to the rollback, so the published file can
            # never be ahead of the state we remember.
            dest, pruned = archive(started.strftime("%Y%m%dT%H%M%SZ"))
            status["archived_to"] = dest
            if pruned:
                notes.append("Pruned %d archived copy(ies) beyond the newest %d." % (pruned, ARCHIVE_KEEP))

            pub = publish()
            status["publish"] = pub
            if pub["state"] == "copied":
                status["published_to"] = pub["dest"]
            elif pub["state"] in ("linked", "same_file"):
                status["published_to"] = pub["dest"]
                notes.append("%s already resolves to this workbook — no copy needed." % pub["dest"])
            elif pub["state"] in ("failed", "stale_link"):
                status["publish_skipped"] = pub["error"]
                notes.append("Publishing to %s did not happen: %s" % (pub["dest"], pub["error"]))
                alerts.append("PUBLISH FAILED: %s is not being updated (%s). Anything reading that "
                              "path is stale." % (pub["dest"], pub["error"]))

            save_state(prev, cur)
            keep_new = True
            status["ok"] = pub["state"] not in ("failed", "stale_link")
        status["workbook"] = os.path.abspath(WB)
    except Exception as e:
        status["error"] = str(e)
        status["traceback"] = traceback.format_exc()[-3000:]
    finally:
        if keep_new:
            discard(bak)
        else:
            status["rolled_back"] = roll_back(bak)
            if bak and not status["rolled_back"]:
                status.setdefault("alerts", []).append(
                    "The run failed and the preserved workbook could not be restored — the file on "
                    "disk may be a partial build.")

    status["finished_utc"] = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    write_status(status)

    # console summary (also captured in the cron log)
    if status.get("error"):
        print("REFRESH FAILED\n" + status["error"])
        if status.get("rolled_back"):
            print("  (published workbook rolled back to the previous run's version)")
        return 1
    s = status["snapshot"]
    print("PA-07 refresh OK  (%s, %s days to election)" % (s["run_utc"], s["days_to_election"]))
    print("  consensus P(Dem) %s%%   PM %s%%  Kalshi %s%%   divergence %s pp"
          % (fmt(s["consensus_dem"], 100), fmt(s["pm_dem"], 100), fmt(s["kalshi_dem"], 100),
             fmt(s["divergence"], 100, "%+.1f")))
    print("  implied margin D%s pts   expected PA Dem seats %s   polls %d (%d general)"
          % (fmt(s["expected_margin_pts"], 1, "%+.2f"), fmt(s["expected_dem_seats"], 1, "%.2f"),
             s["polls_total"], s["polls_general"]))
    for n in status["notes"]:
        print("  note:  " + n)
    for a in status["alerts"]:
        print("  ALERT: " + a)
    if status["audit_exit"] != 0:
        print("  AUDIT PROBLEMS: %s" % status["audit_tail"])
        for _ln in status.get("audit_detail") or []:
            print("    " + _ln)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
