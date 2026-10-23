#!/usr/bin/env python3
"""Supervised Colab G4 FaceRefine trial on EP01 U02 wenwu mp4.

Default is dry-run. Paid allocation only with --execute-paid.
After a successful phase, pulls before/after and extracts still frames for
visual review (see facerefine_extract_frames.py).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from colab_h3_a100_ab_host import exec_file, run, snapshot, stop_and_verify

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts/ops"
BACKUP = Path("/mnt/d/comfyui-h3-backups/rental-20260924-5090")
RESTORE = BACKUP / "colab-stage2/control-scripts"
CONFIG = Path.home() / ".config/rclone-h3/rclone.conf"
WHEEL_DIR = BACKUP / "g4-u02/wheels"
SOURCE_U02 = ROOT / "jobs/facerefine_test/source_U02/EP01-U02-mafia2-wenwu_00001-audio.mp4"
PROMPT_U02 = ROOT / "jobs/facerefine_test/source_U02/prompt_h3.txt"
REF_ELENA = ROOT / "jobs/ep_units_wenwu_test/EP01-黑手党老大-v2-U02/assets/id0-elena_雨夜_四格.png"
REF_STREET = ROOT / "jobs/ep_units_wenwu_test/EP01-黑手党老大-v2-U02/assets/id1-街道_雨夜_四格.png"
STAGING = ROOT / ".cache/facerefine_prep"
UI_WF = ROOT / "templates/yz_h3_facerefine_test/workflow_ui.auto_select.source.json"
AUDIO_VAE = Path("/mnt/d/comfyui/models/vae/minimax_h3_audio_vae_fp32.safetensors")
TURBO = Path("/mnt/d/comfyui/models/loras/minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors")
REMOTE_BASE = "h3drive_h3:comfyui-h3-colab-dedicated/standard-v1/runs/facerefine/ep01-u02"
COLAB_BIN = Path.home() / ".local/share/uv/tools/google-colab-cli/bin/colab"

STAGE_MARKERS = {
    "identity": "G4_IDENTITY_OK",
    "preinstall": '"probe_exit": 0',
    "restore": "restore_ready",
    "setup": "comfy_ready",
    "facerefine": "FACEREFINE_PHASE_RESULT",
}

A100_CONTROL = BACKUP / "a100-perf-pilot/control-scripts"
A100_WHEEL = BACKUP / "a100-perf-pilot/sageattention-2.2.0-cp313-cp313-linux_x86_64.whl"
A100_WHEEL_SHA256 = "36fb6b6febdcd71aa171fa207291b40696a5f4384451100348a1ebdfec8a8238"

STAGE_MARKERS_A100 = {
    # Standard-shape Colab A100 is 40GB; gate script mentions 80GB even on failure.
    "identity": "NVIDIA A100-SXM4",
    "preinstall": '"probe_exit": 0',
    "restore": "restore_ready",
    "wheel_pull": '"exit_code": 0',
    "setup": "comfy_ready",
    "facerefine": "FACEREFINE_PHASE_RESULT",
}


def colab_cmd(*args: str) -> list[str]:
    binary = str(COLAB_BIN if COLAB_BIN.is_file() else "colab")
    return [binary, *args]


def release_orphan_assignments() -> int:
    """Drop paid GPUs that have no local session (e.g. timed-out ``colab new``)."""
    try:
        from colab_cli.common import State
    except ImportError:
        print("ORPHAN_SKIP colab_cli not importable", flush=True)
        return 0
    state = State()
    assignments = state.client.list_assignments()
    released = 0
    for item in assignments:
        print("ORPHAN_UNASSIGN", item.endpoint, flush=True)
        state.client.unassign(item.endpoint)
        released += 1
    return released


def local_preflight(
    *, require_drive: bool = False, gpu: str = "G4",
) -> tuple[Path, str, bool]:
    required = [
        CONFIG, RESTORE / "colab-h3-rclone.gz",
        SCRIPTS / "colab_h3_restore.py", SCRIPTS / "colab_h3_preinstall_torch.py",
        SCRIPTS / "colab_h3_paid_watchdog.sh",
        SCRIPTS / "colab_h3_facerefine_phase.py",
        SCRIPTS / "facerefine_ui_to_api.py",
        SCRIPTS / "facerefine_extract_frames.py",
        SOURCE_U02, PROMPT_U02, UI_WF,
        STAGING / "ComfyUI-H3-FaceRefine" / "nodes.py",
        STAGING / "ComfyUI-H3-NativeAudioLock" / "__init__.py",
        STAGING / "models/ultralytics/bbox/face_yolov8m.pt",
        STAGING / "models/ultralytics/segm/person_yolov8m-seg.pt",
    ]
    if gpu == "A100":
        required += [
            A100_CONTROL / "h3_a100_identity.py",
            A100_CONTROL / "h3_a100_setup.py",
            A100_CONTROL / "h3_gpu_wheel_pull.py",
            A100_WHEEL,
        ]
    else:
        required += [SCRIPTS / "h3_g4_identity.py", SCRIPTS / "h3_g4_setup.py"]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise RuntimeError(f"missing FaceRefine {gpu} inputs: {missing}")
    about = subprocess.run(
        ["rclone", "about", "h3drive_h3:", "--config", str(CONFIG)],
        capture_output=True, text=True, timeout=60,
    )
    drive_ok = about.returncode == 0
    if require_drive and not drive_ok:
        raise RuntimeError(
            "rclone h3drive_h3: failed — run: "
            f"rclone config reconnect h3drive_h3: --config {CONFIG}\n"
            f"{about.stderr or about.stdout}"
        )
    if gpu == "A100":
        wheel = A100_WHEEL
        digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
        if digest != A100_WHEEL_SHA256:
            raise RuntimeError("A100 SageAttention wheel hash mismatch")
        return wheel, digest, drive_ok
    wheels = list(WHEEL_DIR.glob("sageattention-2.2.0-cp313-cp313-linux_x86_64.whl"))
    if len(wheels) != 1:
        raise RuntimeError("expected exactly one locally built cp313 SageAttention wheel")
    wheel = wheels[0]
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    if not drive_ok:
        print("DRIVE_WARN rclone token invalid; --execute-paid will refuse", flush=True)
    return wheel, digest, drive_ok


def remote_json(path: str) -> dict:
    last_error = None
    for _ in range(3):
        try:
            result = subprocess.run(
                ["rclone", "cat", path, "--config", str(CONFIG)],
                capture_output=True, check=True, timeout=60,
            )
            return json.loads(result.stdout)
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired,
                json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(2)
    raise RuntimeError(f"could not read Drive receipt {path}: {last_error}")


def verify_phase(remote: str, session: str, log: Path,
                 local_meta: Path | None = None) -> dict:
    marker = "FACEREFINE_PHASE_RESULT "
    lines = [
        line.partition(marker)[2]
        for line in log.read_text(errors="replace").splitlines()
        if marker in line
    ]
    if not lines:
        raise RuntimeError("FaceRefine phase log missing FACEREFINE_PHASE_RESULT")
    logged = json.loads(lines[-1])
    if (
        logged.get("state") != "success"
        or logged.get("archive_state") not in {"verified", "local_staged"}
        or logged.get("session_id") != session
        or logged.get("label") != "FACEREFINE_EP01_U02"
    ):
        raise RuntimeError("FaceRefine phase log does not match success criteria")
    receipt = logged
    if local_meta and local_meta.is_file():
        receipt = json.loads(local_meta.read_text(encoding="utf-8"))
    elif logged.get("archive_state") == "verified":
        try:
            receipt = remote_json(f"{remote}/run_meta.json")
        except RuntimeError as exc:
            print("DRIVE_RECEIPT_SKIP", exc, flush=True)
            receipt = logged
    for key in ("prompt_id", "label", "state"):
        if receipt.get(key) != logged.get(key):
            raise RuntimeError("FaceRefine phase log and receipt disagree")
    return receipt


# Colab contents API 400s near ~100MiB; 32MiB rclone.gz uploads fine.
UPLOAD_PART_BYTES = 28 * 1024 * 1024


def stage_upload_bundle(
    tmp: Path, source: Path | None = None,
) -> tuple[list[tuple[Path, str]], list[str]]:
    """Build FaceRefine tar split into Colab-safe upload parts.

    Drive is over quota for writes, so the bundle goes through ``colab upload``
    in <=28MiB chunks (proven size). Audio VAE / turbo stay out; phase fetches
    them from HuggingFace. Returns (small_uploads, part_remote_names).
    """
    bundle = tmp / "facerefine"
    bundle.mkdir(parents=True)
    shutil.copytree(
        STAGING / "ComfyUI-H3-FaceRefine",
        bundle / "ComfyUI-H3-FaceRefine",
        ignore=shutil.ignore_patterns(".git", "screenshots", "__pycache__", ".github"),
    )
    shutil.copytree(STAGING / "ComfyUI-H3-NativeAudioLock", bundle / "ComfyUI-H3-NativeAudioLock")
    (bundle / "ultralytics/bbox").mkdir(parents=True)
    (bundle / "ultralytics/segm").mkdir(parents=True)
    shutil.copy2(STAGING / "models/ultralytics/bbox/face_yolov8m.pt",
                 bundle / "ultralytics/bbox/face_yolov8m.pt")
    shutil.copy2(STAGING / "models/ultralytics/segm/person_yolov8m-seg.pt",
                 bundle / "ultralytics/segm/person_yolov8m-seg.pt")
    shutil.copy2(source or SOURCE_U02, bundle / "source.mp4")
    shutil.copy2(PROMPT_U02, bundle / "prompt_h3.txt")
    shutil.copy2(UI_WF, bundle / "workflow_ui.json")
    shutil.copy2(SCRIPTS / "facerefine_ui_to_api.py", bundle / "facerefine_ui_to_api.py")
    if REF_ELENA.is_file():
        shutil.copy2(REF_ELENA, bundle / "ref_elena.png")
    if REF_STREET.is_file():
        shutil.copy2(REF_STREET, bundle / "ref_street.png")
    (bundle / "extra_models").mkdir(parents=True, exist_ok=True)
    (bundle / "extra_models" / "FETCH_FROM_HF").write_text(
        "audio_vae+turbo fetched on Colab; see colab_h3_facerefine_phase.py\n"
    )
    tar_path = tmp / "facerefine-bundle.tar"
    subprocess.run(
        ["tar", "-cf", str(tar_path), "-C", str(tmp), "facerefine"],
        check=True, timeout=300,
    )
    size_mb = tar_path.stat().st_size / (1024 * 1024)
    parts_dir = tmp / "bundle-parts"
    parts_dir.mkdir()
    raw = tar_path.read_bytes()
    part_uploads: list[tuple[Path, str]] = []
    part_names: list[str] = []
    for index in range(0, len(raw), UPLOAD_PART_BYTES):
        part_name = f"facerefine-bundle.tar.part-{index // UPLOAD_PART_BYTES:03d}"
        part_path = parts_dir / part_name
        part_path.write_bytes(raw[index:index + UPLOAD_PART_BYTES])
        part_uploads.append((part_path, f"/content/{part_name}"))
        part_names.append(part_name)
    print(
        f"BUNDLE_OK size_mib={size_mb:.1f} parts={len(part_names)} "
        f"part_mib={UPLOAD_PART_BYTES / (1024 * 1024):.0f}",
        flush=True,
    )
    small_uploads = [
        (CONFIG, "/content/rclone.conf"),
        (RESTORE / "colab-h3-rclone.gz", "/content/rclone.gz"),
        (SCRIPTS / "colab_h3_facerefine_phase.py", "/content/colab_h3_facerefine_phase.py"),
        *part_uploads,
    ]
    return small_uploads, part_names


def unpack_bundle_on_colab(session: str, part_names: list[str], logdir: Path) -> None:
    """Concatenate uploaded parts and unpack under /content/facerefine.

    ``colab exec`` only accepts ``--file`` (Python), not shell argv — so write a
    tiny unpacker and run it through exec_file.
    """
    unpack_py = logdir / "unpack_bundle.py"
    unpack_py.write_text(
        "from pathlib import Path\n"
        "import subprocess\n"
        f"parts = {part_names!r}\n"
        "out = Path('/content/facerefine-bundle.tar')\n"
        "with out.open('wb') as dest:\n"
        "    for name in parts:\n"
        "        dest.write((Path('/content') / name).read_bytes())\n"
        "subprocess.run(['tar', '-xf', str(out), '-C', '/content'], check=True)\n"
        "assert Path('/content/facerefine/source.mp4').is_file()\n"
        "print('UNPACK_OK', flush=True)\n",
        encoding="utf-8",
    )
    unpack_log = logdir / "unpack.log"
    exec_file(session, unpack_py, 300, unpack_log)
    if "UNPACK_OK" not in unpack_log.read_text(errors="replace"):
        raise RuntimeError("facerefine split-bundle unpack failed")
    print("BUNDLE_UNPACK_OK", flush=True)


def download_publish_from_colab(session: str, logdir: Path) -> Path:
    """Pull /content/facerefine-publish into local evidence (Drive may be full)."""
    evidence = logdir / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    for name in ("before.mp4", "after.mp4", "prompt_h3.txt", "run_meta.json"):
        dest = evidence / name
        run(
            colab_cmd(
                "download", "--session", session,
                f"/content/facerefine-publish/{name}", str(dest),
            ),
            logdir / f"download-{name}.log",
            timeout=600,
        )
        if not dest.is_file():
            raise RuntimeError(f"colab download missing {name}")
    print("EVIDENCE_LOCAL_OK", evidence, flush=True)
    return evidence


def extract_local_frames(logdir: Path) -> Path:
    before = logdir / "evidence" / "before.mp4"
    after = logdir / "evidence" / "after.mp4"
    if not before.is_file() or not after.is_file():
        raise RuntimeError(f"missing before/after under {logdir / 'evidence'}")
    frames = logdir / "frames"
    sys.path.insert(0, str(SCRIPTS))
    import facerefine_extract_frames as extract

    extract.extract_pair(before, after, frames)
    return frames


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-paid", action="store_true")
    parser.add_argument("--safety-hours", type=float, default=4.0)
    parser.add_argument(
        "--attach-session", default="",
        help="Use an already assigned Colab session instead of calling colab new",
    )
    parser.add_argument("--gpu", choices=("G4", "A100"), default="G4")
    parser.add_argument(
        "--source", type=Path, default=None,
        help="Source mp4 (default U02 original; pass pass-1 after.mp4 for 2nd pass)",
    )
    args = parser.parse_args()
    if not 2 <= args.safety_hours <= 8:
        raise ValueError("safety deadline must be between two and eight hours")

    gpu = args.gpu
    gpu_tag = "g4" if gpu == "G4" else "a100"
    markers = STAGE_MARKERS if gpu == "G4" else STAGE_MARKERS_A100
    wheel, wheel_sha, drive_ok = local_preflight(
        require_drive=bool(args.execute_paid), gpu=gpu,
    )
    session = f"h3-{gpu_tag}-facerefine-ep01u02-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    remote = f"{REMOTE_BASE}/{session}"
    if not args.execute_paid:
        payload = {
            "ready": True,
            "paid_started": False,
            "drive_ok": drive_ok,
            "wheel": str(wheel),
            "wheel_sha256": wheel_sha,
            "source": str(SOURCE_U02),
            "remote_prefix": remote,
            "balance_hint": "run colab usage; expect ~3-5 CU",
        }
        if not drive_ok:
            payload["blocker"] = "reconnect rclone h3drive_h3 before --execute-paid"
        print(json.dumps(payload, indent=2))
        return

    if args.attach_session:
        session = args.attach_session
        remote = f"{REMOTE_BASE}/{session}"
    logdir = BACKUP / f"{gpu_tag}-facerefine" / session
    logdir.mkdir(parents=True, exist_ok=False)
    snapshots = logdir / "cu-snapshots.jsonl"
    before = snapshot(snapshots, "before_assignment")
    sessions = run(colab_cmd("sessions"), logdir / "sessions-before.log", timeout=30)
    if args.attach_session:
        if before["active"] < 1:
            raise RuntimeError(f"attach session {session} has no paid assignment")
        print(f"{gpu}_ATTACH", session, flush=True)
    elif before["active"] or before["rate"] or "No active sessions" not in sessions:
        released = release_orphan_assignments()
        before = snapshot(snapshots, "after_orphan_release")
        sessions = run(colab_cmd("sessions"), logdir / "sessions-before-retry.log", timeout=30)
        if before["active"] or before["rate"] or "No active sessions" not in sessions:
            raise RuntimeError(
                f"Colab is not idle after releasing {released} orphans; no {gpu} assignment created"
            )
        print(f"ORPHAN_CLEARED count={released}", flush=True)

    (logdir / "trial-inputs.json").write_text(json.dumps({
        "session": session, "remote": remote, "wheel_sha256": wheel_sha,
        "source_sha256": hashlib.sha256(
            (args.source or SOURCE_U02).read_bytes()
        ).hexdigest(),
        "source_override": str(args.source) if args.source else None,
        "safety_hours": args.safety_hours, "before": before,
    }, indent=2) + "\n")

    created = False
    finished = False
    watcher = None
    started = time.monotonic()
    deadline = datetime.now(timezone.utc) + timedelta(hours=args.safety_hours)
    bundle_tmp = logdir / "upload-stage"
    bundle_tmp.mkdir()
    if args.source and not args.source.is_file():
        raise RuntimeError(f"--source mp4 missing: {args.source}")
    small_uploads, part_names = stage_upload_bundle(bundle_tmp, source=args.source)
    local_meta: Path | None = None
    try:
        if args.attach_session:
            created = True
        else:
            # Standard shape: --high-mem A100 assign 503s while standard succeeds.
            new_args = ["new", "--session", session, "--gpu", gpu]
            last_new_error: Exception | None = None
            for attempt in range(1, 9):
                try:
                    run(colab_cmd(*new_args),
                        logdir / f"assignment-attempt{attempt}.log", timeout=300)
                    last_new_error = None
                    break
                except (RuntimeError, TimeoutError) as exc:
                    last_new_error = exc
                    print(f"{gpu}_ASSIGN_RETRY attempt={attempt} err={exc}", flush=True)
                    release_orphan_assignments()
                    time.sleep(20 * attempt)
                    session = f"h3-{gpu_tag}-facerefine-ep01u02-" + datetime.now(timezone.utc).strftime(
                        "%Y%m%d-%H%M%S"
                    )
                    remote = f"{REMOTE_BASE}/{session}"
                    new_args = ["new", "--session", session, "--gpu", gpu]
            if last_new_error is not None:
                raise RuntimeError(
                    f"{gpu} assignment failed after retries: {last_new_error}"
                ) from last_new_error
            created = True
        assigned = snapshot(snapshots, "assigned")
        if assigned["active"] != 1 or assigned["rate"] <= 0:
            raise RuntimeError(f"{gpu} paid assignment was not confirmed")
        watcher_log = (logdir / "watchdog.log").open("w")
        try:
            watcher = subprocess.Popen(
                ["bash", str(SCRIPTS / "colab_h3_paid_watchdog.sh"),
                 session, deadline.isoformat()],
                stdin=subprocess.DEVNULL, stdout=watcher_log,
                stderr=subprocess.STDOUT, start_new_session=True,
            )
        finally:
            watcher_log.close()
        time.sleep(0.2)
        if watcher.poll() is not None:
            raise RuntimeError("paid-session watchdog exited before setup")
        print(f"{gpu}_FACEREFINE_SESSION", session, "remote", remote, flush=True)

        uploads = list(small_uploads)
        if gpu == "G4":
            uploads.append((wheel, "/content/" + wheel.name))
        for source, destination in uploads:
            run(colab_cmd("upload", "--session", session, str(source), destination),
                logdir / ("upload-" + Path(destination).name.replace("/", "_") + ".log"),
                timeout=600)

        unpack_bundle_on_colab(session, part_names, logdir)

        if gpu == "A100":
            stages = (
                ("identity", A100_CONTROL / "h3_a100_identity.py", 60, {}),
                ("preinstall", SCRIPTS / "colab_h3_preinstall_torch.py", 720, {}),
                ("restore", SCRIPTS / "colab_h3_restore.py", 2400, {}),
                ("wheel_pull", A100_CONTROL / "h3_gpu_wheel_pull.py", 300, {}),
                ("setup", A100_CONTROL / "h3_a100_setup.py", 900, {}),
            )
        else:
            stages = (
                ("identity", SCRIPTS / "h3_g4_identity.py", 60, {}),
                ("preinstall", SCRIPTS / "colab_h3_preinstall_torch.py", 720, {}),
                ("restore", SCRIPTS / "colab_h3_restore.py", 2400, {}),
                ("setup", SCRIPTS / "h3_g4_setup.py", 900, {"H3_G4_WHEEL_SHA256": wheel_sha}),
            )
        for name, path, timeout, env in stages:
            began = time.monotonic()
            exec_file(session, path, timeout, logdir / f"{name}.log", **env)
            if markers[name] not in (logdir / f"{name}.log").read_text(errors="replace"):
                raise RuntimeError(f"{name} stage had no success marker; hold without FaceRefine")
            state = snapshot(snapshots, name)
            (logdir / "stage-timing.jsonl").open("a").write(json.dumps({
                "stage": name, "elapsed_s": round(time.monotonic() - began, 2),
                "rate_cu_per_hour": state["rate"], "balance_cu": state["balance"],
            }) + "\n")

        began = time.monotonic()
        phase_log = logdir / "facerefine.log"
        try:
            exec_file(
                session, SCRIPTS / "colab_h3_facerefine_phase.py", 4800, phase_log,
                H3_FACEREFINE_REMOTE=remote,
                H3_FACEREFINE_SESSION=session,
            )
        except (RuntimeError, TimeoutError):
            pass
        # Download before stop — session must still be alive.
        try:
            download_publish_from_colab(session, logdir)
            local_meta = logdir / "evidence" / "run_meta.json"
        except (RuntimeError, TimeoutError) as exc:
            print("EVIDENCE_DOWNLOAD_FAILED", exc, flush=True)
        verify_phase(remote, session, phase_log, local_meta=local_meta)
        state = snapshot(snapshots, "after_facerefine")
        (logdir / "stage-timing.jsonl").open("a").write(json.dumps({
            "stage": "facerefine", "elapsed_s": round(time.monotonic() - began, 2),
            "rate_cu_per_hour": state["rate"], "balance_cu": state["balance"],
        }) + "\n")
        print("FACEREFINE_REMOTE", remote, flush=True)
        finished = True
    finally:
        if created and finished:
            try:
                stop_and_verify(session, logdir, watcher)
            finally:
                try:
                    run(colab_cmd("log", "--session", session, "--output",
                                  str(logdir / "colab-session.jsonl")), timeout=120)
                except (RuntimeError, TimeoutError) as exc:
                    print("SESSION_LOG_UNAVAILABLE", exc, flush=True)
                try:
                    run(["rclone", "copy", remote, str(logdir / "evidence"),
                         "--config", str(CONFIG)], timeout=600)
                except (RuntimeError, TimeoutError) as exc:
                    print("EVIDENCE_PULL_UNAVAILABLE", exc, flush=True)
                try:
                    frames = extract_local_frames(logdir)
                    print("FRAMES", frames, flush=True)
                except Exception as exc:  # noqa: BLE001 — report, do not hide stop
                    print("FRAME_EXTRACT_FAILED", exc, flush=True)
                (logdir / "host-wall-s.txt").write_text(
                    f"{round(time.monotonic() - started, 2)}\n")
        elif created:
            print(
                "HOLD_SESSION", session,
                "logdir", logdir,
                "remote", remote,
                flush=True,
            )
            (logdir / "HOLD_SESSION.txt").write_text(
                f"{session}\n{remote}\n{logdir}\n"
            )


if __name__ == "__main__":
    main()
