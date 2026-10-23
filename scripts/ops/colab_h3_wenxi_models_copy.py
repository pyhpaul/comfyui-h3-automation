"""Colab: no-op validation that the 7 wenxi models arrived via restore.

Since 2026-10-21 the wenxi models live in the main Drive models tree
(``rental-20260924-5090/models/``) and are brought down by
``colab_h3_restore.py``; there is no separate copy stage. This script only
verifies the 7 files are present in the restored local models tree and
prints the legacy marker so old callers keep working.
"""
from pathlib import Path

COMFY = Path("/content/h3-rental/ComfyUI")
EXPECTED = [
    "loras/minimax_h3_dmad_full_dareties_v4_step600_comfy_fro.safetensors",
    "loras/H3_Combat_V2.safetensors",
    "loras/H3_Fight_Flow_V1.safetensors",
    "loras/Motion_Repair_V2.safetensors",
    "loras/motion_speed_slider_mmh3_v1.1.safetensors",
    "latent_upscale_models/minimax_h3_latent_upscaler_3d_fp16.safetensors",
    "vae_approx/taeh3.safetensors",
]
missing = [rel for rel in EXPECTED if not (COMFY / "models" / rel).is_file()]
names = sorted(p.name for p in (COMFY / "models").rglob("*.safetensors"))
print("MODEL_FILES", len(names), names, flush=True)
if missing:
    raise RuntimeError(f"wenxi models missing after restore (expected merged in main tree): {missing}")
print("WENXI_MODELS_COPY_OK", flush=True)
