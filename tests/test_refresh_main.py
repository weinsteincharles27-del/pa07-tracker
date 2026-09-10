"""CROSS-1 (build to staging, commit or roll back), CROSS-2 (status.json is
never left stale), FS-2/FS-3 (archive naming, gating and retention), FS-5
(corrupt state self-heals) and FS-6 (publishing is actually reported).

These drive refresh.main() end to end with the network, the builders and the
auditor all replaced, so only the orchestration is under test.
"""
import contextlib
import json
import os
import re
import shutil

import support

refresh = support.load("refresh")
pollsrc = support.load("pollsrc")

CSV = os.path.join(support.FIX, "house_pa07.csv")
OLD, NEW = b"OLD-WORKBOOK", b"NEW-WORKBOOK"


class Completed(object):
    def __init__(self, rc, out="TOTAL PROBLEMS: 0"):
        self.returncode, self.stdout, self.stderr = rc, out, ""


def builder(content=NEW, fail_on=None):
    """Stand-in for run(): build4.py is the step that writes the published file."""
    def fake(script):
        if script == fail_on:
            raise RuntimeError("%s failed (exit 1)" % script)
        if script == "build4.py":
            with open(refresh.WB, "wb") as f:
                f.write(content)
        return "ok"
    return fake


@contextlib.contextmanager
def staged(audit_rc=0, content=NEW, wb=OLD, publish_to=None, fail_on=None,
           snapshot=None, dump=None, state=None):
    """A sandbox with a published workbook, a fake builder and a fake auditor."""
    with support.sandbox(data=True, workbook=wb) as d:
        if state is not None:
            with open(os.path.join(d, "state.json"), "w") as f:
                f.write(state)
        os.environ["PA07_POLLS_CSV"] = CSV
        patches = [
            support.attrs(refresh, run=builder(content, fail_on),
                          HERE=d, PUBLISH=publish_to or d),
            support.attrs(refresh.subprocess, run=lambda *a, **k: Completed(audit_rc)),
            support.attrs(pollsrc, LOCAL=os.path.join(d, "house.csv"),
                          STAMP=os.path.join(d, "pollstamp.json")),
        ]
        if snapshot is not None:
            patches.append(support.attrs(refresh, snapshot=snapshot))
        if dump is not None:
            patches.append(support.attrs(refresh.json, dump=dump))
        try:
            with contextlib.ExitStack() as stack:
                for p in patches:
                    stack.enter_context(p)
                yield d
        finally:
            os.environ.pop("PA07_POLLS_CSV", None)


def wb_bytes():
    with open(refresh.WB, "rb") as f:
        return f.read()


def archives():
    return sorted(os.listdir("archive"))


# ------------------------------------------------------------------- CROSS-1

def test_cross1_a_failure_after_the_build_leaves_the_published_file_alone():
    """The whole point: the user's workbook must not change unless the run that
    changed it also archived it and recorded its numbers."""
    def boom():
        raise ValueError("min() arg is an empty sequence")
    with staged(snapshot=boom) as d:
        rc = refresh.main()
        assert rc == 1, rc
        assert wb_bytes() == OLD, "the published workbook was overwritten by a failed run"
        assert archives() == [], "a failed run archived something"
        assert not os.path.exists("state.json"), "state was recorded for a failed run"
        status = support.read_json("status.json")
        assert status["ok"] is False
        assert status["rolled_back"] is True
        assert not os.path.exists(refresh.PRESERVED), "the rollback copy was left behind"


def test_cross1_an_audit_failure_does_not_publish_the_bad_build():
    with staged(audit_rc=1) as d:
        rc = refresh.main()
        assert rc == 2, rc
        assert wb_bytes() == OLD, "an audit-failing build replaced the good workbook"
        assert archives() == [], "an audit-failing build replaced a clean archived copy"
        status = support.read_json("status.json")
        assert status["ok"] is False
        assert any("NOT published" in a for a in status["alerts"]), status["alerts"]
        # the run still reports what it saw
        assert status["snapshot"]["polls_total"] == 5


def test_cross1_a_build_failure_leaves_the_published_file_alone():
    with staged(fail_on="build2.py"):
        rc = refresh.main()
        assert rc == 1, rc
        assert wb_bytes() == OLD
        assert not os.path.exists(refresh.PRESERVED)


def test_cross1_a_clean_run_commits_workbook_archive_and_state_together():
    with staged():
        rc = refresh.main()
        assert rc == 0, rc
        assert wb_bytes() == NEW
        assert len(archives()) == 1
        assert support.read_json("state.json")["polls_total"] == 5
        assert not os.path.exists(refresh.PRESERVED)
        assert support.read_json("status.json")["ok"] is True


def test_cross1_state_never_lags_the_published_workbook():
    """Two runs: the second fails late. The file on disk and the recorded
    snapshot must still describe the same build."""
    with staged() as d:
        assert refresh.main() == 0
        first_state = support.read_json("state.json")
        with support.attrs(refresh, run=builder(b"SECOND"),
                           snapshot=lambda: (_ for _ in ()).throw(RuntimeError("late failure"))):
            assert refresh.main() == 1
        assert wb_bytes() == NEW, "the published file moved on without the state"
        assert support.read_json("state.json")["run_utc"] == first_state["run_utc"]


def test_cross1_rollback_is_a_rename_not_a_copy():
    with support.sandbox(workbook=OLD) as d:
        bak = refresh.preserve()
        with open(refresh.WB, "wb") as f:
            f.write(NEW)
        assert refresh.roll_back(bak) is True
        assert wb_bytes() == OLD
        assert not os.path.exists(bak), "os.replace should consume the preserved copy"


# ------------------------------------------------------------------- CROSS-2

def test_cross2_a_failed_status_write_does_not_leave_the_previous_run_standing():
    """status.json is all the scheduler reads; it must never keep saying ok:true
    because the write that should have replaced it threw."""
    real = json.dump
    seen = []

    def flaky(obj, fp, **kw):
        name = getattr(fp, "name", "")
        if "status.json" in name and not seen:
            seen.append(name)
            raise OSError(28, "No space left on device")
        return real(obj, fp, **kw)

    with staged(dump=flaky) as d:
        with open("status.json", "w") as f:
            f.write(json.dumps({"ok": True, "marker": "PREVIOUS RUN"}))
        refresh.main()                       # must not raise
        status = support.read_json("status.json")
    assert status["ok"] is False, status
    assert "marker" not in status, "the previous run's status.json survived"
    assert "could not be written" in status["error"], status
    assert not os.path.exists("status.json.tmp")


def test_cross2_write_status_is_atomic():
    with support.sandbox():
        with open("status.json", "w") as f:
            json.dump({"ok": True, "marker": "PREVIOUS RUN"}, f)
        assert refresh.write_status({"ok": True, "n": 1}) is True
        assert support.read_json("status.json") == {"ok": True, "n": 1}
        assert not os.path.exists("status.json.tmp")


# ---------------------------------------------------------------------- FS-2

def test_fs2_archive_name_carries_the_run_time():
    with staged():
        assert refresh.main() == 0
        name = archives()[0]
    assert re.match(r"PA-07_tracker_\d{8}T\d{6}Z\.xlsx$", name), name


def test_fs2_two_runs_on_the_same_day_keep_both_copies():
    with support.sandbox(workbook=OLD):
        refresh.archive("20260829T071200Z")
        refresh.archive("20260829T131200Z")
        assert len(archives()) == 2, archives()


# ---------------------------------------------------------------------- FS-3

def test_fs3_archive_retention_is_bounded():
    with support.sandbox(workbook=OLD):
        for i in range(8):
            with open(os.path.join("archive", "PA-07_tracker_2026080%dT000000Z.xlsx" % i), "wb") as f:
                f.write(b"x")
        with support.attrs(refresh, ARCHIVE_KEEP=3):
            dest, pruned = refresh.archive("20260829T190000Z")
        kept = archives()
        assert len(kept) == 3, kept
        assert pruned == 6, pruned
        assert os.path.basename(dest) in kept, "the newest copy was pruned"


# ---------------------------------------------------------------------- FS-5

def test_fs5_corrupt_state_is_reset_rather_than_wedging_every_future_run():
    with staged(state="{ this is not json") as d:
        rc = refresh.main()
        assert rc == 0, rc
        status = support.read_json("status.json")
        assert status["ok"] is True
        assert any("state.json" in n for n in status["notes"]), status["notes"]
        assert any("reset" in a for a in status["alerts"]), status["alerts"]
        # and it self-heals: the next run has something to diff against
        assert support.read_json("state.json")["polls_total"] == 5


def test_fs5_load_state_keeps_the_unreadable_copy_for_inspection():
    with support.sandbox():
        with open("state.json", "w") as f:
            f.write("{ truncated")
        prev, note = refresh.load_state()
        assert prev is None and "reset" in note
        assert os.path.exists("state.json.corrupt")


def test_fs5_a_healthy_state_file_is_untouched():
    with support.sandbox():
        support.write_json("state.json", {"polls_total": 5})
        prev, note = refresh.load_state()
        assert prev == {"polls_total": 5} and note is None
        assert not os.path.exists("state.json.corrupt")


# ---------------------------------------------------------------------- FS-6

def test_fs6_a_symlinked_downloads_copy_is_success_not_a_silent_skip():
    """~/Downloads holds a symlink back to this file, so copy2 raises
    SameFileError on every run — an OSError, previously indistinguishable from
    the TCC denial it was meant to catch, and never surfaced either way."""
    with staged() as d:
        pub = os.path.join(d, "pub")
        os.mkdir(pub)
        os.symlink(os.path.join(d, refresh.WB), os.path.join(pub, refresh.WB))
        with support.attrs(refresh, PUBLISH=pub):
            assert refresh.main() == 0
        status = support.read_json("status.json")
    assert "publish_skipped" not in status, status.get("publish_skipped")
    assert status["publish"]["state"] == "linked", status["publish"]
    assert any("resolves to this workbook" in n for n in status["notes"]), status["notes"]
    assert status["ok"] is True


def test_fs6_a_permission_denial_is_loud_and_marks_the_run_not_ok():
    with staged() as d:
        pub = os.path.join(d, "pub")
        os.mkdir(pub, 0o500)
        try:
            with support.attrs(refresh, PUBLISH=pub):
                refresh.main()
            status = support.read_json("status.json")
        finally:
            os.chmod(pub, 0o700)
    assert status["publish"]["state"] == "failed", status["publish"]
    assert any("PUBLISH FAILED" in a for a in status["alerts"]), status["alerts"]
    assert any("did not happen" in n for n in status["notes"]), status["notes"]
    assert status["ok"] is False, "Downloads can go stale for weeks while ok stays true"


def test_fs6_a_symlink_pointing_somewhere_else_is_detected():
    with staged() as d:
        pub = os.path.join(d, "pub")
        os.mkdir(pub)
        other = os.path.join(d, "not-the-workbook.xlsx")
        with open(other, "wb") as f:
            f.write(b"other")
        os.symlink(other, os.path.join(pub, refresh.WB))
        with support.attrs(refresh, PUBLISH=pub):
            refresh.main()
        status = support.read_json("status.json")
    assert status["publish"]["state"] == "stale_link", status["publish"]
    assert any("PUBLISH FAILED" in a for a in status["alerts"]), status["alerts"]
    assert status["ok"] is False


def test_fs6_a_real_copy_still_works():
    with staged() as d:
        pub = os.path.join(d, "pub")
        os.mkdir(pub)
        with support.attrs(refresh, PUBLISH=pub):
            assert refresh.main() == 0
        status = support.read_json("status.json")
        with open(os.path.join(pub, refresh.WB), "rb") as f:
            assert f.read() == NEW
    assert status["publish"]["state"] == "copied", status["publish"]
    assert status["ok"] is True
