"""Reject a Colab assignment that is not the intended G4 Blackwell GPU."""

import json
import subprocess

import torch


name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
capability = torch.cuda.get_device_capability(0) if torch.cuda.is_available() else None
memory = torch.cuda.get_device_properties(0).total_memory if torch.cuda.is_available() else 0
smi = subprocess.run(
    ["nvidia-smi", "--query-gpu=name,memory.total,driver_version,power.limit,clocks.max.sm",
     "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=15,
)
print(json.dumps({"name": name, "capability": capability, "vram_bytes": memory,
                  "torch": torch.__version__, "torch_cuda": torch.version.cuda,
                  "smi": smi.stdout.strip(), "smi_exit": smi.returncode}, indent=2), flush=True)
if (not name or "RTX PRO 6000" not in name or capability != (12, 0)
        or memory < 90_000_000_000 or smi.returncode):
    raise RuntimeError("assigned GPU does not meet G4 RTX PRO 6000 SM120 96GB gate")
print("G4_IDENTITY_OK", flush=True)
