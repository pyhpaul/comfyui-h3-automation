from __future__ import annotations

import re
from pathlib import Path

from comfy_orch.errors import ValidationError

_TITLE = re.compile(
    r"^EP\d+\s*[｜|]\s*(U\d+)\s*[｜|]\s*(.+?)\s*[｜|]\s*(\d+)\s*秒",
    re.I | re.M,
)
_ASSET_NUM = re.compile(r"^\s*(\d+)\.\s+(.+)$")
_ASSET_PATH = re.compile(
    r"images[/\\](?:characters|props|scenes)[/\\][^\s]+\.(?:png|jpe?g|webp)",
    re.I,
)
_SHOT = re.compile(
    r"【镜头\s*(\d+)\s*｜\s*([^｜]+)｜\s*([^】]+)】\s*(.+?)(?=\n【镜头|\n【H3|\n【交出|\Z)",
    re.S,
)
_DIALOGUE = re.compile(r'([A-Z][A-Z\s]*?):\s*[“\"]([^”\"]+)[”\"]')


def _section(text: str, name: str) -> str:
    m = re.search(rf"【{re.escape(name)}】\s*(.+?)(?=\n【|\Z)", text, re.S)
    return m.group(1).strip() if m else ""


def parse_review_sections(text: str) -> dict[str, str]:
    title_m = _TITLE.search(text)
    if not title_m:
        raise ValidationError("review draft missing EP01｜Uxx｜title｜N秒 header")
    return {
        "unit_id": title_m.group(1).upper(),
        "title": title_m.group(2).strip(),
        "duration_seconds": title_m.group(3),
        "reference": _section(text, "参考设定"),
        "atmosphere": _section(text, "氛围与画质"),
        "director": _section(text, "导演意图与表演回写"),
        "latent_in": _section(text, "H3 latent 接入文字"),
        "handoff": _section(text, "交出状态"),
        "latent_relay": _section(text, "H3 latent 接力文字"),
        "shots": text,
    }


def parse_review_asset_labels(text: str) -> list[tuple[str, str]]:
    """Return ordered (filename_stem_hint, label) from upload-order block."""
    out: list[tuple[str, str]] = []
    in_block = False
    pending_label: str | None = None
    for line in text.splitlines():
        if "资产上传路径" in line:
            in_block = True
            continue
        if not in_block:
            continue
        if not line.strip():
            if out:
                break
            continue
        if line.startswith("【"):
            break
        m_num = _ASSET_NUM.match(line)
        if m_num:
            pending_label = m_num.group(2).strip()
            continue
        m_path = _ASSET_PATH.search(line.replace("\\", "/"))
        if m_path and pending_label:
            fname = Path(m_path.group(0).split("/")[-1]).stem
            out.append((fname, pending_label))
            pending_label = None
    return out


def parse_review_shots(text: str) -> list[tuple[int, str, str, str]]:
    shots: list[tuple[int, str, str, str]] = []
    for m in _SHOT.finditer(text):
        shots.append(
            (
                int(m.group(1)),
                m.group(2).strip(),
                m.group(3).strip(),
                m.group(4).strip(),
            )
        )
    return shots


def parse_review_dialogues(text: str) -> list[tuple[str, str]]:
    return [(m.group(1).strip(), m.group(2).strip()) for m in _DIALOGUE.finditer(text)]


def match_asset_label(asset_labels: list[tuple[str, str]], slot_path: str) -> str:
    stem = Path(slot_path).stem.lower()
    for fname, label in asset_labels:
        if fname.lower() in stem or stem in fname.lower():
            return label
    return ""


def list_review_unit_files(pack_root: Path) -> list[Path]:
    root = pack_root.resolve()
    if not root.is_dir():
        raise ValidationError(f"review pack dir not found: {root}")
    files = sorted(root.glob("U*.txt"))
    if not files:
        raise ValidationError(f"no U*.txt review drafts under {root}")
    return files


def find_review_unit_file(pack_root: Path, unit_id: str) -> Path:
    want = unit_id.upper()
    if not want.startswith("U"):
        want = f"U{want}"
    m = re.match(r"U(\d+)$", want, re.I)
    if m:
        want = f"U{int(m.group(1)):02d}"
    for path in list_review_unit_files(pack_root):
        if path.name.upper().startswith(want + "_"):
            return path
    raise ValidationError(f"review draft not found for {unit_id} in {pack_root}")
