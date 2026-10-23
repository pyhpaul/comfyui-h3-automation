#!/usr/bin/env python3
"""Assemble one episode from generated unit clips (rough cut, v1.0).

Pipeline (decisions validated on chaofu EP24, 2026-10-22, v1-v5 tests):
  1. Per unit: word timestamps + scene cuts (cached candidate_audit.json
     when present, else computed via faster-whisper + ffmpeg scene select
     and cached as assembly_audit.json next to the mp4).
  2. Base trims: head = first_word - 0.35s; tail = last_word + 0.5s,
     extended to the next scene cut when <= 1.0s later. Silent units
     are kept whole.
  3. Seams between units (the part that makes or breaks the assembly):
     - break seams (next unit independent): plain hard cut.
     - chain seams (motion_latent): the next unit's head re-renders
       ~1s of the previous tail, so the video in-point is frame-matched
       against the previous unit's final frame. Audio is placed
       independently: dialogue units start their audio at local 0, so
       the first line lands as a J-cut over the outgoing picture and
       stays in sync from the seam onward. The skip (== audio lead) is
       capped by seam class parsed from the prompts:
         same speaker visible in the outgoing tail shot -> <= 0.15s
         otherwise (listener tail / speaker change)     -> 0.30-0.50s
     - previous audio keeps a 0.12s ambience tail (L-cut).
     No video blends anywhere (dissolves ghost; tested and rejected).
  4. Same-scene units are histogram-matched (per-channel p5/p95, 55%
     damped) toward the unit closest to the scene median.
  5. Two-pass loudnorm to -14 LUFS / -1.5 dBTP, audio 48 kHz, keyframes
     forced at seams, merged SRT re-timed from the audio placements.

Inputs: an episode directory whose immediate subdirectories are units
(any layout containing an mp4 plus prompt_h3.txt / run_meta.json, e.g.
Feiniu <EP>/<U>-WENXI/ or a local verify cache). Outputs land in
--out-dir: <EP>_assembled.mp4, edit_manifest.json, <EP>_assembled.srt,
qc.json. Nothing is uploaded; review the manifest before shipping.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

TARGET_I, TARGET_TP, TARGET_LRA = -14.0, -1.5, 11.0
MATCH_WINDOW, MATCH_PENALTY = 1.20, 6.0
LEAD_SAME_SPEAKER, LEAD_MIN, LEAD_MAX = 0.15, 0.30, 0.50


# ---------------------------------------------------------------- media io
def probe_dur(p: Path) -> float:
    return float(subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
         '-of', 'csv=p=0', str(p)], capture_output=True, text=True).stdout)


def run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(r.stderr[-2000:])


def frame_gray(path: Path, t: float, w=96, h=172) -> np.ndarray:
    for tt in (t, t - 0.08, t - 0.2, max(0.0, t - 0.45)):
        raw = subprocess.run(
            ['ffmpeg', '-v', 'error', '-ss', f'{max(0.0, tt):.3f}',
             '-i', str(path), '-frames:v', '1',
             '-vf', f'scale={w}:{h},format=gray',
             '-f', 'rawvideo', '-'], capture_output=True).stdout
        if len(raw) == w * h:
            return np.frombuffer(raw, dtype=np.uint8).reshape(h, w) \
                .astype(np.float32)
    raise RuntimeError(f'no frame at {path}@{t}')


def frame_rgb_small(path: Path, t: float, w=96, h=172) -> np.ndarray:
    raw = subprocess.run(
        ['ffmpeg', '-v', 'error', '-ss', f'{t:.3f}', '-i', str(path),
         '-frames:v', '1', '-vf', f'scale={w}:{h},format=rgb24',
         '-f', 'rawvideo', '-'], capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 3) \
        .astype(np.float32)


def scene_cuts(mp4: Path) -> list[float]:
    out = subprocess.run(
        ['ffmpeg', '-i', str(mp4), '-filter:v',
         "select='gt(scene,0.25)',showinfo", '-f', 'null', '-'],
        capture_output=True, text=True).stderr
    cuts = []
    for line in out.splitlines():
        if 'pts_time:' in line:
            try:
                cuts.append(round(float(
                    line.split('pts_time:')[1].split()[0]), 2))
            except (ValueError, IndexError):
                pass
    return cuts


def word_timestamps(mp4: Path) -> list[dict]:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
    from comfy_orch.dialogue_gate import _get_whisper_model, mp4_to_wav
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / 'a.wav'
        mp4_to_wav(mp4, wav)
        segs, _ = _get_whisper_model().transcribe(
            str(wav), word_timestamps=True)
        return [{'start': round(w.start, 2), 'end': round(w.end, 2),
                 'word': w.word.strip()}
                for s in segs for w in (s.words or [])]


# ------------------------------------------------------------------ parsing
def parse_people(prompt: str) -> list[str]:
    m = re.search(r'人物：([^\n]+)', prompt)
    if not m:
        return []
    names = []
    for part in re.split(r'[、，,]', m.group(1)):
        name = re.sub(r'［[^］]*］', '', part).strip()
        if name and re.search(r'[A-Za-z]', name):
            names.append(name)
    return names


def shot_paragraphs(prompt: str) -> list[str]:
    return [ln for ln in prompt.splitlines() if ln.startswith('▲')]


def para_speaker(para: str, people: list[str]) -> str | None:
    bracket = re.search(r'［([^］]*)］', para)
    if bracket:
        named = [p for p in people if p in bracket.group(1)]
        if len(named) == 1:
            return named[0]
    head = para.split('口型同步开口')[0].split('：（')[0]
    best, at = None, -1
    for p in people:
        i = head.rfind(p)
        if i > at:
            best, at = p, i
    return best


def dialogue_speakers(prompt: str, people: list[str]) -> list[str]:
    out = []
    for para in shot_paragraphs(prompt):
        if '（' in para and '）' in para:
            sp = para_speaker(para, people)
            if sp:
                out.append(sp)
    return out


def last_shot_subject(prompt: str, people: list[str]) -> str | None:
    paras = shot_paragraphs(prompt)
    if not paras:
        return None
    bracket = re.search(r'［([^］]*)］', paras[-1])
    if not bracket:
        return None
    for p in people:
        if p in bracket.group(1):
            return p
    return None


def scene_key(prompt: str) -> str:
    m = re.search(r'场景：([^\n]+)', prompt)
    return m.group(1).strip() if m else ''


# -------------------------------------------------------------------- units
def resolve_unit(unit_dir: Path) -> dict:
    mp4s = sorted(unit_dir.rglob('*.mp4'))
    assert mp4s, f'no mp4 under {unit_dir}'
    mp4 = next((p for p in mp4s if p.name.endswith('-audio.mp4')), mp4s[0])
    asset = mp4.parent
    prompt_path = asset / 'prompt_h3.txt'
    prompt = prompt_path.read_text(encoding='utf-8') \
        if prompt_path.exists() else ''
    meta = {}
    if (asset / 'run_meta.json').exists():
        meta = json.loads((asset / 'run_meta.json').read_text())
    audit = None
    for cand in ('candidate_audit.json', 'assembly_audit.json'):
        if (asset / cand).exists():
            audit = json.loads((asset / cand).read_text())
            break
    if audit is None:
        audit = {'words': word_timestamps(mp4),
                 'scene_cuts': scene_cuts(mp4)}
        (asset / 'assembly_audit.json').write_text(
            json.dumps(audit, ensure_ascii=False), encoding='utf-8')
    srt = next((p for p in sorted(asset.glob('*.srt'))
                if not p.name.endswith('_words.srt')), None)
    uid = re.search(r'(U\d+)', unit_dir.name)
    return {'unit': uid.group(1) if uid else unit_dir.name,
            'dir': unit_dir, 'mp4': mp4, 'asset': asset,
            'prompt': prompt, 'meta': meta, 'audit': audit,
            'srt': srt, 'duration': probe_dur(mp4)}


def base_trim(u: dict) -> None:
    words = u['audit'].get('words') or []
    cuts = u['audit'].get('scene_cuts') or []
    dur = u['duration']
    if words:
        u['in'] = max(0.0, float(words[0]['start']) - 0.35)
        cand = float(words[-1]['end']) + 0.5
        later = [c for c in cuts if c > cand]
        u['out'] = min(later[0] + 0.1 if later and later[0] - cand <= 1.0
                       else cand, dur)
    else:
        u['in'], u['out'] = 0.0, dur
    u['in'], u['out'] = round(u['in'], 2), round(u['out'], 2)


def match_head(prev: dict, nxt: dict) -> tuple[float, float, float]:
    ref = frame_gray(prev['mp4'], prev['out'] - 0.02)
    mad0 = float(np.abs(frame_gray(nxt['mp4'], 0.0) - ref).mean())
    best = (mad0, 0.0)
    for k in range(int(MATCH_WINDOW * 12) + 1):
        t = k / 12.0
        mad = float(np.abs(frame_gray(nxt['mp4'], t) - ref).mean())
        if mad + MATCH_PENALTY * t < best[0] + MATCH_PENALTY * best[1]:
            best = (mad, t)
    return best[1], best[0], mad0


def plan_seams(units: list[dict]) -> list[dict]:
    seams = []
    for i in range(len(units) - 1):
        prev, nxt = units[i], units[i + 1]
        chain = bool(nxt['meta'].get('parent_latent')) or \
            nxt['meta'].get('continuity') in ('motion_latent',
                                              'parent_latent')
        if not chain:
            seams.append({'after': prev['unit'], 'kind': 'break',
                          'video_in_next': nxt['in']})
            continue
        t, mad, mad0 = match_head(prev, nxt)
        people = parse_people(nxt['prompt'])
        nxt_spk = (dialogue_speakers(nxt['prompt'], people) or [None])[0]
        prev_subj = last_shot_subject(prev['prompt'],
                                      parse_people(prev['prompt']))
        words = nxt['audit'].get('words') or []
        if not words:
            vin, cls = min(t, LEAD_MAX), 'action-chain'
        elif nxt_spk and prev_subj and nxt_spk == prev_subj:
            vin, cls = min(t, LEAD_SAME_SPEAKER), 'same-speaker-on-screen'
        else:
            vin = min(max(t, LEAD_MIN), LEAD_MAX)
            cls = 'split-edit'
        nxt['in'] = round(vin, 2)
        seams.append({'after': prev['unit'], 'kind': 'chain',
                      'class': cls, 'match_t': round(t, 2),
                      'mad_at_match': round(mad, 1),
                      'mad_at_0': round(mad0, 1),
                      'video_in_next': nxt['in'],
                      'next_speaker': nxt_spk,
                      'prev_tail_subject': prev_subj})
    for u in units:
        u['kept'] = round(u['out'] - u['in'], 2)
    return seams


def color_plan(units: list[dict]) -> dict[str, str]:
    groups: dict[str, list[dict]] = {}
    for u in units:
        groups.setdefault(scene_key(u['prompt']) or u['unit'],
                          []).append(u)
    filters: dict[str, str] = {}
    for key, members in groups.items():
        if len(members) < 2 or not key:
            continue
        stats = {}
        for u in members:
            frames = [frame_rgb_small(u['mp4'], u['in'] + f *
                                      (u['out'] - u['in']))
                      for f in (0.25, 0.55, 0.85)]
            px = np.concatenate([f.reshape(-1, 3) for f in frames])
            stats[u['unit']] = {'p5': np.percentile(px, 5, axis=0),
                                'p95': np.percentile(px, 95, axis=0)}
        med5 = np.median([s['p5'] for s in stats.values()], axis=0)
        med95 = np.median([s['p95'] for s in stats.values()], axis=0)
        hero = min(stats, key=lambda k:
                   float(np.abs(stats[k]['p5'] - med5).sum()
                         + np.abs(stats[k]['p95'] - med95).sum()))
        hs = stats[hero]
        for u in members:
            if u['unit'] == hero:
                continue
            s = stats[u['unit']]
            parts = []
            for ch, nm in enumerate('rgb'):
                ilo = min(max(s['p5'][ch] / 255, 0.0), 0.6)
                ihi = max(min(s['p95'][ch] / 255, 1.0), ilo + 0.25)
                olo = (s['p5'][ch] + 0.55 * (hs['p5'][ch]
                                             - s['p5'][ch])) / 255
                ohi = (s['p95'][ch] + 0.55 * (hs['p95'][ch]
                                              - s['p95'][ch])) / 255
                parts += [f'{nm}imin={ilo:.3f}', f'{nm}imax={ihi:.3f}',
                          f'{nm}omin={min(max(olo, 0.0), 0.6):.3f}',
                          f'{nm}omax={max(min(ohi, 1.0), 0.4):.3f}']
            filters[u['unit']] = 'colorlevels=' + ':'.join(parts)
    return filters


# ------------------------------------------------------------------ render
def parse_ts(s: str) -> float:
    h, m, rest = s.split(':')
    return int(h) * 3600 + int(m) * 60 + float(rest.replace(',', '.'))


def fmt_ts(sec: float) -> str:
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def render(units: list[dict], seams: list[dict],
           filters: dict[str, str], out_dir: Path, episode: str) -> dict:
    starts, acc = [], 0.0
    for u in units:
        starts.append(acc)
        acc += u['kept']
    total = acc
    inputs, filt = [], []
    for i, u in enumerate(units):
        inputs += ['-i', str(u['mp4'])]
        vf = (f"trim=start={u['in']}:end={u['out']},"
              f"setpts=PTS-STARTPTS,fps=24,settb=AVTB,format=yuv420p")
        if u['unit'] in filters:
            vf += ',' + filters[u['unit']]
        filt.append(f'[{i}:v]{vf}[v{i}]')
    labels = ''.join(f'[v{i}]' for i in range(len(units)))
    filt.append(f'{labels}concat=n={len(units)}:v=1:a=0[v]')

    audio_meta = []
    for i, u in enumerate(units):
        words = u['audit'].get('words') or []
        if i == 0:
            a_in, place = u['in'], 0.0
        elif words:
            a_in, place = 0.0, max(0.0, starts[i] - u['in'])
        else:
            a_in, place = u['in'], starts[i]
        a_out = u['out'] + (0.12 if i < len(units) - 1 else 0.0)
        dur = a_out - a_in
        filt.append(
            f"[{i}:a]atrim=start={a_in}:end={a_out},"
            f"asetpts=PTS-STARTPTS,aresample=48000,"
            f"afade=t=in:st=0:d=0.02,"
            f"afade=t=out:st={max(0.0, dur - 0.12):.3f}:d=0.12,"
            f"adelay=delays={int(round(place * 1000))}:all=1[a{i}]")
        audio_meta.append({'unit': u['unit'], 'audio_in': a_in,
                           'audio_out': round(a_out, 2),
                           'placed_at': round(place, 3)})
    alabels = ''.join(f'[a{i}]' for i in range(len(units)))
    filt.append(f"{alabels}amix=inputs={len(units)}:duration=longest:"
                f"dropout_transition=0:normalize=0,"
                f"atrim=0:{total:.3f}[a]")

    raw = out_dir / '_assembled_raw.mp4'
    final = out_dir / f'{episode}_assembled.mp4'
    seam_times = [round(s, 2) for s in starts[1:]]
    run(['ffmpeg', '-y', '-v', 'error', *inputs, '-filter_complex',
         ';'.join(filt), '-map', '[v]', '-map', '[a]',
         '-c:v', 'libx264', '-crf', '18', '-preset', 'medium',
         '-pix_fmt', 'yuv420p',
         '-force_key_frames', ','.join(str(t) for t in seam_times),
         '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', str(raw)])
    meas = subprocess.run(
        ['ffmpeg', '-i', str(raw), '-af',
         f'loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}:'
         'print_format=json', '-f', 'null', '-'],
        capture_output=True, text=True).stderr
    m = json.loads(re.search(r'\{[^{}]*"input_i"[^{}]*\}', meas).group(0))
    ln = (f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}:"
          f"measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:"
          f"measured_thresh={m['input_thresh']}:"
          f"offset={m['target_offset']}:linear=true")
    run(['ffmpeg', '-y', '-v', 'error', '-i', str(raw), '-af', ln,
         '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000',
         str(final)])

    cues, idx = [], 0
    for u, am in zip(units, audio_meta):
        if not u['srt']:
            continue
        for block in re.split(r'\n\s*\n', u['srt'].read_text(
                encoding='utf-8').strip()):
            lines = block.strip().splitlines()
            if len(lines) < 3 or '-->' not in lines[1]:
                continue
            a, b = lines[1].split('-->')
            s = max(0.0, parse_ts(a.strip()) - am['audio_in']
                    + am['placed_at'])
            en = parse_ts(b.strip()) - am['audio_in'] + am['placed_at']
            idx += 1
            cues.append(f"{idx}\n{fmt_ts(s)} --> {fmt_ts(en)}\n"
                        + '\n'.join(lines[2:]) + '\n')
    srt_path = out_dir / f'{episode}_assembled.srt'
    srt_path.write_text('\n'.join(cues), encoding='utf-8')
    raw.unlink()
    return {'final': final, 'srt': srt_path, 'seam_times': seam_times,
            'audio': audio_meta, 'duration': round(probe_dur(final), 2)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--episode-dir', type=Path, required=True,
                    help='directory whose subdirectories are units')
    ap.add_argument('--episode', required=True, help='e.g. EP24')
    ap.add_argument('--out-dir', type=Path, required=True)
    args = ap.parse_args()

    unit_dirs = sorted(
        (d for d in args.episode_dir.iterdir() if d.is_dir()),
        key=lambda d: (re.search(r'U(\d+)', d.name).group(1)
                       if re.search(r'U(\d+)', d.name) else d.name))
    units = [resolve_unit(d) for d in unit_dirs]
    for i, u in enumerate(units):
        base_trim(u)
        chain = bool(u['meta'].get('parent_latent')) or \
            u['meta'].get('continuity') in ('motion_latent',
                                            'parent_latent')
        if i == 0 or not chain:
            # scene-establishing heads survive: cap the head trim
            u['in'] = min(u['in'], 0.5)
        u['kept'] = round(u['out'] - u['in'], 2)
    seams = plan_seams(units)
    filters = color_plan(units)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    result = render(units, seams, filters, args.out_dir, args.episode)

    qc_meas = subprocess.run(
        ['ffmpeg', '-i', str(result['final']), '-af',
         'loudnorm=print_format=json', '-f', 'null', '-'],
        capture_output=True, text=True).stderr
    qm = json.loads(re.search(r'\{[^{}]*"input_i"[^{}]*\}',
                              qc_meas).group(0))
    manifest = {
        'episode': args.episode,
        'tool': 'scripts/assemble_episode.py v1.0',
        'units': [{'unit': u['unit'], 'source': str(u['mp4']),
                   'duration': round(u['duration'], 2),
                   'in': u['in'], 'out': u['out'], 'kept': u['kept'],
                   'words': len(u['audit'].get('words') or []),
                   'scene_cuts': u['audit'].get('scene_cuts') or []}
                  for u in units],
        'seams': seams, 'audio': result['audio'],
        'seam_times_s': result['seam_times'],
        'color_filters': filters,
        'total_source_s': round(sum(u['duration'] for u in units), 2),
        'final_duration_s': result['duration'],
        'output': str(result['final']), 'merged_srt': str(result['srt']),
        'loudness_final': {'I': qm['input_i'], 'TP': qm['input_tp']},
    }
    (args.out_dir / 'edit_manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding='utf-8')
    (args.out_dir / 'qc.json').write_text(json.dumps(
        {'loudness_final': manifest['loudness_final'],
         'duration_s': result['duration'],
         'seams': len(seams)}, indent=2), encoding='utf-8')
    for s in seams:
        print(s)
    print(f"DONE {result['final']} ({result['duration']}s, "
          f"{qm['input_i']} LUFS / {qm['input_tp']} dBTP)")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
