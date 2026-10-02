#!/usr/bin/env bash
set -euo pipefail

if (( $# != 2 )); then
  echo "usage: $0 SESSION DEADLINE_UTC" >&2
  exit 2
fi

session="$1"
deadline_epoch="$(date -u -d "$2" +%s)"
if (( deadline_epoch <= $(date -u +%s) )); then
  echo "deadline must be in the future" >&2
  exit 2
fi

while :; do
  remaining=$((deadline_epoch - $(date -u +%s)))
  if (( remaining <= 0 )); then
    break
  fi
  if (( remaining > 15 )); then
    sleep 15
  else
    sleep "$remaining"
  fi
done

for attempt in 1 2 3; do
  if timeout 60 colab stop --session "$session"; then
    break
  fi
  if (( attempt == 3 )); then
    echo "failed to stop Colab session after three attempts: $session" >&2
    exit 1
  fi
  sleep 5
done

colab usage
colab sessions
