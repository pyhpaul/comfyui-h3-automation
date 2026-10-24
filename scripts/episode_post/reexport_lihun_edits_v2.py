#!/usr/bin/env python3
"""Re-export archived lihun 整集剪辑 episodes to the new delivery spec.

For each already-edited EP under Feiniu `离婚后（10.22）/整集剪辑/`:
  - pull hash-locked unit mp4/prompt/meta from the unit archive
  - rebuild ASR word tracks
  - refresh skill/preset digests on the shared input contract
  - attach 1:1 `zh_captions` (from a phrase map)
  - re-render with current engine (master = dialogue+SFX, no BGM;
    review keeps BGM + burned EN subs; write zh.srt/zh.ass)
  - force-overwrite the Feiniu edit folder
  - delete local media after a successful archive (ledger stays)

Does not change creative cut/music/ending decisions in creative_plan.json
beyond adding zh_captions and refreshing shared_input_sha256.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from comfy_orch.feiniu_archive import (  # noqa: E402
    SHARE, _ensure_tree, _reader, _remote_sizes, connect_feiniu,
)
from ep_pilot_timeline import Clip, presentation_cues, verify_source  # noqa: E402
from run_ep_post_pilot import collect_captions  # noqa: E402
from run_episode_comparison import load_config, render as render_comparison  # noqa: E402

BATCH = "离婚后（10.22）"
EDIT_ROOT = f"H3_comfyUI_5090\\archive\\{BATCH}\\整集剪辑"
UNIT_ROOT = f"H3_comfyUI_5090\\archive\\{BATCH}"
CACHE = ROOT / ".cache" / "lihun_edit_reexport"
PLANS = CACHE / "plans"
ZH_MAP = CACHE / "zh_captions_map.json"
OUT_ROOT = ROOT / "outputs" / "lihun-edit-reexport"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_zh_map() -> dict[str, str]:
    if ZH_MAP.is_file():
        return json.loads(ZH_MAP.read_text(encoding="utf-8"))
    return {}


def save_zh_map(data: dict[str, str]) -> None:
    ZH_MAP.parent.mkdir(parents=True, exist_ok=True)
    ZH_MAP.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")


def normalize_en(text: str) -> str:
    return " ".join(text.replace("\n", " ").split())


# Ultra-common short cues: avoid free-API rate limits on every EP.
_BOOTSTRAP_ZH: dict[str, str] = {
    "What?": "什么？",
    "Why?": "为什么？",
    "Who?": "谁？",
    "Where?": "哪里？",
    "When?": "什么时候？",
    "How?": "怎么？",
    "No.": "不。",
    "Yes.": "是。",
    "Okay.": "好。",
    "Ok.": "好。",
    "OK.": "好。",
    "Sorry.": "对不起。",
    "Thanks.": "谢谢。",
    "Thank you.": "谢谢。",
    "Please.": "拜托。",
    "Stop.": "停。",
    "Wait.": "等等。",
    "Go.": "走。",
    "Come.": "过来。",
    "I know.": "我知道。",
    "I see.": "我明白了。",
    "Of course.": "当然。",
    "Never.": "绝不。",
    "Always.": "总是。",
    "Really?": "真的？",
    "Right.": "对。",
    "Wrong.": "错了。",
    "Fine.": "行。",
    "Enough.": "够了。",
    "Hello.": "你好。",
    "Goodbye.": "再见。",
    "Whose?": "谁的？",
}


def seed_zh_map_from_repo(zh_map: dict[str, str]) -> None:
    """Absorb bootstrap shorts + any existing phrase maps (exact EN keys only)."""
    for en, zh in _BOOTSTRAP_ZH.items():
        key = normalize_en(en)
        if key not in zh_map:
            zh_map[key] = zh
    for path in (
        ROOT / "runs" / "lihun_zh_map.json",
        ROOT / "runs" / "chaofu_ep01_v2_zh_map.json",
        ROOT / "scripts" / "ops" / "chaofu_zh_map.json",
    ):
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            continue
        for en, zh in data.items():
            key = normalize_en(str(en))
            # only keep single-cue keys (no multi-sentence packs)
            if " " in key and key.count(".") + key.count("?") + key.count("!") > 1:
                continue
            if key not in zh_map and isinstance(zh, str) and zh.strip():
                zh_map[key] = zh.strip()


def _srt_cue_bodies(text: str) -> list[str]:
    bodies: list[str] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.splitlines()
        if len(lines) >= 3 and "-->" in lines[1]:
            bodies.append("\n".join(lines[2:]).strip())
    return bodies


def harvest_zh_from_episode_edits(zh_map: dict[str, str]) -> int:
    """Fill zh_map from already-rendered EP en.srt/zh.srt pairs (index-aligned)."""
    root = ROOT / "outputs" / "episode-edits" / "lihun-v23"
    if not root.is_dir():
        return 0
    added = 0
    for ep_dir in sorted(root.glob("EP*")):
        en_files = list(ep_dir.glob("*.en.srt"))
        zh_files = list(ep_dir.glob("*.zh.srt"))
        if not en_files or not zh_files:
            continue
        ens = _srt_cue_bodies(en_files[0].read_text(encoding="utf-8"))
        zhs = _srt_cue_bodies(zh_files[0].read_text(encoding="utf-8"))
        for en, zh in zip(ens, zhs):
            if not en or not zh:
                continue
            # skip failed English leftovers in zh track
            if not any("\u4e00" <= c <= "\u9fff" for c in zh):
                continue
            key = normalize_en(en)
            if key not in zh_map:
                zh_map[key] = zh
                added += 1
    return added


def _zh_looks_sane(en: str, zh: str) -> bool:
    """Reject runaway / garbled offline translations before caching."""
    z = zh.strip()
    if not z or z == en.strip():
        return False
    if len(z) > max(48, 6 * len(en.strip())):
        return False
    if any(ord(c) < 32 for c in z):
        return False
    # Private Use / weird compatibility junk from bad Argos outputs
    if any(
        0xE000 <= ord(c) <= 0xF8FF
        or 0xF0000 <= ord(c) <= 0xFFFFD
        or 0x3100 <= ord(c) <= 0x312F  # Bopomofo often signals mojibake here
        for c in z
    ):
        return False
    cjk = sum(1 for c in z if "\u4e00" <= c <= "\u9fff")
    if cjk == 0:
        return False
    # mostly-Latin "translation" with a stray CJK punct
    letters = sum(1 for c in z if c.isalpha())
    if letters and cjk / max(1, letters) < 0.35 and len(en.split()) >= 2:
        return False
    for n in (2, 3, 4):
        if len(z) >= n * 8:
            chunk = z[:n]
            if chunk * 8 in z:
                return False
    return True


def _argos_translate(en: str) -> str | None:
    """Offline EN→ZH via argostranslate when installed (no rate limit)."""
    try:
        import argostranslate.translate  # type: ignore
    except ImportError:
        return None
    try:
        zh = argostranslate.translate.translate(en, "en", "zh")
    except Exception:  # noqa: BLE001
        return None
    if zh and _zh_looks_sane(en, zh):
        return zh.strip()
    return None


def _translators_pkg(en: str) -> str | None:
    """Optional `translators` package (bing/baidu/…) when Argos fails."""
    try:
        import translators as ts  # type: ignore
    except ImportError:
        return None
    for engine in ("bing", "baidu", "sogou"):
        try:
            zh = ts.translate_text(
                en, translator=engine, from_language="en", to_language="zh"
            )
            if zh and _zh_looks_sane(en, zh):
                return zh.strip()
        except Exception:  # noqa: BLE001
            continue
    return None


def _translate_one(en: str) -> str:
    """Argos offline → translators pkg → deep_translator online."""
    errors: list[str] = []
    argos = _argos_translate(en)
    if argos:
        return argos
    errors.append("argos_unavailable_or_garbage")
    pkg = _translators_pkg(en)
    if pkg:
        return pkg
    errors.append("translators_pkg_unavailable")
    try:
        from deep_translator import GoogleTranslator, MyMemoryTranslator
    except ImportError as exc:
        raise RuntimeError(
            f"translate failed for {en!r}: {'; '.join(errors)}; no deep_translator ({exc})"
        ) from exc
    for factory in (
        lambda: MyMemoryTranslator(source="en-US", target="zh-CN"),
        lambda: GoogleTranslator(source="en", target="zh-CN"),
    ):
        try:
            zh = factory().translate(en)
            if zh and _zh_looks_sane(en, zh):
                return zh.strip()
            errors.append("empty_or_insane")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{type(exc).__name__}: {exc}")
            if "TooManyRequests" in str(exc):
                break
            time.sleep(1.0)
    raise RuntimeError(f"translate failed for {en!r}: {'; '.join(errors)}")


def warm_zh_map(zh_map: dict[str, str] | None = None) -> dict[str, str]:
    """Load map, seed repo phrase packs, harvest prior EP srt pairs, persist if grown."""
    data = zh_map if zh_map is not None else load_zh_map()
    before = len(data)
    seed_zh_map_from_repo(data)
    harvested = harvest_zh_from_episode_edits(data)
    if len(data) > before or harvested:
        save_zh_map(data)
        print(
            f"ZH_MAP warm +{len(data) - before} (harvest={harvested}) total={len(data)}",
            flush=True,
        )
    return data


def ensure_zh_captions(english: list[str], zh_map: dict[str, str] | None = None) -> list[str]:
    """Resolve zh lines 1:1; translate missing keys via free translators."""
    zh_map = warm_zh_map(zh_map)
    # Drop previously cached garbage so we re-translate.
    scrubbed = 0
    for key in list(zh_map):
        if not _zh_looks_sane(key, zh_map[key]):
            del zh_map[key]
            scrubbed += 1
    if scrubbed:
        save_zh_map(zh_map)
        print(f"ZH_MAP scrubbed {scrubbed} bad entries", flush=True)
    # unique missing, preserve order
    missing: list[str] = []
    seen: set[str] = set()
    for t in english:
        key = normalize_en(t)
        if key in zh_map or key in seen:
            continue
        seen.add(key)
        missing.append(key)
    if missing:
        print(f"ZH_MAP miss {len(missing)}/{len(english)}", flush=True)
        for i, en in enumerate(missing):
            last = None
            for attempt in range(3):
                try:
                    zh = _translate_one(en)
                    zh_map[en] = zh
                    print(f"zh {en} -> {zh}", flush=True)
                    last = None
                    break
                except Exception as exc:  # noqa: BLE001
                    last = exc
                    wait = 2.0 * (attempt + 1)
                    print(
                        f"ZH_RETRY {en!r} attempt={attempt + 1} wait={wait:.0f}s {type(exc).__name__}",
                        flush=True,
                    )
                    time.sleep(wait)
            if last is not None:
                raise RuntimeError(f"translate failed for {en!r}: {last}")
            if (i + 1) % 25 == 0:
                save_zh_map(zh_map)
                print(f"ZH_MAP progress {i + 1}/{len(missing)}", flush=True)
        save_zh_map(zh_map)
    out = []
    for raw in english:
        key = normalize_en(raw)
        zh = zh_map.get(key)
        if not zh:
            raise RuntimeError(f"zh caption missing for {raw!r}")
        out.append(zh)
    return out


def smb_get(smb, remote: str) -> bytes:
    buf = io.BytesIO()
    smb.getFile(SHARE, remote, buf.write)
    return buf.getvalue()


def _rel_or_abs(path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else ROOT / path


def pull_units(smb, episode: str, manifest: dict, ep_cache: Path) -> dict[str, dict]:
    """Stage unit files that match edit_manifest sha256s.

    Prefer already-local paths recorded on the prior manifest (EP01 pilot
    assets). Otherwise pull from Feiniu unit archive.
    """
    inputs = ep_cache / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    sources_out: dict[str, dict] = {}
    for unit, meta in manifest["sources"].items():
        local_candidates = {
            "path": _rel_or_abs(meta["path"]),
            "prompt": _rel_or_abs(meta["prompt"]),
            "meta": _rel_or_abs(meta["meta"]),
        }
        local_ok = (
            local_candidates["path"].is_file()
            and digest(local_candidates["path"]) == meta["sha256"]
            and local_candidates["prompt"].is_file()
            and digest(local_candidates["prompt"]) == meta["prompt_sha256"]
            and local_candidates["meta"].is_file()
            and digest(local_candidates["meta"]) == meta["meta_sha256"]
        )
        if local_ok:
            mp4_path = local_candidates["path"]
            prompt_path = local_candidates["prompt"]
            meta_path = local_candidates["meta"]
            print(f"LOCAL {episode}/{unit}", flush=True)
        else:
            unit_dir = f"{UNIT_ROOT}\\{episode}\\{unit}-WENXI"
            names = [f.get_longname() for f in smb.listPath(SHARE, unit_dir + "\\*")
                     if f.get_longname() not in (".", "..")]
            mp4s = [n for n in names if n.lower().endswith(".mp4")]
            if len(mp4s) != 1:
                raise RuntimeError(f"{episode}/{unit} mp4s={mp4s}")
            local_u = inputs / f"{episode}-{unit}"
            local_u.mkdir(parents=True, exist_ok=True)
            mp4_path = local_u / mp4s[0]
            prompt_path = local_u / "prompt_h3.txt"
            meta_path = local_u / "run_meta.json"
            need = [
                (mp4s[0], mp4_path, meta["sha256"]),
                ("prompt_h3.txt", prompt_path, meta["prompt_sha256"]),
                ("run_meta.json", meta_path, meta["meta_sha256"]),
            ]
            for remote_name, dest, expect in need:
                if dest.is_file() and digest(dest) == expect:
                    continue
                payload = smb_get(smb, f"{unit_dir}\\{remote_name}")
                dest.write_bytes(payload)
                got = digest(dest)
                if got != expect:
                    raise RuntimeError(
                        f"{episode}/{unit}/{remote_name} sha mismatch "
                        f"got={got[:12]} expect={expect[:12]}")
            print(f"FEINIU_PULL {episode}/{unit}", flush=True)

        def as_root_rel(path: Path) -> str:
            try:
                return str(path.resolve().relative_to(ROOT))
            except ValueError:
                # copy into cache if outside root
                dest = inputs / f"{episode}-{unit}" / path.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not dest.is_file() or digest(dest) != digest(path):
                    dest.write_bytes(path.read_bytes())
                return str(dest.relative_to(ROOT))

        sources_out[unit] = {
            "path": as_root_rel(mp4_path),
            "prompt": as_root_rel(prompt_path),
            "meta": as_root_rel(meta_path),
            "sha256": meta["sha256"],
            "prompt_sha256": meta["prompt_sha256"],
            "meta_sha256": meta["meta_sha256"],
            "expected_dialogue": meta.get("expected_dialogue", []),
        }
    return sources_out


def transcribe_units(sources: dict[str, dict], analysis_dir: Path,
                     prior_sources: dict[str, dict] | None = None) -> None:
    analysis_dir.mkdir(parents=True, exist_ok=True)
    from faster_whisper import WhisperModel

    model = None
    for unit, meta in sources.items():
        # Prefer prior hash-locked analysis when the file is still present.
        prior = (prior_sources or {}).get(unit) or {}
        prior_path = _rel_or_abs(prior["analysis"]) if prior.get("analysis") else None
        if (
            prior_path is not None
            and prior_path.is_file()
            and prior.get("analysis_sha256")
            and digest(prior_path) == prior["analysis_sha256"]
            and json.loads(prior_path.read_text(encoding="utf-8")).get("sha256")
            == meta["sha256"]
        ):
            try:
                rel = str(prior_path.resolve().relative_to(ROOT))
            except ValueError:
                dest = analysis_dir / f"{unit}.json"
                dest.write_bytes(prior_path.read_bytes())
                rel = str(dest.relative_to(ROOT))
            meta["analysis"] = rel
            meta["analysis_sha256"] = prior["analysis_sha256"]
            print(f"ASR_REUSE {unit}", flush=True)
            continue

        dest = analysis_dir / f"{unit}.json"
        src = ROOT / meta["path"]
        sha = meta["sha256"]
        if dest.is_file() and json.loads(dest.read_text())["sha256"] == sha:
            meta["analysis"] = str(dest.relative_to(ROOT))
            meta["analysis_sha256"] = digest(dest)
            print(f"ASR_CACHE {unit}", flush=True)
            continue
        if model is None:
            model = WhisperModel("small", device="cpu", compute_type="int8",
                                 cpu_threads=4, local_files_only=True)
        print(f"ASR {unit}", flush=True)
        started = time.monotonic()
        segments, info = model.transcribe(
            str(src), language="en", word_timestamps=True,
            vad_filter=True, beam_size=5, condition_on_previous_text=False)
        rows = [{"start": s.start, "end": s.end, "text": s.text.strip(),
                 "no_speech_prob": s.no_speech_prob,
                 "words": [{"start": w.start, "end": w.end,
                            "word": w.word.strip(), "probability": w.probability}
                           for w in (s.words or [])]} for s in segments]
        result = {"source": str(src), "sha256": sha, "model": "small",
                  "device": "cpu", "compute_type": "int8",
                  "duration": info.duration, "segments": rows,
                  "elapsed_s": round(time.monotonic() - started, 2)}
        dest.write_text(json.dumps(result, indent=2) + "\n")
        meta["analysis"] = str(dest.relative_to(ROOT))
        meta["analysis_sha256"] = digest(dest)


def rebuild_shared(old: dict, episode: str, sources: dict[str, dict]) -> dict:
    skill = sorted((ROOT / ".cursor/skills/comfy-h3-episode-assembly").rglob("*.md"))
    preset = "docs/ending-presets/bloom-hold-suspense-v1.json"
    music = Path(old["available_music"][0]["path"])
    if not music.is_absolute():
        music_path = music
    else:
        music_path = Path("assets/episode_post/local/pilots/lihun-v21-ep01/music/sb_undertow.mp3")
    music_abs = ROOT / music_path
    verify_source(music_abs, digest(music_abs))
    shared = {
        "schema": "episode-edit-comparison/v1",
        "episode": episode,
        "source_version": old.get("source_version", "lihun-v23"),
        "unit_order": old["unit_order"],
        "sources": sources,
        "available_music": [{
            "path": str(music_path),
            "sha256": digest(music_abs),
            "title": old["available_music"][0].get("title", "Undertow"),
            "artist": old["available_music"][0].get("artist", "Scott Buckley"),
            "license": old["available_music"][0].get("license", "CC-BY 4.0"),
        }],
        "available_presets": [{"path": preset, "sha256": digest(ROOT / preset)}],
        "skill_snapshot": [
            {"path": str(p.relative_to(ROOT)), "sha256": digest(p)} for p in skill
        ],
        "delivery": old["delivery"],
        "constraints": old.get("constraints", []),
        "contract_basis": "reexport-spec-v2: same cuts/music/ending; master no BGM; zh track",
    }
    return shared


def preview_english_cues(manifest: dict) -> list[str]:
    """English phrase texts from the prior delivery (presentation form)."""
    cues = manifest.get("displayed_subtitle_cues") or []
    if not cues:
        raise RuntimeError("edit_manifest missing displayed_subtitle_cues")
    return [c["text"] for c in cues]


def force_upload(smb, episode: str, out: Path) -> str:
    remote = f"{EDIT_ROOT}\\{episode}"
    _ensure_tree(smb, remote)
    names = [
        f"{episode}-master.mp4",
        f"{episode}-review-en.mp4",
        f"{episode}.en.srt",
        f"{episode}.en.ass",
        f"{episode}.zh.srt",
        f"{episode}.zh.ass",
        "MUSIC_CREDITS.txt",
        "creative_plan.json",
        "edit_manifest.json",
        "input_contract.json",
        "qc_report.json",
        "SELF_REVIEW.md",
    ]
    # optional diagnostic word track
    words = out / f"{episode}.words.srt"
    if words.is_file():
        names.append(words.name)
    for name in names:
        path = out / name
        if not path.is_file():
            raise RuntimeError(f"missing delivery file: {path}")
        payload = path.read_bytes()
        smb.putFile(SHARE, remote + "\\" + name, _reader(payload))
    checked = _remote_sizes(smb, remote)
    for name in names:
        expect = (out / name).stat().st_size
        if checked.get(name) != expect:
            raise RuntimeError(f"upload size mismatch {episode}/{name}: "
                               f"remote={checked.get(name)} local={expect}")
    # confirm zh present
    if not any(n.endswith(".zh.srt") for n in checked):
        raise RuntimeError(f"{episode} remote missing zh.srt after upload")
    return remote


def write_self_review(out: Path, episode: str, note: str) -> None:
    body = (
        f"# {episode} self-review (spec v2 reexport)\n\n"
        f"- Re-rendered with master = dialogue + ending SFX (no BGM bed).\n"
        f"- Review keeps BGM + burned English subs.\n"
        f"- Added Chinese phrase track `{episode}.zh.srt` / `.zh.ass` "
        f"aligned 1:1 with English cues.\n"
        f"- Editorial cuts/music/ending reused from prior creative_plan.\n"
        f"- {note}\n"
    )
    (out / "SELF_REVIEW.md").write_text(body, encoding="utf-8")


def process_episode(episode: str, *, upload: bool, keep_media: bool) -> None:
    plan_dir = PLANS / episode
    manifest = json.loads((plan_dir / "edit_manifest.json").read_text(encoding="utf-8"))
    old_plan = json.loads((plan_dir / "creative_plan.json").read_text(encoding="utf-8"))
    old_shared = json.loads((plan_dir / "input_contract.json").read_text(encoding="utf-8"))

    ep_cache = CACHE / "work" / episode
    ep_cache.mkdir(parents=True, exist_ok=True)
    print(f"=== {episode} pull ===", flush=True)
    smb = connect_feiniu()
    try:
        sources = pull_units(smb, episode, manifest, ep_cache)
    finally:
        smb.close()

    print(f"=== {episode} asr ===", flush=True)
    transcribe_units(sources, ep_cache / "analysis", prior_sources=manifest["sources"])

    shared = rebuild_shared(old_shared, episode, sources)
    shared_path = ep_cache / "input_contract.json"
    shared_path.write_text(json.dumps(shared, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")

    # Draft plan without zh first so load_config / collect_captions can run.
    plan_draft = dict(old_plan)
    plan_draft["shared_input_sha256"] = digest(shared_path)
    plan_draft["revision"] = f"{plan_draft.get('revision', 'edit')}-spec-v2"
    # Fresh Whisper often contracts "going to"→"gonna"; expand heard side
    # so scripted phrases still align (alias value may be multi-token).
    plan_draft["subtitle_aliases"] = {
        "gonna": "going to",
        "wanna": "want to",
        "gotta": "got to",
        # Whisper often hears "Noah" as the weather agency acronym.
        "noaa": "noah",
        **(plan_draft.get("subtitle_aliases") or {}),
    }
    config = load_config(ROOT, shared, plan_draft)
    clips = [Clip(c["unit"], c["in_frame"], c["out_frame"]) for c in plan_draft["clips"]]
    captions, _words = collect_captions(config, clips)
    readable = presentation_cues(captions, plan_draft.get("subtitle_style") or {})
    english = [c.text for c in readable]
    prior = preview_english_cues(manifest)
    if len(english) != len(prior):
        print(f"WARN {episode} cue count {len(english)} vs prior {len(prior)} "
              f"(using fresh ASR alignment)", flush=True)

    zh_map = load_zh_map()
    zh_captions = ensure_zh_captions(english, zh_map)

    plan = dict(plan_draft)
    plan["zh_captions"] = zh_captions
    plan["review_notes"] = list(plan.get("review_notes") or []) + [
        "spec-v2 reexport: master without BGM; zh phrase track added."
    ]
    plan_path = ep_cache / "creative_plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    # shared hash unchanged; plan already points at it

    out = OUT_ROOT / f"{episode}-spec-v2"
    if out.exists():
        shutil.rmtree(out)
    print(f"=== {episode} render ===", flush=True)
    render_comparison(ROOT, shared_path, plan_path, out)

    # Prefer freshly rendered EN cue count for zh verification
    en_srt = (out / f"{episode}.en.srt").read_text(encoding="utf-8")
    en_blocks = [b for b in en_srt.strip().split("\n\n") if b.strip()]
    zh_srt = out / f"{episode}.zh.srt"
    if not zh_srt.is_file():
        raise RuntimeError(f"{episode} render missing zh.srt")
    zh_blocks = [b for b in zh_srt.read_text(encoding="utf-8").strip().split("\n\n")
                 if b.strip()]
    if len(zh_blocks) != len(en_blocks):
        raise RuntimeError(
            f"{episode} zh/en cue count mismatch {len(zh_blocks)}!={len(en_blocks)}")

    write_self_review(out, episode, f"en_cues={len(en_blocks)} zh_cues={len(zh_blocks)}")
    # Keep a copy of the refreshed plan/contract in out (render already wrote them)

    if upload:
        print(f"=== {episode} feiniu ===", flush=True)
        smb = connect_feiniu()
        try:
            remote = force_upload(smb, episode, out)
        finally:
            smb.close()
        print(f"FEINIU {episode} -> {remote}", flush=True)

    if not keep_media:
        # Drop bulky unit pulls + work intermediates; keep out delivery + plans.
        inputs = ep_cache / "inputs"
        if inputs.is_dir():
            shutil.rmtree(inputs)
        work = out / "work"
        if work.is_dir():
            shutil.rmtree(work)
        logs = out / "logs"
        if logs.is_dir():
            shutil.rmtree(logs)
    print(f"DONE {episode}", flush=True)


def list_episodes() -> list[str]:
    return sorted(
        [p.name for p in PLANS.iterdir() if p.is_dir() and p.name.startswith("EP")],
        key=lambda x: int(x[2:]),
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--episodes", nargs="*", default=None,
                    help="EP codes; default all plans under cache")
    ap.add_argument("--skip-upload", action="store_true")
    ap.add_argument("--keep-media", action="store_true")
    ap.add_argument("--zh-only-prefetch", action="store_true",
                    help="Only fill zh_captions_map from all plan cues, then exit")
    args = ap.parse_args()
    eps = args.episodes or list_episodes()
    if args.zh_only_prefetch:
        zh_map = load_zh_map()
        all_en: list[str] = []
        for ep in eps:
            m = json.loads((PLANS / ep / "edit_manifest.json").read_text(encoding="utf-8"))
            all_en.extend(preview_english_cues(m))
        ensure_zh_captions(all_en, zh_map)
        print(f"ZH_MAP size={len(zh_map)} covered={len(all_en)}", flush=True)
        return 0
    for ep in eps:
        process_episode(ep, upload=not args.skip_upload, keep_media=args.keep_media)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
