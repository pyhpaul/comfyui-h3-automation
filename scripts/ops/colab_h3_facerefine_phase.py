#!/usr/bin/env python3
"""Colab remote phase: install FaceRefine, queue one post-pass, publish to Drive.

Expects host to have uploaded into /content/:
  facerefine/ComfyUI-H3-FaceRefine/  (or tarball extracted)
  facerefine/ComfyUI-H3-NativeAudioLock/
  facerefine/ultralytics/...
  facerefine/source.mp4
  facerefine/prompt_h3.txt
  facerefine/ref_elena.png  (optional LoadImage)
  facerefine/ref_street.png
  facerefine/workflow_ui.json
  facerefine/extra_models/  optional audio_vae + turbo lora
  facerefine_ui_to_api.py

Env:
  H3_FACEREFINE_REMOTE  Drive prefix to publish into
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

CONTENT = Path("/content")
COMFY = CONTENT / "h3-rental/ComfyUI"
PYTHON = COMFY / ".venv/bin/python"
CUSTOM = COMFY / "custom_nodes"
MODELS = COMFY / "models"
STAGE = CONTENT / "facerefine"
CONFIG = CONTENT / "rclone.conf"
RCLONE = CONTENT / "rclone"


def run(*args: str, timeout: int = 600) -> None:
    print("RUN", " ".join(args), flush=True)
    subprocess.run(args, check=True, timeout=timeout)


def http_json(url: str, data: dict | None = None, timeout: int = 60) -> dict:
    body = None
    headers = {}
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:4000]
        print("HTTP_ERROR", exc.code, url, detail, flush=True)
        raise RuntimeError(f"HTTP {exc.code} {url}: {detail}") from exc


def wait_comfy(timeout_s: int = 180) -> dict:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            stats = http_json("http://127.0.0.1:8188/system_stats", timeout=5)
            if (stats.get("devices") or [{}])[0].get("name"):
                return stats
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError):
            time.sleep(2)
    raise RuntimeError("ComfyUI not ready")


def install_nodes() -> None:
    for name in ("ComfyUI-H3-FaceRefine", "ComfyUI-H3-NativeAudioLock"):
        src = STAGE / name
        dst = CUSTOM / name
        if not src.is_dir():
            raise RuntimeError(f"missing staged node pack {src}")
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".git", "screenshots", "__pycache__"))
        print("installed", name, flush=True)

    req = CUSTOM / "ComfyUI-H3-FaceRefine" / "requirements.txt"
    run("uv", "pip", "install", "--python", str(PYTHON), "-r", str(req), timeout=900)

    for pack in ("ComfyUI-Impact-Pack", "ComfyUI-VideoHelperSuite"):
        if not (CUSTOM / pack).is_dir():
            run(
                "git", "clone", "--depth", "1",
                f"https://github.com/{'ltdrdata' if 'Impact' in pack else 'Kosinkadink'}/{pack}.git",
                str(CUSTOM / pack),
                timeout=300,
            )
            req2 = CUSTOM / pack / "requirements.txt"
            if req2.is_file():
                run("uv", "pip", "install", "--python", str(PYTHON), "-r", str(req2), timeout=600)

    bbox = MODELS / "ultralytics" / "bbox"
    segm = MODELS / "ultralytics" / "segm"
    bbox.mkdir(parents=True, exist_ok=True)
    segm.mkdir(parents=True, exist_ok=True)
    shutil.copy2(STAGE / "ultralytics" / "bbox" / "face_yolov8m.pt", bbox / "face_yolov8m.pt")
    shutil.copy2(STAGE / "ultralytics" / "segm" / "person_yolov8m-seg.pt", segm / "person_yolov8m-seg.pt")

    extra = STAGE / "extra_models"
    if extra.is_dir():
        for path in extra.rglob("*"):
            if not path.is_file() or path.name == "FETCH_FROM_HF":
                continue
            rel = path.relative_to(extra)
            dest = MODELS / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
            print("extra_model", rel, flush=True)

    # Colab upload cannot carry ~1GiB extras; pull from HuggingFace.
    vae_dir = MODELS / "vae"
    lora_dir = MODELS / "loras"
    vae_dir.mkdir(parents=True, exist_ok=True)
    lora_dir.mkdir(parents=True, exist_ok=True)
    audio = vae_dir / "minimax_h3_audio_vae_fp32.safetensors"
    if not audio.is_file() or audio.stat().st_size < 100_000_000:
        url = (
            "https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/"
            "vae/minimax_h3_audio_vae_fp32.safetensors"
        )
        print("FETCH_HF audio_vae", flush=True)
        run("wget", "-q", "--show-progress", "-O", str(audio), url, timeout=1800)
    turbo_hits = list(lora_dir.glob("*turbo*"))
    if not turbo_hits:
        # Optional 8-step turbo; FaceRefine example expects it. Public Comfy pack:
        url = (
            "https://huggingface.co/Kijai/MiniMax-H3_comfy/resolve/main/"
            "loras/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors"
        )
        dest = lora_dir / "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors"
        print("FETCH_HF turbo_lora", flush=True)
        try:
            run("wget", "-q", "--show-progress", "-O", str(dest), url, timeout=1800)
        except subprocess.CalledProcessError as exc:
            print("TURBO_FETCH_FAILED", exc, "continuing without turbo", flush=True)


def restart_comfy() -> dict:
    # Soft restart: kill listeners on 8188 then start script again.
    subprocess.run(["pkill", "-f", "main.py.*8188"], check=False)
    time.sleep(3)
    env = os.environ.copy()
    env["COMFY_ROOT"] = str(COMFY)
    env["COMFY_H3_LOG"] = str(COMFY / "comfyUI-h3.log")
    start = CONTENT / "h3-runner" / "scripts" / "ops" / "comfy_gpu_start.sh"
    subprocess.Popen(
        ["bash", str(start)],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return wait_comfy(240)


def pick_model(subdir: str, *needles: str) -> str:
    root = MODELS / subdir
    hits = sorted(p for p in root.rglob("*.safetensors") if all(n.lower() in p.name.lower() for n in needles))
    if not hits:
        # also accept relative under MiniMax H3 folders
        hits = sorted(p for p in root.rglob("*") if p.suffix == ".safetensors" and all(n.lower() in str(p).lower() for n in needles))
    if not hits:
        raise RuntimeError(f"no model in {subdir} matching {needles}")
    # Comfy folder_paths relative name
    return str(hits[0].relative_to(MODELS / subdir if (MODELS / subdir).is_dir() else MODELS)).replace("\\", "/")


def upload_input(local: Path, name: str) -> str:
    import http.client
    import mimetypes

    boundary = "----h3facerefine"
    body = bytearray()
    ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
    payload = local.read_bytes()
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        f'Content-Disposition: form-data; name="image"; filename="{name}"\r\n'.encode()
    )
    body.extend(f"Content-Type: {ctype}\r\n\r\n".encode())
    body.extend(payload)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(b'Content-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n')
    body.extend(f"--{boundary}--\r\n".encode())
    conn = http.client.HTTPConnection("127.0.0.1", 8188, timeout=300)
    conn.request(
        "POST",
        "/upload/image",
        body=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    resp = conn.getresponse()
    raw = resp.read()
    if resp.status >= 400:
        raise RuntimeError(f"upload failed {resp.status}: {raw[:200]!r}")
    data = json.loads(raw.decode())
    return data.get("name") or name


def build_prompt() -> tuple[dict, dict]:
    import importlib.util

    converter = STAGE / "facerefine_ui_to_api.py"
    spec = importlib.util.spec_from_file_location("facerefine_ui_to_api", converter)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    ui = json.loads((STAGE / "workflow_ui.json").read_text(encoding="utf-8"))
    api = mod.convert_ui_workflow(ui)

    # Model names as Comfy expects (often under a subfolder key for UNET/CLIP)
    unet_files = list((MODELS / "diffusion_models").rglob("*.safetensors"))
    clip_files = list((MODELS / "text_encoders").rglob("*.safetensors"))
    vae_files = list((MODELS / "vae").rglob("*.safetensors"))
    lora_files = list((MODELS / "loras").rglob("*turbo*.safetensors")) if (MODELS / "loras").is_dir() else []
    if not unet_files or not clip_files or not vae_files:
        raise RuntimeError("restored H3 models missing")
    unet = unet_files[0].name
    clip = clip_files[0].name
    video_vae = next((p.name for p in vae_files if "audio" not in p.name.lower()), vae_files[0].name)
    audio_vae = next((p.name for p in vae_files if "audio" in p.name.lower()), None)
    if not audio_vae:
        raise RuntimeError("audio VAE missing — upload facerefine/extra_models/vae/…")
    lora = lora_files[0].name if lora_files else None

    api = mod.rebind_models(
        api,
        unet=unet,
        clip=clip,
        video_vae=video_vae,
        audio_vae=audio_vae,
        lora=lora,
    )

    # VHS_LoadVideoPath requires an absolute filesystem path, not just input/.
    input_dir = COMFY / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    video_abs = input_dir / "facerefine_ep01_u02.mp4"
    shutil.copy2(STAGE / "source.mp4", video_abs)
    upload_input(video_abs, "facerefine_ep01_u02.mp4")  # register with Comfy index
    refs: dict[str, str] = {}
    # Example graph LoadImage ids 6 and 7
    if (STAGE / "ref_elena.png").is_file():
        refs["6"] = upload_input(STAGE / "ref_elena.png", "facerefine_ref_elena.png")
    if (STAGE / "ref_street.png").is_file():
        refs["7"] = upload_input(STAGE / "ref_street.png", "facerefine_ref_street.png")
    prompt = (STAGE / "prompt_h3.txt").read_text(encoding="utf-8")
    api = mod.bind_media(
        api, video=str(video_abs), prompt=prompt, ref_images=refs,
    )
    meta = {
        "unet": unet,
        "clip": clip,
        "video_vae": video_vae,
        "audio_vae": audio_vae,
        "lora": lora,
        "video": str(video_abs),
        "refs": refs,
    }
    return api, meta


def wait_history(prompt_id: str, timeout_s: int = 3600) -> dict:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        hist = http_json(f"http://127.0.0.1:8188/history/{prompt_id}", timeout=30)
        entry = hist.get(prompt_id)
        if entry:
            status = ((entry.get("status") or {}).get("status_str") or "").lower()
            if status in {"error", "failed"}:
                raise RuntimeError(f"prompt failed: {entry.get('status')}")
            if entry.get("outputs") or status == "success":
                return entry
        time.sleep(10)
    raise TimeoutError("FaceRefine history timeout")


def find_mp4(entry: dict) -> Path:
    for _nid, outs in (entry.get("outputs") or {}).items():
        for key in ("gifs", "videos", "images"):
            for item in outs.get(key) or []:
                name = item.get("filename") or ""
                if name.lower().endswith(".mp4"):
                    sub = item.get("subfolder") or ""
                    typ = item.get("type") or "output"
                    base = COMFY / typ
                    path = base / sub / name if sub else base / name
                    if path.is_file():
                        return path
    # fallback scan
    hits = sorted((COMFY / "output").rglob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not hits:
        raise RuntimeError("no mp4 output")
    return hits[0]


def publish(remote: str, before: Path, after: Path, meta: dict) -> str:
    """Stage under /content/facerefine-publish; Drive copy is best-effort.

    Host pulls via ``colab download`` when Drive is over quota.
    Returns archive_state: verified | local_staged.
    """
    work = CONTENT / "facerefine-publish"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()
    shutil.copy2(before, work / "before.mp4")
    shutil.copy2(after, work / "after.mp4")
    shutil.copy2(STAGE / "prompt_h3.txt", work / "prompt_h3.txt")
    meta_path = work / "run_meta.json"
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    try:
        run(
            str(RCLONE), "copy", str(work), remote,
            "--config", str(CONFIG), "--transfers", "2",
            timeout=600,
        )
        print("DRIVE_PUBLISH_OK", remote, flush=True)
        return "verified"
    except (subprocess.CalledProcessError, RuntimeError, TimeoutError) as exc:
        print("DRIVE_PUBLISH_FAILED", exc, "keeping local stage", flush=True)
        meta["archive_note"] = f"drive_publish_failed: {exc}"
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return "local_staged"


def main() -> int:
    started = time.monotonic()
    remote = os.environ.get("H3_FACEREFINE_REMOTE")
    if not remote:
        raise SystemExit("set H3_FACEREFINE_REMOTE")
    session = os.environ.get("H3_FACEREFINE_SESSION", "")

    wait_comfy(60)
    install_nodes()
    stats = restart_comfy()
    info = http_json("http://127.0.0.1:8188/object_info", timeout=120)
    for need in ("H3FaceTrackCrop", "H3FaceStitch", "H3InjectVideoLatent", "H3PerFrameDenoise"):
        if need not in info:
            raise RuntimeError(f"missing node after restart: {need}")
    print("FACEREFINE_NODES_OK", flush=True)

    prompt, model_meta = build_prompt()
    (STAGE / "submitted_graph.json").write_text(
        json.dumps(prompt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    queued = http_json(
        "http://127.0.0.1:8188/prompt",
        {"prompt": prompt, "client_id": "facerefine-ep01-u02"},
        timeout=120,
    )
    if queued.get("node_errors"):
        raise RuntimeError(f"queue rejected: {queued.get('node_errors')}")
    prompt_id = queued["prompt_id"]
    print("QUEUED", prompt_id, flush=True)
    entry = wait_history(prompt_id, timeout_s=4200)
    after = find_mp4(entry)
    before = STAGE / "source.mp4"
    meta = {
        "state": "success",
        "label": "FACEREFINE_EP01_U02",
        "session_id": session,
        "prompt_id": prompt_id,
        "device": ((stats.get("devices") or [{}])[0].get("name")),
        "models": model_meta,
        "after_path": str(after),
        "elapsed_s": round(time.monotonic() - started, 2),
        "archive_state": "pending",
    }
    meta["archive_state"] = publish(remote, before, after, meta)
    # refresh on-disk meta with final archive_state
    (CONTENT / "facerefine-publish" / "run_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("FACEREFINE_PHASE_RESULT", json.dumps(meta, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
