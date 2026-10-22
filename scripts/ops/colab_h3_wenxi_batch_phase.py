"""Colab guest: batch-render wenxi units from the uploaded input bundle.

Reads /content/wenxi_setup/input/units.json (built locally by
prepare_lihun_v23_colab.py), renders each unit in manifest order against
the local ComfyUI on 127.0.0.1:8188, and publishes every finished unit
(mp4 + saved motion latent + prompt_h3.txt + run_meta.json + phase.json
receipt) to Drive at $H3_WENXI_REMOTE/<tag>/ with verified copies, so
the host can archive to Feiniu while rendering continues. Units whose
phase.json already says success are skipped, so a re-exec resumes.

Prints BATCH_PHASE_DONE ok=<n>/<total> at the end; any unit failure is
recorded in its phase.json (state=failed) and the batch continues.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, "/content")
from h3_a100_phase_receipt import publish_verified  # noqa: E402

BASE = "http://127.0.0.1:8188"
INPUT = Path("/content/wenxi_setup/input")
OUTPUT = Path("/content/wenxi_setup/output")
REMOTE = os.environ["H3_WENXI_REMOTE"]
RCLONE = Path("/content/rclone")
RCLONE_CONF = Path("/content/rclone.conf")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def http_json(path, data=None, timeout=30):
    req = Request(BASE + path,
                  data=json.dumps(data).encode() if data is not None else None,
                  headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=timeout) as r:
        return json.load(r)


def http_bytes(path, timeout=300):
    with urlopen(Request(BASE + path), timeout=timeout) as r:
        return r.read()


def upload_image(path):
    boundary = "----wenxi" + uuid.uuid4().hex
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


def server_wall(entry):
    try:
        s = {n: d["timestamp"] for n, d in entry["status"]["messages"]
             if n in {"execution_start", "execution_success"}}
        return round((s["execution_success"] - s["execution_start"]) / 1000, 3)
    except Exception:
        return None


def heartbeat(tag):
    try:
        p = OUTPUT / "heartbeat.json"
        p.write_text(json.dumps({"tag": tag, "at_utc": now()}, indent=1))
        subprocess.run([str(RCLONE), "--config", str(RCLONE_CONF),
                        "copyto", str(p), f"{REMOTE}/heartbeat.json"],
                       check=False, timeout=120,
                       capture_output=True)
    except Exception as exc:
        print(f"HEARTBEAT_FAIL {exc}", flush=True)


DONE_REMOTES = [r.strip() for r in
                os.environ.get("H3_DONE_REMOTES", "").split(",") if r.strip()]


def remote_receipt(remote, tag):
    try:
        result = subprocess.run(
            [str(RCLONE), "--config", str(RCLONE_CONF), "cat",
             f"{remote}/{tag}/phase.json"],
            capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            return None
        receipt = json.loads(result.stdout)
        return receipt if receipt.get("state") == "success" else None
    except Exception:
        return None


def done_elsewhere(tag):
    for remote in dict.fromkeys([REMOTE, *DONE_REMOTES]):
        receipt = remote_receipt(remote, tag)
        if receipt is not None:
            return remote, receipt
    return None


COMFY_OUTPUT = Path("/content/h3-rental/ComfyUI/output")


def seed_parent_latent(parent_rel):
    """Fetch a chain parent's latent from a previous session's Drive
    receipt when this VM never rendered the parent (it was skipped).
    Returns True when the file is in place afterwards."""
    target = COMFY_OUTPUT / parent_rel
    if target.is_file():
        return True
    m = re.search(r"(ep\d+)_u(\d+)", Path(parent_rel).name.lower())
    if not m:
        return False
    parent_tag = f"{m.group(1).upper()}-U{m.group(2)}"
    for remote in dict.fromkeys([REMOTE, *DONE_REMOTES]):
        receipt = remote_receipt(remote, parent_tag)
        if not receipt or not receipt.get("latent_file"):
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [str(RCLONE), "--config", str(RCLONE_CONF), "copyto",
             f"{remote}/{parent_tag}/{receipt['latent_file']}",
             str(target)],
            capture_output=True, text=True, timeout=1200)
        if result.returncode == 0 and target.is_file():
            print(f"SEEDED_PARENT {parent_tag} -> {parent_rel} "
                  f"from {remote}", flush=True)
            return True
        print(f"PARENT_SEED_FAIL {parent_tag} from {remote}: "
              f"{result.stderr[-500:]}", flush=True)
    return False


def run_unit(unit, uploaded):
    tag = unit["tag"]
    outdir = OUTPUT / tag
    outdir.mkdir(parents=True, exist_ok=True)
    phase_path = outdir / "phase.json"
    if phase_path.is_file():
        try:
            if json.loads(phase_path.read_text()).get("state") == "success":
                print(f"SKIP done {tag}", flush=True)
                return True
        except Exception:
            pass
    prior = done_elsewhere(tag)
    if prior is not None:
        prior_remote, prior_receipt = prior
        if prior_remote == REMOTE:
            phase_path.write_text(
                json.dumps(prior_receipt, indent=2) + "\n", encoding="utf-8")
            print(f"SKIP done-current-remote {tag}", flush=True)
            return True
        receipt = {
            "tag": tag,
            "episode": unit["episode"],
            "unit": unit["unit"],
            "seed": unit["seed"],
            "started_at_utc": prior_receipt.get("started_at_utc", now()),
            "finished_at_utc": now(),
            "state": "success",
            "skipped_done_remote": prior_remote,
            "mp4_file": prior_receipt.get("mp4_file"),
            "latent_file": prior_receipt.get("latent_file"),
        }
        phase_path.write_text(json.dumps(receipt, indent=2) + "\n",
                              encoding="utf-8")
        result = subprocess.run(
            [str(RCLONE), "--config", str(RCLONE_CONF), "copyto",
             str(phase_path), f"{REMOTE}/{tag}/phase.json"],
            capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            print(f"SKIP_PUBLISH_FAIL {tag} {result.stderr[-1000:]}",
                  flush=True)
            return False
        print(f"SKIP done-remote {tag} from {prior_remote}", flush=True)
        heartbeat(tag)
        return True
    started = time.monotonic()
    receipt = {"tag": tag, "episode": unit["episode"], "unit": unit["unit"],
               "seed": unit["seed"], "started_at_utc": now(),
               "state": "running"}
    try:
        for blob in unit["assets"]:
            if blob not in uploaded:
                uploaded[blob] = upload_image(INPUT / "assets" / blob)
                print("UPLOADED", blob, uploaded[blob], flush=True)
        if unit.get("parent_latent"):
            seed_parent_latent(unit["parent_latent"])
        wf = json.loads((INPUT / unit["workflow"]).read_text())
        wf = replace_blobs(wf, uploaded)
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
            (INPUT / unit["prompt_file"]).read_text(encoding="utf-8"),
            encoding="utf-8")
        meta = {
            "continuity": ("motion_latent" if unit.get("parent_latent")
                           else "independent"),
            "second_pass": False,
            "template": "yz_h3_wenwu_test/wenxi",
            "chain": "wenxi",
            "seed": unit["seed"],
            "parent_latent": unit.get("parent_latent"),
            "latent_path": rel,
            "prompt_id": pid,
            "source_job": unit["job"],
            "elapsed_s": round(time.monotonic() - started),
        }
        (outdir / "run_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        receipt.update({
            "state": "success",
            "server_wall_s": server_wall(entry),
            "mp4_file": mp4_name, "mp4_bytes": mp4.stat().st_size,
            "mp4_sha256": hashlib.sha256(mp4.read_bytes()).hexdigest(),
            "latent_file": lat_name, "latent_bytes": lat.stat().st_size,
        })
        print(f"UNIT_DONE {tag} wall={receipt['server_wall_s']} "
              f"mp4={receipt['mp4_bytes']}", flush=True)
    except Exception as exc:
        receipt.update({"state": "failed",
                        "error": f"{type(exc).__name__}: {exc}"})
        print(f"UNIT_FAILED {tag} {exc}", flush=True)
    receipt["finished_at_utc"] = now()
    phase_path.write_text(json.dumps(receipt, indent=2) + "\n",
                          encoding="utf-8")
    try:
        publish_verified(outdir, f"{REMOTE}/{tag}", RCLONE, RCLONE_CONF,
                         timeout=1200)
        print(f"PUBLISHED {tag}", flush=True)
    except Exception as exc:
        print(f"PUBLISH_FAIL {tag} {exc}", flush=True)
        return False
    heartbeat(tag)
    return receipt["state"] == "success"


def main():
    stats = http_json("/system_stats", timeout=10)
    device = stats["devices"][0]["name"]
    print("device:", device, flush=True)
    if "RTX PRO 6000" not in device or "cudaMallocAsync" in device:
        raise RuntimeError(f"bad device {device}")
    manifest = json.loads((INPUT / "units.json").read_text())
    units = manifest["units"]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    uploaded = {}
    ok = 0
    for unit in units:
        if run_unit(unit, uploaded):
            ok += 1
    print(f"BATCH_PHASE_DONE ok={ok}/{len(units)}", flush=True)
    if ok != len(units):
        raise RuntimeError(f"batch incomplete {ok}/{len(units)}")


if __name__ == "__main__":
    main()
