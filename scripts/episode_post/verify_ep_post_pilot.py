#!/usr/bin/env python3
"""Post-render dialogue, audio-offset and image-defect evidence, not a human verdict."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

import numpy as np

from ep_pilot_media import run_logged
from ep_pilot_timeline import Word, align_dialogue, tokens


def mono(path: Path) -> np.ndarray:
    result = subprocess.run([
        "ffmpeg", "-nostdin", "-v", "error", "-i", str(path),
        "-vn", "-ar", "16000", "-ac", "1", "-f", "f32le", "-",
    ], capture_output=True, check=True)
    return np.frombuffer(result.stdout, dtype="<f4").astype(np.float64)


def audio_offsets(manifest: dict, final: Path) -> list[dict]:
    rendered = mono(final)
    offset = 0.0
    results = []
    for clip in manifest["clips"]:
        source = manifest["sources"][clip["unit"]]
        words = json.loads(Path(source["analysis"]).read_text())["segments"][0]["words"]
        source_time = max(clip["in_frame"] / 24, words[0]["start"]) + 0.1
        reference = mono(Path(source["path"]))[round(source_time * 16000):round((source_time + 1) * 16000)]
        expected = round((offset + source_time - clip["in_frame"] / 24) * 16000)
        left = max(0, expected - 2400)
        search = rendered[left:expected + len(reference) + 2400]
        reference = reference - reference.mean()
        cross = np.correlate(search, reference, mode="valid")
        energy = np.concatenate(([0.0], np.cumsum(search ** 2)))
        energies = energy[len(reference):] - energy[:-len(reference)]
        scores = cross / np.maximum(1e-12, np.linalg.norm(reference) * np.sqrt(np.maximum(0, energies)))
        index = int(np.argmax(scores))
        shift = (left + index - expected) / 16000
        result = {"unit": clip["unit"], "source_anchor_s": source_time,
                  "expected_output_s": expected / 16000, "offset_error_s": shift,
                  "correlation": float(scores[index])}
        if abs(shift) > 1 / 24 or result["correlation"] < 0.75:
            raise ValueError(f"audio anchor mismatch: {result}")
        results.append(result)
        offset += (clip["out_frame"] - clip["in_frame"]) / 24
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    config = json.loads((out / "edit_manifest.json").read_text())
    final = out / "EP01-review-en.mp4"
    analysis = json.loads((out / "analysis/EP01-review-en.json").read_text())
    words = [Word("EP01", word["start"], word["end"], word["word"])
             for segment in analysis["segments"] for word in segment["words"]]
    expected = [cue["text"] for cue in config["rendered_subtitle_cues"]]
    # Final-mix ASR spells the known character Ava as Eva once; retain raw evidence.
    aliases = {**config["subtitle_aliases"], "eva": "ava"}
    aligned = align_dialogue(expected, words, aliases)
    need = tokens(" ".join(expected), aliases)
    heard = tokens(" ".join(w.text for w in words), aliases)
    anchors = audio_offsets(config, final)
    duration = sum(c["out_frame"] - c["in_frame"] for c in config["clips"]) / 24
    output = run_logged([
        "ffmpeg", "-nostdin", "-hide_banner", "-i", str(final), "-t", str(duration - 0.25),
        "-vf", "blackdetect=d=0.3:pix_th=0.1,freezedetect=n=-50dB:d=1", "-an", "-f", "null", "-",
    ], out / "logs/image-defects.log")
    events = [line for line in output.splitlines() if re.search(r"black_start:|freeze_(start|end|duration):", line)]
    report = json.loads((out / "qc_report.json").read_text())
    report["post_render_dialogue"] = {
        "hash_bound_to_final": analysis["sha256"] == report["outputs"][1]["sha256"]
        == hashlib.sha256(final.read_bytes()).hexdigest(),
        "phrases_aligned_in_order": len(aligned), "scripted_tokens": len(need),
        "heard_tokens": len(heard), "exact_token_sequence_after_explicit_aliases": need == heard,
        "explicit_asr_name_aliases": aliases,
        "observed_asr_aliases": {name: canonical for name, canonical in aliases.items()
                                 if name in tokens(" ".join(w.text for w in words), {})},
        "speaker_attribution": "NOT_VERIFIED",
    }
    if not report["post_render_dialogue"]["hash_bound_to_final"]:
        raise ValueError("post-render ASR not bound to final output")
    if need != heard:
        raise ValueError("final dialogue differs from scripted token sequence")
    report["audio_anchor_checks"] = anchors
    report["image_defect_scan"] = {
        "scope": "story picture excluding intentional final fade and end card",
        "events": events, "black_min_s": 0.3, "freeze_min_s": 1,
        "limitation": "No events does not certify motion, continuity or absence of semantic defects.",
    }
    (out / "qc_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"dialogue": report["post_render_dialogue"],
                      "audio_anchors": anchors, "image_events": events}), flush=True)


if __name__ == "__main__":
    main()
