"""Colab wenxi smoke phase: 1 independent unit (EP01-继母-v21-U01), 768x1376, one pass, fixed seed."""
import hashlib, json, os, subprocess, sys, time, uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode
sys.path.insert(0, "/content")
from h3_a100_phase_receipt import identity_from_environment, publish_verified

BASE = "http://127.0.0.1:8188"
INPUT = Path("/content/wenxi_setup/input")
OUTPUT = Path("/content/wenxi_setup/output")
REMOTE = os.environ["H3_WENXI_REMOTE"]
LABEL = "SMOKE"
REF_NODE = {"ref_image_0":"51","ref_image_1":"49","ref_image_2":"50","ref_image_3":"43","ref_image_4":"19","ref_image_5":"23","ref_image_6":"199","ref_image_7":"200","ref_image_8":"201"}

def now(): return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
def http_json(path, data=None, timeout=30):
    req = Request(BASE+path, data=json.dumps(data).encode() if data is not None else None, headers={"Content-Type":"application/json"})
    with urlopen(req, timeout=timeout) as r: return json.load(r)

def upload_image(path):
    boundary = "----wenxi" + uuid.uuid4().hex; body = b""
    body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n".encode()
    body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{path.name}\"\r\nContent-Type: image/png\r\n\r\n".encode()
    body += path.read_bytes() + b"\r\n" + f"--{boundary}--\r\n".encode()
    req = Request(BASE+"/upload/image", data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urlopen(req, timeout=120) as r: resp = json.load(r)
    name = resp.get("name") or path.name; sub = resp.get("subfolder") or ""
    return f"{sub}/{name}" if sub else name

def server_wall(entry):
    s = {n: d["timestamp"] for n, d in entry["status"]["messages"] if n in {"execution_start","execution_success"}}
    return round((s["execution_success"]-s["execution_start"])/1000, 3)

def main():
    pre = Path("/content/wenxi_setup/preflight.json")
    rep = json.loads(pre.read_text())
    if not rep.get("all_match") or not rep.get("native_allocator"): raise RuntimeError("preflight did not pass; do not submit")
    manifest = json.loads((INPUT/"manifest.json").read_text())
    OUTPUT.mkdir(parents=True, exist_ok=True)
    identity = identity_from_environment(LABEL, pre)
    result = {**vars(identity), "started_at_utc": now(), "job": manifest["job"], "seed": manifest["seed"]}
    started = time.monotonic()
    try:
        stats = http_json("/system_stats", timeout=10); device = stats["devices"][0]["name"]
        if "cudaMallocAsync" in device or "RTX PRO 6000" not in device: raise RuntimeError(f"bad device {device}")
        result["device"] = device
        uploaded = {}
        for a in manifest["assets"]:
            uploaded[a["file"]] = upload_image(INPUT/a["file"]); print("UPLOADED", a["file"], uploaded[a["file"]], flush=True)
        wf = json.loads((INPUT/"workflow_api.json").read_text())
        wired = (INPUT/manifest["prompt_file"]).read_text(encoding="utf-8")
        for field, fname in manifest["asset_files"].items():
            wf[REF_NODE[field]]["inputs"]["image"] = uploaded[fname]
        wf["263"]["inputs"]["text"] = wired
        wf["259"]["inputs"]["value"] = float(manifest["duration_seconds"])
        wf["252"]["inputs"]["aspect_ratio"] = manifest["aspect_ratio"]; wf["252"]["inputs"]["megapixels"] = float(manifest["megapixels"])
        wf["9001"]["inputs"]["filename_prefix"] = "h3_context/wenxi_smoke/ep01_u01"; wf["9001"]["inputs"]["clip_index"] = 1
        keep = {}
        for nid, node in wf.items():
            ct = node.get("class_type"); ins = node.get("inputs") or {}
            if ct == "LoadAudio" and ins.get("audio") in (None, "None", ""): continue
            if ct == "VHS_LoadVideo" and not ins.get("video"): continue
            if ct == "LoadImage" and ins.get("image") in (None, "None", ""): continue
            keep[nid] = node
        wf = keep
        wf["265"]["inputs"]["prompt"] = wired
        wf["265"]["inputs"]["width"] = 768; wf["265"]["inputs"]["height"] = 1376
        dur = float(manifest["duration_seconds"]); n = max(5, round(dur*24)); wf["265"]["inputs"]["length"] = n + (5-(n % 17)) % 17
        for k in [k for k in wf["265"]["inputs"] if k.startswith("ref_images.ref_image_") and int(k.rsplit("_",1)[1]) >= len(manifest["assets"])]: del wf["265"]["inputs"][k]
        for k in [k for k in wf["265"]["inputs"] if k.startswith("ref_videos.") or k.startswith("ref_audios.")]: del wf["265"]["inputs"][k]
        wf["397"]["inputs"]["seed"] = int(manifest["seed"])
        wf["364"]["inputs"]["filename_prefix"] = "EP01-U01-lihun-wenxi-smoke"; wf["364"]["inputs"]["save_output"] = True
        (OUTPUT/"submitted_graph.json").write_text(json.dumps(wf, indent=2)+"\n")
        resp = http_json("/prompt", {"prompt": wf, "client_id": uuid.uuid4().hex})
        prompt_id = resp["prompt_id"]; result["prompt_id"] = prompt_id
        print(f"SMOKE_SUBMIT seed={manifest['seed']} prompt_id={prompt_id}", flush=True)
        deadline = time.monotonic()+3600; entry = None
        while time.monotonic() < deadline:
            hist = http_json(f"/history/{prompt_id}", timeout=20)
            if prompt_id in hist:
                st = hist[prompt_id].get("status", {})
                if st.get("status_str") == "success" or st.get("completed") is True: entry = hist[prompt_id]; break
                if st.get("status_str") == "error": raise RuntimeError(f"comfy error: {st}")
            time.sleep(5)
        if entry is None: raise RuntimeError("timeout waiting smoke")
        (OUTPUT/"history.json").write_text(json.dumps(entry, indent=2)+"\n")
        files = []
        for node_out in (entry.get("outputs") or {}).values():
            for key in ("gifs","videos","images"):
                for item in node_out.get(key) or []:
                    if str(item.get("filename","")).lower().endswith(".mp4"): files.append(item)
        if len(files) != 1: raise RuntimeError(f"expected 1 mp4, got {files}")
        item = files[0]; q = urlencode({"filename": item["filename"], "subfolder": item.get("subfolder",""), "type": item.get("type","output")})
        mp4 = OUTPUT/"EP01-U01-lihun-wenxi-smoke.mp4"
        with urlopen(f"{BASE}/view?{q}", timeout=300) as r: mp4.write_bytes(r.read())
        probe = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-show_entries","stream=codec_type,codec_name,width,height,r_frame_rate,nb_frames","-of","json",str(mp4)], capture_output=True, text=True, timeout=60, check=True)
        media = json.loads(probe.stdout); v = next(s for s in media["streams"] if s["codec_type"]=="video")
        if v.get("codec_name") != "h264" or v.get("width") != 768 or v.get("height") != 1376: raise RuntimeError(f"unexpected media {media}")
        frames = OUTPUT/"frames"; frames.mkdir(exist_ok=True)
        for sec in (1,7,13):
            subprocess.run(["ffmpeg","-y","-v","error","-ss",str(sec),"-i",str(mp4),"-frames:v","1",str(frames/f"t{sec}s.png")], check=True, timeout=60)
        result.update({"server_wall_s": server_wall(entry), "video": {"bytes": mp4.stat().st_size, "sha256": hashlib.sha256(mp4.read_bytes()).hexdigest(), "probe": media}, "frames": [f"frames/t{s}s.png" for s in (1,7,13)]})
        result["state"] = "success"; print(f"SMOKE_OK {prompt_id} wall={result['server_wall_s']}", flush=True)
    except Exception as exc:
        result["state"] = "failed"; result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        result["finished_at_utc"] = now(); result["wall_s"] = round(time.monotonic()-started, 2)
        (OUTPUT/"phase.json").write_text(json.dumps(result, indent=2)+"\n")
        publish_verified(OUTPUT, f"{REMOTE}/SMOKE", Path("/content/rclone"), Path("/content/rclone.conf"), timeout=1200)
    print("SMOKE_PHASE_RESULT", json.dumps(result), flush=True)
    if result["state"] != "success": raise RuntimeError("smoke phase failed")
if __name__ == "__main__": main()
