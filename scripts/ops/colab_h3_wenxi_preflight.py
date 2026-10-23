"""Colab wenxi preflight: /object_info all class_types + model files by name + SHA for present.

Runs inside the Colab guest; hashes the restored local ``models/`` tree
(which now includes the 7 wenxi models merged into the main Drive tree),
so a full match here proves restore brought every model down correctly.
"""
import hashlib, json, os, subprocess, time
from pathlib import Path
from urllib.request import urlopen

COMFY = Path("/content/h3-rental/ComfyUI")
INPUT = Path("/content/wenxi_setup/input")
OUT = Path("/content/wenxi_setup/preflight.json")
REMOTE = os.environ["H3_WENXI_REMOTE"]
KNOWN_SHA = {
 "minimax_h3_video_vae_int8_convrot.safetensors": "9bb2d96f218c76babd85e0611b85ca8fb330a90546c01a0005e8a58a59593410",
 "minimax_h3_audio_vae_fp32.safetensors": "8e505d95dd1561d47abd43d4238fd40d9bb1ae9e147ed0a4cba778d76ae4db48",
 "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors": "35a88d51044231fe332301d7a62aa81e3f2cba62febeb446e2c1e3e0ef76f2c6",
 "minimax_h3_hybrid_fl2va_ref2va_b25-49-int8.safetensors": "a629cfea8d89a071b140c6e1935dc9a23e72de6badc18975a2bb9e6d1423d76d",
 "MysticXXX_MMH3-V1.safetensors": "7dd837f4c5420d4ec59f3ff1757b3f9d264a6c0f120d65d9c4f59c77584dd0be",
 "minimax_h3_dmad_full_dareties_v4_step600_comfy_fro.safetensors": "4d4ea608992d72303e4971f78728f587f43ecb72490f365a042ed82e37a907ce",
 "H3_Combat_V2.safetensors": "5b3edb09e9d6029439badf9bc9db4ba4a355ae679b0810888de82c4793c0bac8",
 "H3_Fight_Flow_V1.safetensors": "579e8eca67b6d70f4db94b2db67cd938751d576ee3d72aba875dae3d911f7398",
 "Motion_Repair_V2.safetensors": "edfa0e2858caeba7be9108883f61da8525d3c58af998c94ac7a449d9603d7574",
 "motion_speed_slider_mmh3_v1.1.safetensors": "e5970e97f8a5aa69e3ddc8d2ec4018e6c493cf8c7d0f1f1aa5c17d16e01270b1",
 "minimax_h3_latent_upscaler_3d_fp16.safetensors": "043e5a48e161610ef6c3ea974645220354d06fa618abca15f76d084812eb55c2",
 "taeh3.safetensors": "f0f60fa072089997f817402098c2fd90777cb2660dd79cf5df42fc1e3e08e527",
}
def digest(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(8*1024*1024), b""): h.update(b)
    return h.hexdigest()

manifest = json.loads((INPUT/"manifest.json").read_text())
with urlopen("http://127.0.0.1:8188/system_stats", timeout=10) as r: stats = json.load(r)
device = stats["devices"][0]["name"]
with urlopen("http://127.0.0.1:8188/object_info", timeout=120) as r: oi = json.load(r)
classes = manifest["class_types"]
missing_nodes = [c for c in classes if c not in oi]
print("NODES", len(classes), "missing", missing_nodes, flush=True)
by_name = {}
for p in (COMFY/"models").rglob("*.safetensors"): by_name.setdefault(p.name, p)
records = []
for name in manifest["model_files"]:
    p = by_name.get(name); exp = KNOWN_SHA.get(name)
    rec = {"file": name, "expected_sha256": exp, "present": p is not None,
           "path": str(p) if p else None, "bytes": p.stat().st_size if p else None,
           "sha256": None, "match": None}
    if p is not None:
        rec["sha256"] = digest(p); rec["match"] = (rec["sha256"] == exp) if exp else None
        print("HASH", name, rec["sha256"], "match", rec["match"], flush=True)
    else:
        print("MISSING_MODEL", name, flush=True)
    records.append(rec)
missing_models = [r["file"] for r in records if not r["present"]]
bad_sha = [r["file"] for r in records if r["present"] and r["match"] is False]
# uploaded smoke inputs: assets + wired prompt + workflow
for a in manifest.get("assets", []):
    p = INPUT/a["file"]; actual = digest(p) if p.is_file() else None
    records.append({"file": a["file"], "expected_sha256": a["sha256"], "present": p.is_file(),
                    "path": str(p), "bytes": p.stat().st_size if p.is_file() else None,
                    "sha256": actual, "match": actual == a["sha256"]}); print("HASH", a["file"], records[-1]["match"], flush=True)
for fname, exp in ((manifest.get("prompt_file","prompt_wired.txt"), manifest.get("prompt_sha256")),
                   ("workflow_api.json", manifest.get("workflow_sha256"))):
    p = INPUT/fname; actual = digest(p) if p.is_file() else None
    records.append({"file": fname, "expected_sha256": exp, "present": p.is_file(), "path": str(p),
                    "bytes": p.stat().st_size if p.is_file() else None, "sha256": actual, "match": actual == exp})
    print("HASH", fname, records[-1]["match"], flush=True)
bad_sha = [r["file"] for r in records if r["present"] and r["match"] is False]
missing_any = [r["file"] for r in records if not r["present"]]
ok = not missing_nodes and not missing_any and not bad_sha and "cudaMallocAsync" not in device and "RTX PRO 6000" in device
report = {"checked_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "device": device,
  "native_allocator": "cudaMallocAsync" not in device, "class_types_required": classes,
  "missing_nodes": missing_nodes, "models": records, "missing_models": missing_models,
  "bad_sha": bad_sha, "all_match": ok, "workflow_sha256": manifest["workflow_sha256"]}
OUT.parent.mkdir(parents=True, exist_ok=True); OUT.write_text(json.dumps(report, indent=2)+"\n")
subprocess.run(["/content/rclone","copyto",str(OUT),f"{REMOTE}/preflight.json","--config","/content/rclone.conf"],check=True,timeout=120)
print("WENXI_PREFLIGHT_OK" if ok else f"WENXI_PREFLIGHT_FAIL nodes={missing_nodes} models={missing_models} bad_sha={bad_sha}", flush=True)
if not ok: raise RuntimeError("wenxi preflight did not pass; do not submit")
