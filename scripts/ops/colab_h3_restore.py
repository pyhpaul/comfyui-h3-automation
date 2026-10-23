"""Restore the frozen H3 source, six models, and U01 parent on Colab.

This is the source-controlled successor of the tested D: stage-2 restore
script. The default remote remains the immutable 2026-09-24 snapshot.
"""

from __future__ import annotations

import gzip
import hashlib
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable


REMOTE = os.environ.get(
    "H3_RESTORE_REMOTE",
    "h3drive_h3:comfyui-h3-colab-dedicated/rental-20260924-5090",
)
CONTENT = Path("/content")
COMFY_ROOT = CONTENT / "h3-rental/ComfyUI"
RCLONE = CONTENT / "rclone"
CONFIG = CONTENT / "rclone.conf"
PART_SIZE = 512 * 1024 * 1024
LARGE_MODELS = (
    ("vae/minimax_h3_video_vae_int8_convrot.safetensors", 3_171_670_912,
     "9bb2d96f218c76babd85e0611b85ca8fb330a90546c01a0005e8a58a59593410"),
    ("text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", 15_687_142_551,
     "35a88d51044231fe332301d7a62aa81e3f2cba62febeb446e2c1e3e0ef76f2c6"),
    ("diffusion_models/minimax_h3_hybrid_fl2va_ref2va_b25-49-int8.safetensors", 20_970_379_632,
     "a629cfea8d89a071b140c6e1935dc9a23e72de6badc18975a2bb9e6d1423d76d"),
)


def run(*args: str) -> None:
    print("RUN", " ".join(args), flush=True)
    subprocess.run(args, check=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def restore_split_model(models: Path, relative_path: str, expected_size: int,
                        expected_sha256: str) -> None:
    output = models / relative_path
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(output.name + ".incomplete")
    part = CONTENT / "h3-model-part.tmp"
    digest = hashlib.sha256()
    copied = 0
    part_count = (expected_size + PART_SIZE - 1) // PART_SIZE
    try:
        with partial.open("wb") as assembled:
            for index in range(part_count):
                part.unlink(missing_ok=True)
                run(str(RCLONE), "copyto",
                    f"{REMOTE}/model-parts/{relative_path}/part-{index:03d}",
                    str(part), "--config", str(CONFIG),
                    "--retries", "3", "--low-level-retries", "3")
                expected_part_size = min(PART_SIZE, expected_size - copied)
                if part.stat().st_size != expected_part_size:
                    raise RuntimeError(f"wrong part size: {relative_path} part-{index:03d}")
                with part.open("rb") as source:
                    for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
                        assembled.write(block)
                        digest.update(block)
                        copied += len(block)
                part.unlink()
                print("model_part", relative_path, index + 1, part_count, flush=True)
        if copied != expected_size or digest.hexdigest() != expected_sha256:
            raise RuntimeError(f"reassembled model mismatch: {relative_path}")
        partial.replace(output)
    finally:
        part.unlink(missing_ok=True)


def main(*, restore_model: Callable[[Path, str, int, str], None] | None = None) -> None:
    started = time.monotonic()
    with gzip.open(CONTENT / "rclone.gz", "rb") as compressed, RCLONE.open("wb") as binary:
        shutil.copyfileobj(compressed, binary)
    os.chmod(RCLONE, 0o700)
    os.chmod(CONFIG, 0o600)

    source_archive = CONTENT / "source-only.tar"
    runner_archive = CONTENT / "colab-stage2-runner.tar"
    run(str(RCLONE), "copyto", f"{REMOTE}/source-only.tar", str(source_archive),
        "--config", str(CONFIG))
    if sha256(source_archive) != "db6e20a71fe6ac87c7a4a981f08ae0685db7c0229d3db5bdd5b51f0832ab1fc7":
        raise RuntimeError("source-only.tar SHA-256 mismatch")
    (CONTENT / "h3-rental").mkdir(exist_ok=True)
    run("tar", "-xf", str(source_archive), "-C", str(CONTENT / "h3-rental"))

    run(str(RCLONE), "copyto", f"{REMOTE}/colab-stage2-runner.tar",
        str(runner_archive), "--config", str(CONFIG))
    if sha256(runner_archive) != "8ac917e997722abcb5b11a6f1068a260fdc2dc092b243075d524dadb151b1f5a":
        raise RuntimeError("colab-stage2-runner.tar SHA-256 mismatch")
    runner_root = CONTENT / "h3-runner"
    runner_root.mkdir(exist_ok=True)
    run("tar", "-xf", str(runner_archive), "-C", str(runner_root))

    models = COMFY_ROOT / "models"
    models.mkdir(parents=True, exist_ok=True)
    model_start = time.monotonic()
    run(str(RCLONE), "copy", f"{REMOTE}/models", str(models),
        "--config", str(CONFIG), "--transfers", "3", "--checkers", "3",
        "--stats", "1m", "--stats-one-line")
    run(str(RCLONE), "check", f"{REMOTE}/models", str(models),
        "--config", str(CONFIG))
    for relative_path, expected_size, expected_sha256 in LARGE_MODELS:
        (restore_model or restore_split_model)(
            models, relative_path, expected_size, expected_sha256)
    print("model_restore_seconds", round(time.monotonic() - model_start, 2), flush=True)

    latent = COMFY_ROOT / "output/h3_context/ep04_u01_00001.safetensors"
    latent.parent.mkdir(parents=True, exist_ok=True)
    run(str(RCLONE), "copyto", f"{REMOTE}/parent/h3_context/{latent.name}",
        str(latent), "--config", str(CONFIG))
    if sha256(latent) != "6def89c01d367a64be354a93dfb7e96806d236211eb0fdfcbf4bfe493a95946a":
        raise RuntimeError("parent latent SHA-256 mismatch")
    model_count = len(list(models.rglob("*.safetensors")))
    if model_count != 6:
        raise RuntimeError(f"expected six H3 models, found {model_count}")
    print("restore_ready", {"models": model_count,
                            "seconds": round(time.monotonic() - started, 2)}, flush=True)


if __name__ == "__main__":
    main()
