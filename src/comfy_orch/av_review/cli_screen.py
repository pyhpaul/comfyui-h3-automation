"""CLI inference with independently checked image-tool coverage and bounded calls."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from pathlib import Path

from .cli_progress import CaptureProgress


def decode_final(events: list[dict]) -> dict:
    results = [e for e in events if e.get("type") == "result"]
    if len(results) != 1 or results[0].get("is_error"):
        raise ValueError("No single successful CLI result")
    text = results[0].get("result", "")
    start = text.find("{")
    if start < 0:
        raise ValueError("CLI final answer has no JSON")
    answer, _ = json.JSONDecoder().raw_decode(text[start:])
    if not isinstance(answer, dict):
        raise ValueError("CLI answer is not an object")
    return answer


def image_read_coverage(events: list[dict], expected: set[str]) -> dict:
    read = set()
    unexpected = []
    for event in events:
        if event.get("type") != "tool_call" or event.get("subtype") != "completed":
            continue
        call = event.get("tool_call", {})
        tool = call.get("readToolCall")
        if tool is None:
            unexpected.append("non-Read tool")
            continue
        path = str(Path(tool.get("args", {}).get("path", "")).resolve())
        success = tool.get("result", {}).get("success", {})
        if path.lower().endswith((".jpg", ".jpeg", ".png")):
            if path not in expected:
                unexpected.append(path)
            elif success.get("dataBlobId"):
                read.add(path)
    return {"expected_image_reads": len(expected), "completed_image_reads": len(read),
            "missing": sorted(expected-read), "unexpected": unexpected}


def validate_screen_answer(answer: dict, unit: str, frame_ids: set[str]) -> list[str]:
    issues = []
    if answer.get("unit") != unit:
        issues.append("Answer unit does not match input")
    for field in ("visible_events", "mouth_visibility_notes", "suspects", "detail_frame_ids", "limitations"):
        if not isinstance(answer.get(field), list):
            issues.append(f"Invalid {field}: list required")
    ids = list(answer.get("detail_frame_ids", [])) if isinstance(answer.get("detail_frame_ids"), list) else []
    for group in ("visible_events", "suspects"):
        items = answer.get(group, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                issues.append(f"Invalid {group} entry")
                continue
            for field in ("frame_ids", "detail_frame_ids"):
                values = item.get(field, [])
                if not isinstance(values, list):
                    issues.append(f"Invalid {field}")
                else:
                    ids.extend(values)
    if any(not isinstance(i, str) or i not in frame_ids for i in ids):
        issues.append("Model cited unknown frame IDs")
    return issues


def run_cli(project: Path, directory: Path, prompt: str, images: list[Path], timeout: int = 240,
            *, model: str = "grok-4.7-medium") -> dict:
    if model not in ("grok-4.7-medium", "grok-4.7-low"):
        raise ValueError("Screening model must be an explicitly supported Grok profile")
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "prompt.txt").write_text(prompt, encoding="utf-8")
    command = ["cursor-cli", "--print", "--mode", "ask", "--trust", "--sandbox", "enabled",
               "--model", model, "--output-format", "stream-json", prompt]
    started = time.monotonic()
    with (directory / "raw.jsonl").open("x") as stdout, (directory / "stderr.txt").open("x") as stderr:
        process = subprocess.Popen(command, cwd=project, stdout=stdout, stderr=stderr, start_new_session=True)
        with CaptureProgress(directory, {str(p.resolve()) for p in images}, started) as progress:
            try:
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                code = "TIMEOUT_NO_AUTOMATIC_RETRY"
    report = {"elapsed_seconds": round(time.monotonic()-started, 3), "exit_code": code,
              "model": model, "human_full_watch_count": 0, "may_issue_verdict": False,
              "progress": progress.recorder.summary()}
    try:
        events = [json.loads(line) for line in (directory / "raw.jsonl").read_text().splitlines()]
        coverage = image_read_coverage(events, {str(p.resolve()) for p in images})
        report["coverage"] = coverage
        if code != 0 or coverage["missing"] or coverage["unexpected"]:
            raise ValueError("CLI exit or image coverage did not pass")
        answer = decode_final(events)
        if answer.get("audio_status") != "AUDIO_UNAVAILABLE" or answer.get("L2_status") != "NOT_DONE":
            raise ValueError("Still-only result contradicts required modality boundary")
        report.update(status="MODEL_SCREEN_RECORDED", answer=answer)
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        report.update(status="SCREEN_INCOMPLETE", validation_error=str(error))
    (directory / "result.json").write_text(json.dumps(report, indent=2, ensure_ascii=False)+"\n")
    return report
