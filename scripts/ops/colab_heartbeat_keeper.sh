#!/bin/bash
# Independent Colab keep-alive keeper.
#
# Why this exists (2026-10-22 lihun incident): Colab only keeps a
# runtime alive while a local CLI process is connected. A batch host
# that dies (or whose execs all return) silently drops the last
# connection and Google recycles the VM ~15-20 min later, killing
# in-flight renders. The orphan guard cannot prevent this — it only
# watches billing. So keep-alive is its own detached process:
# a light exec every INTERVAL seconds, independent of any supervisor.
#
# Usage: colab_heartbeat_keeper.sh <session> <stop_file> [interval_s]
# Exits when the stop file appears or the account shows no active
# assignment. While an assignment remains active it keeps retrying:
# a probe queued behind a long batch exec can exceed the CLI's own
# execution timeout, so queueing failures must not be treated as
# session loss (the paid watchdog remains the hard billing cap).
set -u
SESSION=${1:?session required}
STOP_FILE=${2:?stop file required}
INTERVAL=${3:-120}
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PROBE="$ROOT/scripts/ops/colab_keepalive_probe.py"
LOG="$ROOT/runs/colab_heartbeat_keeper.log"
fails=0
echo "$(date -u +%FT%TZ) keeper start session=$SESSION interval=${INTERVAL}s" >> "$LOG"
while true; do
  if [ -f "$STOP_FILE" ]; then
    echo "$(date -u +%FT%TZ) keeper: stop flag, exit" >> "$LOG"
    exit 0
  fi
  echo "$(date -u +%FT%TZ) keeper: attempt $SESSION" >> "$LOG"
  # `timeout 150` is a local hard bound: the CLI's --timeout does not
  # include time spent queued behind a busy kernel.
  out=$(timeout 150 colab exec --session "$SESSION" --file "$PROBE" \
        --timeout 90 2>&1 || true)
  if echo "$out" | grep -q H3_KEEPALIVE_OK; then
    fails=0
    echo "$(date -u +%FT%TZ) keeper: ok $SESSION" >> "$LOG"
  else
    fails=$((fails + 1))
    echo "$(date -u +%FT%TZ) keeper: exec fail x$fails $SESSION" >> "$LOG"
    if colab usage 2>/dev/null | grep -q "Active assignments: 0"; then
      echo "$(date -u +%FT%TZ) keeper: session gone, exit" >> "$LOG"
      exit 0
    fi
    echo "$(date -u +%FT%TZ) keeper: assignment still active, retrying" \
      >> "$LOG"
  fi
  sleep "$INTERVAL"
done
