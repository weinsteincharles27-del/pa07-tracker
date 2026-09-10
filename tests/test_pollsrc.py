"""ALERT-1: poll staleness must be measured on content, not on mtime.

shutil.copy2 in sync() — and any re-download or backup of a byte-identical file —
gives the local copy a fresh mtime while leaving every poll untouched, which used
to reset the 14-day clock forever.
"""
import datetime
import os
import shutil
import time

import support

pollsrc = support.load("pollsrc")
refresh = support.load("refresh")

CSV = os.path.join(support.FIX, "house_pa07.csv")


def rows(path=CSV, pct=None):
    import csv
    with open(path) as f:
        out = [r for r in csv.DictReader(f) if r.get("state") == "PA" and r.get("seat_number") == "7"]
    if pct is not None:
        out[0]["pct"] = pct
    return out


def test_alert1_a_content_neutral_recopy_does_not_reset_the_clock():
    """The bug in one line: re-importing the same file used to make the polls
    look brand new."""
    with support.sandbox() as d:
        local = os.path.join(d, "house.csv")
        stamp = os.path.join(d, "pollstamp.json")
        shutil.copy2(CSV, local)
        with support.attrs(pollsrc, LOCAL=local, STAMP=stamp):
            old = datetime.datetime.utcnow() - datetime.timedelta(days=40)
            first, changed = pollsrc.content_stamp(pollsrc.content_digest(rows(local)), now=old)
            assert changed is True

            # a fresh download of the identical file: new mtime, same polls
            shutil.copy2(CSV, local)
            os.utime(local, None)
            again, changed = pollsrc.content_stamp(pollsrc.content_digest(rows(local)))
            assert changed is False
            assert again == first, "the content clock restarted on an unchanged file"
            assert pollsrc.content_age_days(again) >= 40

            mtime_age = (datetime.datetime.utcnow()
                         - datetime.datetime.utcfromtimestamp(os.path.getmtime(local))).days
            assert mtime_age == 0, "mtime really was reset — that is why it cannot be trusted"


def test_alert1_changed_percentages_restart_the_clock():
    with support.sandbox() as d:
        with support.attrs(pollsrc, STAMP=os.path.join(d, "pollstamp.json")):
            old = datetime.datetime.utcnow() - datetime.timedelta(days=40)
            pollsrc.content_stamp(pollsrc.content_digest(rows()), now=old)
            fresh, changed = pollsrc.content_stamp(pollsrc.content_digest(rows(pct="99")))
            assert changed is True
            assert pollsrc.content_age_days(fresh) == 0


def test_alert1_stale_content_raises_the_alert():
    old = (datetime.datetime.utcnow() - datetime.timedelta(days=40)).isoformat(timespec="seconds") + "Z"
    cur = {"polls_content_age_days": 40, "polls_content_since": old, "run_utc": "x"}
    notes, alerts = refresh.diff(None, cur)
    hit = [a for a in alerts if "Poll CSV content is" in a]
    assert hit, alerts
    assert "40 days old" in hit[0], hit


def test_alert1_fresh_content_does_not_alert():
    cur = {"polls_content_age_days": 2, "polls_content_since": "2026-08-27T00:00:00Z"}
    notes, alerts = refresh.diff(None, cur)
    assert not any("Poll CSV content" in a for a in alerts), alerts


def test_alert1_an_unwritable_stamp_file_does_not_break_the_run():
    with support.sandbox() as d:
        with support.attrs(pollsrc, STAMP=os.path.join(d, "no-such-dir", "pollstamp.json")):
            seen, changed = pollsrc.content_stamp("abc")
            assert changed is True and seen


def test_sync_still_imports_a_genuinely_newer_csv():
    """The mtime comparison stays: it is the right tool for 'is there a new file'."""
    with support.sandbox() as d:
        local = os.path.join(d, "house.csv")
        ext = os.path.join(d, "external.csv")
        shutil.copy(CSV, ext)
        with open(local, "w") as f:
            f.write("state,seat_number\n")
        os.utime(local, (time.time() - 3600, time.time() - 3600))
        os.environ["PA07_POLLS_CSV"] = ext
        try:
            with support.attrs(pollsrc, LOCAL=local):
                used, note = pollsrc.sync()
        finally:
            os.environ.pop("PA07_POLLS_CSV", None)
        assert note and "Imported a newer poll CSV" in note, note
        with open(local) as f:
            assert "poll_id" in f.readline()
