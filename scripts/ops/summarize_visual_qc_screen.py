"""Summarize verified model screening separately from reused L1 and incomplete L2."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from comfy_orch.av_review.cli_screen import decode_final, image_read_coverage, validate_screen_answer


def load(path):
    return json.loads(path.read_text()) if path.is_file() else None


def verify_receipt(directory, report, images):
    if not report or report["status"] != "MODEL_SCREEN_RECORDED":
        return
    events = [json.loads(line) for line in (directory / "raw.jsonl").read_text().splitlines()]
    coverage = image_read_coverage(events, {str((ROOT / p).resolve()) for p in images})
    if coverage != report["coverage"] or coverage["missing"] or coverage["unexpected"]:
        raise ValueError("Recorded image coverage differs from captured CLI tool calls")
    if decode_final(events) != report["answer"]:
        raise ValueError("Recorded model answer differs from captured CLI final answer")


def summarize_unit(batch_root, entry, overview_dir):
    directory = batch_root / entry["unit"]
    data = load(ROOT / entry["input"])
    source = ROOT / data["source"]["path"]
    if hashlib.sha256(source.read_bytes()).hexdigest() != entry["source_sha256"]:
        raise ValueError("Source changed after preparation")
    for sheet in data["sheets"]:
        if hashlib.sha256((ROOT / sheet["path"]).read_bytes()).hexdigest() != sheet["sha256"]:
            raise ValueError("Navigation sheet changed after model request")
        for cell in sheet["cells"]:
            if hashlib.sha256((ROOT / cell["frame_path"]).read_bytes()).hexdigest() != cell["frame_sha256"]:
                raise ValueError("Source frame changed after preparation")
    overview = load(directory / overview_dir / "result.json")
    verify_receipt(directory / overview_dir, overview, [s["path"] for s in data["sheets"]])
    ids = {c["frame_id"] for s in data["sheets"] for c in s["cells"]}
    issues = validate_screen_answer(overview["answer"], entry["unit"], ids) if overview and overview.get("answer") else ["No valid overview answer"]
    detail = load(directory / "detail/result.json")
    selected_detail_dir = directory / "detail"
    detail_attempts = []
    for attempt in (directory / "detail", directory / "detail-retry-01"):
        candidate = load(attempt / "result.json")
        if candidate:
            detail_attempts.append({"directory": str(attempt.relative_to(ROOT)),
                                    "status": candidate["status"], "exit_code": candidate["exit_code"],
                                    "elapsed_seconds": candidate["elapsed_seconds"]})
            if candidate["status"] == "MODEL_SCREEN_RECORDED":
                detail = candidate
                selected_detail_dir = attempt
    detail_input = load(directory / "detail-prepared/input.json")
    if detail_input:
        image_paths = [f["path"] for f in detail_input["selected"]]
        image_paths.extend(s["path"] for s in detail_input.get("dense_navigation", {}).get("sheets", []))
        verify_receipt(selected_detail_dir, detail, image_paths)
        for frame in detail_input["selected"]:
            if hashlib.sha256((ROOT / frame["path"]).read_bytes()).hexdigest() != frame["sha256"]:
                raise ValueError("Detail frame changed after request")
        for sheet in detail_input.get("dense_navigation", {}).get("sheets", []):
            if hashlib.sha256((ROOT / sheet["path"]).read_bytes()).hexdigest() != sheet["sha256"]:
                raise ValueError("Dense navigation sheet changed after request")
    return {"unit": entry["unit"], "source_sha256": entry["source_sha256"],
            "prompt_sha256": entry["prompt_sha256"], "input": entry["input"],
            "L0": data["L0_status"], "L0_medium_risk": data["L0_medium_risk"],
            "L1": data["L1_status"], "L1_prior_score": data["L1_prior_score"],
            "L2": "NOT_DONE", "overview": overview, "overview_schema_issues": issues,
            "overview_valid": bool(overview and overview["status"] == "MODEL_SCREEN_RECORDED" and not issues),
            "detail": detail, "detail_selection": detail_input, "detail_attempts": detail_attempts,
            "detail_not_run": load(directory / "detail-prepared/not-run.json"),
            "human_clearance": "NOT_DONE"}


def metrics(units):
    valid = [u for u in units if u["overview_valid"]]
    detail = [u for u in units if u["detail"] and u["detail"]["status"] == "MODEL_SCREEN_RECORDED"]
    return {"units": len(units), "source_hashes_match": len(units), "overview_model_success_units": len(valid),
            "overview_success_image_reads": sum(u["overview"]["coverage"]["completed_image_reads"] for u in valid),
            "detail_model_success_units": len(detail),
            "detail_success_image_reads": sum(u["detail"]["coverage"]["completed_image_reads"] for u in detail),
            "detail_success_native_reads": sum(len(u["detail_selection"]["selected"]) for u in detail),
            "detail_dense_sheet_reads": sum(len(u["detail_selection"].get("dense_navigation", {}).get("sheets", [])) for u in detail),
            "overview_suspect_items": sum(len(u["overview"]["answer"]["suspects"]) for u in valid),
            "overview_elapsed_sum_seconds": round(sum(u["overview"]["elapsed_seconds"] for u in units if u["overview"]), 3),
            "detail_elapsed_sum_seconds": round(sum(u["detail"]["elapsed_seconds"] for u in units if u["detail"]), 3),
            "detail_attempt_count": sum(len(u["detail_attempts"]) for u in units),
            "detail_failed_attempts": sum(a["status"] != "MODEL_SCREEN_RECORDED" for u in units for a in u["detail_attempts"]),
            "detail_all_attempt_elapsed_sum_seconds": round(sum(a["elapsed_seconds"] for u in units for a in u["detail_attempts"]), 3),
            "human_full_watch_count": 0, "may_issue_l2_verdict": False}


def markdown(report):
    summary = report["summary"]
    lines = ["# 前三集 Grok CLI 两阶段视觉筛查", "", "**模型视觉筛查；完整 L2 未完成，未作人审签字；L0 灰区未重新闭环。**", "",
             f"- 同源 hash 匹配：{summary['source_hashes_match']}/{summary['units']}。",
             f"- 导航有效结果：{summary['overview_model_success_units']} U；实际拼图 Read：{summary['overview_success_image_reads']}。",
             f"- 原分辨率细查有效结果：{summary['detail_model_success_units']} U；实际原图 Read：{summary['detail_success_native_reads']}；密帧导航拼图 Read：{summary['detail_dense_sheet_reads']}。",
             "- 旧 L0 只作风险种子；旧 L1 hash 匹配复用，未重新跑 ASR。", "",
             "| U | 导航 | 原图细查 | 模型嫌疑数 | L1原分 |", "|---|---|---|---|---|"]
    for unit in report["units"]:
        overview = unit["overview"]
        detail = unit["detail"]
        suspects = len(overview["answer"]["suspects"]) if unit["overview_valid"] else "未有效完成"
        detail_status = detail["status"] if detail else (unit["detail_not_run"] or {}).get("status", "NOT_RUN")
        lines.append(f"| {unit['unit']} | {'RECORDED' if unit['overview_valid'] else 'INCOMPLETE'} | {detail_status} | {suspects} | {unit['L1_prior_score']['reason']} |")
    lines.extend(["", "## 模型线索（均非确认缺陷）", ""])
    for unit in report["units"]:
        if not unit["overview_valid"]:
            lines.extend([f"### {unit['unit']}", "", "导航未有效完成，不给阴性结论。", ""])
            continue
        suspects = unit["overview"]["answer"]["suspects"]
        if not suspects:
            continue
        lines.extend([f"### {unit['unit']}", ""])
        for suspect in suspects:
            lines.append(f"- {suspect.get('id')}/{suspect.get('category')} {suspect.get('frame_ids')}: {suspect.get('observed')}")
            lines.append(f"  - 替代解释：{suspect.get('alternative_explanation')}")
        detail = unit["detail"]
        if detail and detail.get("answer"):
            lines.append("- 原图复核（模型建议，不是人工关闭）：")
            for item in detail["answer"].get("suspect_updates", []):
                lines.append(f"  - {item.get('id')}: {item.get('status')} — {item.get('reason')}")
        selection = unit["detail_selection"]
        if selection and selection["deferred"]:
            lines.append(f"- 原图预算外未复核帧：{selection['deferred']}（不是已通过）。")
        lines.append("")
    lines.extend(["## 未覆盖 / 限制", "", "- 导航是1 FPS拼图，不能与此前4 FPS逐图视为等价覆盖；缩图不证明细指节正常。",
                  "- 细查仍是选定原图，不是连续播放；没有模型直接声音输入，不判说话人、口型、同念。",
                  "- 没有独立真人真值，不报准确率；模型未列嫌疑不反证历史问题已关闭。",
                  "- 原 L1 的 EP01-U03 / EP02-U03 尾段 ASR、EP03-U02 问句仍待听音；本轮视觉不能替代。",
                  "- 未写 NAS / registry，未自动重渲。原始模型回执仅本地保存。", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", required=True)
    parser.add_argument("--report-name", default="report")
    parser.add_argument("--overview-dir", choices=["overview", "overview-low"], default="overview")
    args = parser.parse_args()
    root = ROOT / args.batch
    batch = load(root / "batch.json")
    units = [summarize_unit(root, entry, args.overview_dir) for entry in batch["units"]]
    report = {"schema": "visual_qc_cli_report_v1", "summary": metrics(units), "units": units,
              "primary_agent_triage": load(root / "agent-triage.json"),
              "L2": "NOT_DONE", "final_visual_verdict": "NOT_ISSUED"}
    for suffix, text in (("json", json.dumps(report, indent=2, ensure_ascii=False)), ("md", markdown(report))):
        with (root / f"{args.report_name}.{suffix}").open("x", encoding="utf-8") as handle:
            handle.write(text+"\n")
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
