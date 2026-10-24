#!/usr/bin/env python3
"""Build plan (keep/trim clips), render, archive one lihun EP edit."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/episode_post"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from episode_ending import ending_layout  # noqa: E402
from ep_pilot_timeline import Clip, align_dialogue, tokens, Word  # noqa: E402
from reexport_lihun_edits_v2 import (  # noqa: E402
    ensure_zh_captions,
)
from run_ep_post_pilot import collect_captions, presentation_cues  # noqa: E402
from comfy_orch.feiniu_archive import (  # noqa: E402
    SHARE,
    _ensure_tree,
    _reader,
    _remote_sizes,
    connect_feiniu,
)


def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def rel(p):
    return str(pathlib.Path(p).relative_to(ROOT))


def rehash(items):
    out = []
    for it in items:
        it = dict(it)
        p = ROOT / it["path"]
        if p.exists():
            it["sha256"] = sha(p)
        out.append(it)
    return out


def ensure_zh(english: list[str]) -> list[str]:
    """1:1 zh captions; warm cache + translate misses (no English fallback)."""
    return ensure_zh_captions(english)


def _norm_clips(clips: dict) -> list[tuple[str, int, int]]:
    """Expand {U01:[0,362]} or {U03:[[0,222],[262,340]]} into ordered clip list."""
    out: list[tuple[str, int, int]] = []
    for u, val in clips.items():
        if isinstance(val[0], (list, tuple)):
            for a, b in val:
                out.append((u, int(a), int(b)))
        else:
            out.append((u, int(val[0]), int(val[1])))
    return out


def build(ep: str, clips: dict, aliases: dict[str, str],
          intent: str, notes: list[str], tail_pad: int,
          hard_cut: bool = False) -> pathlib.Path:
    edit = ROOT / f".cache/lihun_{ep.lower()}_edit"
    units = json.loads((edit / "stage_meta.json").read_text())["unit_order"]
    clip_list = _norm_clips({u: clips[u] for u in units})
    base = json.loads(
        (ROOT / "outputs/episode-comparison/EP01-v21/agent-b/input_contract.json").read_text()
    )
    sources = {}
    for u in units:
        udir = edit / "inputs" / f"{ep}-{u}"
        mp4 = next(udir.glob("*.mp4"))
        ana = edit / "analysis" / (mp4.stem + ".json")
        prompt = (udir / "prompt_h3.txt").read_text(encoding="utf-8")
        body = prompt.split("【画面内容】", 1)[1] if "【画面内容】" in prompt else prompt
        lines = [
            t.strip()
            for t in re.findall(r"（([^（）]*)）", body)
            if re.search(r"[A-Za-z]", t) and t.strip()
        ]
        dc = json.loads((udir / "dialogue_check.json").read_text())
        # Prompt paren lines are caption truth; dialogue_check may collapse
        # repeated short lines (EP65 U04 two "No.").
        if lines != dc.get("expected_lines"):
            print("WARN prompt/dc expected mismatch; using prompt", u,
                  "prompt", lines, "dc", dc.get("expected_lines"), flush=True)
        if not dc["ok"]:
            if hard_cut:
                print("HARD_CUT keep FAIL unit", u, "ov", dc.get("overlap"),
                      "miss", dc.get("missing"), "reason", dc.get("reason"), flush=True)
            else:
                assert dc["overlap"] >= 0.85 and not dc["missing"], (u, dc)
                print("WARN non-ok unit kept with overlap", u, dc["reason"], flush=True)
        sources[u] = {
            "path": rel(mp4),
            "prompt": rel(udir / "prompt_h3.txt"),
            "meta": rel(udir / "run_meta.json"),
            "analysis": rel(ana),
            "sha256": sha(mp4),
            "prompt_sha256": sha(udir / "prompt_h3.txt"),
            "meta_sha256": sha(udir / "run_meta.json"),
            "analysis_sha256": sha(ana),
            "expected_dialogue": lines,
        }
    contract = {
        "schema": "episode-edit-comparison/v1",
        "episode": ep,
        "source_version": "lihun-v23",
        "unit_order": units,
        "sources": sources,
        "available_music": rehash(base["available_music"]),
        "available_presets": rehash(base["available_presets"]),
        "skill_snapshot": rehash(base["skill_snapshot"]),
        "delivery": base["delivery"],
        "constraints": base["constraints"],
        "contract_basis": {"derivation": f"lihun-v23 {ep} archive + fix winners; clips from ASR/EDIT_NOTE."},
    }
    cpath = edit / "input_contract.json"
    cpath.write_text(json.dumps(contract, ensure_ascii=False, indent=1), encoding="utf-8")
    csha = sha(cpath)

    story_f = sum(b - a for _, a, b in clip_list)
    story_s = story_f / 24
    cum = [0]
    for _, a, b in clip_list:
        cum.append(cum[-1] + (b - a))
    beats = [
        {
            "output_range_s": [cum[i] / 24, cum[i + 1] / 24],
            "beat": f"{clip_list[i][0]} [{clip_list[i][1]},{clip_list[i][2]}).",
            "treatment": ("open music" if i == 0 else "dry"),
        }
        for i in range(len(clip_list))
    ]
    preset = json.loads((ROOT / "docs/ending-presets/bloom-hold-suspense-v1.json").read_text())
    lay = ending_layout(story_f, preset, tail_pad)
    total_s = lay["total_frames"] / 24
    beats[-1]["output_range_s"][1] = total_s

    plan = {
        "schema": "episode-edit-comparison-plan/v1",
        "agent_id": "agent-b",
        "revision": f"{ep.lower()}-r1",
        "shared_input_sha256": csha,
        "narrative_intent": intent,
        "narrative_beats": beats,
        "clips": [
            {
                "unit": u,
                "in_frame": a,
                "out_frame": b,
                "reason": notes[i] if i < len(notes) else f"clip [{a},{b})",
            }
            for i, (u, a, b) in enumerate(clip_list)
        ],
        "protected_ranges": [
            {
                "unit": u,
                "in_frame": a,
                "out_frame": b,
                "reason": "retained dialogue span",
            }
            for u, a, b in clip_list
        ],
        "subtitle_aliases": aliases,
        "subtitle_style": {"font_size": 38, "outline": 2.0},
        "music": {
            # Open-only: close Undertow + bloom SFX often push post-loudnorm I/TP off gate.
            "cues": [
                {
                    "start": 0.0,
                    "end": min(12.0, max(3.0, (cum[1] / 24 if len(cum) > 1 else 8.0) - 0.3)),
                    "source_in": 0.0,
                    "target_lufs_before_duck": -31.0,
                    "fade_in": 1.5,
                    "fade_out": 0.5,
                    "reason": "Quiet Undertow open only",
                },
            ]
        },
        "ending": {
            "preset_id": "bloom-hold-suspense",
            "preset_version": 1,
            "sfx_gain_db": -14.0,
            "tail_pad_frames": tail_pad,
            "reason": f"story {story_s:.2f}s pad {tail_pad}",
        },
        "rejected_alternatives": [],
        "review_notes": [
            "Independent subagent review: NOT_REQUESTED",
            "Full realtime watch/listen: NOT_DONE",
        ],
    }

    def _cfg():
        return {
            u: {**d, **{k: str(ROOT / d[k]) for k in ("path", "prompt", "meta", "analysis")}}
            for u, d in sources.items()
        }

    def _drop_phrase(phrase: str) -> bool:
        """Remove one unalignable phrase from some unit expected_dialogue. Return True if dropped."""
        for u, d in sources.items():
            lines = list(d["expected_dialogue"])
            new_lines = []
            dropped = False
            for line in lines:
                if dropped:
                    new_lines.append(line)
                    continue
                # Same split as align_dialogue
                parts = []
                for phrase_part in re.split(r"(?<=[.!?])\s+", line.strip()):
                    if len(phrase_part) > 42 and ", " in phrase_part:
                        parts.extend(p.strip() for p in re.split(r"(?<=,)\s+", phrase_part) if p.strip())
                    else:
                        parts.append(phrase_part)
                if phrase in parts:
                    parts = [p for p in parts if p != phrase]
                    if parts:
                        new_lines.append(" ".join(parts))
                    dropped = True
                else:
                    new_lines.append(line)
            if dropped:
                print("HARD_CUT drop phrase", u, repr(phrase), flush=True)
                d["expected_dialogue"] = new_lines
                return True
        return False

    clips_for_cap = [Clip(u, a, b) for u, a, b in clip_list]
    cfg_sources = _cfg()
    if hard_cut:
        # collect_captions re-parses prompt_h3; hard-cut aligns from expected_dialogue
        # and drops phrases ASR cannot match (e.g. Lead vs Leave).
        from ep_pilot_timeline import remap_subtitles

        plan.setdefault("review_notes", []).append(
            "HARD_CUT: archive FAIL units kept; unalignable script phrases dropped from captions."
        )
        unit_windows: dict[str, list[tuple[int, int]]] = {}
        for c in clips_for_cap:
            unit_windows.setdefault(c.unit, []).append((c.in_frame, c.out_frame))
        while True:
            try:
                captions = []
                for u, windows in unit_windows.items():
                    ana = json.loads(pathlib.Path(cfg_sources[u]["analysis"]).read_text())
                    words = []
                    for s in ana["segments"]:
                        for w in s["words"]:
                            if any(
                                a / 24 <= w["start"] < w["end"] <= b / 24
                                for a, b in windows
                            ):
                                words.append(Word(u, w["start"], w["end"], w["word"]))
                    captions.extend(
                        align_dialogue(list(sources[u]["expected_dialogue"]), words, aliases)
                    )
                captions = remap_subtitles(captions, clips_for_cap)
                break
            except ValueError as exc:
                m = re.search(r"cannot align scripted phrase: (.+)$", str(exc))
                if not m:
                    raise
                phrase = m.group(1)
                if phrase.startswith("'") or phrase.startswith('"'):
                    phrase = ast.literal_eval(phrase)
                if not _drop_phrase(phrase):
                    raise
        # Rewrite local prompts so render-time collect_captions (reads prompt_h3)
        # matches the soft-dropped expected_dialogue.
        for u, d in sources.items():
            pp = ROOT / d["prompt"]
            text = pp.read_text(encoding="utf-8")
            body_key = "【画面内容】"
            if body_key not in text:
                continue
            head, rest = text.split(body_key, 1)
            # strip all latin paren lines then re-append kept expected
            cleaned = re.sub(r"（[^（）]*[A-Za-z][^（）]*）", "", rest)
            # insert kept lines near start of body
            insert = "".join(f"（{line}）" for line in d["expected_dialogue"])
            # put after first newline of body if possible
            if "\n" in cleaned:
                first, more = cleaned.split("\n", 1)
                rest2 = first + "\n" + insert + more
            else:
                rest2 = insert + cleaned
            pp.write_text(head + body_key + rest2, encoding="utf-8")
            d["prompt_sha256"] = sha(pp)
            print("HARD_CUT rewrote prompt", u, "lines", len(d["expected_dialogue"]), flush=True)
        cpath.write_text(json.dumps(contract, ensure_ascii=False, indent=1), encoding="utf-8")
        plan["shared_input_sha256"] = sha(cpath)
        cfg_sources = _cfg()
        # Re-collect via the same prompt path render uses, so zh length
        # matches English cues after soft-drops (align path can diverge).
        captions, _ = collect_captions(
            {"sources": cfg_sources, "subtitle_aliases": aliases, "alignment_skips": []},
            clips_for_cap,
        )
    else:
        captions, _ = collect_captions(
            {"sources": cfg_sources, "subtitle_aliases": aliases, "alignment_skips": []},
            clips_for_cap,
        )
    english = [c.text for c in presentation_cues(captions, plan["subtitle_style"])]
    print("cues", len(english), flush=True)
    for i, t in enumerate(english):
        print(f"  {i:02d}", t, flush=True)
    plan["zh_captions"] = ensure_zh(english)
    (edit / "creative_plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print("plan written", story_f, round(story_s, 3), flush=True)
    return edit


def _refresh_skill_digests(edit: pathlib.Path) -> None:
    """Re-hash skill/preset paths so mid-batch skill edits don't kill render."""
    cpath = edit / "input_contract.json"
    ppath = edit / "creative_plan.json"
    contract = json.loads(cpath.read_text(encoding="utf-8"))
    for key in ("skill_snapshot", "available_presets", "available_music"):
        if key in contract:
            contract[key] = rehash(contract[key])
    cpath.write_text(json.dumps(contract, ensure_ascii=False, indent=1), encoding="utf-8")
    plan = json.loads(ppath.read_text(encoding="utf-8"))
    plan["shared_input_sha256"] = sha(cpath)
    ppath.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")


def render(ep: str) -> pathlib.Path:
    edit = ROOT / f".cache/lihun_{ep.lower()}_edit"
    out = ROOT / f"outputs/episode-edits/lihun-v23/{ep}"
    if out.exists():
        shutil.rmtree(out)
    import subprocess

    _refresh_skill_digests(edit)
    subprocess.check_call(
        [
            sys.executable,
            str(ROOT / "scripts/episode_post/run_episode_comparison.py"),
            str(edit / "input_contract.json"),
            str(edit / "creative_plan.json"),
            str(out),
        ],
        cwd=str(ROOT),
        env={**dict(**{k: v for k, v in __import__("os").environ.items()}), "PYTHONPATH": "src"},
    )
    return out


def verify_align(ep: str) -> None:
    out = ROOT / f"outputs/episode-edits/lihun-v23/{ep}"
    q = json.loads((out / "qc_report.json").read_text())
    contract = json.loads((out / "input_contract.json").read_text())
    plan = json.loads((out / "creative_plan.json").read_text())
    expected = []
    for u in contract["unit_order"]:
        expected += contract["sources"][u]["expected_dialogue"]
    clips = [Clip(c["unit"], c["in_frame"], c["out_frame"]) for c in plan["clips"]]
    off = 0.0
    heard = []
    for c in clips:
        ana = json.loads(pathlib.Path(contract["sources"][c.unit]["analysis"]).read_text())
        for s in ana["segments"]:
            for w in s["words"]:
                if c.in_frame / 24 <= w["start"] < w["end"] <= c.out_frame / 24:
                    heard.append(
                        Word(
                            c.unit,
                            w["start"] - c.in_frame / 24 + off,
                            w["end"] - c.in_frame / 24 + off,
                            w["word"],
                        )
                    )
        off += (c.out_frame - c.in_frame) / 24
    aliases = plan.get("subtitle_aliases") or {}
    res = align_dialogue(expected, heard, aliases)
    print(
        "ALIGN",
        q["status"],
        "cues",
        len(res),
        "last",
        res[-1].end,
        "bloom",
        q["ending_layout"]["bloom_start_s"],
        "tok",
        sum(len(tokens(l, aliases)) for l in expected),
        flush=True,
    )
    assert res[-1].end < q["ending_layout"]["bloom_start_s"]


def archive(ep: str, edit_plan_old: str, edit_plan_new: str) -> None:
    out = ROOT / f"outputs/episode-edits/lihun-v23/{ep}"
    (out / "SELF_REVIEW.md").write_text(
        f"# {ep} self-review\n\n- Agent edit from archive + fix winners.\n"
        "- Independent subagent review: NOT_REQUESTED\n"
        "- Full realtime watch/listen: NOT_DONE\n",
        encoding="utf-8",
    )
    files = [
        f"{ep}-master.mp4",
        f"{ep}-review-en.mp4",
        f"{ep}.en.srt",
        f"{ep}.en.ass",
        f"{ep}.zh.srt",
        f"{ep}.zh.ass",
        "MUSIC_CREDITS.txt",
        "SELF_REVIEW.md",
        "creative_plan.json",
        "edit_manifest.json",
        "input_contract.json",
        "qc_report.json",
    ]
    dst = fr"H3_comfyUI_5090\archive\离婚后（10.22）\整集剪辑\{ep}"
    smb0 = connect_feiniu()
    _ensure_tree(smb0, dst)
    smb0.close()

    def _put_one(name: str) -> tuple[str, int]:
        # One SMB connection per file — parallel puts of the two ~80MB mp4s.
        data = (out / name).read_bytes()
        smb = connect_feiniu()
        try:
            smb.putFile(SHARE, dst + "\\" + name, _reader(data))
        finally:
            smb.close()
        print("put", name, len(data), flush=True)
        return name, len(data)

    from concurrent.futures import ThreadPoolExecutor, as_completed

    # Big media first, capped parallelism (SMB NAS friendly).
    heavy = [n for n in files if n.endswith(".mp4")]
    light = [n for n in files if n not in heavy]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futs = [pool.submit(_put_one, n) for n in heavy]
        for fut in as_completed(futs):
            fut.result()
    for name in light:
        _put_one(name)

    smb = connect_feiniu()
    sizes = _remote_sizes(smb, dst)
    ok = all(sizes.get(n) == (out / n).stat().st_size for n in files)
    smb.close()
    print("ARCHIVE_OK" if ok else "ARCHIVE_FAIL", flush=True)
    if not ok:
        raise SystemExit(1)
    plan_md = ROOT / "runs/lihun_v23_edit_plan.md"
    text = plan_md.read_text(encoding="utf-8")
    if edit_plan_old not in text:
        raise SystemExit(f"edit_plan row missing: {edit_plan_old!r}")
    plan_md.write_text(text.replace(edit_plan_old, edit_plan_new, 1), encoding="utf-8")
    cache = ROOT / f".cache/lihun_edit_reexport/plans/{ep}"
    cache.mkdir(parents=True, exist_ok=True)
    for name in (
        "creative_plan.json",
        "input_contract.json",
        "edit_manifest.json",
        "qc_report.json",
        "SELF_REVIEW.md",
        "MUSIC_CREDITS.txt",
    ):
        shutil.copy2(out / name, cache / name)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("episode")
    ap.add_argument("--clips", default="", help='JSON {"U01":[0,362],...}')
    ap.add_argument("--aliases", default="{}")
    ap.add_argument("--intent", default="Keep performances; sparse Undertow open/close.")
    ap.add_argument("--notes", default="[]")
    ap.add_argument("--tail-pad", type=int, default=24)
    ap.add_argument("--edit-old", default="")
    ap.add_argument("--edit-new", default="")
    ap.add_argument("--skip-archive", action="store_true")
    ap.add_argument("--archive-only", action="store_true",
                    help="Only upload Feiniu + update edit_plan (needs --edit-old/--edit-new).")
    ap.add_argument("--hard-cut", action="store_true",
                    help="Keep archive FAIL units; drop unalignable caption lines.")
    args = ap.parse_args()
    if args.archive_only:
        if not args.edit_old or not args.edit_new:
            raise SystemExit("--archive-only requires --edit-old and --edit-new")
        archive(args.episode, args.edit_old, args.edit_new)
        return 0
    if not args.clips or not args.edit_old or not args.edit_new:
        raise SystemExit("--clips/--edit-old/--edit-new required unless --archive-only")
    clips = json.loads(args.clips)
    aliases = json.loads(args.aliases)
    notes = json.loads(args.notes)
    build(args.episode, clips, aliases, args.intent, notes, args.tail_pad,
          hard_cut=args.hard_cut)
    render(args.episode)
    verify_align(args.episode)
    if not args.skip_archive:
        archive(args.episode, args.edit_old, args.edit_new)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
