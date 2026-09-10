"""FS-1 (one run at a time) and FS-4 (numbered, non-lossy log rotation).

run.sh is copied into a sandbox next to a stub refresh.py, so the lock and the
rotation are exercised without touching the network or the real project.
"""
import os
import shutil
import subprocess
import time

import support

RUN_SH = os.path.join(support.SRC, "run.sh")


def stage(d, stub="print('STUB REFRESH RAN')"):
    shutil.copy(RUN_SH, os.path.join(d, "run.sh"))
    os.chmod(os.path.join(d, "run.sh"), 0o755)
    with open(os.path.join(d, "refresh.py"), "w") as f:
        f.write(stub + "\n")
    return os.path.join(d, "run.sh")


def invoke(path, **env):
    e = dict(os.environ)
    e.update({"PA07_PUBLISH_TO": os.path.dirname(path), "HOME": os.path.dirname(path)})
    e.update(env)
    return subprocess.run(["/bin/bash", path], capture_output=True, text=True, env=e, timeout=120)


def log(d):
    p = os.path.join(d, "logs", "refresh.log")
    if not os.path.exists(p):
        return ""
    with open(p) as f:
        return f.read()


# ---------------------------------------------------------------------- FS-1

def hold(lock):
    """Take the same advisory lock run.sh takes, and wait until it is really ours."""
    holder = subprocess.Popen(["/usr/bin/lockf", "-k", "-s", "-t", "60", lock, "/bin/sleep", "60"])
    for _ in range(100):
        probe = subprocess.run(["/usr/bin/lockf", "-s", "-t", "0", lock, "/usr/bin/true"])
        if probe.returncode == 75:
            return holder
        time.sleep(0.05)
    holder.kill()
    raise AssertionError("could not get the holder to take the lock")


def test_fs1_a_second_run_exits_cleanly_instead_of_piling_up():
    """RunAtLoad fires on every wake and can land on a calendar slot. Two runs
    share _stage1..4.xlsx, data.json and the ref JSONs, and both call wb.save()
    on the same path."""
    with support.sandbox() as d:
        sh = stage(d)
        os.makedirs(os.path.join(d, "logs"), exist_ok=True)
        holder = hold(os.path.join(d, "logs", "run.lock"))
        try:
            r = invoke(sh)
            body = log(d)
        finally:
            holder.kill()
            holder.wait()
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    assert "already running" in body, body
    assert "STUB REFRESH RAN" not in body, "a second concurrent run went ahead anyway"


def test_fs1_the_lock_is_released_so_the_next_run_proceeds():
    with support.sandbox() as d:
        sh = stage(d)
        first = invoke(sh)
        second = invoke(sh)
        body = log(d)
    assert first.returncode == 0 and second.returncode == 0
    assert body.count("STUB REFRESH RAN") == 2, body
    assert "already running" not in body, body


def test_fs1_a_lock_file_left_by_a_killed_run_does_not_wedge_the_scheduler():
    """The lock is advisory and held by the kernel, so a file left behind by a
    run that was killed is not a lock — the next run must take it."""
    with support.sandbox() as d:
        sh = stage(d)
        os.makedirs(os.path.join(d, "logs"), exist_ok=True)
        with open(os.path.join(d, "logs", "run.lock"), "w") as f:
            f.write("leftover from a killed run\n")
        r = invoke(sh)
        body = log(d)
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "STUB REFRESH RAN" in body, body


def test_fs1_the_wrapper_still_reports_the_refresh_exit_code():
    with support.sandbox() as d:
        sh = stage(d, "import sys; print('STUB REFRESH RAN'); sys.exit(2)")
        r = invoke(sh)
        body = log(d)
    assert r.returncode == 2, (r.returncode, body)
    assert "----- exit 2 -----" in body, body


# ---------------------------------------------------------------------- FS-4

def test_fs4_log_rotation_keeps_generations_instead_of_discarding_them():
    with support.sandbox() as d:
        sh = stage(d)
        logs = os.path.join(d, "logs")
        os.makedirs(logs, exist_ok=True)
        with open(os.path.join(logs, "refresh.log"), "w") as f:
            f.write("A" * 600000)
        with open(os.path.join(logs, "refresh.log.1"), "w") as f:
            f.write("older generation")
        invoke(sh)
        names = sorted(os.listdir(logs))
        with open(os.path.join(logs, "refresh.log.2")) as f:
            second = f.read()
    assert "refresh.log.1" in names and "refresh.log.2" in names, names
    assert second == "older generation", "the previous generation was thrown away"


def test_fs4_launchd_logs_rotate_by_copying_so_the_open_descriptor_survives():
    with support.sandbox() as d:
        sh = stage(d)
        logs = os.path.join(d, "logs")
        os.makedirs(logs, exist_ok=True)
        for name in ("launchd.out", "launchd.err"):
            with open(os.path.join(logs, name), "w") as f:
                f.write("B" * 600000)
            before = os.stat(os.path.join(logs, name)).st_ino
            invoke(sh)
            after = os.stat(os.path.join(logs, name))
            assert after.st_size == 0, name
            assert after.st_ino == before, "%s was renamed; launchd would keep writing to the old inode" % name
            assert os.path.getsize(os.path.join(logs, name + ".1")) == 600000


def test_fs4_a_small_log_is_left_alone():
    with support.sandbox() as d:
        sh = stage(d)
        invoke(sh)
        names = os.listdir(os.path.join(d, "logs"))
    assert "refresh.log.1" not in names, names
