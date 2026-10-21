#!/bin/bash
# Account-level Colab orphan guard.
#
# Watches `colab usage` (account state, NOT the fragile local session map).
# A production host touches HEARTBEAT at least once per phase/render. If an
# assignment is active while the heartbeat is stale beyond GRACE_MIN, the
# runtime is either orphaned (host died / CLI lost the session) or idle-kept:
# log COLAB_ORPHAN_ALERT. With AUTO_UNASSIGN=1, once stale beyond HARD_MIN it
# stops the single assignment server-side via colab_unassign.py.
#
# Usage:
#   HEARTBEAT=runs/<batch>_heartbeat AUTO_UNASSIGN=1 \
#     bash scripts/ops/colab_orphan_guard.sh
# Env: GRACE_MIN=10 HARD_MIN=30 POLL_S=120 LOG=runs/colab_orphan_guard.log
set -u
cd "$(dirname "$0")/../.."
HEARTBEAT=${HEARTBEAT:?set HEARTBEAT to the file the production host touches}
GRACE_MIN=${GRACE_MIN:-10}
HARD_MIN=${HARD_MIN:-30}
POLL_S=${POLL_S:-120}
AUTO_UNASSIGN=${AUTO_UNASSIGN:-0}
LOG=${LOG:-runs/colab_orphan_guard.log}
CLI_PY="$HOME/.local/share/uv/tools/google-colab-cli/bin/python3"
mkdir -p "$(dirname "$LOG")"
log() { echo "$(date -u +%FT%TZ) ORPHAN_GUARD $*" >> "$LOG"; echo "$*"; }

log "start heartbeat=$HEARTBEAT grace=${GRACE_MIN}m hard=${HARD_MIN}m auto=$AUTO_UNASSIGN"
alerted=0
while true; do
  usage=$(colab usage 2>/dev/null)
  active=$(echo "$usage" | grep -oE "Active assignments: [0-9]+" | grep -oE "[0-9]+$" || echo "?")
  if [ "$active" = "0" ]; then
    log "active=0, guard exit (nothing billing)"
    exit 0
  fi
  if [ "$active" = "?" ]; then sleep "$POLL_S"; continue; fi
  now=$(date +%s)
  hb=$(stat -c %Y "$HEARTBEAT" 2>/dev/null || echo 0)
  age_min=$(( (now - hb) / 60 ))
  if [ "$age_min" -lt "$GRACE_MIN" ]; then
    alerted=0
  else
    if [ "$alerted" = "0" ]; then
      log "COLAB_ORPHAN_ALERT active=$active heartbeat_age=${age_min}m (check production host; terminate in web UI or run colab_unassign.py)"
      alerted=1
    fi
    if [ "$AUTO_UNASSIGN" = "1" ] && [ "$age_min" -ge "$HARD_MIN" ]; then
      log "auto-unassign: heartbeat stale ${age_min}m >= ${HARD_MIN}m"
      if [ -x "$CLI_PY" ]; then
        "$CLI_PY" scripts/ops/colab_unassign.py --execute >> "$LOG" 2>&1 \
          && log "auto-unassign done" || log "auto-unassign FAILED (see above)"
      else
        log "auto-unassign FAILED: colab-cli python not at $CLI_PY"
      fi
      sleep "$POLL_S"
    fi
  fi
  sleep "$POLL_S"
done
