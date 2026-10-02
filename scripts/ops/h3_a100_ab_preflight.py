"""Verify frozen A100 A/B inputs after the one-time Colab restore."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


CONTENT = Path("/content")
COMFY = CONTENT / "h3-rental/ComfyUI"
RUNNER = CONTENT / "h3-runner"
OUTPUT = CONTENT / "h3-a100-ab/preflight.json"
REMOTE = "h3drive_h3:comfyui-h3-colab-dedicated/rental-20260924-5090/a100-perf-pilot/formal-ab-1"
ASSETS = {
    COMFY / "models/vae/minimax_h3_video_vae_int8_convrot.safetensors": "9bb2d96f218c76babd85e0611b85ca8fb330a90546c01a0005e8a58a59593410",
    COMFY / "models/vae/minimax_h3_audio_vae_fp32.safetensors": "8e505d95dd1561d47abd43d4238fd40d9bb1ae9e147ed0a4cba778d76ae4db48",
    COMFY / "models/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors": "35a88d51044231fe332301d7a62aa81e3f2cba62febeb446e2c1e3e0ef76f2c6",
    COMFY / "models/diffusion_models/minimax_h3_hybrid_fl2va_ref2va_b25-49-int8.safetensors": "a629cfea8d89a071b140c6e1935dc9a23e72de6badc18975a2bb9e6d1423d76d",
    COMFY / "models/loras/MysticXXX_MMH3-V1.safetensors": "7dd837f4c5420d4ec59f3ff1757b3f9d264a6c0f120d65d9c4f59c77584dd0be",
    COMFY / "models/loras/minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors": "7098acf3ee75028fd9fcd948f50fcc8d995057fabb76f86bd3ca2c0ffc58e409",
    RUNNER / "jobs/ep_units/EP04-H3-manual-v16-U02/assets/prompt_source.txt": "14f083a4b95b47125bd0226a38de182216a8a75750c84ae0ba23232cd71b6f11",
    RUNNER / "jobs/ep_units/EP04-H3-manual-v16-U02/assets/id0-char-001.png": "34361d08d64c11663840e3d3085f72359f70c6082a9b6b39031c035876e82c67",
    RUNNER / "jobs/ep_units/EP04-H3-manual-v16-U02/assets/id1-char-012-overseer-gorke-v4-right-eye-patch.png": "34eb810dd71d39d44cc4964fabbbd244a18b834852d31402820a93b128edec3d",
    RUNNER / "jobs/ep_units/EP04-H3-manual-v16-U02/assets/id2-scene-013.png": "63859afe287249d9d867e756b3de48897e9d10647d4ffce065be39ba8586c4b7",
    RUNNER / "jobs/ep_units/EP04-H3-manual-v16-U02/assets/id3-prop-016-barbed-steel-whip-v2.png": "63bda7a744753b3754430193647f9b2425c9ffad7477514c2d90e3769b3dd52b",
    RUNNER / "src/comfy_orch/gpu_adapt.py": "138218e54c2df112b88eea10035faf564fd8111ef6cc79ecdd8c2ae53a4cb2bf",
    COMFY / "custom_nodes/ComfyUI-KJNodes/nodes/ltxv_nodes.py": "11286583c56e653dbd57f5e8eda6902c84b759f16b359b3bf0c895b43e6b5364",
}
PARENT = COMFY / "output/h3_context/ep04_u01_00001.safetensors"


def digest(path: Path, algorithm: str) -> str:
    value = hashlib.new(algorithm)
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    records = []
    expected_assets = dict(ASSETS)
    gpu_adapt = RUNNER / "src/comfy_orch/gpu_adapt.py"
    if override := os.environ.get("H3_GPU_ADAPT_EXPECTED_SHA256"):
        expected_assets[gpu_adapt] = override
    for path, expected in expected_assets.items():
        started = time.monotonic()
        actual = digest(path, "sha256") if path.is_file() else None
        records.append({"path": str(path), "bytes": path.stat().st_size if path.is_file() else None,
                        "sha256": actual, "expected": expected, "match": actual == expected,
                        "elapsed_s": round(time.monotonic() - started, 2)})
        print("HASH", path.name, records[-1]["match"], flush=True)
    parent_actual = digest(PARENT, "md5") if PARENT.is_file() else None
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "assets": records,
              "parent_md5": parent_actual, "parent_match": parent_actual == "1fb13e523c23b48b0b9480b18016f91a"}
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n")
    evidence_remote = os.environ.get("H3_AB_PREFLIGHT_REMOTE", REMOTE)
    subprocess.run(["/content/rclone", "copyto", str(OUTPUT), f"{evidence_remote}/preflight.json",
                    "--config", "/content/rclone.conf"], check=True, timeout=120)
    if not all(item["match"] for item in records) or not report["parent_match"]:
        raise RuntimeError("frozen A/B input mismatch; do not start paid prompts")
    print("PREFLIGHT_OK", len(records), flush=True)


if __name__ == "__main__":
    main()
