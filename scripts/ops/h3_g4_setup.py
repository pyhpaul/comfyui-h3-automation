"""Install the frozen H3 runtime and the locally built SM120 SageAttention wheel."""

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from urllib.request import urlopen


root = Path("/content/h3-rental/ComfyUI")
python = root / ".venv/bin/python"
wheel = Path("/content/sageattention-2.2.0-cp313-cp313-linux_x86_64.whl")
expected = os.environ["H3_G4_WHEEL_SHA256"]
started = time.monotonic()


def run(*args: str) -> None:
    print("RUN", " ".join(args), flush=True)
    subprocess.run(args, check=True)


if hashlib.sha256(wheel.read_bytes()).hexdigest() != expected:
    raise RuntimeError("SM120 SageAttention wheel hash mismatch")
if not python.is_file():
    raise RuntimeError("pinned Python environment is missing")
run("uv", "pip", "install", "--python", str(python), "-r", str(root / "requirements.txt"))
for name in ("ComfyUI-KJNodes", "ComfyUI-VideoHelperSuite", "ComfyUI-Easy-Use", "kaytool"):
    run("uv", "pip", "install", "--python", str(python), "-r",
        str(root / "custom_nodes" / name / "requirements.txt"))
run("uv", "pip", "install", "--python", str(python), "httpx==0.28.1")
run("uv", "pip", "install", "--python", str(python), "--no-deps", str(wheel))
run(str(python), "-c", "import torch, sageattention; from sageattention import _qattn_sm89, _fused; "
    "assert torch.__version__ == '2.14.0+cu130'; "
    "assert torch.cuda.get_device_capability(0) == (12, 0); "
    "assert hasattr(_qattn_sm89, 'qk_int8_sv_f8_accum_f32_attn'); "
    "print('sage_sm120_import_ready', sageattention.__file__, _fused.__file__)")

env = os.environ.copy()
env["COMFY_ROOT"] = str(root)
env["COMFY_H3_LOG"] = str(root / "comfyUI-h3.log")
process = subprocess.Popen(["bash", "/content/h3-runner/scripts/ops/comfy_gpu_start.sh"],
                           env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, start_new_session=True)
for attempt in range(90):
    if process.poll() is not None:
        raise RuntimeError(f"ComfyUI exited during startup: {process.returncode}")
    try:
        with urlopen("http://127.0.0.1:8188/system_stats", timeout=3) as response:
            stats = json.load(response)
        name = stats["devices"][0]["name"]
        if "RTX PRO 6000" not in name:
            raise RuntimeError(f"unexpected ComfyUI device: {name}")
        print("comfy_ready", json.dumps({"device": name, "attempt": attempt + 1,
             "setup_seconds": round(time.monotonic() - started, 2)}), flush=True)
        break
    except (OSError, KeyError, IndexError, ValueError):
        time.sleep(2)
else:
    raise RuntimeError("ComfyUI did not become ready")
