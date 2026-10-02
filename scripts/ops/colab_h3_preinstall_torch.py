"""Pin the Torch/CUDA ABI used by the frozen Colab H3 runtime."""

import json
import os
import subprocess
import time
from pathlib import Path


def main() -> None:
    venv = Path("/content/h3-rental/ComfyUI/.venv")
    venv.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["UV_CACHE_DIR"] = "/content/uv-cache"
    started = time.monotonic()
    steps = [
        ["uv", "venv", "--python", "/usr/bin/python3.13", "--system-site-packages", str(venv)],
        ["uv", "pip", "install", "--python", str(venv / "bin/python"),
         "torch==2.14.0+cu130", "--index-url", "https://download.pytorch.org/whl/cu130"],
    ]
    for command in steps:
        result = subprocess.run(command, capture_output=True, text=True, env=env, timeout=600)
        print(json.dumps({"command": command, "exit": result.returncode,
                          "elapsed_s": round(time.monotonic() - started, 1),
                          "tail": (result.stdout + result.stderr)[-2500:]}, indent=2), flush=True)
        if result.returncode:
            raise RuntimeError("failed to pin H3 Torch/CUDA runtime")
    probe = subprocess.run(
        [str(venv / "bin/python"), "-c",
         "import torch; print(torch.__version__, torch.version.cuda, "
         "int(torch._C._GLIBCXX_USE_CXX11_ABI))"],
        capture_output=True, text=True, timeout=60,
    )
    print(json.dumps({"probe_exit": probe.returncode, "probe": probe.stdout.strip(),
                      "probe_error": probe.stderr[-1000:]}, indent=2), flush=True)
    if probe.returncode or probe.stdout.strip() != "2.14.0+cu130 13.0 1":
        raise RuntimeError("pinned H3 Torch/CUDA ABI probe failed")


if __name__ == "__main__":
    main()
