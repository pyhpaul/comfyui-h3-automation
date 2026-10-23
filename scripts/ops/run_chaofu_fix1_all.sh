#!/usr/bin/env bash
# Chaofu fix1 full run: every fix unit rendered twice —
#   A) original workflow (yz_h3_ep_unit, run_ep_units_profiled.py)
#   B) wenxi chain (run_chaofu_wenxi.py)
# Both archive to Feiniu batch 潮缚修复（10.20） (wenxi under <U>-WENXI).
# Sequential, continue-on-error; per-invocation logs in runs/chaofu_fix1/.
# EP23-U05 A-side already done (prompt 77a84615, recovered) — skipped here;
# its B-side pilot is run separately before this script.
set -u
cd /home/linux_dev/projects/comfyui-h3-automation
export COMFY_BASE_URL=http://192.168.50.106:8190
export PYTHONPATH=src
PY=.worktrees/feat-orch/.venv/bin/python
BATCH='潮缚修复（10.20）'
LOG=runs/chaofu_fix1
mkdir -p "$LOG"

run() { # name, then command...
  local name="$1"; shift
  echo "=== $name $(date +%H:%M:%S) ==="
  if "$@" > "$LOG/$name.log" 2>&1; then
    echo "OK $name"
  else
    echo "FAIL $name (see $LOG/$name.log)"
  fi
}

orig() { # glob units [parent]
  local glob="$1" units="$2" parent="${3:-}"
  local args=(--units $units --job-glob "$glob" --continuity motion_latent
              --feiniu-batch "$BATCH")
  [ -n "$parent" ] && args+=(--parent-latent "h3_context/$parent")
  run "orig_${glob%%-*}_${units// /_}" $PY scripts/run_ep_units_profiled.py "${args[@]}"
}

wenxi() { # prefix units [parent]
  local prefix="$1" units="$2" parent="${3:-}"
  local args=(--job-prefix "$prefix" --units $units --feiniu-batch "$BATCH")
  [ -n "$parent" ] && args+=(--parent-latent "h3_context/$parent")
  run "wenxi_${prefix%%-*}_${units// /_}" $PY scripts/run_chaofu_wenxi.py "${args[@]}"
}

# ---- A side: dialogue singles ----
# EP06-U04 A-side done 2026-10-20 (prompt b471cf26, recovered to Feiniu).
# orig 'EP06-潮缚-fix1-{unit}' U04 ep06_u03_00003.safetensors
orig 'EP23-潮缚-fix1-{unit}' U01
orig 'EP33-潮缚-fix1-{unit}' U01
orig 'EP41-潮缚-fix1-{unit}' U05 ep41_u04_00004.safetensors
orig 'EP42-潮缚-fix1-{unit}' U02 ep42_u01_00001.safetensors
orig 'EP42-潮缚-fix1-{unit}' U04 ep42_u03_00003.safetensors
orig 'EP43-潮缚-fix1-{unit}' U05 ep43_u04_00004.safetensors
orig 'EP50-潮缚-fix1-{unit}' U02 ep50_u01_00001.safetensors
orig 'EP51-潮缚-fix1-{unit}' U06 ep51_u05_00005.safetensors
orig 'EP53-潮缚-fix1-{unit}' U05 ep53_u04_00004.safetensors
# ---- A side: full episodes ----
orig 'EP24-潮缚-fix1-{unit}' 'U01 U02 U03 U04 U05 U06'
orig 'EP62-潮缚-v1-{unit}' 'U01 U02 U03 U04 U05 U06 U07'
orig 'EP63-潮缚-v1-{unit}' 'U01 U02 U03 U04 U05 U06'

# ---- B side: dialogue singles ----
wenxi 'EP06-潮缚-fix1' U04 ep06_u03_00003.safetensors
wenxi 'EP23-潮缚-fix1' U05 ep23_u04_00004.safetensors
wenxi 'EP23-潮缚-fix1' U01
wenxi 'EP33-潮缚-fix1' U01
wenxi 'EP41-潮缚-fix1' U05 ep41_u04_00004.safetensors
wenxi 'EP42-潮缚-fix1' U02 ep42_u01_00001.safetensors
wenxi 'EP42-潮缚-fix1' U04 ep42_u03_00003.safetensors
wenxi 'EP43-潮缚-fix1' U05 ep43_u04_00004.safetensors
wenxi 'EP50-潮缚-fix1' U02 ep50_u01_00001.safetensors
wenxi 'EP51-潮缚-fix1' U06 ep51_u05_00005.safetensors
wenxi 'EP53-潮缚-fix1' U05 ep53_u04_00004.safetensors
# ---- B side: full episodes ----
wenxi 'EP24-潮缚-fix1' 'U01 U02 U03 U04 U05 U06'
wenxi 'EP62-潮缚-v1' 'U01 U02 U03 U04 U05 U06 U07'
wenxi 'EP63-潮缚-v1' 'U01 U02 U03 U04 U05 U06'

echo "ALL_DONE $(date +%H:%M:%S)"
