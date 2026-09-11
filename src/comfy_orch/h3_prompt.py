from __future__ import annotations

import re
from pathlib import Path

_SECTION_HEADERS = (
    "subject_definitions",
    "summary",
    "retention_analysis",
    "detailed_description",
    "overall_soundscape",
    "non_diegetic_music",
)

_UPLOAD_ORDER_HEADER = re.compile(r"【本\s*U\s*实际上传顺序】")
_ATMOSPHERE = re.compile(r"【氛围与画质】\s*(.+?)(?=\n【|\n##|\Z)", re.S)
_SHOT = re.compile(
    r"【镜头\s*(\d+)\s*｜\s*([^｜]+)｜\s*([^】]+)】\s*(.+?)(?=\n【镜头|\Z)",
    re.S,
)
_TITLE = re.compile(r"^##\s+(.+)$", re.M)
_DURATION = re.compile(r"[（(](\d+)\s*s[）)]|[｜|]\s*(\d+)\s*秒", re.I)
_CJK = re.compile(r"[\u4e00-\u9fff]")

# Longer phrases first.
_PHRASE_EN: tuple[tuple[str, str], ...] = (
    ("1880 年代末维多利亚工业暗黑奇幻", "late-1880s Victorian industrial dark fantasy"),
    ("冷灰日光从高处漏下", "cold grey daylight leaking from above"),
    ("酸性紫黑毒液与煤尘蒸汽", "acidic purple-black toxin and coal-dust steam"),
    ("写实电影质感，高反差", "live-action cinematic look with high contrast"),
    ("湿石、铸铁门", "wet stone, cast-iron gate"),
    ("坠入毒池", "falls into the toxic pool"),
    ("干石带", "dry-stone ledge"),
    ("毒池", "toxic pool"),
    ("湿石", "wet stone"),
    ("北闸", "north gate"),
    ("门线", "gate line"),
    ("铁靴", "iron boots"),
    ("面具呼吸", "masked breathing"),
    ("长矛", "spears"),
    ("毒雾", "toxic mist"),
    ("毒液", "toxic liquid"),
    ("碎石", "stone shards"),
    ("守卫", "the guard"),
    ("双肩僵硬", "shoulders stiff"),
    ("压向池缘", "forced toward the pool edge"),
    ("同步前逼", "advancing together"),
    ("重心压向后脚", "shifts weight onto the rear foot"),
    ("鞋跟已临", "heels reach"),
    ("被逼退半步", "is forced back half a step"),
    ("右脚踩碎", "right foot cracks"),
    ("左臂挡矛", "blocks a spear with the left arm"),
    ("下颌绷紧", "jaw tight"),
    ("滑向池内", "slide toward the pool"),
    ("失去最后稳定支点", "loses the last stable foothold"),
    ("不穿越", "does not cross"),
    ("一记矛击只作用于肩侧", "a spear strike hits only the shoulder side"),
    ("离开干石带坠入中央", "leaves the dry-stone ledge and falls into the central"),
    ("从抗拒到失重", "from resistance to freefall"),
    ("手指抓空", "fingers clawing empty air"),
    ("落水后", "on impact,"),
    ("炸起", "erupts"),
    ("立刻从液面翻涌", "immediately surges from the liquid surface"),
    ("瞬间吞没", "instantly engulfs"),
    ("闷响、酸液飞溅", "a muffled impact and acid splash"),
    ("停在", "stops at"),
    ("矛杆摩石", "spear shafts grind on stone"),
    ("起始贴着", "starts pressed against"),
    ("先盯矛尖再", "first stares at the spear tips then"),
    ("任务是把", "task is to push"),
    ("触发是两支", "triggered as two"),
    ("结束时", "and by the end"),
    ("整个人", "the whole body"),
)


def _strip_upload_meta(text: str) -> str:
    match = _UPLOAD_ORDER_HEADER.search(text)
    if not match:
        return text
    end = match.start()
    head = text[:end]
    for marker in ("【上传素材】", "【独立图生视频提示词编号】"):
        idx = head.rfind(marker)
        if idx >= 0:
            head = head[:idx]
    rest = text[match.end() :]
    lines = rest.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            if i > 0:
                break
            continue
        if line.startswith("##"):
            break
        if re.match(r"^\d+\.\s+\S+", line):
            i += 1
            continue
        break
    return head.rstrip() + "\n\n" + "\n".join(lines[i:]).lstrip()


def _to_english(text: str) -> str:
    out = text
    out = re.sub(r"@[\w\-]+", "", out)
    for zh, en in _PHRASE_EN:
        out = out.replace(zh, en)
    out = out.replace("／", "/")
    out = re.sub(r"[，、；]", ", ", out)
    out = re.sub(r"[。！？]", ". ", out)
    out = re.sub(r"\s+", " ", out).strip(" ,.")
    # Drop residual CJK so H3 sees a clean English body.
    out = _CJK.sub("", out)
    out = re.sub(r"\s+", " ", out).strip(" ,.")
    return out


def _identity_label(path: str) -> str:
    stem = Path(path).stem
    low = stem.lower()
    if "char-001-detail" in low or ("char-001" in low and ("nape" in low or "detail" in low or "blood-contract" in low)):
        return "Liam's fresh nape blood-contract burn detail"
    if "char-001" in low:
        return "Liam, the male lead"
    if "char-002" in low:
        return "Mia, the female patient"
    if "char-010" in low or "nurse" in low:
        return "the Nurse / caregiver"
    if "char-003" in low or "vance" in low:
        return "Vance, the armored captain"
    if "char-004" in low or "vane" in low:
        return "Lord Vane, the noble host"
    if "char-007" in low or "recruiter" in low:
        return "the Recruiter / intake officer"
    if "char-011" in low or "lurker" in low:
        return "the unique corrupted lurker beast"
    if "char-009" in low or "guard" in low:
        return "the heavy-duty guard"
    if "prop-013" in low or "lure" in low or "powder" in low:
        return "the unique dark-red lure powder"
    if "prop-012" in low or "bone-core" in low or "beast-bone" in low:
        return "the unique pale-blue beast bone core"
    if "prop-007" in low or "resonance-crystal" in low or "crystal" in low:
        return "the resonance crystal on a fixed base"
    if "prop-008" in low or "failure-stamp" in low or "stamp" in low:
        return "the failure stamp prop"
    if "prop-011" in low or "drip" in low or "monitor" in low:
        return "the aether drip / mechanical monitor prop"
    if "prop-001" in low or "parchment" in low or "blood-contract" in low:
        return "the blood-contract parchment and copper quill prop"
    if "prop-002" in low or "nectar" in low:
        return "the Pure Nectar prop"
    if "prop-005" in low:
        return "the ward-side prop reference"
    if "prop-006" in low or "revolver" in low:
        return "the rune revolver prop"
    if "scene-002" in low:
        return "the top-floor private meeting room"
    if "scene-005" in low:
        return "the ward corridor / morgue deadline space"
    if "scene-006" in low:
        return "the Aether Rift gate military checkpoint at night"
    if "scene-007" in low:
        return "the daytime Aether Rift trench battlefield"
    if "scene-008" in low:
        return "the intake tent / recruiter tent interior"
    if "scene-010" in low:
        return "the Number Nine death-cell toxic pool environment"
    if "scene" in low:
        return "the scene environment from the reference plate"
    return re.sub(r"[-_]+", " ", stem).strip()


def _parse_duration(text: str) -> int | None:
    m = _DURATION.search(text)
    if not m:
        return None
    return int(m.group(1) or m.group(2))


def _parse_shots(text: str) -> list[tuple[int, str, str, str]]:
    shots: list[tuple[int, str, str, str]] = []
    for m in _SHOT.finditer(text):
        shots.append(
            (
                int(m.group(1)),
                m.group(2).strip(),
                m.group(3).strip(),
                " ".join(m.group(4).split()),
            )
        )
    return shots


def _shot_timestamp(time_span: str, shot_num: int) -> str | None:
    if shot_num <= 1:
        return None
    m = re.search(r"(\d+)\s*[–\-〜~]\s*\d+", time_span)
    if m:
        return f"00:{int(m.group(1)):02d}.000"
    return None


def _camera_phrase(framing: str) -> str:
    if "侧移" in framing:
        return "The camera trucks laterally with medium amplitude at moderate speed"
    if "短推" in framing or ("推" in framing and "下压" not in framing):
        return "The camera pushes in with small amplitude at slow speed"
    if "下压" in framing or "俯" in framing:
        return "The camera pedestals down with medium amplitude at moderate speed"
    return "The camera follows the motion path from <Video 1>"


def _english_title(title: str, duration: int) -> str:
    en = _to_english(title)
    en = re.sub(r"^\s*U\d+\s*[·•.\-]*\s*", "", en, flags=re.I).strip()
    en = re.sub(r"[（(]\s*\d+\s*s\s*[）)]", "", en, flags=re.I).strip()
    en = re.sub(r"\s+", " ", en).strip(" ·.-")
    if not en:
        en = "episode unit"
    return f"{en} ({duration}s)"


def _english_atmosphere(raw: str) -> str:
    en = _to_english(raw)
    if not en:
        return "live-action cinematic dark fantasy with high contrast"
    return en


def _sfx_from_shots(shots: list[tuple[int, str, str, str]]) -> str:
    joined = " ".join(s[3] for s in shots)
    bits: list[str] = []
    if "铁靴" in joined:
        bits.append("Iron boots scrape wet stone")
    if "矛" in joined:
        bits.append("spear shafts grind on stone")
    if "呼吸" in joined:
        bits.append("masked breathing")
    if "碎石" in joined or "踩碎" in joined:
        bits.append("wet stone cracks underfoot")
    if "溅" in joined or "坠入" in joined or "落" in joined:
        bits.append("a muffled impact and acid splash")
    if "雾" in joined or "蒸汽" in joined:
        bits.append("hissing purple vapor")
    if not bits:
        return (
            "Prison ambience with wet stone, metal contact, and physical action sounds "
            "matching the on-screen beats."
        )
    head = ", ".join(bits[:-1])
    if head:
        return f"{head}, and {bits[-1]} over low prison ambience."
    return f"{bits[0]} over low prison ambience."


def _shot_english(
    num: int,
    framing: str,
    body: str,
    *,
    subject_count: int,
) -> str:
    """Rewrite a beat into English and bind YZ subject labels."""
    s1 = "<Subject 1>" if subject_count >= 1 else "the lead character"
    s2 = "<Subject 2>" if subject_count >= 2 else "the opposing figure"
    s3 = "<Subject 3>" if subject_count >= 3 else "the environment"

    # Prefer structured beat templates keyed by EP shot language.
    if num == 1 or ("压向池缘" in body and "侧移" in framing):
        return (
            f"A medium-wide lateral tracking shot opens inside {s3}. "
            f"{s2} forces {s1} toward the toxic pool edge along the dry-stone ledge. "
            f"{s1} stands with stiff shoulders, stares at the advancing spears, then shifts "
            f"weight onto the rear foot until the heels reach the wet stone rim. "
            f"Iron boots, masked breathing, and spear shafts grinding on stone are audible."
        )
    if num == 2 or ("踩碎" in body and "短推" in framing):
        return (
            f"A near-medium push-in continues inside {s3}. "
            f"{s1} is forced back half a step; the right foot cracks wet stone. "
            f"{s1} blocks a spear with the left arm, jaw tight, as stone shards slide toward "
            f"the pool and the last stable foothold is lost. "
            f"{s2} stays on the safe gate side and does not cross the dry-stone ledge."
        )
    if num == 3 or ("坠入" in body or "俯" in framing or "下压" in framing):
        return (
            f"A high near-angle looking down. A spear strike hits only the shoulder side of {s1}; "
            f"{s1} leaves the dry-stone ledge and falls into the central toxic pool, shifting from "
            f"resistance to freefall with fingers clawing empty air. Purple toxic mist erupts from "
            f"the liquid and instantly engulfs {s1}. {s2} stops at the gate line."
        )

    en = _to_english(body)
    if not en:
        en = "The referenced subjects continue the locked action beat."
    return f"Inside {s3}, {s1} and {s2} perform the beat: {en}."


def picture_index_for_ref_image(slot_index: int) -> int:
    """YZ ref_image_i → H3 <Picture N>. Control is 0 → Picture 1."""
    return slot_index + 1


def build_h3_r2v_prompt(ep_text: str, slots: dict[str, str]) -> str:
    """Build MiniMax H3 R2V six-section English prompt aligned to YZ wiring.

    Wiring contract (must match ``map_yz_media_slots`` / MiniMaxH3ReferenceToVideo):
    - ref_image_0 (control) → <Picture 1> storyboard only
    - ref_image_1..N (identities) → <Picture 2..> / <Subject 1..>
    - ref_video_0 (previz) → <Video 1> motion/camera only
    """
    cleaned = _strip_upload_meta(ep_text)
    title_m = _TITLE.search(cleaned)
    raw_title = title_m.group(1).strip() if title_m else "episode unit"
    duration = _parse_duration(cleaned) or 10
    title = _english_title(raw_title, duration)
    atmos_m = _ATMOSPHERE.search(cleaned)
    atmosphere = _english_atmosphere(
        " ".join(atmos_m.group(1).split()) if atmos_m else ""
    )
    shots = _parse_shots(cleaned)

    identities: list[str] = []
    for i in range(1, 10):
        key = f"ref_image_{i}"
        if key not in slots:
            break
        identities.append(slots[key])

    subject_lines: list[str] = []
    for idx, path in enumerate(identities, start=1):
        pic = picture_index_for_ref_image(idx)
        label = _identity_label(path)
        subject_lines.append(
            f"<Subject {idx}> is {label} whose appearance comes from <Picture {pic}>."
        )

    shot_list = ", ".join(f"[Shot {n}]" for n, *_ in shots) or "[Shot 1]"
    subject_lines.append(
        f"<Picture 1> is a storyboard / director-control reference for {shot_list}, "
        "defining blocking, facing, entity boundaries, and spatial relations only — "
        "do not render color blocks, arrows, labels, grids, text, or UI from <Picture 1>."
    )
    subject_lines.append(
        "<Video 1> provides timing, character movement, key prop ownership, and camera path "
        "for the target video only — ignore the low-poly / colour-blockout appearance of <Video 1>."
    )

    subjects_csv = ", ".join(f"<Subject {i}>" for i in range(1, len(identities) + 1))
    env = f"<Subject {len(identities)}>" if identities else "the referenced scene"
    summary = (
        f"The target video is a {duration}-second live-action sequence ({title}) set in {env}, "
        f"driven by {subjects_csv or '<Subject 1>'}. "
        "Spatial blocking follows <Picture 1>; motion and camera follow <Video 1>. "
        "Do not use Seedance @tags or pack file paths; only <Picture>/<Video>/<Subject> labels."
    )

    retention: list[str] = []
    for idx in range(1, len(identities) + 1):
        retention.append(
            f"<Subject {idx}> (appears in {shot_list}): fully_preserved - "
            f"identity from <Picture {picture_index_for_ref_image(idx)}> retained throughout."
        )
    retention.append(
        "<Picture 1>: attribute_transfer - blocking and spatial relations only; "
        "markers must not appear in the target video."
    )
    retention.append(
        "<Video 1>: attribute_transfer - timing, movement, and camera path only; "
        "whitebox look must not appear in the target video."
    )

    detail_parts = [
        f"The target video uses {atmosphere}."
    ]
    if not shots:
        detail_parts.append(
            "[Shot 1] Live-action cinematic coverage follows <Video 1> motion inside "
            "the referenced environment, preserving subject identities from the pictures."
        )
    for num, time_span, framing, body in shots:
        ts = _shot_timestamp(time_span, num)
        cam = _camera_phrase(framing)
        beat = _shot_english(num, framing, body, subject_count=len(identities))
        prefix = f"[Shot {num}]"
        if ts:
            prefix = f"[Shot {num}] At {ts},"
        detail_parts.append(f"{prefix} {beat} {cam}, matching <Video 1>.")

    sections = {
        "subject_definitions": "\n".join(subject_lines),
        "summary": summary,
        "retention_analysis": "\n".join(retention),
        "detailed_description": "\n".join(detail_parts),
        "overall_soundscape": _sfx_from_shots(shots),
        "non_diegetic_music": "N/A",
    }
    out = "\n\n".join(f"{name}:\n{sections[name]}" for name in _SECTION_HEADERS) + "\n"
    if _CJK.search(out):
        # Final safety: strip any leftover CJK from title/edge cases.
        out = _CJK.sub("", out)
        out = re.sub(r"[ \t]+\n", "\n", out)
    return out

def build_h3_r2v_prompt_latent(ep_text: str, slots: dict[str, str]) -> str:
    """H3 R2V prompt for EP01-style latent packs: identity images only, no control/previz."""
    from comfy_orch.latent_pack import parse_latent_sections

    sections_in = parse_latent_sections(ep_text)
    duration = int(sections_in["duration_seconds"])
    title = _english_title(sections_in.get("title") or "unit", duration)
    atmosphere = _english_atmosphere(sections_in.get("style") or "")
    body_en = _to_english(sections_in.get("body") or "")
    latent_en = _to_english(sections_in.get("latent") or "")

    image_slots: list[tuple[int, str]] = []
    for i in range(0, 6):
        key = f"ref_image_{i}"
        if key in slots:
            image_slots.append((i, slots[key]))

    subject_lines: list[str] = []
    for order, (_slot_i, path) in enumerate(image_slots, start=1):
        label = _identity_label(path)
        subject_lines.append(
            f"<Subject {order}> is {label} whose appearance comes from <Picture {order}>."
        )

    n = len(image_slots)
    subjects_csv = ", ".join(f"<Subject {i}>" for i in range(1, n + 1))
    continuity = f" Continuity lock: {latent_en}." if latent_en else ""
    summary = (
        f"The target video is a {duration}-second live-action vertical 9:16 sequence ({title}) "
        f"driven by {subjects_csv or '<Subject 1>'}.{continuity} "
        "Use only <Picture>/<Subject> labels; no pack file paths."
    )
    retention = [
        f"<Subject {i}> (appears in [Shot 1]): fully_preserved - identity from <Picture {i}> retained."
        for i in range(1, n + 1)
    ]
    dialogue_bits = re.findall(r'"([^"]+)"', sections_in.get("body") or "")
    dialogue_note = ""
    if dialogue_bits:
        dialogue_note = " Spoken English lines with natural lip sync: " + " / ".join(
            f"<d>[English] {d}</d>" for d in dialogue_bits
        )
    detail = (
        f"The target video uses {atmosphere}.\n"
        f"[Shot 1] {body_en or 'The locked action plays out with the referenced subjects.'}"
        f"{dialogue_note}"
    )
    sound = (
        "Diegetic ward ambience, monitor alarm beeps, fabric and metal contact, breath; "
        "no non-diegetic music."
    )
    sections = {
        "subject_definitions": "\n".join(subject_lines),
        "summary": summary,
        "retention_analysis": "\n".join(retention),
        "detailed_description": detail,
        "overall_soundscape": sound,
        "non_diegetic_music": "N/A",
    }
    out = "\n\n".join(f"{name}:\n{sections[name]}" for name in _SECTION_HEADERS) + "\n"
    parts = re.split(r"(<d>.*?</d>)", out, flags=re.S)
    cleaned: list[str] = []
    for part in parts:
        if part.startswith("<d>"):
            cleaned.append(part)
        else:
            cleaned.append(_CJK.sub("", part))
    out = "".join(cleaned)
    out = re.sub(r"[ \t]+\n", "\n", out)
    return out


_REVIEW_CAMERA: tuple[tuple[str, str], ...] = (
    ("极特写", "extreme close-up"),
    ("中近景", "medium close-up"),
    ("特写", "close-up"),
    ("近景", "close shot"),
    ("全景", "wide shot"),
    ("过肩近景", "over-the-shoulder close shot"),
    ("过肩", "over-the-shoulder"),
    ("侧面双人近景", "side two-shot medium close-up"),
    ("背后全景", "wide shot from behind"),
    ("腰部近景", "waist close-up"),
    ("道具近景", "prop close-up"),
    ("锁定机位", "locked camera"),
    ("固定机位", "locked camera"),
    ("缓推", "slow push-in"),
    ("急后拉", "hard pull-back"),
    ("微移", "slight move"),
    ("跟拍", "tracking shot"),
    ("反打", "reverse angle"),
)

_REVIEW_PHRASE: tuple[tuple[str, str], ...] = (
    ("身份", "identity"),
    ("煤黑风衣", "coal-black coat"),
    ("病危身份", "critical patient identity"),
    ("象牙白病号睡衣", "ivory sick-ward pajamas"),
    ("浅灰披肩", "light-grey shawl"),
    ("灰蓝护士裙", "grey-blue nurse dress"),
    ("低髻", "low bun"),
    ("围裙", "apron"),
    ("重铠身份", "armored identity"),
    ("唯一佩剑在角色左腰", "sole sword on character left hip"),
    ("领主身份", "noble lord identity"),
    ("单片眼镜", "monocle"),
    ("黑礼服", "black formal coat"),
    ("竖屏 9:16", "vertical 9:16"),
    ("电影写实", "cinematic live-action"),
    ("无字幕", "no subtitles"),
    ("无水印", "no watermarks"),
    ("无背景音乐", "no background music"),
    ("禁止背景音乐", "no background music"),
    ("机械长鸣", "continuous mechanical alarm"),
    ("机械警报", "mechanical alarm"),
    ("滴管", "drip tube"),
    ("断开", "disconnected"),
    ("平卧", "lying flat"),
    ("铁床", "iron bed"),
    ("病房", "ward"),
    ("口型", "lip sync"),
    ("完整口型说", "completes lip sync saying"),
    ("完整口型", "full lip sync"),
    ("1880 年代末维多利亚工业暗黑奇幻", "late-1880s Victorian industrial dark fantasy"),
)


def _review_framing_en(framing: str) -> str:
    out = framing.replace("／", " / ")
    for zh, en in _REVIEW_CAMERA:
        out = out.replace(zh, en)
    out = re.sub(r"\s+", " ", out).strip(" /")
    return out or "locked camera"


def _review_prose_en(text: str) -> str:
    if not text.strip():
        return ""
    protected: dict[str, str] = {}

    def _stash(m: re.Match[str]) -> str:
        key = f"__KEEP{len(protected)}__"
        protected[key] = m.group(0)
        return key

    work = text
    work = re.sub(r"`[^`]+`", _stash, work)
    work = re.sub(r"[A-Z][A-Z\s]*?:\s*[“\"][^”\"]+[”\"]", _stash, work)
    work = re.sub(r"\b\d+\.\.\.\s*\d+\.\.\.", _stash, work)
    for zh, en in _REVIEW_PHRASE:
        work = work.replace(zh, en)
    work = work.replace("，", ", ").replace("。", ". ").replace("；", "; ")
    work = work.replace("：", ": ").replace("（", " (").replace("）", ") ")
    work = work.replace("、", ", ")
    work = _CJK.sub(" ", work)
    work = re.sub(r"\s+", " ", work).strip(" ,.")
    for key, val in protected.items():
        if re.match(r'[A-Z][A-Z\s]*:\s*"', val):
            quote = re.search(r'"([^"]+)"', val)
            if quote:
                work = work.replace(key, f'<d>[English] {quote.group(1)}</d>')
            else:
                work = work.replace(key, val)
        else:
            work = work.replace(key, val.strip("`"))
    return re.sub(r"\s+", " ", work).strip()


def _subject_from_review_label(order: int, label: str, fallback: str) -> str:
    m = re.match(r"^([^（(]+)[（(](.+)[）)]\s*$", label.strip())
    if m:
        name = m.group(1).strip()
        desc = _review_prose_en(m.group(2))
        core = f"{name} ({desc})" if desc else name
    else:
        core = _review_prose_en(label) or fallback
    return f"<Subject {order}> is {core} whose appearance comes from <Picture {order}>."


def _review_soundscape(atmosphere: str, shots: list[tuple[int, str, str, str]]) -> str:
    joined = " ".join(s[3] for s in shots) + " " + atmosphere
    bits: list[str] = []
    if "alarm" in joined.lower() or "警报" in joined or "长鸣" in joined:
        bits.append("continuous mechanical alarm")
    if "呼吸" in joined or "breath" in joined.lower():
        bits.append("sharp breath and fabric contact")
    if "脚步" in joined or "footstep" in joined.lower():
        bits.append("footsteps")
    if "雨" in joined or "rain" in joined.lower():
        bits.append("rain and wind")
    if "壁炉" in joined or "fireplace" in joined.lower():
        bits.append("low fireplace crackle")
    if "金属" in joined or "metal" in joined.lower():
        bits.append("metal friction and contact")
    if "电弧" in joined:
        bits.append("thin arc-lamp hiss")
    if re.search(r"[A-Z]+:\s*\"", joined):
        bits.append("spoken English lines with natural lip sync")
    bits.append("no non-diegetic music")
    return "; ".join(bits) + "."


def build_h3_r2v_prompt_review(ep_text: str, slots: dict[str, str]) -> str:
    """H3 R2V six-section prompt from EP01 formal review drafts."""
    from comfy_orch.review_pack import (
        match_asset_label,
        parse_review_asset_labels,
        parse_review_dialogues,
        parse_review_sections,
        parse_review_shots,
    )

    sections_in = parse_review_sections(ep_text)
    duration = int(sections_in["duration_seconds"])
    unit_id = sections_in["unit_id"]
    title = sections_in["title"]
    asset_labels = parse_review_asset_labels(ep_text)
    shots = parse_review_shots(ep_text)

    image_slots: list[tuple[int, str]] = []
    for i in range(0, 8):
        key = f"ref_image_{i}"
        if key in slots:
            image_slots.append((i, slots[key]))

    subject_lines: list[str] = []
    for order, (_slot_i, path) in enumerate(image_slots, start=1):
        label = match_asset_label(asset_labels, path)
        fallback = _identity_label(path)
        subject_lines.append(_subject_from_review_label(order, label, fallback))

    n = len(image_slots)
    subjects_csv = ", ".join(f"<Subject {i}>" for i in range(1, n + 1))
    latent_in = _review_prose_en(sections_in["latent_in"])
    handoff = _review_prose_en(sections_in["handoff"])
    relay = _review_prose_en(sections_in["latent_relay"])
    continuity_bits = [b for b in (latent_in, relay) if b]
    continuity = f" Continuity lock: {' '.join(continuity_bits)}" if continuity_bits else ""
    summary = (
        f"The target video is a {duration}-second live-action vertical 9:16 sequence "
        f"(EP01 {unit_id} {_review_prose_en(title) or title}). "
        f"Driven by {subjects_csv or '<Subject 1>'}.{continuity} "
        "Use only <Picture>/<Subject> labels; no pack file paths."
    )

    retention = [
        f"<Subject {i}> (appears throughout): fully_preserved - identity from <Picture {i}> retained."
        for i in range(1, n + 1)
    ]

    detail_parts: list[str] = []
    ref = _review_prose_en(sections_in["reference"])
    atm = _review_prose_en(sections_in["atmosphere"])
    if ref or atm:
        detail_parts.append(f"World and look: {ref} {atm}".strip())
    director = _review_prose_en(sections_in["director"])
    if director:
        detail_parts.append(f"Director intent: {director}")

    for num, time_span, framing, body in shots:
        ts = time_span.replace("秒", "s").replace("–", "-").replace("—", "-")
        cam = _review_framing_en(framing)
        beat = _review_prose_en(body)
        detail_parts.append(f"[Shot {num}] At {ts}, {cam}. {beat}")

    if handoff:
        detail_parts.append(f"Handoff state into next unit: {handoff}")

    dialogues = parse_review_dialogues(ep_text)
    if dialogues:
        spoken = " / ".join(f"<d>[English] {line}</d>" for _sp, line in dialogues)
        detail_parts.append(f"Locked spoken lines: {spoken}")

    sections = {
        "subject_definitions": "\n".join(subject_lines),
        "summary": summary,
        "retention_analysis": "\n".join(retention),
        "detailed_description": "\n\n".join(detail_parts),
        "overall_soundscape": _review_soundscape(sections_in["atmosphere"], shots),
        "non_diegetic_music": "N/A",
    }
    out = "\n\n".join(f"{name}:\n{sections[name]}" for name in _SECTION_HEADERS) + "\n"
    parts = re.split(r"(<d>.*?</d>)", out, flags=re.S)
    cleaned: list[str] = []
    for part in parts:
        if part.startswith("<d>"):
            cleaned.append(part)
        else:
            cleaned.append(_CJK.sub("", part))
    out = "".join(cleaned)
    out = re.sub(r"[ \t]+\n", "\n", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out


def build_h3_r2v_prompt_causality(ep_text: str, slots: dict[str, str]) -> str:
    """H3 R2V six-section prompt from EP02 physical-causality unit TXT."""
    from comfy_orch.causality_pack import (
        parse_causality_dialogues,
        parse_causality_sections,
        parse_causality_shots,
    )

    sections_in = parse_causality_sections(ep_text)
    duration = int(sections_in["duration_seconds"])
    unit_id = sections_in["unit_id"] or "Uxx"
    title = _review_prose_en(sections_in["title"]) or sections_in["title"]
    shots = parse_causality_shots(ep_text)

    image_slots: list[tuple[int, str]] = []
    for i in range(0, 8):
        key = f"ref_image_{i}"
        if key in slots:
            image_slots.append((i, slots[key]))

    subject_lines = [
        f"<Subject {order}> is {_identity_label(path)} whose appearance comes from <Picture {order}>."
        for order, (_slot_i, path) in enumerate(image_slots, start=1)
    ]
    n = len(image_slots)
    subjects_csv = ", ".join(f"<Subject {i}>" for i in range(1, n + 1))
    latent_in = _review_prose_en(sections_in["latent_in"])
    relay = _review_prose_en(sections_in["latent_relay"])
    continuity = " ".join(b for b in (latent_in, relay) if b)
    summary = (
        f"The target video is a {duration}-second live-action vertical 9:16 sequence "
        f"(EP02 {unit_id} {title}). Driven by {subjects_csv or '<Subject 1>'}."
        + (f" Continuity lock: {continuity}" if continuity else "")
        + " Use only <Picture>/<Subject> labels; no pack file paths. "
        "No parent-clip file is attached in this job — establish from uploaded stills "
        "and the stated continuity text."
    )
    retention = [
        f"<Subject {i}> (appears throughout): fully_preserved - identity from <Picture {i}> retained."
        for i in range(1, n + 1)
    ]

    detail_parts: list[str] = []
    constraints = _review_prose_en(sections_in["constraints"])
    effect = _review_prose_en(sections_in["effect"])
    if constraints:
        detail_parts.append(f"World and look: {constraints}")
    if effect:
        detail_parts.append(f"Causal through-line: {effect}")
    for num, time_span, framing, body in shots:
        ts = time_span.replace("秒", "s").replace("–", "-").replace("—", "-")
        cam = _review_framing_en(framing)
        beat = _review_prose_en(body)
        detail_parts.append(f"[Shot {num}] At {ts}, {cam}. {beat}")
    handoff = _review_prose_en(sections_in["handoff"])
    if handoff:
        detail_parts.append(f"Handoff state into next unit: {handoff}")
    dialogues = parse_causality_dialogues(ep_text)
    if dialogues:
        spoken = " / ".join(f"<d>[English] {d}</d>" for d in dialogues)
        detail_parts.append(f"Locked spoken lines: {spoken}")

    sound = _review_soundscape(sections_in["constraints"], shots)
    sections = {
        "subject_definitions": "\n".join(subject_lines),
        "summary": summary,
        "retention_analysis": "\n".join(retention),
        "detailed_description": "\n\n".join(detail_parts),
        "overall_soundscape": sound,
        "non_diegetic_music": "N/A",
    }
    out = "\n\n".join(f"{name}:\n{sections[name]}" for name in _SECTION_HEADERS) + "\n"
    parts = re.split(r"(<d>.*?</d>)", out, flags=re.S)
    cleaned: list[str] = []
    for part in parts:
        if part.startswith("<d>"):
            cleaned.append(part)
        else:
            cleaned.append(_CJK.sub("", part))
    out = "".join(cleaned)
    out = re.sub(r"[ \t]+\n", "\n", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out
