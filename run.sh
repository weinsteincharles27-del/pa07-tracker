#!/bin/bash
# PA-07 tracker — scheduled refresh wrapper.
# Invoked by launchd (com.charlieweinstein.pa07-tracker). Safe to run by hand.

set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR" || exit 1

LOG="$DIR/logs/refresh.log"
LOCK="$DIR/logs/run.lock"
mkdir -p "$DIR/logs" "$DIR/archive"

skip() {
  echo "===== $(date -u '+%Y-%m-%dT%H:%M:%SZ') refresh already running (lock $LOCK) — skipping ====="
  exit 0
}

# One run at a time. RunAtLoad fires on every login and wake and can land on top
# of a calendar slot, and a slow run can still be going when the next one starts.
# Two of those share _stage1..4.xlsx, data.json and the ref JSONs, and both call
# wb.save() on the same path — the result is a workbook stitched from two runs,
# or a corrupt zip.
#
# lockf(1) is the flock(2) wrapper macOS ships (shlock is deprecated, and will
# not break a lock left by a killed run). The kernel drops the lock however the
# process ends, so there is no stale-lock case to reason about. Re-exec once
# under the lock rather than holding a descriptor open by hand.
if [ -z "${PA07_RUN_LOCKED:-}" ]; then
  export PA07_RUN_LOCKED=1
  if command -v lockf >/dev/null 2>&1; then
    lockf -k -s -t 0 "$LOCK" "$0" "$@"
    rc=$?
    [ $rc -eq 75 ] && skip >> "$LOG"      # EX_TEMPFAIL: someone else holds it
    exit $rc
  fi
  # Fallback for a system without lockf: mkdir is atomic. Only clear the lock if
  # the process that recorded it is gone.
  if ! mkdir "$LOCK.d" 2>/dev/null; then
    pid="$(cat "$LOCK.d/pid" 2>/dev/null || true)"
    if [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null; then skip >> "$LOG"; fi
    rm -rf "$LOCK.d"
    mkdir "$LOCK.d" 2>/dev/null || skip >> "$LOG"
  fi
  echo $$ > "$LOCK.d/pid"
  trap 'rm -rf "$LOCK.d"' EXIT
fi

# Numbered rotation once a log passes ~512 KB, keeping five generations. The old
# single-level rotation threw .1 away every time it fired.
# $3 = "truncate" for the launchd logs: launchd holds those descriptors open and
# would keep writing into the renamed inode, so copy the contents out instead.
rotate() {
  local f="$1" keep="$2" mode="${3:-move}" i
  [ -f "$f" ] || return 0
  [ "$(wc -c < "$f")" -gt 524288 ] || return 0
  rm -f "$f.$keep"
  for ((i=keep-1; i>=1; i--)); do
    [ -f "$f.$i" ] && mv -f "$f.$i" "$f.$((i+1))"
  done
  if [ "$mode" = "truncate" ]; then
    cp "$f" "$f.1" && : > "$f"
  else
    mv -f "$f" "$f.1"
  fi
  return 0
}
rotate "$LOG" 5
rotate "$DIR/logs/launchd.out" 3 truncate
rotate "$DIR/logs/launchd.err" 3 truncate

# Where the poll CSV lives, and where the finished workbook gets published.
export PA07_POLLS_CSV="${PA07_POLLS_CSV:-$HOME/Downloads/house.csv}"
export PA07_PUBLISH_TO="${PA07_PUBLISH_TO:-$HOME/Downloads}"
export KALSHI_KEY_PATH="${KALSHI_KEY_PATH:-$DIR/kalshi_key.pem}"

{
  echo "===== $(date -u '+%Y-%m-%dT%H:%M:%SZ') starting refresh ====="
  /usr/bin/python3 "$DIR/refresh.py" 2>&1 | grep -v "NotOpenSSLWarning\|warnings.warn"
  rc=${PIPESTATUS[0]}
  echo "----- exit $rc -----"
  exit $rc
} >> "$LOG" 2>&1
