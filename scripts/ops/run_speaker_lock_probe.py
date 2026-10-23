#!/usr/bin/env python3
"""Run speaker-lock probes on the local 5090 via vm106:8190.

Reads .cache/chaofu_probe/input/manifest.json (built by
build_speaker_lock_probe.py), submits each probe workflow in plan order
(P-A, P-B1, P-B2 — B2 needs B1's server-side saved latent), downloads the
mp4 + saved latent, and writes unit.json receipts under
.cache/chaofu_probe/out/<tag>/.

Requires the production parent latent for P-B1 to already sit on the GPU
at output/h3_context/chaofu_wenxi/ep01_u05_00005.safetensors.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
BASE = "http://192.168.50.106:8190"
INPUT = ROOT / ".cache/chaofu_fx21_colab/input"
PROBE_IN = ROOT / ".cache/chaofu_probe/input"
OUT = ROOT / ".cache/chaofu_probe/out"
ORDER = ["P-A-U04L1", "P-B1-U06L1", "P-B2-U06L2",
         "P-C-U04L1-OTS", "P-B1R-U06L1", "P-E-U06L1-OTS", "P-D-U06L2-OTS",
         "P-F-U04L2-OTS", "P-G-U04L3-OTS", "P-H-U04L4", "P-G2-U04L3-OTS-INDEP",
         "P-G3-U04L3-FRAG", "PROD3-U04-3SHOT", "PROD3-U06-3SHOT"]


def http_json(path, data=None, timeout=30):
    req = Request(BASE + path,
                  data=json.dumps(data).encode() if data is not None else None,
                  headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=timeout) as r:
        return json.load(r)


def http_bytes(path, timeout=300):
    with urlopen(Request(BASE + path), timeout=timeout) as r:
        return r.read()


def upload_image(path: Path) -> str:
    boundary = "----probe" + uuid.uuid4().hex
    body = b""
    body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n".encode()
    body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; "
             f"filename=\"{path.name}\"\r\nContent-Type: image/png\r\n\r\n").encode()
    body += path.read_bytes() + b"\r\n" + f"--{boundary}--\r\n".encode()
    req = Request(BASE + "/upload/image", data=body,
                  headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urlopen(req, timeout=120) as r:
        resp = json.load(r)
    name = resp.get("name") or path.name
    sub = resp.get("subfolder") or ""
    return f"{sub}/{name}" if sub else name


def replace_blobs(node, uploaded):
    if isinstance(node, dict):
        return {k: replace_blobs(v, uploaded) for k, v in node.items()}
    if isinstance(node, list):
        return [replace_blobs(v, uploaded) for v in node]
    if isinstance(node, str) and node in uploaded:
        return uploaded[node]
    return node


def server_wall(entry) -> float | None:
    try:
        s = {n: d["timestamp"] for n, d in entry["status"]["messages"]
             if n in {"execution_start", "execution_success"}}
        return round((s["execution_success"] - s["execution_start"]) / 1000, 3)
    except Exception:
        return None


def run(tag: str, meta: dict, uploaded: dict) -> None:
    outdir = OUT / tag
    outdir.mkdir(parents=True, exist_ok=True)
    if (outdir / "unit.json").is_file():
        print(f"SKIP done {tag}", flush=True)
        return
    for blob in meta["assets"]:
        if blob not in uploaded:
            uploaded[blob] = upload_image(INPUT / "assets" / blob)
            print("UPLOADED", blob, uploaded[blob], flush=True)
    wf = json.loads((PROBE_IN / f"{tag}.json").read_text())
    wf = replace_blobs(wf, uploaded)
    resp = http_json("/prompt", {"prompt": wf, "client_id": uuid.uuid4().hex})
    pid = resp["prompt_id"]
    print(f"UNIT_QUEUED {tag} seed={meta['seed']} prompt_id={pid}", flush=True)
    deadline = time.monotonic() + 1800
    entry = None
    while time.monotonic() < deadline:
        hist = http_json(f"/history/{pid}", timeout=20)
        if pid in hist:
            st = hist[pid].get("status", {})
            if st.get("status_str") == "success" or st.get("completed") is True:
                entry = hist[pid]
                break
            if st.get("status_str") == "error":
                raise RuntimeError(f"comfy error {tag}: {st}")
        time.sleep(5)
    if entry is None:
        raise RuntimeError(f"timeout waiting {tag}")
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
    assert len(files) == 1, files
    item = files[0]
    q = urlencode({"filename": item["filename"],
                   "subfolder": item.get("subfolder", ""),
                   "type": item.get("type", "output")})
    mp4 = outdir / item["filename"]
    mp4.write_bytes(http_bytes(f"/view?{q}"))
    prefix = meta["save_prefix"]
    folder, name = prefix.rsplit("/", 1)
    lname = f"{name}_00001.safetensors"
    q2 = urlencode({"filename": lname, "subfolder": folder, "type": "output"})
    lat = outdir / lname
    lat.write_bytes(http_bytes(f"/view?{q2}"))
    receipt = {"tag": tag, "state": "success", "seed": meta["seed"],
               "prompt_id": pid, "server_wall_s": server_wall(entry),
               "mp4_file": item["filename"], "mp4_bytes": mp4.stat().st_size,
               "latent_file": lname, "latent_bytes": lat.stat().st_size,
               "variant": "speaker-lock-probe", "gpu": "chenyu-5090-local"}
    (outdir / "unit.json").write_text(json.dumps(receipt, indent=2))
    print(f"UNIT_DONE {tag} wall={receipt['server_wall_s']} mp4={receipt['mp4_bytes']}",
          flush=True)


def main() -> int:
    stats = http_json("/system_stats", timeout=10)
    print("device:", stats["devices"][0]["name"], flush=True)
    manifest = json.loads((PROBE_IN / "manifest.json").read_text())
    uploaded: dict = {}
    for tag in ORDER:
        run(tag, manifest[tag], uploaded)
    print("PROBE_DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
