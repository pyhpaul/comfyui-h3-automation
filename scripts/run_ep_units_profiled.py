#!/usr/bin/env python3
"""Run EP units with selectable continuity / second-pass profiles.

Examples:
  # original behavior (MP4 parent + one pass)
  python scripts/run_ep_units_profiled.py --units U01 U02 --continuity ref_video

  # causality acceptance (latent Motion Context + 二采)
  python scripts/run_ep_units_profiled.py --units U01 U02 \\
      --continuity motion_latent --second-pass \\
      --download-dir /mnt/c/Users/lxy/Downloads/EP02-H3-causality-v21-latent-mc

  # store the four delivery files on Feiniu and skip the local download dir
  python scripts/run_ep_units_profiled.py --units U01 \\
      --continuity motion_latent --feiniu-batch '这杯奶茶你请不起（10.10）'
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import threading
import time
import uuid
from pathlib import Path

import yaml

from comfy_orch.artifacts import collect_outputs
from comfy_orch.feiniu_archive import archive_named_files
from comfy_orch.binder import apply_bindings, list_media_fields
from comfy_orch.client import ComfyClient
from comfy_orch.dialogue_gate import (
    bump_noise_seed,
    check_mp4_dialogue,
    gate_enabled,
    select_primary_mp4,
)
from comfy_orch.manifest import load_and_validate_job
from comfy_orch.paths import project_root
from comfy_orch.prompt_wire import audit_pack_prompt_wiring, wire_pack_prompt
from comfy_orch.gpu_adapt import apply_gpu_profile, resolve_gpu_profile
from comfy_orch.latent_scene import breaks_motion_chain
from comfy_orch.named_assets_bind import motion_latent_prefix
from comfy_orch.render_profile import (
    RenderProfile,
    apply_render_profile,
    extract_saved_latent_path,
    preferred_video_node_ids,
)
from comfy_orch.status import JobStatus, write_status
from comfy_orch.ui_bind import prune_unused_api_ref_images


_UNIT_NUM = re.compile(r"^U(\d+)", re.I)


def handoff_latent_then_archive(latent_path: str, archive):
    """Return the GPU latent path before ``archive`` finishes.

    The next unit only needs that path. Downloading the film and uploading it
    to Feiniu can run while the GPU starts the following unit.
    """
    if not latent_path:
        raise RuntimeError("motion_latent mode could not resolve SaveLatent slot path")
    errors: list[BaseException] = []

    def run() -> None:
        try:
            archive()
        except BaseException as exc:
            errors.append(exc)
            print(f"ARCHIVE_FAILED {exc}", flush=True)

    thread = threading.Thread(target=run, name="h3-feiniu-archive")
    thread.start()
    return latent_path, thread, errors


def _output_rel(path: str) -> str:
    rel = path.replace("\\", "/")
    marker = "/output/"
    if marker in rel:
        rel = rel.split(marker, 1)[1]
    return rel


def _unit_clip_index(unit: str) -> int:
    """U03 -> 3, U03A -> 3. Letter suffixes share the number; latent prefix keeps them apart."""
    m = _UNIT_NUM.match(unit.strip())
    if not m:
        raise ValueError(f"cannot parse clip index from unit {unit!r}")
    return int(m.group(1))


_TRANSIENT_MARKERS = (
    "no route to host",
    "connection reset",
    "connection refused",
    "timed out",
    "timeout",
    "temporarily unavailable",
    "name or service not known",
    "network is unreachable",
    "remote end closed",
    "connection aborted",
    "broken pipe",
)


def _transient_tunnel(exc: BaseException) -> bool:
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return True
    text = str(exc).lower()
    return any(marker in text for marker in _TRANSIENT_MARKERS)


def _retry_tunnel(action, label: str, timeout: float = 1800.0):
    start = time.time()
    while True:
        try:
            return action()
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if not (_transient_tunnel(exc) or status in {502, 503, 504}) or time.time() - start > timeout:
                raise
            print(f"  {label} tunnel={type(exc).__name__} elapsed={time.time()-start:.0f}s", flush=True)
            time.sleep(10)


def _get_json(client: ComfyClient, path: str, prompt_id: str, start: float, timeout: float) -> dict:
    while True:
        try:
            # Hard per-request cap so a stuck tunnel cannot freeze the waiter.
            response = client._client.get(path, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if not (_transient_tunnel(exc) or status in {502, 503, 504}) or time.time() - start > timeout:
                raise
            print(
                f"  wait {prompt_id[:8]} tunnel={type(exc).__name__} elapsed={time.time()-start:.0f}s",
                flush=True,
            )
            time.sleep(10)


def _history_done(entry: dict) -> bool:
    st = (entry.get("status") or {})
    if st.get("status_str") == "success" or st.get("completed") is True:
        return True
    msgs = st.get("messages") or []
    return any(
        isinstance(m, (list, tuple)) and m and m[0] == "execution_success" for m in msgs
    )


def _wait(client: ComfyClient, prompt_id: str, timeout: float = 7200.0) -> dict:
    start = time.time()
    while True:
        hist = _get_json(client, f"/history/{prompt_id}", prompt_id, start, timeout)
        entry = hist.get(prompt_id)
        if entry:
            st = (entry.get("status") or {}).get("status_str")
            msgs = (entry.get("status") or {}).get("messages") or []
            interrupted = any(
                isinstance(m, (list, tuple)) and m and m[0] == "execution_interrupted"
                for m in msgs
            )
            if interrupted or st == "error":
                raise RuntimeError(f"failed status={st} interrupted={interrupted}")
            if _history_done(entry):
                return entry
            # Outputs present after a tunnel blip: treat as done even if status lagging.
            if entry.get("outputs") and time.time() - start > 90:
                return entry
        q = _get_json(client, "/queue", prompt_id, start, timeout)
        run_ids = [i[1] for i in (q.get("queue_running") or []) if isinstance(i, list) and len(i) > 1]
        pen_ids = [i[1] for i in (q.get("queue_pending") or []) if isinstance(i, list) and len(i) > 1]
        state = "running" if prompt_id in run_ids else ("pending" if prompt_id in pen_ids else "not_in_queue")
        print(f"  wait {prompt_id[:8]} queue={state} elapsed={time.time()-start:.0f}s", flush=True)
        # Ghost running + empty real queue: history already done above, else lose after 120s.
        if state == "not_in_queue" and time.time() - start > 120:
            # One more history pull before declaring lost.
            hist2 = _get_json(client, f"/history/{prompt_id}", prompt_id, start, timeout)
            entry2 = hist2.get(prompt_id)
            if entry2 and (_history_done(entry2) or entry2.get("outputs")):
                return entry2
            raise RuntimeError("lost from queue without history")
        if time.time() - start > timeout:
            raise TimeoutError(prompt_id)
        # Completion lag averages poll/2; 2s is enough vs ~10min renders.
        time.sleep(2)


def _store_unit_outputs(
    client,
    *,
    entry,
    root,
    job_id,
    profile,
    continuity,
    second_pass,
    job_dir,
    unit_name,
    unit,
    episode,
    feiniu_batch,
    dl_root,
    rec,
    known_latent: str | None = None,
):
    """Download the finished unit and copy it to Feiniu or the local download dir."""
    from pathlib import PurePosixPath

    out_dir = root / "outputs" / job_id
    saved = _retry_tunnel(
        lambda: collect_outputs(
            client,
            entry,
            out_dir,
            prefer_node_ids=preferred_video_node_ids(profile),
        ),
        f"download {unit_name}",
    )
    latent_path = known_latent or extract_saved_latent_path(
        entry,
        filename_prefix=profile.latent_filename_prefix,
        clip_index=profile.save_clip_index,
    )
    if continuity == "motion_latent":
        if not latent_path:
            raise RuntimeError("motion_latent mode could not resolve SaveLatent slot path")
        rel = _output_rel(latent_path)
        sub = str(PurePosixPath(rel).parent)
        name = PurePosixPath(rel).name
        if sub == ".":
            sub = ""
        probe = _retry_tunnel(
            lambda: client._client.get(
                "/view",
                params={"filename": name, "subfolder": sub, "type": "output"},
            ),
            f"latent {name}",
        )
        if probe.status_code >= 400:
            raise RuntimeError(f"motion latent slot missing on server: {rel} (HTTP {probe.status_code})")
        latent_bytes = probe.content
        latent_file = name
        latent_path = rel
    else:
        latent_bytes = None
        latent_file = None

    meta = {
        "continuity": continuity,
        "second_pass": bool(second_pass),
        "latent_path": latent_path,
        "prompt_id": rec["prompt_id"],
        "job_id": job_id,
    }
    meta_text = json.dumps(meta, ensure_ascii=False, indent=2) + "\n"
    if dl_root is not None:
        unit_dl = dl_root / unit_name
        unit_dl.mkdir(parents=True, exist_ok=True)
        for path in saved:
            (unit_dl / path.name).write_bytes(path.read_bytes())
        for filename in ("prompt_h3.txt", "prompt_source.txt", "prompt_audit.json"):
            src = job_dir / "assets" / filename
            if src.is_file():
                (unit_dl / filename).write_bytes(src.read_bytes())
        if latent_file is not None and latent_bytes is not None:
            (unit_dl / latent_file).write_bytes(latent_bytes)
        (unit_dl / "run_meta.json").write_text(meta_text, encoding="utf-8")
        published = [path.name for path in saved]
        message = f"profiled {continuity}"
    else:
        payloads: dict[str, bytes] = {
            path.name: path.read_bytes() for path in saved if path.suffix.lower() == ".mp4"
        }
        payloads["prompt_h3.txt"] = (job_dir / "assets" / "prompt_h3.txt").read_bytes()
        payloads["run_meta.json"] = meta_text.encode("utf-8")
        if latent_file is not None and latent_bytes is not None:
            payloads[latent_file] = latent_bytes
        remote = archive_named_files(
            payloads,
            batch=feiniu_batch,
            episode=str(episode),
            unit=unit,
        )
        published = list(payloads)
        message = f"feiniu {remote}"
        print(f"FEINIU {unit_name} {remote}", flush=True)
        if continuity == "motion_latent" and out_dir.is_dir():
            shutil.rmtree(out_dir)
    write_status(
        root / "runs" / job_id / "status.json",
        JobStatus(
            job_id=job_id,
            state="done",
            prompt_id=rec["prompt_id"],
            outputs=published,
            message=message,
        ),
    )
    rec["state"] = "done"
    rec["outputs"] = published
    rec["latent_path"] = latent_path
    print(f"SUCCESS {unit_name} outputs={rec['outputs']} latent={latent_path!r}", flush=True)
    return saved


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--units", nargs="+", required=True, help="e.g. U01 U02")
    ap.add_argument(
        "--job-glob",
        default="EP02-H3-physical-causality-test-v2_1-20260910-{unit}",
        help="Job dir name pattern under jobs/ep_units",
    )
    ap.add_argument("--continuity", choices=("ref_video", "motion_latent"), default="ref_video")
    ap.add_argument("--second-pass", action="store_true")
    ap.add_argument("--pass2-scale", type=float, default=1.5)
    ap.add_argument(
        "--parent-latent",
        default=None,
        help="Resume motion_latent chain from this output-relative safetensors path",
    )
    ap.add_argument(
        "--download-dir",
        type=Path,
        default=None,
        help="Local copy of each finished unit. Omit when --feiniu-batch is set.",
    )
    ap.add_argument(
        "--feiniu-batch",
        default=os.environ.get("H3_FEINIU_BATCH"),
        help="Upload mp4, latent, prompt_h3.txt, and run_meta.json to this Feiniu archive batch.",
    )
    ap.add_argument("--batch-log", type=Path, default=None)
    ap.add_argument(
        "--gpu-profile",
        default=os.environ.get("COMFY_GPU_PROFILE", "auto"),
        help="Attention/VRAM adaptation: auto|rtx5090|rtx4080|a100_sage_sm80 (or COMFY_GPU_PROFILE)",
    )
    ap.add_argument(
        "--dialogue-gate",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="ASR-check finished speech vs （） lines before motion_latent HANDOFF "
        "(default: on when H3_DIALOGUE_GATE=1)",
    )
    ap.add_argument(
        "--dialogue-gate-retries",
        type=int,
        default=int(os.environ.get("H3_DIALOGUE_GATE_RETRIES", "2")),
        help="Re-queue the same unit this many times after DIALOGUE_GATE_FAIL (default 2)",
    )
    ap.add_argument(
        "--seed-offset",
        type=int,
        default=int(os.environ.get("H3_SEED_OFFSET", "0")),
        help="Offset added to the attempt number for seed bumping, so a fresh "
        "round starts from new seeds instead of reproducing earlier attempts",
    )
    args = ap.parse_args()

    root = project_root()
    base = os.environ.get("COMFY_BASE_URL", "http://192.168.50.106:8190").rstrip("/")
    feiniu_batch = (args.feiniu_batch or "").strip()
    if feiniu_batch:
        dl_root = None
    else:
        dl_root = args.download_dir or Path("/mnt/c/Users/lxy/Downloads/EP02-H3-profiled")
        dl_root.mkdir(parents=True, exist_ok=True)
    batch_log = args.batch_log or (root / "runs" / f"profiled_{args.continuity}.json")
    results: list[dict] = []
    use_dialogue_gate = gate_enabled(args.dialogue_gate) and args.continuity == "motion_latent"
    gate_retries = max(0, int(args.dialogue_gate_retries))

    parent_mp4: Path | None = None
    parent_latent: str | None = args.parent_latent
    archive_jobs: list[tuple[str, threading.Thread, list]] = []
    log_lock = threading.Lock()
    client = ComfyClient(base, timeout=180.0)
    try:
        device_name = (client.system_stats().get("devices") or [{}])[0].get("name") or ""
        gpu_profile = resolve_gpu_profile(args.gpu_profile, device_name=device_name)
        print(
            "doctor",
            device_name,
            f"continuity={args.continuity} second_pass={args.second_pass}",
            f"gpu_profile={gpu_profile.id}({gpu_profile.attention})",
            f"dialogue_gate={use_dialogue_gate} retries={gate_retries}",
            flush=True,
        )
        for idx, unit in enumerate(args.units):
            job_dir = root / "jobs" / "ep_units" / args.job_glob.format(unit=unit)
            raw = yaml.safe_load((job_dir / "job.yaml").read_text(encoding="utf-8"))
            source = (job_dir / "assets" / "prompt_source.txt").read_text(encoding="utf-8")
            if breaks_motion_chain(raw.get("start_mode")):
                parent_mp4 = None
                parent_latent = None

            raw["fields"].pop("ref_video_0", None)
            if args.continuity == "ref_video" and parent_mp4 and parent_mp4.is_file():
                parent_rel = "assets/parent_prev.mp4"
                shutil.copy2(parent_mp4, job_dir / parent_rel)
                raw["fields"]["ref_video_0"] = parent_rel

            ref_fields = {k: v for k, v in raw["fields"].items() if k.startswith("ref_")}
            if args.continuity == "motion_latent":
                # Media labels only for stills; no parent video phrase injection.
                wired = wire_pack_prompt(source, {k: v for k, v in ref_fields.items() if k.startswith("ref_image_")})
            else:
                wired = wire_pack_prompt(source, ref_fields)
            violations = audit_pack_prompt_wiring(
                source,
                wired,
                {k: v for k, v in ref_fields.items() if k.startswith("ref_image_")}
                if args.continuity == "motion_latent"
                else ref_fields,
            )
            if violations:
                raise RuntimeError(f"{unit} audit failed: {violations}")
            raw["fields"]["prompt"] = wired
            (job_dir / "assets" / "prompt_h3.txt").write_text(wired, encoding="utf-8")
            (job_dir / "job.yaml").write_text(
                yaml.safe_dump(raw, allow_unicode=True, sort_keys=False, width=1000),
                encoding="utf-8",
            )

            job = load_and_validate_job(
                job_dir, schema_path=root / "templates" / raw["template"] / "manifest.schema.yaml"
            )
            template_dir = root / "templates" / job.template
            bindings_yaml = (template_dir / "bindings.yaml").read_text(encoding="utf-8")
            values = dict(job.fields)
            if gpu_profile.megapixels is not None:
                values["megapixels"] = float(gpu_profile.megapixels)
            for field in list_media_fields(bindings_yaml):
                if field in job.fields:
                    values[field] = client.upload_image(job.resolve_path(field))

            episode = str(raw.get("episode") or "")
            latent_prefix = motion_latent_prefix(episode, unit)
            _lat_sfx = os.environ.get("H3_LATENT_SUFFIX", "").strip()
            if _lat_sfx:
                latent_prefix = f"{latent_prefix}_{_lat_sfx}"
            unit_name = values.get("filename_prefix") or f"{episode or 'EP'}-{unit}"
            workflow = json.loads((template_dir / "workflow_api.json").read_text(encoding="utf-8"))

            pending_archive = [f"{name}: {errors[0]}" for name, _thread, errors in archive_jobs if errors]
            if pending_archive:
                for _name, thread, _errors in archive_jobs:
                    thread.join()
                print(f"ARCHIVE_FAILED {pending_archive[0]}", flush=True)
                return 2

            max_attempts = 1 + (gate_retries if use_dialogue_gate else 0)
            unit_passed = False
            rec: dict = {}
            for attempt in range(1, max_attempts + 1):
                profile = RenderProfile(
                    continuity=args.continuity,
                    second_pass=bool(args.second_pass),
                    pass2_scale=float(args.pass2_scale),
                    save_clip_index=_unit_clip_index(unit),
                    load_clip_index=(
                        _unit_clip_index(unit) - 1
                        if args.continuity == "motion_latent" and parent_latent
                        else 0
                    ),
                    motion_latent_path=parent_latent,
                    latent_filename_prefix=latent_prefix,
                )
                bound = prune_unused_api_ref_images(
                    apply_bindings(workflow, bindings_yaml=bindings_yaml, values=values),
                    values=values,
                )
                bound = apply_render_profile(bound, profile, filename_prefix=unit_name)
                bound = apply_gpu_profile(bound, gpu_profile)
                effective_attempt = attempt + max(0, int(args.seed_offset))
                if effective_attempt > 1:
                    bound = bump_noise_seed(bound, attempt=effective_attempt)
                    print(
                        f"SEED_BUMP {unit_name} attempt={attempt} "
                        f"effective={effective_attempt}",
                        flush=True,
                    )

                job_id = uuid.uuid4().hex[:12]
                prompt_id = client.queue_prompt(bound)
                write_status(
                    root / "runs" / job_id / "status.json",
                    JobStatus(job_id=job_id, state="running", prompt_id=prompt_id),
                )
                print(
                    f"START {unit_name} job={job_id} prompt={prompt_id} "
                    f"continuity={args.continuity} second_pass={args.second_pass} "
                    f"gpu_profile={gpu_profile.id} latent_prefix={latent_prefix} "
                    f"parent_latent={parent_latent!r} parent_mp4={parent_mp4.name if parent_mp4 else None} "
                    f"attempt={attempt}/{max_attempts}",
                    flush=True,
                )
                rec = {
                    "unit": unit_name,
                    "job_id": job_id,
                    "prompt_id": prompt_id,
                    "continuity": args.continuity,
                    "second_pass": bool(args.second_pass),
                    "gpu_profile": gpu_profile.id,
                    "attention": gpu_profile.attention,
                    "latent_prefix": latent_prefix,
                    "parent_latent": parent_latent,
                    "attempt": attempt,
                    "state": "running",
                }
                try:
                    entry = _wait(client, prompt_id)
                    store_kwargs = dict(
                        entry=entry,
                        root=root,
                        job_id=job_id,
                        profile=profile,
                        continuity=args.continuity,
                        second_pass=bool(args.second_pass),
                        job_dir=job_dir,
                        unit_name=unit_name,
                        unit=unit,
                        episode=episode,
                        feiniu_batch=feiniu_batch,
                        dl_root=dl_root,
                        rec=rec,
                    )
                    if args.continuity == "motion_latent":
                        latent_path = extract_saved_latent_path(
                            entry,
                            filename_prefix=profile.latent_filename_prefix,
                            clip_index=profile.save_clip_index,
                        )
                        rel = _output_rel(latent_path or "")

                        if use_dialogue_gate:
                            gate_dir = root / "outputs" / job_id / "dialogue_gate"
                            saved_gate = _retry_tunnel(
                                lambda: collect_outputs(
                                    client,
                                    entry,
                                    gate_dir,
                                    prefer_node_ids=preferred_video_node_ids(profile),
                                ),
                                f"dialogue-gate download {unit_name}",
                            )
                            mp4 = select_primary_mp4(saved_gate)
                            if mp4 is None:
                                raise RuntimeError(f"{unit_name} dialogue gate: no mp4 in outputs")
                            verdict = check_mp4_dialogue(mp4, source)
                            print(
                                f"DIALOGUE_GATE {unit_name} attempt={attempt} "
                                f"{verdict.reason} overlap={verdict.overlap} "
                                f"extras={len(verdict.extras)} missing={len(verdict.missing)}",
                                flush=True,
                            )
                            if not verdict.ok:
                                rec["state"] = "dialogue_gate_fail"
                                rec["dialogue_gate"] = {
                                    "reason": verdict.reason,
                                    "extras": verdict.extras[:5],
                                    "missing": verdict.missing[:5],
                                    "overlap": verdict.overlap,
                                }
                                print(
                                    f"DIALOGUE_GATE_FAIL {unit_name} reason={verdict.reason} "
                                    f"extras={verdict.extras[:2]!r} missing={verdict.missing[:2]!r}",
                                    flush=True,
                                )
                                if attempt < max_attempts:
                                    print(f"DIALOGUE_GATE_RETRY {unit_name}", flush=True)
                                    continue
                                results.append(rec)
                                with log_lock:
                                    batch_log.write_text(
                                        json.dumps(results, ensure_ascii=False, indent=2),
                                        encoding="utf-8",
                                    )
                                for _name, thread, _errors in archive_jobs:
                                    thread.join()
                                return 2

                        def archive(
                            store_kwargs=store_kwargs,
                            rel=rel,
                        ) -> None:
                            archive_client = ComfyClient(base, timeout=180.0)
                            try:
                                _store_unit_outputs(archive_client, known_latent=rel, **store_kwargs)
                                with log_lock:
                                    batch_log.write_text(
                                        json.dumps(results, ensure_ascii=False, indent=2),
                                        encoding="utf-8",
                                    )
                            finally:
                                archive_client.close()

                        parent_latent, thread, errors = handoff_latent_then_archive(rel, archive)
                        archive_jobs.append((unit_name, thread, errors))
                        parent_mp4 = None
                        print(f"HANDOFF {unit_name} latent={rel!r}", flush=True)
                        rec["state"] = "handed_off"
                        rec["latent_path"] = rel
                        unit_passed = True
                        break
                    else:
                        saved = _store_unit_outputs(client, **store_kwargs)
                        mp4s = [p for p in saved if p.suffix.lower() == ".mp4"]
                        if not mp4s:
                            raise RuntimeError("no mp4 for parent chain")
                        pass2 = [p for p in mp4s if "pass2" in p.name.lower() or "二采" in p.name]
                        parent_mp4 = pass2[0] if pass2 else mp4s[0]
                        parent_latent = None
                        unit_passed = True
                        break
                except Exception as e:
                    write_status(
                        root / "runs" / job_id / "status.json",
                        JobStatus(job_id=job_id, state="failed", prompt_id=prompt_id, message=str(e)[:1500]),
                    )
                    rec["state"] = "failed"
                    rec["error"] = str(e)[:500]
                    print(f"FAILED {unit_name} {e}", flush=True)
                    results.append(rec)
                    with log_lock:
                        batch_log.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
                    for _name, thread, _errors in archive_jobs:
                        thread.join()
                    return 2
            if not unit_passed:
                print(f"FAILED {unit_name} no successful take", flush=True)
                for _name, thread, _errors in archive_jobs:
                    thread.join()
                return 2
            results.append(rec)
            with log_lock:
                batch_log.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        for _name, thread, _errors in archive_jobs:
            thread.join()
        failed_archive = [f"{name}: {errors[0]}" for name, _thread, errors in archive_jobs if errors]
        if failed_archive:
            print(f"ARCHIVE_FAILED {failed_archive[0]}", flush=True)
            return 2
        dest = feiniu_batch or str(dl_root)
        print(f"BATCH_DONE ok={len(results)} dest={dest}", flush=True)
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
