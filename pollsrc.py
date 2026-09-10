"""Locate a readable PA-07 poll CSV.

macOS TCC blocks launchd background agents from ~/Downloads, ~/Documents and
~/Desktop unless the executing binary has Full Disk Access. Opening a file there
raises PermissionError (errno 1) even though the path exists and the Unix mode
looks fine. So the canonical copy lives inside this project directory, and
anything in Downloads is treated as an optional, best-effort upgrade.
"""
import os, shutil, json, hashlib, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.join(HERE, "house.csv")
STAMP = os.path.join(HERE, "pollstamp.json")


def _readable(path):
    if not path or not os.path.exists(path):
        return False
    try:
        with open(path, "rb") as f:
            f.read(1)
        return True
    except (PermissionError, OSError):
        return False


def candidates():
    out = []
    env = os.environ.get("PA07_POLLS_CSV")
    if env:
        out.append(env)
    out.append(LOCAL)
    out.append(os.path.expanduser("~/Downloads/house.csv"))
    seen, uniq = set(), []
    for p in out:
        rp = os.path.realpath(p)
        if rp not in seen:
            seen.add(rp)
            uniq.append(p)
    return uniq


def sync():
    """Copy in a newer readable CSV from outside the project, when permitted.

    Returns (path_used, note). Never raises: under launchd the Downloads probe
    simply fails and the local copy is used.
    """
    note = None
    external = [p for p in candidates() if os.path.realpath(p) != os.path.realpath(LOCAL)]
    for ext in external:
        if not _readable(ext):
            continue
        try:
            if not os.path.exists(LOCAL) or os.path.getmtime(ext) > os.path.getmtime(LOCAL) + 1:
                shutil.copy2(ext, LOCAL)
                note = "Imported a newer poll CSV from %s" % ext
            break
        except OSError:
            continue

    if _readable(LOCAL):
        return LOCAL, note
    for p in candidates():
        if _readable(p):
            return p, "Using %s directly; no local copy available." % p
    return None, "No readable poll CSV found. Looked in: %s" % ", ".join(candidates())


def resolve():
    """Path only, no copying — for builders that just need to read."""
    for p in candidates():
        if _readable(p):
            return p
    raise FileNotFoundError("No readable poll CSV. Looked in: %s" % ", ".join(candidates()))


# ---------------------------------------------------------------- content age
# mtime answers "is there a newer file to import?" and nothing else. It cannot
# answer "how old is this polling data?", because the copy2 above — and any
# re-download or backup of a byte-identical file — hands the local copy a fresh
# mtime while leaving every poll exactly as it was. Age is therefore measured on
# the content: fingerprint the PA-07 rows, and remember when that fingerprint
# first appeared.

def content_digest(rows):
    """Fingerprint of what the PA-07 rows actually say — which polls, and their
    reported numbers. Field order and file layout deliberately do not count."""
    key = sorted([r.get("poll_id", ""), r.get("question_id", ""), r.get("answer", ""),
                  r.get("candidate_name", ""), r.get("pct", ""), r.get("stage", ""),
                  r.get("end_date", "")] for r in rows)
    return hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()


def content_stamp(digest, now=None):
    """(first_seen_utc_iso, changed) for this digest, persisted in pollstamp.json.

    Never raises: an unwritable or corrupt stamp file degrades to "first seen
    now", which is the same answer a fresh install gives.
    """
    now = now or datetime.datetime.utcnow()
    iso = now.isoformat(timespec="seconds") + "Z"
    prev = {}
    try:
        with open(STAMP) as f:
            prev = json.load(f)
    except (ValueError, OSError):
        prev = {}
    if isinstance(prev, dict) and prev.get("digest") == digest and prev.get("first_seen_utc"):
        return prev["first_seen_utc"], False
    try:
        with open(STAMP, "w") as f:
            json.dump({"digest": digest, "first_seen_utc": iso}, f, indent=1)
    except OSError:
        pass
    return iso, True


def content_age_days(first_seen_utc, now=None):
    """Whole days since the poll content last changed, or None if unknown."""
    if not first_seen_utc:
        return None
    try:
        seen = datetime.datetime.fromisoformat(first_seen_utc.rstrip("Z"))
    except (ValueError, AttributeError):
        return None
    return ((now or datetime.datetime.utcnow()) - seen).days
