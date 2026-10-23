#!/usr/bin/env bash
# Watch: when the shouming driver chain exits AND pod 8190 queue is empty
# (twice, 60s apart), launch the chaofu redo batch (EP24/62/63, wenxi,
# local-only, audit-first). Launched detached; safe to leave running.
set -u
cd /home/linux_dev/projects/comfyui-h3-automation
WATCH_LOG=runs/chaofu_redo_watch.log
RUN_LOG=runs/chaofu_redo_20261021.log
SHOUMING_PIDS="240741 240746"

log() { echo "[$(date '+%F %T')] $*" >> "$WATCH_LOG"; }

queue_empty() {
  curl -sS --max-time 15 http://192.168.50.106:8190/queue 2>/dev/null | \
    python3 -c "import json,sys; d=json.load(sys.stdin); \
sys.exit(0 if not d['queue_running'] and not d['queue_pending'] else 1)"
}

log "watch start; waiting for shouming pids $SHOUMING_PIDS and empty 8190 queue"
while :; do
  alive=0
  for p in $SHOUMING_PIDS; do kill -0 "$p" 2>/dev/null && alive=1; done
  if [ "$alive" = 0 ] && queue_empty; then
    sleep 60
    if queue_empty; then
      log "shouming done + queue stable empty -> launching chaofu redo"
      break
    fi
  fi
  sleep 60
done

export COMFY_BASE_URL=http://192.168.50.106:8190
export PYTHONPATH=src
PY=.worktrees/feat-orch/.venv/bin/python
{
  echo "=== EP24 $(date '+%F %T') ==="
  $PY scripts/run_chaofu_wenxi.py --job-prefix 'EP24-潮缚-v2' \
    --units U01 U02 U03 U04 U05 U06 --local-only
  echo "=== EP62 $(date '+%F %T') ==="
  $PY scripts/run_chaofu_wenxi.py --job-prefix 'EP62-潮缚-v2' \
    --units U01 U02 U03 U04 U05 U06 U07 --local-only
  echo "=== EP63 $(date '+%F %T') ==="
  $PY scripts/run_chaofu_wenxi.py --job-prefix 'EP63-潮缚-v2' \
    --units U01 U02 U03 U04 U05 U06 --local-only
  echo "BATCH_DONE $(date '+%F %T')"
} >> "$RUN_LOG" 2>&1
log "chaofu redo batch finished (see $RUN_LOG)"
