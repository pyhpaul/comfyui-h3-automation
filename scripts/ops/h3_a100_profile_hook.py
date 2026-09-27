"""Reversible, hash-locked profiler hook for the archived ComfyUI sampler."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


EXPECTED_SHA256 = "b0ba1521c72475e06fed15db004274ed7c8bb2bf73f1d58849faf6f9f9d264fe"
RELATIVE_SOURCE = Path("comfy_extras/nodes_custom_sampler.py")
ANCHOR = ("        samples = guider.sample(noise.generate_noise(latent), latent_image, sampler, "
          "sigmas, denoise_mask=noise_mask, callback=callback, disable_pbar=disable_pbar, "
          "seed=noise.seed)")
PATCH = ("        if os.environ.get(\"H3_PROFILE_SAMPLER\") == \"1\":\n"
         "            from h3_a100_profile_runtime import profile_sampler\n"
         "            samples = profile_sampler(lambda: guider.sample(noise.generate_noise(latent), "
         "latent_image, sampler, sigmas, denoise_mask=noise_mask, callback=callback, "
         "disable_pbar=disable_pbar, seed=noise.seed))\n"
         "        else:\n"
         "            samples = guider.sample(noise.generate_noise(latent), latent_image, "
         "sampler, sigmas, denoise_mask=noise_mask, callback=callback, "
         "disable_pbar=disable_pbar, seed=noise.seed)")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def instrument_text(source: str) -> str:
    if source.count(ANCHOR) != 1 or source.count("import math\n") != 1:
        raise RuntimeError("archived ComfyUI sampler anchor mismatch")
    return source.replace("import math\n", "import math\nimport os\n", 1).replace(ANCHOR, PATCH, 1)


def install(root: Path, backup_dir: Path) -> dict[str, str]:
    source = root / RELATIVE_SOURCE
    original = source.read_bytes()
    if digest(original) != EXPECTED_SHA256:
        raise RuntimeError("ComfyUI sampler source differs from the frozen archived version")
    if backup_dir.exists():
        raise RuntimeError(f"profiler backup already exists: {backup_dir}")
    patched = instrument_text(original.decode()).encode()
    backup_dir.mkdir(parents=True)
    shutil.copy2(source, backup_dir / "nodes_custom_sampler.py")
    manifest = {"source": str(source), "original_sha256": digest(original),
                "patched_sha256": digest(patched)}
    (backup_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    source.write_bytes(patched)
    return manifest


def restore(root: Path, backup_dir: Path) -> None:
    source = root / RELATIVE_SOURCE
    manifest = json.loads((backup_dir / "manifest.json").read_text())
    if digest(source.read_bytes()) != manifest["patched_sha256"]:
        raise RuntimeError("patched sampler changed; refusing to overwrite it")
    original = (backup_dir / "nodes_custom_sampler.py").read_bytes()
    if digest(original) != manifest["original_sha256"]:
        raise RuntimeError("profiler backup hash mismatch")
    source.write_bytes(original)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "restore"))
    parser.add_argument("--root", type=Path, default=Path("/content/h3-rental/ComfyUI"))
    parser.add_argument("--backup-dir", type=Path, default=Path("/content/h3-profile-original"))
    args = parser.parse_args()
    if args.action == "install":
        print(json.dumps(install(args.root, args.backup_dir)), flush=True)
    else:
        restore(args.root, args.backup_dir)
        print("PROFILE_HOOK_RESTORED", flush=True)


if __name__ == "__main__":
    main()
