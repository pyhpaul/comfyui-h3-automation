"""Hash-locked, reversible H3 attention metadata hook for archived KJNodes."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


EXPECTED_SHA256 = "11286583c56e653dbd57f5e8eda6902c84b759f16b359b3bf0c895b43e6b5364"
RELATIVE_SOURCE = Path("custom_nodes/ComfyUI-KJNodes/nodes/ltxv_nodes.py")
ANCHOR = ("        o = _sageattn_int8_fp8_nhd(qkv, dtype)\n"
          "        return self.out_proj(o.view(s, self.heads * self.head_dim))")
PATCH = ("        if os.environ.get(\"H3_A100_ATTENTION_PROBE\") == \"1\":\n"
         "            from h3_a100_attention_probe import probe_attention\n"
         "            o = probe_attention(qkv, dtype, _sageattn_int8_fp8_nhd)\n"
         "        else:\n"
         "            o = _sageattn_int8_fp8_nhd(qkv, dtype)\n"
         "        return self.out_proj(o.view(s, self.heads * self.head_dim))")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def instrument_text(source: str) -> str:
    if source.count(ANCHOR) != 1 or source.count("import types\n") != 1:
        raise RuntimeError("archived H3 attention anchor mismatch")
    return source.replace("import types\n", "import types\nimport os\n", 1).replace(ANCHOR, PATCH, 1)


def install(root: Path, backup_dir: Path) -> dict[str, str]:
    source = root / RELATIVE_SOURCE
    original = source.read_bytes()
    if digest(original) != EXPECTED_SHA256:
        raise RuntimeError("KJNodes source differs from the frozen archived version")
    if backup_dir.exists():
        raise RuntimeError(f"attention backup already exists: {backup_dir}")
    patched = instrument_text(original.decode()).encode()
    backup_dir.mkdir(parents=True)
    shutil.copy2(source, backup_dir / "ltxv_nodes.py")
    manifest = {"source": str(source), "original_sha256": digest(original),
                "patched_sha256": digest(patched)}
    (backup_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    source.write_bytes(patched)
    return manifest


def restore(root: Path, backup_dir: Path) -> None:
    source = root / RELATIVE_SOURCE
    manifest = json.loads((backup_dir / "manifest.json").read_text())
    if digest(source.read_bytes()) != manifest["patched_sha256"]:
        raise RuntimeError("patched attention source changed; refusing overwrite")
    original = (backup_dir / "ltxv_nodes.py").read_bytes()
    if digest(original) != manifest["original_sha256"]:
        raise RuntimeError("attention source backup hash mismatch")
    source.write_bytes(original)
