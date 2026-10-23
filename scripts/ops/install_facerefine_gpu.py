#!/usr/bin/env python3
"""Upload staged FaceRefine custom nodes + YOLO detectors to the rental GPU.

Does not start Comfy or queue jobs. Run after the pod is up and SSH env is set,
before any FaceRefine test queue.

Staging (local, already prepared):
  .cache/facerefine_prep/ComfyUI-H3-FaceRefine/
  .cache/facerefine_prep/ComfyUI-H3-NativeAudioLock/
  .cache/facerefine_prep/models/ultralytics/{bbox,segm}/

Usage:
  export COMFY_GPU_SSH_HOST='<id>.gz15.chenyu.cn'
  export COMFY_GPU_SSH_PORT='<port>'
  export COMFY_GPU_SSH_PASSFILE=/home/linux_dev/.config/fnos/.chenyu-gpu.pass
  export PATH="/home/linux_dev/projects/comfyui-h3-automation/.worktrees/feat-orch/.venv/bin:$PATH"
  python scripts/ops/install_facerefine_gpu.py
  python scripts/ops/install_facerefine_gpu.py --pip   # also pip install requirements
  python scripts/ops/install_facerefine_gpu.py --check # remote inventory only
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[2]
STAGING = ROOT / ".cache" / "facerefine_prep"
COMFY = Path("/root/autodl-tmp/ComfyUI")
REMOTE_CUSTOM = COMFY / "custom_nodes"
REMOTE_MODELS = COMFY / "models" / "ultralytics"

REQUIRED_LOCAL = [
    STAGING / "ComfyUI-H3-FaceRefine" / "nodes.py",
    STAGING / "ComfyUI-H3-NativeAudioLock" / "__init__.py",
    STAGING / "models" / "ultralytics" / "bbox" / "face_yolov8m.pt",
    STAGING / "models" / "ultralytics" / "segm" / "person_yolov8m-seg.pt",
]


def _pass() -> str:
    path = os.environ.get("COMFY_GPU_SSH_PASSFILE")
    if path:
        return Path(path).read_text(encoding="utf-8").strip()
    env = os.environ.get("COMFY_GPU_SSH_PASS")
    if env:
        return env.strip()
    raise SystemExit("set COMFY_GPU_SSH_PASSFILE or COMFY_GPU_SSH_PASS")


def _connect() -> paramiko.SSHClient:
    host = os.environ.get("COMFY_GPU_SSH_HOST")
    port_s = os.environ.get("COMFY_GPU_SSH_PORT")
    if not host or not port_s:
        raise SystemExit("set COMFY_GPU_SSH_HOST and COMFY_GPU_SSH_PORT")
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        host,
        port=int(port_s),
        username="root",
        password=_pass(),
        timeout=25,
        allow_agent=False,
        look_for_keys=False,
    )
    return c


def _run(c: paramiko.SSHClient, cmd: str, timeout: int = 300) -> tuple[int, str]:
    _, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    code = stdout.channel.recv_exit_status()
    return code, (out if out.strip() else err)


def _sftp_put_dir(sftp: paramiko.SFTPClient, local: Path, remote: str) -> None:
    """Upload a directory tree (no .git, no screenshots)."""
    skip = {".git", "screenshots", "__pycache__", ".github"}

    def walk(src: Path, dst: str) -> None:
        try:
            sftp.stat(dst)
        except OSError:
            sftp.mkdir(dst)
        for child in sorted(src.iterdir()):
            if child.name in skip:
                continue
            rpath = f"{dst}/{child.name}"
            if child.is_dir():
                walk(child, rpath)
            else:
                sftp.put(str(child), rpath)
                print(f"PUT {child.relative_to(STAGING)} -> {rpath}", flush=True)

    walk(local, remote)


def check_remote(c: paramiko.SSHClient) -> None:
    code, text = _run(
        c,
        f"""
set -e
echo "=== custom_nodes ==="
ls -1 {REMOTE_CUSTOM} | sort
echo "=== FaceRefine ==="
ls -la {REMOTE_CUSTOM}/ComfyUI-H3-FaceRefine/nodes.py 2>/dev/null || echo MISSING_FACEREFINE
ls -la {REMOTE_CUSTOM}/ComfyUI-H3-NativeAudioLock/__init__.py 2>/dev/null || echo MISSING_AUDIOLOCK
echo "=== Impact / VHS ==="
ls -d {REMOTE_CUSTOM}/ComfyUI-Impact-Pack 2>/dev/null || echo MISSING_IMPACT
ls -d {REMOTE_CUSTOM}/ComfyUI-VideoHelperSuite 2>/dev/null || echo MISSING_VHS
echo "=== ultralytics ==="
ls -lh {REMOTE_MODELS}/bbox/face_yolov8m.pt 2>/dev/null || echo MISSING_FACE_YOLO
ls -lh {REMOTE_MODELS}/segm/person_yolov8m-seg.pt 2>/dev/null || echo MISSING_PERSON_SEG
echo "=== object_info probe (Comfy must be up) ==="
python3 - <<'PY' || true
import json,urllib.request
try:
    raw=urllib.request.urlopen('http://127.0.0.1:8188/object_info', timeout=5).read()
    info=json.loads(raw)
    for name in ('H3FaceTrackCrop','H3FaceStitch','H3InjectVideoLatent','H3PerFrameDenoise','MiniMaxH3NativeAudioLock','VHS_LoadVideoPath','UltralyticsDetectorProvider'):
        print(name, 'OK' if name in info else 'MISSING')
except Exception as e:
    print('object_info_unavailable', type(e).__name__, e)
PY
""",
    )
    print(text)
    if code != 0:
        raise SystemExit(code)


def install(c: paramiko.SSHClient, *, do_pip: bool) -> None:
    for path in REQUIRED_LOCAL:
        if not path.is_file():
            raise SystemExit(f"missing staged file: {path}")

    sftp = c.open_sftp()
    try:
        _run(c, f"mkdir -p {REMOTE_MODELS}/bbox {REMOTE_MODELS}/segm")
        _sftp_put_dir(
            sftp,
            STAGING / "ComfyUI-H3-FaceRefine",
            f"{REMOTE_CUSTOM}/ComfyUI-H3-FaceRefine",
        )
        _sftp_put_dir(
            sftp,
            STAGING / "ComfyUI-H3-NativeAudioLock",
            f"{REMOTE_CUSTOM}/ComfyUI-H3-NativeAudioLock",
        )
        face = STAGING / "models" / "ultralytics" / "bbox" / "face_yolov8m.pt"
        person = STAGING / "models" / "ultralytics" / "segm" / "person_yolov8m-seg.pt"
        sftp.put(str(face), f"{REMOTE_MODELS}/bbox/face_yolov8m.pt")
        print(f"PUT face_yolov8m.pt ({face.stat().st_size} bytes)", flush=True)
        sftp.put(str(person), f"{REMOTE_MODELS}/segm/person_yolov8m-seg.pt")
        print(f"PUT person_yolov8m-seg.pt ({person.stat().st_size} bytes)", flush=True)
    finally:
        sftp.close()

    if do_pip:
        req = REMOTE_CUSTOM / "ComfyUI-H3-FaceRefine" / "requirements.txt"
        code, text = _run(
            c,
            f"""
set -e
VENV={COMFY}/.venv/bin/pip
if [ ! -x "$VENV" ]; then VENV={COMFY}/venv/bin/pip; fi
"$VENV" install -r {req}
""",
            timeout=600,
        )
        print(text)
        if code != 0:
            raise SystemExit(f"pip install failed: {code}")

    # Leave a marker so preflight can see install time without passwords.
    _run(
        c,
        f"date -u +%Y-%m-%dT%H:%M:%SZ > {REMOTE_CUSTOM}/ComfyUI-H3-FaceRefine/.installed_by_h3_automation",
    )
    print("INSTALL_OK — restart Comfy so nodes load, then re-run with --check", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="remote inventory only")
    ap.add_argument("--pip", action="store_true", help="pip install FaceRefine requirements")
    args = ap.parse_args()

    if not args.check:
        missing = [p for p in REQUIRED_LOCAL if not p.is_file()]
        if missing:
            raise SystemExit(
                "staging incomplete:\n  " + "\n  ".join(str(p) for p in missing)
            )

    c = _connect()
    try:
        if args.check:
            check_remote(c)
        else:
            install(c, do_pip=args.pip)
            check_remote(c)
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
