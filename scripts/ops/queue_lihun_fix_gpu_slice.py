#!/usr/bin/env python3
"""Queue a disjoint lihun fix1 candidate slice on local Chenyu Comfy (vm106:8190).

Reads a slim units.json (GPU slice), uploads assets, submits wenxi API
workflows with start_mode=independent, pulls mp4+latent, archives to Feiniu
fix folder. Does not touch the Colab batch.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from comfy_orch.client import ComfyClient  # noqa: E402
from comfy_orch.feiniu_archive import archive_named_files  # noqa: E402

DEFAULT_BASE = os.environ.get("COMFY_BASE_URL", "http://192.168.50.106:8190").rstrip("/")
FEINIU_BATCH = r"离婚后修复定版（10.22）\文戏工作流"
_CLIENT: ComfyClient | None = None


def client() -> ComfyClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = ComfyClient(DEFAULT_BASE, timeout=120.0)
    return _CLIENT


def http_json(path: str, payload: dict | None = None, timeout: float = 60) -> dict:
    data = None if payload is None else json.dumps(payload).encode()
    req = Request(
        DEFAULT_BASE + path,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method="POST" if data else "GET",
    )
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def http_bytes(path: str, timeout: float = 300) -> bytes:
    with urlopen(DEFAULT_BASE + path, timeout=timeout) as resp:
        return resp.read()


def upload_image(path: Path) -> str:
    return client().upload_image(path)


def replace_blobs(wf: dict, uploaded: dict[str, str]) -> dict:
    text = json.dumps(wf)
    for blob, name in uploaded.items():
        text = text.replace(json.dumps(blob), json.dumps(name))
    return json.loads(text)


def archive_feiniu(tag: str, outdir: Path, episode: str, unit: str) -> str:
    payloads = {}
    for path in outdir.iterdir():
        if path.is_file() and path.name in {
            next(outdir.glob("*.mp4")).name,
            next(outdir.glob("*.safetensors")).name,
            "prompt_h3.txt", "run_meta.json",
        }:
            payloads[path.name] = path.read_bytes()
    # unit folder name keeps candidate tag so C1/C2/C3 do not collide
    return archive_named_files(
        payloads, batch=FEINIU_BATCH, episode=episode, unit=tag)


def run_unit(unit: dict, input_dir: Path, out_root: Path, uploaded: dict[str, str]) -> bool:
    tag = unit["tag"]
    outdir = out_root / tag
    outdir.mkdir(parents=True, exist_ok=True)
    phase_path = outdir / "phase.json"
    if phase_path.is_file():
        try:
            if json.loads(phase_path.read_text()).get("state") == "success":
                print(f"SKIP done {tag}", flush=True)
                return True
        except Exception:
            pass
    started = time.monotonic()
    receipt = {
        "tag": tag, "episode": unit["episode"], "unit": unit["unit"],
        "seed": unit["seed"], "state": "running",
        "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    try:
        for blob in unit["assets"]:
            if blob not in uploaded:
                uploaded[blob] = upload_image(input_dir / "assets" / blob)
                print("UPLOADED", blob, uploaded[blob], flush=True)
        wf = json.loads((input_dir / unit["workflow"]).read_text())
        wf = replace_blobs(wf, uploaded)
        # Force independent: clear any leftover latent refs if present is already done in pack.
        resp = http_json("/prompt", {"prompt": wf, "client_id": uuid.uuid4().hex})
        pid = resp["prompt_id"]
        receipt["prompt_id"] = pid
        print(f"UNIT_QUEUED {tag} seed={unit['seed']} prompt_id={pid}", flush=True)
        deadline = time.monotonic() + 2400
        entry = None
        while time.monotonic() < deadline:
            hist = http_json(f"/history/{pid}", timeout=20)
            if pid in hist:
                st = hist[pid].get("status", {})
                if st.get("status_str") == "success" or st.get("completed") is True:
                    entry = hist[pid]
                    break
                if st.get("status_str") == "error":
                    raise RuntimeError(f"comfy error: {st}")
            time.sleep(5)
        if entry is None:
            raise RuntimeError("timeout waiting unit")
        files, seen = [], set()
        for node_out in (entry.get("outputs") or {}).values():
            for key in ("gifs", "videos", "images"):
                for item in node_out.get(key) or []:
                    if str(item.get("filename", "")).lower().endswith(".mp4"):
                        k = (item.get("filename"), item.get("subfolder", ""),
                             item.get("type", "output"))
                        if k not in seen:
                            seen.add(k)
                            files.append(item)
        if len(files) != 1:
            raise RuntimeError(f"expected 1 mp4 got {files}")
        item = files[0]
        q = urlencode({"filename": item["filename"],
                       "subfolder": item.get("subfolder", ""),
                       "type": item.get("type", "output")})
        mp4_name = f"{tag}-lihun-wenxi_00001-audio.mp4"
        mp4 = outdir / mp4_name
        mp4.write_bytes(http_bytes(f"/view?{q}"))
        rel = unit["latent_rel"]
        folder, lname = rel.rsplit("/", 1)
        q2 = urlencode({"filename": lname, "subfolder": folder, "type": "output"})
        lat_name = (f"{unit['episode'].lower()}_{unit['unit'].lower()}"
                    f"_wenxi_00001.safetensors")
        lat = outdir / lat_name
        lat.write_bytes(http_bytes(f"/view?{q2}"))
        (outdir / "prompt_h3.txt").write_text(
            (input_dir / unit["prompt_file"]).read_text(encoding="utf-8"),
            encoding="utf-8")
        meta = {
            "continuity": "independent",
            "second_pass": False,
            "template": "yz_h3_wenwu_test/wenxi",
            "chain": "wenxi",
            "seed": unit["seed"],
            "parent_latent": None,
            "latent_path": rel,
            "prompt_id": pid,
            "source_job": unit["job"],
            "host": "chenyu-gpu",
            "elapsed_s": round(time.monotonic() - started),
        }
        (outdir / "run_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        receipt.update({
            "state": "success",
            "mp4_file": mp4_name, "mp4_bytes": mp4.stat().st_size,
            "mp4_sha256": hashlib.sha256(mp4.read_bytes()).hexdigest(),
            "latent_file": lat_name, "latent_bytes": lat.stat().st_size,
        })
        print(f"UNIT_DONE {tag} wall={meta['elapsed_s']} mp4={receipt['mp4_bytes']}",
              flush=True)
        remote = archive_feiniu(tag, outdir, unit["episode"], unit["unit"])
        print(f"FEINIU {tag} -> {remote}", flush=True)
    except Exception as exc:
        receipt.update({"state": "failed", "error": f"{type(exc).__name__}: {exc}"})
        print(f"UNIT_FAILED {tag} {exc}", flush=True)
        phase_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        return False
    receipt["finished_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    phase_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--log", type=Path, required=True)
    args = ap.parse_args()
    stats = http_json("/system_stats", timeout=20)
    device = stats["devices"][0]["name"]
    print("device:", device, flush=True)
    if "CUDA" not in device.upper() and "cuda" not in device:
        raise SystemExit(f"no CUDA device: {device}")
    units = json.loads((args.input / "units.json").read_text())["units"]
    args.out.mkdir(parents=True, exist_ok=True)
    uploaded: dict[str, str] = {}
    ok = fail = 0
    with args.log.open("a", encoding="utf-8") as log:
        def emit(msg: str) -> None:
            print(msg, flush=True)
            log.write(msg + "\n")
            log.flush()

        emit(f"GPU_SLICE_START n={len(units)} base={DEFAULT_BASE}")
        for unit in units:
            # Force disconnect for fix candidates.
            unit = dict(unit)
            unit["parent_latent"] = None
            unit["start_mode"] = "independent"
            if run_unit(unit, args.input, args.out, uploaded):
                ok += 1
            else:
                fail += 1
        emit(f"GPU_SLICE_DONE ok={ok} fail={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
