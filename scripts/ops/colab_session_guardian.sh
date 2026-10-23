#!/bin/bash
# Session guardian: keeps the local colab-cli session handle valid.
#
# Root cause found 2026-10-22 (lihun production, two roster losses):
# the runtime proxy token in ~/.config/colab-cli/sessions.json lives
# only 3600s, and nothing in the CLI refreshes it there. After expiry
# the next name-based exec hits 404/401 and the CLI prunes the roster,
# even though the account assignment (and the VM) is still alive.
#
# This guardian prevents that: every ROTATE_S it proactively rebuilds
# the handle from the server side (fresh token via list_assignments,
# see colab_takeover_rebuild.py), and if the roster is lost anyway it
# rebuilds within one poll. It also respawns the CLI keep-alive
# daemon on each rotation and kills the previous one.
#
# Usage: colab_session_guardian.sh <session> <backup_json> [rotate_s] [poll_s]
# backup_json holds only endpoint/kernel_id/session_id (never a
# token); it is created from the live roster on first run if missing.
set -u
SESSION=${1:?session required}
BACKUP=${2:?backup json required}
ROTATE_S=${3:-2400}
POLL_S=${4:-60}
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LOG="$ROOT/runs/colab_session_guardian.log"
CLI_PY="$HOME/.local/share/uv/tools/google-colab-cli/bin/python3"
ROSTER="$HOME/.config/colab-cli/sessions.json"
mkdir -p "$(dirname "$BACKUP")"

log() { echo "$(date -u +%FT%TZ) guardian: $*" >> "$LOG"; }

session_field() { # field name -> value or empty
  python3 - "$ROSTER" "$SESSION" "$1" <<'EOF' 2>/dev/null
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    print(d.get(sys.argv[2], {}).get(sys.argv[3], "") or "")
except Exception:
    print("")
EOF
}

snapshot_backup() {
  python3 - "$ROSTER" "$SESSION" "$BACKUP" <<'EOF'
import json, sys
d = json.load(open(sys.argv[1]))
s = d[sys.argv[2]]
keep = {k: s.get(k) for k in ("name", "endpoint", "kernel_id", "session_id")}
json.dump({sys.argv[2]: keep}, open(sys.argv[3], "w"), indent=2)
EOF
}

last_rotate=$(date +%s)
[ -f "$BACKUP" ] || snapshot_backup
log "start session=$SESSION rotate=${ROTATE_S}s poll=${POLL_S}s"
while true; do
  has=$(session_field endpoint)
  kapid=$(session_field keep_alive_pid)
  alive=0
  [ -n "$kapid" ] && kill -0 "$kapid" 2>/dev/null && alive=1
  now=$(date +%s)
  need=0; why=""
  if [ -z "$has" ]; then need=1; why="roster-missing";
  elif [ $((now - last_rotate)) -ge "$ROTATE_S" ]; then need=1; why="rotate";
  elif [ "$alive" != "1" ]; then need=1; why="keep-alive-dead"; fi
  if [ "$need" = "1" ]; then
    if colab usage 2>/dev/null | grep -q "Active assignments: 0"; then
      log "assignment gone, exit"
      exit 0
    fi
    oldka=$kapid
    if "$CLI_PY" "$ROOT/scripts/ops/colab_takeover_rebuild.py" \
         "$SESSION" --backup "$BACKUP" >> "$LOG" 2>&1; then
      last_rotate=$(date +%s)
      snapshot_backup
      newka=$(session_field keep_alive_pid)
      if [ -n "$oldka" ] && [ "$oldka" != "$newka" ]; then
        kill "$oldka" 2>/dev/null || true
      fi
      log "rebuilt ($why) keep_alive_pid=$newka"
    else
      log "rebuild FAILED ($why), retry next poll"
    fi
  fi
  sleep "$POLL_S"
done
