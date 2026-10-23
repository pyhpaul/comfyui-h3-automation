"""Colab: install comfyui-SelfLift (pinned) + restart Comfy with native CUDA allocator."""
import json, os, subprocess, time
from pathlib import Path
from urllib.request import urlopen

COMFY = Path("/content/h3-rental/ComfyUI")
PIN = "835c3cf7919410f71f414688f049c6ca497789d0"
URL = "https://github.com/facok/comfyui-SelfLift.git"

def run(*a, **kw):
    print("RUN", " ".join(a), flush=True); subprocess.run(a, check=True, **kw)

dest = COMFY / "custom_nodes/comfyui-SelfLift"
if not dest.is_dir():
    run("git", "clone", URL, str(dest))
run("git", "-C", str(dest), "fetch", "--depth", "1", "origin", PIN)
run("git", "-C", str(dest), "checkout", PIN)
print("SELFLIFT_HEAD", subprocess.run(["git","-C",str(dest),"rev-parse","HEAD"],capture_output=True,text=True,check=True).stdout.strip(), flush=True)
req = dest / "requirements.txt"
if req.is_file():
    run(str(COMFY/".venv/bin/python"), "-m", "pip", "install", "-r", str(req))
else:
    print("SELFLIFT_NO_REQUIREMENTS", flush=True)

# kill existing Comfy (started by setup with archived script = cudaMallocAsync)
subprocess.run(["pkill", "-f", "main.py.*--port 8188"], check=False)
for _ in range(30):
    try:
        urlopen("http://127.0.0.1:8188/system_stats", timeout=2); time.sleep(1)
    except Exception:
        break
log = COMFY / "comfyUI-h3-wenxi.log"
stream = log.open("wb")
env = os.environ.copy(); env["CUDA_VISIBLE_DEVICES"] = "0"
proc = subprocess.Popen([str(COMFY/".venv/bin/python"), "main.py", "--listen", "127.0.0.1", "--port", "8188",
    "--cuda-device", "0", "--lowvram", "--reserve-vram", "4", "--disable-smart-memory",
    "--disable-cuda-malloc", "--force-fp16", "--disable-cuda-graphs", "--enable-manager"],
    cwd=str(COMFY), env=env, stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
device = None
for _ in range(90):
    if proc.poll() is not None: raise RuntimeError(f"Comfy exited {proc.returncode}; see {log}")
    try:
        with urlopen("http://127.0.0.1:8188/system_stats", timeout=3) as r: stats = json.load(r)
        device = stats["devices"][0]["name"]; break
    except Exception: time.sleep(2)
print("WENXI_DEVICE", device, flush=True)
if not device or "RTX PRO 6000" not in device: raise RuntimeError(f"unexpected device {device}")
if "cudaMallocAsync" in device: raise RuntimeError("allocator still cudaMallocAsync; native restart failed")
print("WENXI_NATIVE_ALLOCATOR_OK", device, flush=True)
